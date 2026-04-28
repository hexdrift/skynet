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
from collections.abc import AsyncGenerator, Callable
from functools import partial
from typing import Any

import dspy

from ...config import settings
from ...exceptions import ServiceError
from ...models import ModelConfig
from ..language_models import build_language_model
from ..safe_exec import validate_metric_code, validate_signature_code
from .constants import REASONING_FIELD

logger = logging.getLogger(__name__)


def _format_agent_error(exc: BaseException) -> str:
    """Produce a short, user-facing message from an agent failure.

    Walks through ``BaseExceptionGroup`` to the first leaf exception so
    structured-concurrency groups resolve to their underlying cause.
    Network-level failures are rewritten to a friendlier message.

    Args:
        exc: The exception (possibly a ``BaseExceptionGroup``) raised by the agent.

    Returns:
        A short string suitable for surfacing to the end user.
    """
    leaf = exc
    while isinstance(leaf, BaseExceptionGroup) and leaf.exceptions:
        leaf = leaf.exceptions[0]
    text = str(leaf).strip()
    name = type(leaf).__name__
    if not text:
        return name or "code agent failed"
    if "Cannot connect to host" in text or "nodename nor servname" in text:
        return "Can't reach the model provider. Check your network and try again."
    return f"{name}: {text}" if name not in text else text


def _validate_signature_code(code: str) -> str:
    """Smoke-test a signature snippet.

    Args:
        code: User-authored signature source code.

    Returns:
        An empty string when the snippet validates, otherwise a short error message.
    """
    try:
        validate_signature_code(code)
    except ServiceError as exc:
        return str(exc)
    except Exception as exc:
        return f"signature error: {exc}"
    return ""


def _validate_metric_code(code: str) -> str:
    """Smoke-test a metric snippet.

    Args:
        code: User-authored metric source code.

    Returns:
        An empty string when the snippet validates, otherwise a short error message.
    """
    try:
        validate_metric_code(code)
    except ServiceError as exc:
        return str(exc)
    except Exception as exc:
        return f"metric error: {exc}"
    return ""


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

    ## Image inputs (``dspy.Image``)

    ``column_kinds`` flags the detected modality of every input column.
    For any input column whose kind is ``"image"`` you MUST type the
    InputField as ``dspy.Image`` — never ``str`` — and write the
    ``desc=`` to describe what the image depicts (the model sees the
    image directly, the desc tells it how to interpret it). Image
    columns hold URLs or base64 data URIs at the row level; the runtime
    wraps them into ``dspy.Image`` instances before the model is called.

    ## Hard rules

    * EXACTLY one InputField per column marked ``input`` and EXACTLY
      one OutputField per column marked ``output`` — no more, no fewer.
    * Field identifiers MUST match the dataset column names verbatim.
    * Image input columns (``column_kinds[name] == "image"``) MUST be
      typed ``dspy.Image``; text input columns follow the type rules
      above.
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
    column_kinds: str = dspy.InputField(
        desc=(
            "JSON object mapping input-column name → 'text' | 'image'. "
            "Image columns MUST be typed ``dspy.Image`` in the generated "
            "InputField; text columns follow the standard type rules."
        ),
    )
    sample_rows: str = dspy.InputField(
        desc=(
            "JSON array of up to 5 representative rows — read them "
            "carefully to infer types, vocabulary, formatting, and "
            "length for your docstring and field descs. Image cells "
            "appear as URLs or base64 data URIs."
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
    column_kinds: str = dspy.InputField(
        desc=(
            "JSON object mapping input-column name → 'text' | 'image'. "
            "Image inputs are ``dspy.Image`` instances at runtime — never "
            "compare them as strings in your metric."
        ),
    )
    sample_rows: str = dspy.InputField(
        desc=(
            "JSON array of up to 5 representative rows — read them "
            "carefully to pick the right comparison per output column "
            "(string normalize, numeric tolerance, list overlap, ...). "
            "Image cells appear as URLs or base64 data URIs."
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
    column_kinds: str = dspy.InputField(
        desc="JSON object mapping input-column name → 'text' | 'image'.",
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
    column_kinds: str = dspy.InputField(
        desc=(
            "JSON object mapping input-column name → 'text' | 'image'. "
            "Image columns are typed ``dspy.Image`` in the Signature; "
            "reference this when explaining why a field is typed that way."
        ),
    )
    sample_rows: str = dspy.InputField(
        desc="JSON array of up to 5 representative rows from the dataset.",
    )
    current_signature: str = dspy.InputField(
        desc=("The Signature class currently shown in the editor. Reference its fields by name in your reply."),
    )
    current_metric: str = dspy.InputField(
        desc=(
            "The metric function currently shown in the editor. Quote its comparison and return values in your reply."
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
        desc=("Latest validator output for current_metric. Same rules as current_signature_validation."),
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


def _extract_reasoning_token(chunk: object) -> str | None:
    """Pull a thinking/reasoning token from a raw LiteLLM streaming chunk.

    Handles both conventions in the wild:
      - LiteLLM-normalized: ``delta.reasoning_content`` (string). Emitted by
        Fireworks, DeepSeek, OpenAI o-series, and most reasoning providers.
      - MiniMax M2 native with ``reasoning_split=true``: ``delta.reasoning_details``
        (list of ``{"text": "..."}`` blocks).

    Args:
        chunk: A streaming chunk object from LiteLLM.

    Returns:
        The reasoning token text, or ``None`` when the chunk has no reasoning content.
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
        """Bind the listener to a specific Predict and mark the synthetic reasoning field.

        Args:
            predict: The :class:`dspy.Predict` whose reasoning chunks should be intercepted.
            allow_reuse: Whether the listener can fire more than once (required for
                ReAct's inner predict, which fires per loop iteration).
        """
        super().__init__(
            signature_field_name=REASONING_FIELD,
            predict=predict,
            allow_reuse=allow_reuse,
        )
        self.predict_name = REASONING_FIELD

    def receive(self, chunk: object) -> dspy.streaming.StreamResponse | None:
        """Extract a reasoning token from a LiteLLM chunk and re-emit it as a stream response.

        Args:
            chunk: A raw LiteLLM streaming chunk.

        Returns:
            A synthetic :class:`dspy.streaming.StreamResponse` carrying the
            reasoning token, or ``None`` when no token is present.
        """
        token = _extract_reasoning_token(chunk)
        if not token:
            return None
        return dspy.streaming.StreamResponse(
            predict_name=self.predict_name,
            signature_field_name=REASONING_FIELD,
            chunk=token,
            is_last_chunk=False,
        )

    def finalize(self) -> None:
        """No-op — reasoning has no terminal aggregate event.

        Kept as an explicit method so the listener satisfies the streamer's
        aggregator protocol alongside peers that do emit a final summary.
        """
        return


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

    Returns:
        A configured :class:`dspy.LM` instance for the code agent.
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


async def _pump_seed_stream(
    program: Any,
    inputs: dict[str, Any],
    field: str,
    event_name: str,
    *,
    queue: asyncio.Queue[dict | None],
    results: dict[str, str],
) -> None:
    """Drive one streamify program and fan its tokens out to the shared SSE queue.

    Forwards provider reasoning tokens as ``reasoning_patch`` events and the
    target field's own tokens as ``event_name`` (``signature_patch`` or
    ``metric_patch``). On the final ``dspy.Prediction`` the completed text
    is written to ``results[field]`` for the orchestrator to consume.

    Args:
        program: The streamify-wrapped predictor to invoke.
        inputs: Keyword arguments forwarded to the program.
        field: Signature field name whose tokens are forwarded as ``event_name``.
        event_name: Outbound SSE event name for ``field`` tokens.
        queue: Shared SSE queue receiving the events.
        results: Mutable result map; the final value of ``field`` is written here.
    """
    async for chunk in program(**inputs):
        if isinstance(chunk, dspy.streaming.StreamResponse):
            if chunk.signature_field_name == REASONING_FIELD:
                await queue.put({"event": "reasoning_patch", "data": {"chunk": chunk.chunk}})
            elif chunk.signature_field_name == field:
                await queue.put({"event": event_name, "data": {"chunk": chunk.chunk}})
        elif isinstance(chunk, dspy.Prediction):
            results[field] = getattr(chunk, field, "") or ""


async def _run_seed(
    *,
    lm: dspy.LM,
    dataset_columns: list[str],
    column_roles_json: str,
    column_kinds_json: str,
    sample_rows_json: str,
    queue: asyncio.Queue[dict | None],
) -> dict[str, str]:
    """Run the non-agentic seed: Signature + metric in parallel, then intro.

    Signature and metric tokens are streamed as ``signature_patch`` /
    ``metric_patch`` events so the editor fills in live. After both are
    complete, an intro message is generated from the finished code (which
    gives the message model real context to talk about) and returned as
    ``assistant_message`` on the final ``done`` payload.

    Args:
        lm: The language model to drive the seed predictors.
        dataset_columns: All dataset column names.
        column_roles_json: JSON string mapping column → role.
        column_kinds_json: JSON string mapping input column → kind (text/image).
        sample_rows_json: JSON-encoded list of representative sample rows.
        queue: SSE event queue to push token events onto.

    Returns:
        Mapping with keys ``signature_code``, ``metric_code``, and
        ``assistant_message`` carrying the seed output.
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
        "column_kinds": column_kinds_json,
        "sample_rows": sample_rows_json,
    }
    results: dict[str, str] = {"signature_code": "", "metric_code": "", "assistant_message": ""}

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
            _pump_seed_stream(
                sig_program,
                shared_inputs,
                "signature_code",
                "signature_patch",
                queue=queue,
                results=results,
            ),
            _pump_seed_stream(
                met_program,
                shared_inputs,
                "metric_code",
                "metric_patch",
                queue=queue,
                results=results,
            ),
        )
        async for chunk in msg_program(
            dataset_columns=dataset_columns,
            column_roles=column_roles_json,
            column_kinds=column_kinds_json,
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


def _emit_to_code_queue(
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue[dict | None],
    ev: dict,
) -> None:
    """Hand ``ev`` to ``queue`` from any thread by scheduling ``put_nowait`` on ``loop``.

    DSPy may invoke ReAct tools on a worker thread; ``asyncio.Queue`` is not
    thread-safe, so SSE events must be enqueued via the owning loop. Binding
    ``loop`` and ``queue`` with :func:`functools.partial` turns this helper
    into a closure-free drop-in emit callback.

    Args:
        loop: The event loop owning ``queue``.
        queue: The destination SSE queue.
        ev: The event payload to enqueue.
    """
    loop.call_soon_threadsafe(queue.put_nowait, ev)


class _CodeEditSession:
    """Per-turn state for the ReAct ``edit_signature`` / ``edit_metric`` tools.

    Holds the current signature and metric source, a guardrail counter that
    rejects duplicate edits within a single turn, and the thread-safe emit
    callback used to publish SSE events from worker threads.

    ``edit_signature`` and ``edit_metric`` are exposed as bound methods so
    :class:`dspy.ReAct` can register them as tools; bound methods preserve
    the per-method Google-style docstring and the ``(reason, new_code)``
    signature that the ReAct prompt builder introspects.
    """

    def __init__(
        self,
        *,
        signature_code: str,
        metric_code: str,
        emit: Callable[[dict], None],
    ) -> None:
        """Initialize the session with the starting code and a thread-safe emitter.

        Args:
            signature_code: Initial Signature class source.
            metric_code: Initial metric function source.
            emit: Callback used to publish SSE events thread-safely.
        """
        # Per-turn guardrail: once an artifact has been successfully replaced,
        # subsequent calls for it are rejected so ReAct can't loop on the same
        # edit (which we've seen happen — four identical rewrites in one turn,
        # burning tokens and cluttering the UI). A failed validation does NOT
        # count as a successful edit, so the agent can still retry after a fix.
        self._slots = {"signature_code": signature_code, "metric_code": metric_code}
        self._successful_edits = {"signature": 0, "metric": 0}
        self._emit = emit

    @property
    def signature_code(self) -> str:
        """Return the live Signature source (updated after each successful edit).

        Returns:
            The current Signature class source as a string.
        """
        return self._slots["signature_code"]

    @property
    def metric_code(self) -> str:
        """Return the live metric source (updated after each successful edit).

        Returns:
            The current metric function source as a string.
        """
        return self._slots["metric_code"]

    def edit_signature(self, reason: str, new_code: str) -> str:
        """Replace the current Signature class in the editor.

        Call ONLY when the user asks for a change to the Signature and the
        artifact has NOT yet been edited this turn. For questions,
        explanations, or after any successful edit, call ``finish`` and
        answer in ``reply`` instead.

        The new code is validated before it's applied. If validation fails,
        the edit is rejected and the observation returns the error message
        so you can fix the code and try again in the next iteration.

        ``reason`` must be HEBREW prose (≤10 words); product terms like
        Signature/Metric may stay in English.

        Args:
            reason: Short Hebrew rationale for the edit.
            new_code: Complete replacement Signature class body.

        Returns:
            An observation string the ReAct agent reads back: a confirmation
            on success or a rejection message on validation/policy failure.
        """
        call_id = uuid.uuid4().hex[:8]
        self._emit(
            {
                "event": "tool_start",
                "data": {"id": call_id, "tool": "edit_signature", "reason": reason or ""},
            }
        )
        if self._successful_edits["signature"] >= 1:
            self._emit(
                {
                    "event": "tool_end",
                    "data": {"id": call_id, "tool": "edit_signature", "status": "error"},
                }
            )
            return (
                "Edit rejected — signature was already replaced in this "
                "turn. STOP editing; call finish and summarize the change "
                "in reply."
            )
        if new_code.strip() == self._slots["signature_code"].strip():
            self._emit(
                {
                    "event": "tool_end",
                    "data": {"id": call_id, "tool": "edit_signature", "status": "error"},
                }
            )
            return "Edit rejected — new_code is identical to the current signature. Call finish."
        err = _validate_signature_code(new_code)
        if err:
            self._emit(
                {
                    "event": "tool_end",
                    "data": {"id": call_id, "tool": "edit_signature", "status": "error"},
                }
            )
            return (
                f"Edit rejected — new_code is invalid: {err}. "
                "Fix the error and call edit_signature again with the "
                "corrected full class body."
            )
        self._slots["signature_code"] = new_code
        self._successful_edits["signature"] += 1
        self._emit({"event": "signature_replace", "data": {"code": new_code}})
        self._emit(
            {
                "event": "tool_end",
                "data": {"id": call_id, "tool": "edit_signature", "status": "ok"},
            }
        )
        return (
            "Signature replaced and validated. Do NOT edit the signature "
            "again this turn — call finish and summarize the change in "
            "reply."
        )

    def edit_metric(self, reason: str, new_code: str) -> str:
        """Replace the current metric function in the editor.

        Call ONLY when the user asks for a change to the metric and the
        artifact has NOT yet been edited this turn. For questions,
        explanations, or after any successful edit, call ``finish`` and
        answer in ``reply`` instead.

        The new code is validated before it's applied. If validation fails,
        the edit is rejected and the observation returns the error message
        so you can fix the code and try again in the next iteration.

        ``reason`` must be HEBREW prose (≤10 words); product terms like
        Signature/Metric may stay in English. ``new_code`` must return
        ``dspy.Prediction(score=..., feedback=...)``.

        Args:
            reason: Short Hebrew rationale for the edit.
            new_code: Complete replacement metric function body.

        Returns:
            An observation string the ReAct agent reads back: a confirmation
            on success or a rejection message on validation/policy failure.
        """
        call_id = uuid.uuid4().hex[:8]
        self._emit(
            {
                "event": "tool_start",
                "data": {"id": call_id, "tool": "edit_metric", "reason": reason or ""},
            }
        )
        if self._successful_edits["metric"] >= 1:
            self._emit(
                {
                    "event": "tool_end",
                    "data": {"id": call_id, "tool": "edit_metric", "status": "error"},
                }
            )
            return (
                "Edit rejected — metric was already replaced in this "
                "turn. STOP editing; call finish and summarize the change "
                "in reply."
            )
        if new_code.strip() == self._slots["metric_code"].strip():
            self._emit(
                {
                    "event": "tool_end",
                    "data": {"id": call_id, "tool": "edit_metric", "status": "error"},
                }
            )
            return "Edit rejected — new_code is identical to the current metric. Call finish."
        err = _validate_metric_code(new_code)
        if err:
            self._emit(
                {
                    "event": "tool_end",
                    "data": {"id": call_id, "tool": "edit_metric", "status": "error"},
                }
            )
            return (
                f"Edit rejected — new_code is invalid: {err}. "
                "Fix the error and call edit_metric again with the corrected "
                "full function body."
            )
        self._slots["metric_code"] = new_code
        self._successful_edits["metric"] += 1
        self._emit({"event": "metric_replace", "data": {"code": new_code}})
        self._emit(
            {
                "event": "tool_end",
                "data": {"id": call_id, "tool": "edit_metric", "status": "ok"},
            }
        )
        return (
            "Metric replaced and validated. Do NOT edit the metric again "
            "this turn — call finish and summarize the change in reply."
        )


async def _run_agent(
    *,
    lm: dspy.LM,
    dataset_columns: list[str],
    column_roles_json: str,
    column_kinds_json: str,
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

    Tools are bound methods on a :class:`_CodeEditSession` that mutate the
    session's slot dict and emit SSE events (``tool_start``,
    ``signature_replace`` / ``metric_replace``, ``tool_end``) via
    ``loop.call_soon_threadsafe`` — DSPy may invoke tools from a worker
    thread, so we can't touch the asyncio queue directly.

    The final ``reply`` field is streamed as ``message_patch`` tokens and
    returned as ``assistant_message``. For reasoning-capable providers, the
    ReAct loop's inner ``next_thought`` predict emits ``reasoning_patch``
    tokens (with ``allow_reuse=True`` so the listener survives the loop).

    Args:
        lm: Language model bound to the ReAct loop.
        dataset_columns: All dataset column names.
        column_roles_json: JSON string mapping column → role.
        column_kinds_json: JSON string mapping input column → kind (text/image).
        sample_rows_json: JSON-encoded list of representative sample rows.
        user_message: The user's latest message driving the turn.
        chat_history_json: JSON-encoded prior chat turns.
        prior_signature: Signature source as currently shown in the editor.
        prior_metric: Metric source as currently shown in the editor.
        prior_signature_validation: Latest validator output for the signature.
        prior_metric_validation: Latest validator output for the metric.
        initial_signature: Original signature source before any edits this conversation.
        initial_metric: Original metric source before any edits this conversation.
        queue: SSE event queue receiving lifecycle and token events.

    Returns:
        Mapping with keys ``signature_code``, ``metric_code``, and
        ``assistant_message`` reflecting post-turn state.
    """
    loop = asyncio.get_running_loop()
    emit: Callable[[dict], None] = partial(_emit_to_code_queue, loop, queue)
    session = _CodeEditSession(
        signature_code=prior_signature,
        metric_code=prior_metric,
        emit=emit,
    )

    # Keep max_iters tight. A normal turn is: (1) think → (2) edit_* OR
    # finish. A validator-driven retry may need one more iteration if the
    # first edit fails validation: (1) edit fails → (2) edit succeeds →
    # extract produces reply. max_iters=3 covers the worst case without
    # room to run away.
    react = dspy.ReAct(
        CodeAssistant,
        tools=[session.edit_signature, session.edit_metric],
        max_iters=3,
    )
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
        "column_kinds": column_kinds_json,
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
        "signature_code": session.signature_code,
        "metric_code": session.metric_code,
        "assistant_message": reply_text,
    }


async def _run_code_agent_orchestration(
    *,
    is_seed: bool,
    lm: dspy.LM,
    queue: asyncio.Queue[dict | None],
    dataset_columns: list[str],
    column_roles_json: str,
    column_kinds_json: str,
    sample_rows_json: str,
    user_message: str,
    chat_history_json: str,
    prior_signature: str,
    prior_metric: str,
    prior_signature_validation: str,
    prior_metric_validation: str,
    initial_signature: str,
    initial_metric: str,
) -> None:
    """Run the seed or chat path and push the terminal envelope into ``queue``.

    Dispatches to :func:`_run_seed` when ``is_seed`` is true (the user sent
    no message and we need to generate the initial Signature + metric) and
    to :func:`_run_agent` otherwise. Emits exactly one terminal event
    (``done`` on success, ``error`` on failure) followed by the ``None``
    sentinel that unblocks the outer consumer.

    Args:
        is_seed: True to run the seed path; False to run the chat agent.
        lm: Language model bound to the chosen runner.
        queue: SSE event queue.
        dataset_columns: All dataset column names.
        column_roles_json: JSON string mapping column → role.
        column_kinds_json: JSON string mapping input column → kind.
        sample_rows_json: JSON-encoded list of sample rows.
        user_message: User's latest message (empty in seed mode).
        chat_history_json: JSON-encoded prior chat turns.
        prior_signature: Current Signature source in the editor.
        prior_metric: Current metric source in the editor.
        prior_signature_validation: Latest signature validator output.
        prior_metric_validation: Latest metric validator output.
        initial_signature: Original signature source for revert support.
        initial_metric: Original metric source for revert support.
    """
    try:
        if is_seed:
            results = await _run_seed(
                lm=lm,
                dataset_columns=dataset_columns,
                column_roles_json=column_roles_json,
                column_kinds_json=column_kinds_json,
                sample_rows_json=sample_rows_json,
                queue=queue,
            )
        else:
            results = await _run_agent(
                lm=lm,
                dataset_columns=dataset_columns,
                column_roles_json=column_roles_json,
                column_kinds_json=column_kinds_json,
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


async def run_code_agent(
    *,
    dataset_columns: list[str],
    column_roles: dict[str, str],
    column_kinds: dict[str, str] | None = None,
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

    Args:
        dataset_columns: All dataset column names.
        column_roles: Mapping of column name to role (input/output/ignore).
        column_kinds: Optional mapping of input column to kind (text/image).
        sample_rows: Up to 5 representative dataset rows.
        user_message: User's latest message; empty triggers seed mode.
        chat_history: Prior {role, content} chat turns.
        prior_signature: Signature source currently shown in the editor.
        prior_metric: Metric source currently shown in the editor.
        prior_signature_validation: Latest signature validator output.
        prior_metric_validation: Latest metric validator output.
        initial_signature: Original signature source for revert support.
        initial_metric: Original metric source for revert support.

    Yields:
        SSE event dicts of shape ``{"event": str, "data": dict}``.
    """
    lm = _build_agent_lm()
    column_roles_json = json.dumps(column_roles, ensure_ascii=False)
    column_kinds_json = json.dumps(column_kinds or {}, ensure_ascii=False)
    sample_rows_json = json.dumps(sample_rows[:5], ensure_ascii=False, default=str)
    chat_history_json = json.dumps(chat_history or [], ensure_ascii=False)
    is_seed = not user_message.strip()

    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    task = asyncio.create_task(
        _run_code_agent_orchestration(
            is_seed=is_seed,
            lm=lm,
            queue=queue,
            dataset_columns=dataset_columns,
            column_roles_json=column_roles_json,
            column_kinds_json=column_kinds_json,
            sample_rows_json=sample_rows_json,
            user_message=user_message,
            chat_history_json=chat_history_json,
            prior_signature=prior_signature,
            prior_metric=prior_metric,
            prior_signature_validation=prior_signature_validation,
            prior_metric_validation=prior_metric_validation,
            initial_signature=initial_signature,
            initial_metric=initial_metric,
        )
    )
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
