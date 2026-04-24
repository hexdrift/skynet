"""DSPy-powered code agent for the submit wizard.

Two distinct modes share this module:

* **Seed** (``user_message`` is empty): a single non-agentic pass that writes
  the initial ``class MySignature`` and ``def metric`` in parallel. The
  tokens are streamed so the editor fills in live while the user sets up
  the rest of the wizard. A short English intro message is composed at the
  end from the finished code.

* **Chat** (``user_message`` is set): a :class:`dspy.ReAct` agent with two
  tools — ``edit_signature`` and ``edit_metric``. Simple questions don't
  touch the editor; the model answers in the ``reply`` field and no tool
  fires. When a tool does fire, the backend emits ``tool_start`` /
  ``signature_replace`` (or ``metric_replace``) / ``tool_end`` around the
  call so the UI can render a tool-call card and swap the code atomically.

The agent runs on whatever LiteLLM-compatible model is configured via
``settings.code_agent_model`` (default: ``openai/gpt-4o-mini``). Users can
point it at an internal gateway via ``CODE_AGENT_BASE_URL``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator

import dspy

from ..config import settings
from ..exceptions import ServiceError
from ..models import ModelConfig
from .data import load_metric_from_code, load_signature_from_code
from .language_models import build_language_model

logger = logging.getLogger(__name__)


def _unwrap_exception(exc: BaseException) -> BaseException:
    """Walk through ExceptionGroups to find the first concrete cause."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def _format_agent_error(exc: BaseException) -> str:
    """Produce a short, user-facing message from an agent failure."""
    leaf = _unwrap_exception(exc)
    text = str(leaf).strip()
    name = type(leaf).__name__
    if not text:
        return name or "code agent failed"
    if "Cannot connect to host" in text or "nodename nor servname" in text:
        return "Can't reach the model provider. Check your network and try again."
    return f"{name}: {text}" if name not in text else text


def _validate_signature_code(code: str) -> str:
    """Smoke-test a signature snippet; return '' if clean, else a short error."""
    try:
        load_signature_from_code(code)
    except ServiceError as exc:
        return str(exc)
    except Exception as exc:
        return f"signature error: {exc}"
    return ""


def _validate_metric_code(code: str) -> str:
    """Smoke-test a metric snippet; return '' if clean, else a short error."""
    try:
        load_metric_from_code(code)
    except ServiceError as exc:
        return str(exc)
    except Exception as exc:
        return f"metric error: {exc}"
    return ""


# ─────────────────────────── Seed-mode signatures ────────────────────────────


class GenerateSignatureCode(dspy.Signature):
    """Write a dspy.Signature class that teaches the downstream LLM what to do.

    Every part of the code you emit becomes part of the runtime prompt:
    * the class docstring becomes the TASK INSTRUCTION,
    * ``desc=`` on each InputField becomes the hint for that input,
    * ``desc=`` on each OutputField becomes the hint for the answer —
      the single most impactful field for output quality.

    Write rich, specific text everywhere. A generic signature produces a
    generic prompt and weak accuracy out of the box; a concrete,
    sample-grounded signature gives the LLM everything it needs.

    ## Docstring (3–6 sentences)

    Describe (a) the concrete task, (b) what each input represents,
    (c) what a high-quality answer looks like, and (d) any implicit
    constraint visible in the sample rows (length, vocabulary,
    formatting, units). Reference the kind of values present in the
    samples — e.g. "reviews are 1–3 sentences in English", "answers
    are always a single integer with no units". Avoid generic phrasing
    like "answer the question"; say what KIND of answer is expected.
    The docstring should be specific enough that a new developer
    reading ONLY the class could reproduce the task.

    ## Field descriptions (``desc=``)

    For every InputField: one concrete sentence on semantic meaning +
    any format hint grounded in the samples
    (e.g. ``desc="A product review in English, 1–3 sentences long, may
    contain emoji."``). Do not just repeat the field name.

    For every OutputField: spell out format, length, valid values, and
    any constraint the LLM must obey
    (e.g. ``desc="One of: positive, negative, neutral. Lowercase, no
    punctuation, no surrounding quotes."``). Be prescriptive — this
    string is the main lever on answer quality.

    ## Types inferred from the sample rows

    Pick the narrowest type that fits EVERY sample (import from
    ``typing`` as needed):
    * small finite vocabulary in outputs → ``Literal["a", "b", "c"]``
    * integer-only values → ``int``
    * numeric with decimals → ``float``
    * "yes"/"no" or "true"/"false" → ``bool``
    * obvious multi-value (commas, newlines, pipes) → ``list[str]``
    * everything else → ``str``.

    Types constrain the parser and reduce failures — prefer them over
    ``str`` whenever the samples support it.

    ## Hard rules

    * EXACTLY one InputField per column marked ``input`` and EXACTLY
      one OutputField per column marked ``output`` — no more, no fewer.
    * Field identifiers MUST match the dataset column names verbatim.
    * Do NOT invent auxiliary fields (``rationale``, ``explanation``,
      ``confidence``, ``reasoning``, ...). Modules that wrap the
      signature at runtime (``dspy.ChainOfThought``, ``dspy.ReAct``,
      ...) add their own reasoning fields automatically; any extra
      OutputField will fail validation because it has no matching
      dataset column.
    * Self-contained, importable at module scope. The allowed imports
      are ``dspy`` and ``typing`` (for ``Literal``) — nothing else. No
      markdown fences, no prose outside the class body.
    """

    dataset_columns: list[str] = dspy.InputField(desc="Every column name in the dataset.")
    column_roles: str = dspy.InputField(
        desc="JSON object mapping column name → 'input' | 'output' | 'ignore'.",
    )
    sample_rows: str = dspy.InputField(
        desc=(
            "JSON array of up to 5 representative rows — read them "
            "carefully to infer types, vocabulary, formatting, and "
            "length for your docstring and field descs."
        ),
    )

    signature_code: str = dspy.OutputField(
        desc=(
            "Complete ``class MySignature(dspy.Signature):`` Python code. "
            "Include a 3–6 sentence task docstring grounded in the "
            "samples, typed InputField / OutputField for every role-mapped "
            "column (matching names), and a specific ``desc=`` on every "
            "field. No markdown fences, no surrounding prose."
        ),
    )


class GenerateMetricCode(dspy.Signature):
    """Write a GEPA-ready metric function that scores predictions AND
    returns rich, actionable feedback for the reflective optimizer.

    ## Why feedback matters

    GEPA is a reflective prompt optimizer: on every rollout it reads the
    ``feedback`` string to decide how to mutate the signature's prompt.
    A scalar score alone gives GEPA nothing to reason about; a rich
    feedback string turns each failure into a diagnosis and lets GEPA
    converge in far fewer rollouts. Write feedback the way you would
    brief a teammate debugging the model: concrete, grounded, and
    actionable.

    ## Required shape

    Exact signature:

        ``def metric(gold, pred, trace=None, pred_name=None,
                     pred_trace=None) -> dspy.Prediction``

    Always return ``dspy.Prediction(score=float, feedback=str)`` — never
    a bare float. Never raise. Handle ``pred_name is None`` (top-level
    eval) the SAME as a named predictor — always return both score and
    feedback. On malformed input return
    ``dspy.Prediction(score=0.0, feedback="expected <what>, got
    <raw!r>")``.

    ## Reading gold and pred

    * ``pred.<field>`` for the predicted values — fields match the
      ``output`` columns.
    * ``gold.<column>`` OR ``gold["<column>"]`` for ground truth —
      support BOTH (``getattr(gold, col, None) or gold.get(col)``)
      because ``gold`` may arrive as a ``dspy.Example`` or a plain
      dict.

    ## Comparison logic (pick per-field from the samples)

    * **Strings** — normalize with ``str(x).strip().lower()`` then
      exact match.
    * **Integers** — parse both sides to ``int``; compare.
    * **Floats** — parse + compare with a small tolerance
      (``abs(a - b) <= 1e-3`` or ``1e-6 * max(1, abs(a))``).
    * **Booleans** — coerce yes/no/true/false/1/0 consistently.
    * **Lists / sets** — Jaccard overlap; enumerate matched /
      missing / extra in the feedback.
    * **Structured JSON** — parse and compare field-by-field.

    If the signature has MULTIPLE output fields, compute a per-field
    sub-score, average into the final score, AND include every field's
    verdict in the feedback so GEPA sees which component failed.

    ## Feedback content — the core of a good GEPA metric

    Every feedback string must tell the reflection model three things:

    1. **Ground truth** — show the gold value: ``f"expected
       {gold_value!r}"``.
    2. **Prediction** — show what the model produced: ``f"got
       {pred_value!r}"``.
    3. **Diagnosis + fix on failure** — name WHY it failed (format
       mismatch, wrong label, off by N, missing items, extra items,
       wrong case, extra punctuation) and WHAT the output should look
       like instead. For multi-field tasks, list the verdict for each
       field so GEPA knows which predictor to patch.

    Do NOT emit only "correct" / "incorrect" — the score already says
    that. The feedback is the LLM's side of the conversation with the
    optimizer.

    ## Feedback shape (copy the structure, not the words)

        correct:  "Correct — {field} = {gold_v!r} matches (compared
                   {how})."
        wrong:    "Incorrect: {field} got {pred_v!r}, expected
                   {gold_v!r}. {why}. Output should be {format_hint}."
        parse:    "Parse failed: expected {format}, got {raw!r}.
                   {how_to_format}."
        partial:  "Partial: {field} {k}/{n} — matched
                   {overlap}, missing {missing}, extra {extra}.
                   Return items as {format_hint}."

    ## Hard rules

    * Self-contained, importable at module scope.
    * Allowed imports: ``dspy`` and common stdlib modules (``re``,
      ``json``, ``math``, ``difflib``, ``typing``). No third-party
      packages.
    * Never raise. Wrap every parse / lookup / comparison in
      ``try/except`` and return a diagnostic
      ``dspy.Prediction(score=0.0, feedback=...)`` instead.
    * No markdown fences, no prose outside the function body.
    """

    dataset_columns: list[str] = dspy.InputField(desc="Every column name in the dataset.")
    column_roles: str = dspy.InputField(
        desc="JSON object mapping column name → 'input' | 'output' | 'ignore'.",
    )
    sample_rows: str = dspy.InputField(
        desc=(
            "JSON array of up to 5 representative rows — read them "
            "carefully to pick the right comparison per output column "
            "(string normalize, numeric tolerance, list overlap, ...)."
        ),
    )

    metric_code: str = dspy.OutputField(
        desc=(
            "Complete ``def metric(gold, pred, trace=None, "
            "pred_name=None, pred_trace=None):`` Python code that "
            "returns ``dspy.Prediction(score=float, feedback=str)``. "
            "Feedback must name the gold value, the prediction, and a "
            "concrete diagnosis + fix on failure — no bare 'correct' / "
            "'incorrect'. Never raises. No markdown fences, no "
            "surrounding prose."
        ),
    )


class GenerateSeedMessage(dspy.Signature):
    """Write a short Hebrew chat reply describing what was generated.

    Respond in one or two short, friendly Hebrew sentences explaining what
    the Signature and Metric actually do, grounded in the code just
    produced. No code, no markdown, no English. Addressed to a
    non-technical user. Keep the terms ``Signature`` and ``Metric`` in
    English (they are product terms); everything else must be Hebrew.
    """

    dataset_columns: list[str] = dspy.InputField(desc="Every column name in the dataset.")
    column_roles: str = dspy.InputField(
        desc="JSON object mapping column name → 'input' | 'output' | 'ignore'.",
    )
    sample_rows: str = dspy.InputField(
        desc="JSON array of up to 5 representative rows from the dataset.",
    )
    signature_code: str = dspy.InputField(desc="The Signature code just produced.")
    metric_code: str = dspy.InputField(desc="The metric code just produced.")

    assistant_message: str = dspy.OutputField(
        desc=(
            "One or two short Hebrew sentences for the user. No code, no "
            "markdown, no English (except the product terms ``Signature`` "
            "and ``Metric``, which stay in English)."
        ),
    )


# ─────────────────────────── Chat-mode signature ─────────────────────────────


class CodeAssistant(dspy.Signature):
    """Chat assistant attached to a DSPy Signature + metric-function editor.

    ## Your tools

    * ``edit_signature(reason, new_code)`` — REWRITES the Signature class.
    * ``edit_metric(reason, new_code)`` — REWRITES the metric function.
    * ``finish`` — end the turn and answer in ``reply``.

    ## Rule 1: Default to ``finish``. Editing is the exception.

    Call ``edit_signature`` or ``edit_metric`` ONLY when the user's latest
    message is a direct instruction to CHANGE, MODIFY, REPLACE, ADD,
    REMOVE, FIX, or REWRITE code in that artifact.

    For EVERYTHING ELSE — questions, explanations, "how does X work",
    confirmations, clarifications, opinions, critique, small talk — call
    ``finish`` immediately and answer in ``reply``. Never edit code just
    to "satisfy" a question.

    If the user says "don't change the code" (or any variant), you MUST
    call ``finish`` and answer in ``reply`` only.

    ## Rule 1a: Revert requests use ``initial_signature`` / ``initial_metric``.

    If the user asks to REVERT, UNDO, RESTORE, or go back to the ORIGINAL
    (any language), call the appropriate ``edit_*`` tool with new_code set
    VERBATIM to ``initial_signature`` or ``initial_metric`` — those fields
    hold the actual pre-edit code. NEVER guess what the original was from
    the chat history, and NEVER claim "already reverted" without checking
    whether ``current_*`` differs from ``initial_*``. If they are identical,
    call ``finish`` and say so; if they differ, the user genuinely wants a
    revert — perform it.

    ## Rule 2: Ground every reply in the actual code.

    When explaining or answering, READ ``current_signature`` and
    ``current_metric`` line by line, then reference what you see:
    * Name the fields by their Python identifier.
    * Quote the exact comparison the metric performs
      (e.g. "it does ``str(pred.label).strip().lower() == str(gold.label)...``").
    * State the concrete score values (e.g. "returns 1.0 on match, 0.0
      otherwise") and the feedback strings.

    Do NOT answer abstractly ("it rewards correct matches", "it finds
    patterns in your data"). Do NOT re-describe the overall system. Only
    describe what the code literally does.

    ## Examples

    * user: "how does the metric work?"
      → call ``finish``; reply names the fields, quotes the comparison,
        and states the return values.
    * user: "what does the Signature do?"
      → call ``finish``; reply lists the InputFields and OutputFields by
        name and their types.
    * user: "don't change any code, just explain"
      → call ``finish``; reply is an explanation only, no edits.
    * user: "make the metric case-sensitive"
      → call ``edit_metric`` with the full new function.
    * user: "add an 'explanation' OutputField"
      → call ``edit_signature`` with the full new class.

    ## Reply format

    Reply in Hebrew by default — the product UI is Hebrew. Switch to the
    user's language ONLY if their latest message is clearly in another
    language. Keep product terms like ``Signature``, ``Metric``,
    ``InputField``, ``OutputField`` in English; prose around them is
    Hebrew. Plain prose. No markdown headings, no bullet lists, no code
    fences. 2-5 sentences for explanations, 1-2 for confirmations.

    When you DO edit, pass the COMPLETE replacement file body — not a
    diff, not markdown fences. Only ``dspy`` is importable.
    """

    dataset_columns: list[str] = dspy.InputField(desc="Every column name in the dataset.")
    column_roles: str = dspy.InputField(
        desc="JSON object mapping column name → 'input' | 'output' | 'ignore'.",
    )
    sample_rows: str = dspy.InputField(
        desc="JSON array of up to 5 representative rows from the dataset.",
    )
    current_signature: str = dspy.InputField(
        desc=(
            "The Signature class currently shown in the editor. "
            "Reference its fields by name in your reply."
        ),
    )
    current_metric: str = dspy.InputField(
        desc=(
            "The metric function currently shown in the editor. "
            "Quote its comparison and return values in your reply."
        ),
    )
    current_signature_validation: str = dspy.InputField(
        desc=(
            "Latest validator output for current_signature. 'OK' means the "
            "code parsed and the signature class loaded. Non-empty 'errors: "
            "...' text means the code is broken — if you edit_signature, you "
            "MUST fix those errors in new_code."
        ),
    )
    current_metric_validation: str = dspy.InputField(
        desc=(
            "Latest validator output for current_metric. Same rules as "
            "current_signature_validation."
        ),
    )
    initial_signature: str = dspy.InputField(
        desc=(
            "The ORIGINAL signature code, before any edits in this "
            "conversation. May equal current_signature when nothing has been "
            "changed yet. Use this as the new_code for edit_signature when "
            "the user asks to REVERT, undo, or restore the original — do NOT "
            "confabulate what the original looked like."
        ),
    )
    initial_metric: str = dspy.InputField(
        desc=(
            "The ORIGINAL metric code, before any edits in this conversation. "
            "Same semantics as initial_signature: use it verbatim as new_code "
            "when the user asks to revert the metric."
        ),
    )
    chat_history: str = dspy.InputField(
        desc="Prior conversation turns as a JSON list of {role, content} objects.",
    )
    user_message: str = dspy.InputField(desc="The user's latest message.")

    reply: str = dspy.OutputField(
        desc=(
            "Reply to the user. For questions/explanations, ground it in "
            "the literal current_signature / current_metric code — name "
            "the fields and quote the comparison. 2-5 sentences. For "
            "edit confirmations, 1-2 sentences. Hebrew by default (the "
            "product UI is Hebrew); mirror the user's language only if "
            "their message is clearly in another language. Keep product "
            "terms (Signature, Metric, InputField, OutputField, Python "
            "identifiers) in English. Plain prose, no markdown, no code "
            "fences."
        ),
    )


# ─────────────────────────── Reasoning streaming ─────────────────────────────


REASONING_FIELD = "_provider_reasoning"


def _extract_reasoning_token(chunk: object) -> str | None:
    """Pull a thinking/reasoning token from a raw LiteLLM streaming chunk.

    Handles both conventions in the wild:
      - LiteLLM-normalized: ``delta.reasoning_content`` (string). Emitted by
        Fireworks, DeepSeek, OpenAI o-series, and most reasoning providers.
      - MiniMax M2 native with ``reasoning_split=true``: ``delta.reasoning_details``
        (list of ``{"text": "..."}`` blocks).

    Returns ``None`` when the chunk carries no reasoning token.
    """
    choices = getattr(chunk, "choices", None)
    if not choices:
        return None
    delta = getattr(choices[0], "delta", None)
    if delta is None:
        return None
    content = getattr(delta, "reasoning_content", None)
    if isinstance(content, str) and content:
        return content
    details = getattr(delta, "reasoning_details", None)
    if isinstance(details, list) and details:
        parts: list[str] = []
        for block in details:
            text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
            if isinstance(text, str) and text:
                parts.append(text)
        if parts:
            return "".join(parts)
    return None


class ReasoningStreamListener(dspy.streaming.StreamListener):
    """StreamListener subclass that harvests provider reasoning tokens.

    DSPy's built-in ``StreamListener`` only reads ``delta.content``. For
    reasoning-capable providers (Fireworks/MiniMax/DeepSeek/o-series) the
    model's thinking arrives on ``delta.reasoning_content`` or, for native
    MiniMax, on ``delta.reasoning_details`` — channels DSPy drops on the
    floor. This subclass intercepts those and emits them as synthetic
    ``StreamResponse`` events with ``signature_field_name = REASONING_FIELD``.

    The listener is manually bound to a specific ``Predict`` via the
    ``predict=...`` constructor arg so DSPy's auto-resolution never tries
    to find the synthetic field on the signature (it doesn't exist there).
    ``allow_reuse=True`` is required when bound to ReAct's inner predict
    because that predict fires once per loop iteration.
    """

    def __init__(self, predict: dspy.Predict, allow_reuse: bool = False):
        super().__init__(
            signature_field_name=REASONING_FIELD,
            predict=predict,
            allow_reuse=allow_reuse,
        )
        self.predict_name = REASONING_FIELD

    def receive(self, chunk):
        token = _extract_reasoning_token(chunk)
        if not token:
            return None
        return dspy.streaming.StreamResponse(
            predict_name=self.predict_name,
            signature_field_name=REASONING_FIELD,
            chunk=token,
            is_last_chunk=False,
        )

    def finalize(self):
        return None


# ─────────────────────────── LM construction ─────────────────────────────────


def _build_agent_lm() -> dspy.LM:
    """Construct the LM used by the code agent from global settings.

    Reasoning knobs we send, by provider:

    - **Native MiniMax** (``minimax/...`` or a MiniMax base_url): forward
      ``extra_body={"reasoning_split": true}`` so the provider emits its
      interleaved ``<think>`` reasoning in a clean ``reasoning_details``
      channel. Thinking depth is always max on this endpoint — no knob.
    - **Fireworks-hosted MiniMax** (``fireworks_ai/.../minimax-*``):
      reasoning arrives inline in the assistant content as ``<think>…</think>``
      blocks. Fireworks rejects ``reasoning_split``, so we send nothing.
    - **Everything else** (``openai/gpt-4o-mini`` etc.): no reasoning knob.
    """
    model_name = settings.code_agent_model
    lower = model_name.lower()
    extra: dict = {}
    is_native_minimax = lower.startswith("minimax/") or (
        "minimax" in lower and "fireworks" not in lower and "openrouter" not in lower
    )
    if is_native_minimax:
        extra["extra_body"] = {"reasoning_split": True}
    config = ModelConfig(
        name=model_name,
        base_url=settings.code_agent_base_url or None,
        max_tokens=4000,
        extra=extra,
    )
    return build_language_model(config)


# ─────────────────────────── Seed path ───────────────────────────────────────


async def _run_seed(
    *,
    lm: dspy.LM,
    dataset_columns: list[str],
    column_roles_json: str,
    sample_rows_json: str,
    queue: asyncio.Queue[dict | None],
) -> dict[str, str]:
    """Run the non-agentic seed: Signature + metric in parallel, then intro.

    Signature and metric tokens are streamed as ``signature_patch`` /
    ``metric_patch`` events so the editor fills in live. After both are
    complete, an intro message is generated from the finished code (which
    gives the message model real context to talk about) and returned as
    ``assistant_message`` on the final ``done`` payload.
    """
    sig_predict = dspy.Predict(GenerateSignatureCode)
    met_predict = dspy.Predict(GenerateMetricCode)
    sig_program = dspy.streamify(
        sig_predict,
        stream_listeners=[
            dspy.streaming.StreamListener(signature_field_name="signature_code"),
            ReasoningStreamListener(predict=sig_predict),
        ],
        async_streaming=True,
    )
    met_program = dspy.streamify(
        met_predict,
        stream_listeners=[
            dspy.streaming.StreamListener(signature_field_name="metric_code"),
            ReasoningStreamListener(predict=met_predict),
        ],
        async_streaming=True,
    )

    shared_inputs = {
        "dataset_columns": dataset_columns,
        "column_roles": column_roles_json,
        "sample_rows": sample_rows_json,
    }
    results: dict[str, str] = {"signature_code": "", "metric_code": "", "assistant_message": ""}

    async def pump(program, inputs, field, event_name):
        async for chunk in program(**inputs):
            if isinstance(chunk, dspy.streaming.StreamResponse):
                if chunk.signature_field_name == REASONING_FIELD:
                    await queue.put({"event": "reasoning_patch", "data": {"chunk": chunk.chunk}})
                elif chunk.signature_field_name == field:
                    await queue.put({"event": event_name, "data": {"chunk": chunk.chunk}})
            elif isinstance(chunk, dspy.Prediction):
                results[field] = getattr(chunk, field, "") or ""

    msg_predict = dspy.Predict(GenerateSeedMessage)
    msg_program = dspy.streamify(
        msg_predict,
        stream_listeners=[
            dspy.streaming.StreamListener(signature_field_name="assistant_message"),
        ],
        async_streaming=True,
    )

    with dspy.context(lm=lm):
        await asyncio.gather(
            pump(sig_program, shared_inputs, "signature_code", "signature_patch"),
            pump(met_program, shared_inputs, "metric_code", "metric_patch"),
        )
        async for chunk in msg_program(
            dataset_columns=dataset_columns,
            column_roles=column_roles_json,
            sample_rows=sample_rows_json,
            signature_code=results["signature_code"],
            metric_code=results["metric_code"],
        ):
            if isinstance(chunk, dspy.streaming.StreamResponse):
                if chunk.signature_field_name == "assistant_message":
                    await queue.put({"event": "message_patch", "data": {"chunk": chunk.chunk}})
            elif isinstance(chunk, dspy.Prediction):
                results["assistant_message"] = getattr(chunk, "assistant_message", "") or ""

    return results


# ─────────────────────────── Chat (ReAct) path ───────────────────────────────


async def _run_agent(
    *,
    lm: dspy.LM,
    dataset_columns: list[str],
    column_roles_json: str,
    sample_rows_json: str,
    user_message: str,
    chat_history_json: str,
    prior_signature: str,
    prior_metric: str,
    prior_signature_validation: str,
    prior_metric_validation: str,
    initial_signature: str,
    initial_metric: str,
    queue: asyncio.Queue[dict | None],
) -> dict[str, str]:
    """Run a ReAct agent with ``edit_signature`` + ``edit_metric`` tools.

    Tools are plain Python callables that mutate a local slot dict and emit
    SSE events (``tool_start``, ``signature_replace`` / ``metric_replace``,
    ``tool_end``) via ``loop.call_soon_threadsafe`` — DSPy may invoke tools
    from a worker thread, so we can't touch the asyncio queue directly.

    The final ``reply`` field is streamed as ``message_patch`` tokens and
    returned as ``assistant_message``. For reasoning-capable providers, the
    ReAct loop's inner ``next_thought`` predict emits ``reasoning_patch``
    tokens (with ``allow_reuse=True`` so the listener survives the loop).
    """
    slots = {"signature_code": prior_signature, "metric_code": prior_metric}
    # Per-turn guardrail: once an artifact has been successfully replaced,
    # subsequent calls for it are rejected so ReAct can't loop on the same
    # edit (which we've seen happen — four identical rewrites in one turn,
    # burning tokens and cluttering the UI). A failed validation does NOT
    # count as a successful edit, so the agent can still retry after a fix.
    successful_edits = {"signature": 0, "metric": 0}
    loop = asyncio.get_running_loop()

    def emit(ev: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    def edit_signature(reason: str, new_code: str) -> str:
        """Replace the current Signature class in the editor.

        Call ONLY when the user asks for a change to the Signature and the
        artifact has NOT yet been edited this turn. For questions,
        explanations, or after any successful edit, call ``finish`` and
        answer in ``reply`` instead.

        The new code is validated before it's applied. If validation fails,
        the edit is rejected and the observation returns the error message
        so you can fix the code and try again in the next iteration.

        Args:
            reason: One short sentence (≤10 words) in HEBREW describing
                what the edit accomplishes. Shown to the user in the
                tool-call card — must be Hebrew prose (product terms like
                Signature/Metric may stay in English).
            new_code: The complete new ``class MySignature(dspy.Signature):``
                Python source. No markdown fences.
        """
        call_id = uuid.uuid4().hex[:8]
        emit({
            "event": "tool_start",
            "data": {"id": call_id, "tool": "edit_signature", "reason": reason or ""},
        })
        if successful_edits["signature"] >= 1:
            emit({
                "event": "tool_end",
                "data": {"id": call_id, "tool": "edit_signature", "status": "error"},
            })
            return (
                "Edit rejected — signature was already replaced in this "
                "turn. STOP editing; call finish and summarize the change "
                "in reply."
            )
        if new_code.strip() == slots["signature_code"].strip():
            emit({
                "event": "tool_end",
                "data": {"id": call_id, "tool": "edit_signature", "status": "error"},
            })
            return (
                "Edit rejected — new_code is identical to the current "
                "signature. Call finish."
            )
        err = _validate_signature_code(new_code)
        if err:
            emit({
                "event": "tool_end",
                "data": {"id": call_id, "tool": "edit_signature", "status": "error"},
            })
            return (
                f"Edit rejected — new_code is invalid: {err}. "
                "Fix the error and call edit_signature again with the "
                "corrected full class body."
            )
        slots["signature_code"] = new_code
        successful_edits["signature"] += 1
        emit({"event": "signature_replace", "data": {"code": new_code}})
        emit({
            "event": "tool_end",
            "data": {"id": call_id, "tool": "edit_signature", "status": "ok"},
        })
        return (
            "Signature replaced and validated. Do NOT edit the signature "
            "again this turn — call finish and summarize the change in "
            "reply."
        )

    def edit_metric(reason: str, new_code: str) -> str:
        """Replace the current metric function in the editor.

        Call ONLY when the user asks for a change to the metric and the
        artifact has NOT yet been edited this turn. For questions,
        explanations, or after any successful edit, call ``finish`` and
        answer in ``reply`` instead.

        The new code is validated before it's applied. If validation fails,
        the edit is rejected and the observation returns the error message
        so you can fix the code and try again in the next iteration.

        Args:
            reason: One short sentence (≤10 words) in HEBREW describing
                what the edit accomplishes. Shown to the user in the
                tool-call card — must be Hebrew prose (product terms like
                Signature/Metric may stay in English).
            new_code: The complete new ``def metric(...)`` Python source.
                Must return ``dspy.Prediction(score=..., feedback=...)``. No
                markdown fences.
        """
        call_id = uuid.uuid4().hex[:8]
        emit({
            "event": "tool_start",
            "data": {"id": call_id, "tool": "edit_metric", "reason": reason or ""},
        })
        if successful_edits["metric"] >= 1:
            emit({
                "event": "tool_end",
                "data": {"id": call_id, "tool": "edit_metric", "status": "error"},
            })
            return (
                "Edit rejected — metric was already replaced in this "
                "turn. STOP editing; call finish and summarize the change "
                "in reply."
            )
        if new_code.strip() == slots["metric_code"].strip():
            emit({
                "event": "tool_end",
                "data": {"id": call_id, "tool": "edit_metric", "status": "error"},
            })
            return (
                "Edit rejected — new_code is identical to the current "
                "metric. Call finish."
            )
        err = _validate_metric_code(new_code)
        if err:
            emit({
                "event": "tool_end",
                "data": {"id": call_id, "tool": "edit_metric", "status": "error"},
            })
            return (
                f"Edit rejected — new_code is invalid: {err}. "
                "Fix the error and call edit_metric again with the corrected "
                "full function body."
            )
        slots["metric_code"] = new_code
        successful_edits["metric"] += 1
        emit({"event": "metric_replace", "data": {"code": new_code}})
        emit({
            "event": "tool_end",
            "data": {"id": call_id, "tool": "edit_metric", "status": "ok"},
        })
        return (
            "Metric replaced and validated. Do NOT edit the metric again "
            "this turn — call finish and summarize the change in reply."
        )

    # Keep max_iters tight. A normal turn is: (1) think → (2) edit_* OR
    # finish. A validator-driven retry may need one more iteration if the
    # first edit fails validation: (1) edit fails → (2) edit succeeds →
    # extract produces reply. max_iters=3 covers the worst case without
    # room to run away.
    react = dspy.ReAct(CodeAssistant, tools=[edit_signature, edit_metric], max_iters=3)
    # Two reasoning listeners: one for the iterative ReAct predict (fires
    # once per loop step; allow_reuse=True is required), and one for the
    # final extract CoT (fires once). Reasoning tokens from reasoning-capable
    # providers arrive on the raw LiteLLM chunk regardless of which predict
    # is active — binding per-predict is how DSPy routes chunks to listeners.
    program = dspy.streamify(
        react,
        stream_listeners=[
            dspy.streaming.StreamListener(signature_field_name="reply", allow_reuse=True),
            ReasoningStreamListener(predict=react.react, allow_reuse=True),
            ReasoningStreamListener(predict=react.extract.predict, allow_reuse=True),
        ],
        async_streaming=True,
    )

    inputs = {
        "dataset_columns": dataset_columns,
        "column_roles": column_roles_json,
        "sample_rows": sample_rows_json,
        "current_signature": prior_signature,
        "current_metric": prior_metric,
        "current_signature_validation": prior_signature_validation or "",
        "current_metric_validation": prior_metric_validation or "",
        "initial_signature": initial_signature or prior_signature,
        "initial_metric": initial_metric or prior_metric,
        "chat_history": chat_history_json,
        "user_message": user_message,
    }

    reply_text = ""
    with dspy.context(lm=lm):
        async for chunk in program(**inputs):
            if isinstance(chunk, dspy.streaming.StreamResponse):
                if chunk.signature_field_name == REASONING_FIELD:
                    await queue.put({"event": "reasoning_patch", "data": {"chunk": chunk.chunk}})
                elif chunk.signature_field_name == "reply":
                    reply_text += chunk.chunk
                    await queue.put({"event": "message_patch", "data": {"chunk": chunk.chunk}})
            elif isinstance(chunk, dspy.Prediction):
                final = getattr(chunk, "reply", "") or ""
                if final and final != reply_text:
                    reply_text = final

    return {
        "signature_code": slots["signature_code"],
        "metric_code": slots["metric_code"],
        "assistant_message": reply_text,
    }


# ─────────────────────────── Public entrypoint ───────────────────────────────


async def run_code_agent(
    *,
    dataset_columns: list[str],
    column_roles: dict[str, str],
    sample_rows: list[dict],
    user_message: str,
    chat_history: list[dict] | None = None,
    prior_signature: str,
    prior_metric: str,
    prior_signature_validation: str = "",
    prior_metric_validation: str = "",
    initial_signature: str = "",
    initial_metric: str = "",
) -> AsyncGenerator[dict, None]:
    """Stream code-agent events to the UI.

    When ``user_message`` is empty → seed path (parallel Signature + metric
    generation). When set → chat path (ReAct with two tools). Both paths
    share the same ``done`` / ``error`` envelope and the same
    ``reasoning_patch`` event for reasoning-capable providers.

    Events:

    * ``signature_patch`` / ``metric_patch`` — seed-mode token streams.
    * ``reasoning_patch`` — provider thinking tokens (both modes).
    * ``tool_start`` — ``{id, tool, reason}``, before a tool is invoked.
    * ``signature_replace`` / ``metric_replace`` — ``{code}``, full
      replacement when a tool runs.
    * ``tool_end`` — ``{id, tool, status}``, after the tool returns.
    * ``message_patch`` — chat-mode reply token stream.
    * ``done`` — ``{signature_code, metric_code, assistant_message}``.
    * ``error`` — ``{error}``.
    """
    lm = _build_agent_lm()
    column_roles_json = json.dumps(column_roles, ensure_ascii=False)
    sample_rows_json = json.dumps(sample_rows[:5], ensure_ascii=False, default=str)
    chat_history_json = json.dumps(chat_history or [], ensure_ascii=False)
    is_seed = not user_message.strip()

    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def orchestrator():
        try:
            if is_seed:
                results = await _run_seed(
                    lm=lm,
                    dataset_columns=dataset_columns,
                    column_roles_json=column_roles_json,
                    sample_rows_json=sample_rows_json,
                    queue=queue,
                )
            else:
                results = await _run_agent(
                    lm=lm,
                    dataset_columns=dataset_columns,
                    column_roles_json=column_roles_json,
                    sample_rows_json=sample_rows_json,
                    user_message=user_message,
                    chat_history_json=chat_history_json,
                    prior_signature=prior_signature,
                    prior_metric=prior_metric,
                    prior_signature_validation=prior_signature_validation,
                    prior_metric_validation=prior_metric_validation,
                    initial_signature=initial_signature,
                    initial_metric=initial_metric,
                    queue=queue,
                )
            await queue.put({"event": "done", "data": dict(results)})
        except Exception as exc:
            logger.exception("Code agent failed")
            await queue.put({"event": "error", "data": {"error": _format_agent_error(exc)}})
        finally:
            await queue.put(None)

    task = asyncio.create_task(orchestrator())
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
        await task
    except asyncio.CancelledError:
        task.cancel()
        raise
