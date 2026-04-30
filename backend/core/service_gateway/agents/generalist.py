"""Generalist agent that drives the Skynet wizard via MCP tools.

A :class:`dspy.ReAct` on top of the MCP surface exposed by
``backend/core/api/mcp_mount.py``. The agent observes the current wizard
state, chooses from a phased tool list, and streams reasoning + sub-tool
progress over the same SSE envelope used by :mod:`code_agent`.

Phased exposure (the gate):

* Always available: read-only discovery tools (``list_models``,
  ``list_templates``, ``get_registry_snapshot``, ``get_job_*``, analytics).
* Unlocked once the dataset has columns + roles: ``edit_code``,
  ``validate_code``, ``profile_datasets``.
* Unlocked once signature + metric + model are all set: ``submit_job``,
  ``submit_grid_search``.
* Always available post-submit: ``cancel_job``, rename/pin/archive.

Tool docstrings become the agent prompt, so we rely on the trimming in
:mod:`mcp_mount._trim_tool_spec` to keep each description ≤240 chars. Any
gating logic that would need a long description lives in the system
prompt of :class:`GeneralistSig` instead.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from functools import partial
from typing import Any, Literal, TypedDict

import dspy
from dspy.streaming import StatusMessageProvider
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from ...config import settings
from ...exceptions import ServiceError
from ...i18n import t
from ...models import ModelConfig
from ..language_models import build_language_model
from .code import ReasoningStreamListener, _format_agent_error
from .constants import REASONING_FIELD


def _is_openai_reasoning_model(model_name: str) -> bool:
    """Detect OpenAI reasoning models (gpt-5.x, o1/o3/o4 series).

    These require ``temperature=1.0`` and ``max_tokens >= 16000`` at ``dspy.LM``
    init; they also emit thinking on the ``reasoning_content`` channel when
    ``reasoning_effort`` is set. Fireworks/OpenRouter hosts of these models
    don't share the same constraints, so we scope to the ``openai/`` prefix.

    Args:
        model_name: The fully-qualified model identifier.

    Returns:
        True when ``model_name`` is an OpenAI-hosted reasoning model.
    """
    lower = model_name.lower()
    if not lower.startswith("openai/"):
        return False
    tail = lower.removeprefix("openai/")
    return tail.startswith(("gpt-5", "o1", "o3", "o4"))


def _build_generalist_lm() -> dspy.LM:
    """Construct the default LM for the generalist agent from settings.

    Reasoning configuration, by provider:

    - **Native MiniMax** (``minimax/...``): ``extra_body={"reasoning_split": true}``
      surfaces the interleaved ``<think>`` channel as ``reasoning_details``.
    - **OpenAI reasoning models** (``openai/gpt-5.*``, ``openai/o1|o3|o4*``):
      pass ``reasoning_effort="medium"`` so the model emits reasoning content
      that LiteLLM normalizes to ``delta.reasoning_content``. DSPy validates
      these models at init — ``temperature=1.0`` and ``max_tokens>=16000`` are
      mandatory, not optional.
    - **Everything else**: no reasoning knob; ``max_tokens=4000`` is plenty for
      a chat-style reply.

    Returns:
        A configured :class:`dspy.LM` instance for the generalist agent.
    """
    model_name = settings.generalist_agent_model
    lower = model_name.lower()
    extra: dict = {}
    temperature: float | None = None
    max_tokens = 4000

    is_native_minimax = lower.startswith("minimax/") or (
        "minimax" in lower and "fireworks" not in lower and "openrouter" not in lower
    )
    if is_native_minimax:
        extra["extra_body"] = {"reasoning_split": True}
    elif _is_openai_reasoning_model(model_name):
        extra["reasoning_effort"] = "medium"
        temperature = 1.0
        max_tokens = 16000

    config = ModelConfig(
        name=model_name,
        base_url=settings.generalist_agent_base_url or None,
        temperature=temperature,
        max_tokens=max_tokens,
        extra=extra,
    )
    return build_language_model(config, disable_cache=True)


logger = logging.getLogger(__name__)

TrustMode = Literal["ask", "auto_safe", "yolo"]

# Tools whose side-effects can destroy or create billing-bearing work.
# Always require confirmation except in YOLO mode.
_DESTRUCTIVE_TOOLS: frozenset[str] = frozenset(
    {
        "delete_job_optimizations",
        "bulk_delete_jobs_optimizations_bulk_delete_post",
        "delete_template_templates",
        "submit_job_run_post",
        "submit_grid_search_grid_search_post",
        "cancel_job_optimizations",
        "bulk_cancel_jobs_optimizations_bulk_cancel_post",
        "clone_job_optimizations",
        "retry_job_optimizations",
    }
)

# Safe mutations — metadata toggles, local-only operations, template saves.
# Confirm in Ask mode; auto-approve in Auto-safe and YOLO.
_SAFE_MUTATIONS: frozenset[str] = frozenset(
    {
        "rename_job_optimizations",
        "toggle_pin_job_optimizations",
        "toggle_archive_job_optimizations",
        "create_template_templates_post",
        "update_template_templates",
        "apply_template_templates",
        "edit_code_optimizations_edit_code_post",
        "validate_code_validate_code_post",
        "profile_datasets_profile_post",
        "discover_models_models_discover_post",
        "serve_program_serve",
        "stage_sample_dataset_datasets_samples",
        "set_column_roles_datasets_column_roles_post",
        "update_wizard_state",
        "bulk_pin_jobs_optimizations_bulk_pin_post",
        "bulk_archive_jobs_optimizations_bulk_archive_post",
    }
)


class ApprovalRegistry:
    """In-memory ``call_id → Future[bool]`` store for pending approvals.

    The generalist SSE stream emits a ``pending_approval`` event carrying
    a ``call_id``; the paired ``POST /optimizations/generalist-agent/confirm``
    endpoint calls :meth:`resolve` with the same id to unblock the tool.
    In-process for v1; swap for Redis when we need cross-worker consistency.
    """

    def __init__(self) -> None:
        """Initialize the in-memory pending-approvals map."""
        self._pending: dict[str, asyncio.Future[bool]] = {}

    def register(self, call_id: str) -> asyncio.Future[bool]:
        """Register ``call_id`` and return a future the tool awaits until resolved.

        Args:
            call_id: Unique identifier for the pending tool call.

        Returns:
            A future that resolves to the user's approval decision.
        """
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[call_id] = fut
        return fut

    def resolve(self, call_id: str, approved: bool) -> bool:
        """Complete a pending approval future.

        Args:
            call_id: Identifier matching a previous :meth:`register` call.
            approved: The user's decision (True to allow, False to decline).

        Returns:
            True when a matching pending future was resolved; False if the
            id was unknown or already settled.
        """
        fut = self._pending.pop(call_id, None)
        if fut is None or fut.done():
            return False
        fut.set_result(approved)
        return True

    def cancel(self, call_id: str) -> None:
        """Cancel a still-pending approval (e.g. the stream was torn down).

        Args:
            call_id: Identifier matching a previous :meth:`register` call.
        """
        fut = self._pending.pop(call_id, None)
        if fut is not None and not fut.done():
            fut.cancel()


_global_registry = ApprovalRegistry()


def get_approval_registry() -> ApprovalRegistry:
    """Return the process-wide :class:`ApprovalRegistry` singleton.

    Returns:
        The shared registry used to coordinate tool approvals.
    """
    return _global_registry


def _needs_approval(tool_name: str, trust_mode: TrustMode) -> bool:
    """Decide whether a tool call must pause for user confirmation.

    Args:
        tool_name: The MCP tool's registered name.
        trust_mode: The caller's selected trust level.

    Returns:
        True when the call should be gated behind an approval prompt.
    """
    if trust_mode == "yolo":
        return False
    if tool_name in _DESTRUCTIVE_TOOLS:
        return True
    return trust_mode == "ask" and tool_name in _SAFE_MUTATIONS


def _serialize_tool_result(v: Any) -> Any:
    """Best-effort JSON-friendly conversion for SSE ``tool_end.result``.

    Args:
        v: The raw value returned by an MCP tool.

    Returns:
        ``v`` unchanged if already JSON-friendly, the parsed JSON value
        when ``str(v)`` decodes, or the stringified form as a last resort.
    """
    if v is None or isinstance(v, (dict, list, bool, int, float)):
        return v
    s = str(v)
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return s


class _ApprovalGatedTool:
    """Callable replacement for a ``dspy.Tool.func`` that enforces approval.

    Installed by :func:`_wrap_tool_with_approval`. The original async
    callable is stored on the instance so the wrapper can live at module
    scope instead of inside a closure. ``__call__`` emits ``tool_start``
    before the underlying call and ``tool_end`` after it (status
    ``ok``/``error`` with a best-effort JSON-serialized result). When the
    tool is gated by the caller's ``TrustMode`` it also emits
    ``pending_approval`` / ``approval_resolved`` events and returns
    ``"User declined"`` on refusal so the ReAct loop can reason about it.
    """

    def __init__(
        self,
        original: Callable[..., Awaitable[Any]],
        tool_name: str,
        trust_mode: TrustMode,
        registry: ApprovalRegistry,
        emit: Callable[[dict], None],
    ) -> None:
        """Capture the underlying tool and the side-channel plumbing.

        Args:
            original: The async callable to wrap.
            tool_name: Registered MCP tool name.
            trust_mode: The caller's trust level.
            registry: Approval registry used for gating.
            emit: Thread-safe callback for SSE events.
        """
        self._original = original
        self._tool_name = tool_name
        self._trust_mode = trust_mode
        self._registry = registry
        self._emit = emit

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Run the wrapped tool, emitting approval and lifecycle events.

        Returns ``"User declined"`` when the gated approval is rejected;
        re-raises ``CancelledError`` and tool-side exceptions after emitting
        a ``tool_end`` with ``status="error"``.

        Args:
            *args: Positional arguments forwarded to the underlying tool.
            **kwargs: Keyword arguments forwarded to the underlying tool.

        Returns:
            The wrapped tool's return value, or the literal string
            ``"User declined"`` when the call is rejected.

        Raises:
            asyncio.CancelledError: If the surrounding stream is cancelled.
            Exception: Re-raised after emitting a ``tool_end`` error event
                when the underlying tool raises.
        """
        call_id = uuid.uuid4().hex[:12]
        self._emit(
            {
                "event": "tool_start",
                "data": {
                    "id": call_id,
                    "tool": self._tool_name,
                    "reason": "",
                    "arguments": kwargs,
                },
            }
        )
        try:
            if _needs_approval(self._tool_name, self._trust_mode):
                fut = self._registry.register(call_id)
                self._emit(
                    {
                        "event": "pending_approval",
                        "data": {"id": call_id, "tool": self._tool_name, "arguments": kwargs},
                    }
                )
                try:
                    approved = await fut
                except asyncio.CancelledError:
                    self._registry.cancel(call_id)
                    self._emit(
                        {
                            "event": "tool_end",
                            "data": {
                                "id": call_id,
                                "tool": self._tool_name,
                                "status": "error",
                                "result": "cancelled",
                            },
                        }
                    )
                    raise
                self._emit(
                    {
                        "event": "approval_resolved",
                        "data": {"id": call_id, "tool": self._tool_name, "approved": approved},
                    }
                )
                if not approved:
                    self._emit(
                        {
                            "event": "tool_end",
                            "data": {
                                "id": call_id,
                                "tool": self._tool_name,
                                "status": "error",
                                "result": "User declined",
                            },
                        }
                    )
                    return "User declined"
            result = await self._original(*args, **kwargs)
            self._emit(
                {
                    "event": "tool_end",
                    "data": {
                        "id": call_id,
                        "tool": self._tool_name,
                        "status": "ok",
                        "result": _serialize_tool_result(result),
                    },
                }
            )
            return result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._emit(
                {
                    "event": "tool_end",
                    "data": {
                        "id": call_id,
                        "tool": self._tool_name,
                        "status": "error",
                        "result": _format_agent_error(exc),
                    },
                }
            )
            raise


def _wrap_tool_with_approval(
    tool: dspy.Tool,
    *,
    trust_mode: TrustMode,
    registry: ApprovalRegistry,
    emit: Callable[[dict], None],
) -> dspy.Tool:
    """Replace ``tool.func`` with an approval-aware wrapper.

    Args:
        tool: The DSPy tool whose ``func`` is being wrapped in place.
        trust_mode: Caller's trust level.
        registry: Approval registry used for gating.
        emit: Thread-safe SSE event emitter.

    Returns:
        The same ``tool`` instance with its ``func`` replaced.
    """
    tool.func = _ApprovalGatedTool(
        original=tool.func,
        tool_name=tool.name,
        trust_mode=trust_mode,
        registry=registry,
        emit=emit,
    )
    return tool


class WizardState(TypedDict, total=False):
    """Snapshot of the wizard the agent is driving.

    Fed into ``tools_for`` to phase tool exposure. Every field is optional
    so callers can send a partial snapshot; missing fields count as "not
    ready". Mirrors a subset of the frontend ``SubmissionDraft`` state.
    """

    dataset_ready: bool
    columns_configured: bool
    signature_code: str
    metric_code: str
    model_configured: bool


_ALWAYS_TOOLS = frozenset(
    {
        "list_models_models_get",
        "list_templates_templates_get",
        "get_template_templates",
        "get_registry_snapshot_registry_get",
        "list_jobs_optimizations_get",
        "get_optimization_counts_optimizations_counts_get",
        "get_job_summary_optimizations",
        "get_job_logs_optimizations",
        "get_analytics_summary_analytics_summary_get",
        "get_optimizer_stats_analytics_optimizers_get",
        "get_model_stats_analytics_models_get",
        "serve_info_serve",
        "serve_pair_info_serve",
        "discover_models_models_discover_post",
        "rename_job_optimizations",
        "toggle_pin_job_optimizations",
        "toggle_archive_job_optimizations",
        # Job lifecycle tools that can run on an existing optimization at any time.
        "clone_job_optimizations",
        "retry_job_optimizations",
        "compare_jobs_optimizations_compare_post",
        "bulk_pin_jobs_optimizations_bulk_pin_post",
        "bulk_archive_jobs_optimizations_bulk_archive_post",
        # Wizard-prefill tools — safe to expose before a dataset is uploaded
        # since they *produce* a dataset or column map, they don't consume one.
        "list_sample_datasets_datasets_samples_get",
        "stage_sample_dataset_datasets_samples",
        "apply_template_templates",
        "update_template_templates",
        "set_column_roles_datasets_column_roles_post",
        # Generalized wizard patch — any editable field, partial updates.
        "update_wizard_state",
    }
)
_DATASET_READY_TOOLS = frozenset(
    {
        "edit_code_optimizations_edit_code_post",
        "validate_code_validate_code_post",
        "profile_datasets_profile_post",
    }
)
_READY_TO_SUBMIT_TOOLS = frozenset(
    {
        "submit_job_run_post",
        "submit_grid_search_grid_search_post",
    }
)
_POST_SUBMIT_TOOLS = frozenset(
    {
        "cancel_job_optimizations",
        "bulk_cancel_jobs_optimizations_bulk_cancel_post",
        "delete_job_optimizations",
        "bulk_delete_jobs_optimizations_bulk_delete_post",
        "serve_program_serve",
        "create_template_templates_post",
        "delete_template_templates",
    }
)


def tools_for(state: WizardState) -> set[str]:
    """Compute the MCP tool names exposed for a given wizard snapshot.

    The generalist never sees all tools at once — it would burn context
    and invite misuse. Each phase of the wizard unlocks its own slice.

    Args:
        state: Snapshot describing what the wizard has filled in so far.

    Returns:
        The set of MCP tool names allowed for this wizard state.
    """
    allowed = set(_ALWAYS_TOOLS) | set(_POST_SUBMIT_TOOLS)
    dataset_ready = bool(state.get("dataset_ready") and state.get("columns_configured"))
    if dataset_ready:
        allowed |= _DATASET_READY_TOOLS
    if dataset_ready and state.get("signature_code") and state.get("metric_code") and state.get("model_configured"):
        allowed |= _READY_TO_SUBMIT_TOOLS
    return allowed


class GeneralistSig(dspy.Signature):
    """You are the Skynet assistant driving a DSPy optimization wizard.

    The user is typically non-technical and communicates in Hebrew (RTL).
    Your job is to move the user toward a successful optimization run by
    calling tools — one coherent action per turn, not a chain of every
    possible step.

    Rules:
    * Reply in Hebrew. Product terms (Signature, Metric, optimizer names)
      stay in English inside Hebrew prose.
    * Prefer calling tools over explaining. One tool call per turn is ideal.
    * If a tool returns an error, surface it to the user in Hebrew and ask
      how to proceed — do not retry blindly.
    * Never invent optimization IDs, template IDs, or model names. Get
      them from the discovery tools first.

    Capabilities worth knowing about:
    * First-run demos: when the user has no dataset, call
      ``list_sample_datasets`` then ``stage_sample_dataset`` to prefill the
      wizard with a curated demo (sentiment, email triage, Q&A).
    * Templates: ``apply_template`` prefills the wizard from a saved config;
      ``update_template`` edits one in place. ``create_template`` saves a
      new one.
    * Existing jobs: ``clone_job`` duplicates a job (1–5 copies),
      ``retry_job`` re-runs a failed/cancelled one, ``compare_jobs`` gives
      a side-by-side snapshot of 2–5 optimizations, ``bulk_pin_jobs`` /
      ``bulk_archive_jobs`` toggle metadata in batch, ``bulk_cancel_jobs``
      stops many running/pending jobs at once, ``bulk_delete_jobs`` removes
      many terminal jobs at once.
    * Column roles: ``set_column_roles`` writes a validated input/output
      map back to the wizard; prefer it over hand-editing code.
    * Any other wizard field: ``update_wizard_state`` patches any subset
      of editable fields — optimizer_name, module_name, model_config
      (teacher/student), reflection_model_config, generation_models /
      reflection_models (grid search), split_fractions, split_mode, seed,
      shuffle, optimizer_kwargs, job_name, job_description,
      job_type, signature_code, metric_code. Supply only the fields you
      want to change; everything else is left alone. Prefer it over the
      narrow per-field tools when changing one thing, and combine edits
      (e.g. optimizer + kwargs + split) in a single call.
    * Logs: ``get_job_logs`` returns the log trail when the user is
      debugging a failed run.
    """

    wizard_state: str = dspy.InputField(desc="JSON snapshot of the current wizard state.")
    chat_history: str = dspy.InputField(desc="Prior {role, content} turns as JSON.")
    user_message: str = dspy.InputField(desc="The user's latest Hebrew message.")
    assistant_message: str = dspy.OutputField(desc="Hebrew reply to the user summarizing what you did and what's next.")


class GeneralistStatusProvider(StatusMessageProvider):
    """Emit short Hebrew status messages around each tool call.

    DSPy's streamify pipes these as ``status`` chunks; the SSE wrapper in
    :func:`run_generalist_agent` forwards them as ``status_patch`` events.
    """

    def tool_start_status_message(self, instance: Any, inputs: dict[str, Any]) -> str:
        """Return the localized status line shown just before a tool call.

        Args:
            instance: The tool instance about to run.
            inputs: Keyword arguments the tool will be invoked with.

        Returns:
            Localized status text for the ``tool_start`` event.
        """
        return t("agent.status.tool_start")

    def tool_end_status_message(self, outputs: Any) -> str:
        """Return the localized status line shown after a tool call settles.

        Args:
            outputs: The value returned by the completed tool call.

        Returns:
            Localized status text for the ``tool_end`` event.
        """
        return t("agent.status.tool_end")


@asynccontextmanager
async def _mcp_session(mcp_url: str) -> AsyncGenerator[ClientSession, None]:
    """Open a Streamable-HTTP MCP client session bound to ``mcp_url``.

    The generalist agent typically hits its own sibling-mounted MCP
    server (``http://localhost:<port>/mcp/``); taking the URL as an
    argument keeps the function testable against an out-of-process
    MCP server or a test fixture.

    Args:
        mcp_url: The HTTP endpoint of the target MCP server.

    Yields:
        An initialized :class:`ClientSession` ready for ``list_tools``.
    """
    async with streamablehttp_client(mcp_url) as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        yield session


def _emit_to_queue_threadsafe(loop: asyncio.AbstractEventLoop, out_queue: asyncio.Queue[dict], ev: dict) -> None:
    """Hand ``ev`` to ``out_queue`` from any thread by scheduling ``put_nowait`` on ``loop``.

    The ReAct loop runs tool wrappers on worker threads; SSE events must
    land on the coroutine's queue from the coroutine's loop to avoid
    ``asyncio.Queue`` thread-unsafety. Binding ``loop`` and ``out_queue``
    with :func:`functools.partial` turns this into a closure-free drop-in
    emit callback.

    Args:
        loop: The event loop owning ``out_queue``.
        out_queue: Destination queue for SSE events.
        ev: The event payload to enqueue.
    """
    loop.call_soon_threadsafe(out_queue.put_nowait, ev)


async def _drive_generalist_agent(
    *,
    mcp_url: str,
    wizard_state: WizardState,
    chat_history: list[dict],
    user_message: str,
    trust_mode: TrustMode,
    registry: ApprovalRegistry,
    emit: Callable[[dict], None],
    lm: Any,
) -> str:
    """Open the MCP session, run the ReAct loop, and return the final assistant message.

    Streams reasoning / assistant / status chunks through ``emit`` as they
    arrive from DSPy's async streamer. The final assistant reply is
    returned so the outer coroutine can emit a terminal ``done`` event.

    Args:
        mcp_url: HTTP endpoint of the target MCP server.
        wizard_state: Snapshot of wizard state used to phase tool exposure.
        chat_history: Prior chat turns as ``{role, content}`` dicts.
        user_message: The user's latest message.
        trust_mode: Caller's trust level for tool gating.
        registry: Approval registry used for tool gating.
        emit: Thread-safe SSE event emitter.
        lm: Language model bound to the ReAct program.

    Returns:
        The full assistant reply text after the loop completes.
    """
    async with _mcp_session(mcp_url) as session:
        listing = await session.list_tools()
        allowed_names = tools_for(wizard_state)
        dspy_tools = [
            _wrap_tool_with_approval(
                dspy.Tool.from_mcp_tool(session, t),
                trust_mode=trust_mode,
                registry=registry,
                emit=emit,
            )
            for t in listing.tools
            if t.name in allowed_names
        ]
        react = dspy.ReAct(GeneralistSig, tools=dspy_tools, max_iters=8)
        # Two reasoning listeners: one on the iterative ReAct predict (fires
        # once per loop step — allow_reuse=True is mandatory) and one on the
        # final extract CoT. Reasoning tokens arrive on the raw LiteLLM chunk
        # regardless of which predict is active; binding per-predict is how
        # DSPy routes chunks to the listener at each stage.
        program = dspy.streamify(
            react,
            stream_listeners=[
                dspy.streaming.StreamListener(signature_field_name="assistant_message", allow_reuse=True),
                ReasoningStreamListener(predict=react.react, allow_reuse=True),
                ReasoningStreamListener(predict=react.extract.predict, allow_reuse=True),
            ],
            status_message_provider=GeneralistStatusProvider(),
            async_streaming=True,
            is_async_program=True,
        )

        inputs = {
            "wizard_state": json.dumps(wizard_state, ensure_ascii=False),
            "chat_history": json.dumps(chat_history, ensure_ascii=False),
            "user_message": user_message,
        }
        reply_text = ""
        with dspy.context(lm=lm):
            async for chunk in program(**inputs):
                if isinstance(chunk, dspy.streaming.StatusMessage):
                    emit({"event": "status_patch", "data": {"chunk": chunk.message}})
                elif isinstance(chunk, dspy.streaming.StreamResponse):
                    if chunk.signature_field_name == REASONING_FIELD:
                        emit({"event": "reasoning_patch", "data": {"chunk": chunk.chunk}})
                    elif chunk.signature_field_name == "assistant_message":
                        reply_text += chunk.chunk
                        emit({"event": "message_patch", "data": {"chunk": chunk.chunk}})
                elif isinstance(chunk, dspy.Prediction):
                    final = getattr(chunk, "assistant_message", "") or ""
                    if final and final != reply_text:
                        reply_text = final
        return reply_text


async def run_generalist_agent(
    *,
    wizard_state: WizardState,
    chat_history: list[dict],
    user_message: str,
    trust_mode: TrustMode = "ask",
    mcp_url: str | None = None,
    model_config: ModelConfig | None = None,
    approval_registry: ApprovalRegistry | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream generalist-agent events for one user turn.

    Emits the same SSE envelope as :func:`run_code_agent` so the frontend
    chat primitives work unchanged:

    * ``reasoning_patch`` — per-token reasoning
    * ``tool_start`` / ``tool_end`` — wrap each MCP tool call
    * ``status_patch`` — human-readable progress from ``StatusMessageProvider``
    * ``message_patch`` — per-token assistant reply
    * ``done`` — terminal event with the final assistant message and the model id used
    * ``error`` — terminal event carrying a user-facing error string

    On caller-side cancellation (SSE stream dropped) the orchestration task
    is cancelled and ``CancelledError`` is re-raised; every other
    orchestration error is caught and surfaced as an ``error`` envelope.

    Args:
        wizard_state: Snapshot of the wizard the agent is driving.
        chat_history: Prior chat turns as ``{role, content}`` dicts.
        user_message: The user's latest Hebrew message.
        trust_mode: Trust level controlling which tool calls require approval.
        mcp_url: Optional override for the MCP server URL.
        model_config: Optional override for the language model configuration.
        approval_registry: Optional registry used for tool approval coordination.

    Yields:
        SSE event dicts of shape ``{"event": str, "data": dict}``.

    Raises:
        asyncio.CancelledError: Re-raised when the stream is cancelled.
    """
    url = mcp_url or settings.generalist_agent_mcp_url
    registry = approval_registry or get_approval_registry()
    model_name = model_config.name if model_config else settings.generalist_agent_model
    try:
        lm = build_language_model(model_config) if model_config else _build_generalist_lm()
    except ServiceError as exc:
        yield {"event": "error", "data": {"error": str(exc)}}
        return

    # The approval wrapper is called from a worker thread by DSPy, so we
    # need a thread-safe hop back to this coroutine's event loop to emit
    # SSE events onto the out-queue below.
    out_queue: asyncio.Queue[dict] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    emit: Callable[[dict], None] = partial(_emit_to_queue_threadsafe, loop, out_queue)

    drive_task = asyncio.create_task(
        _drive_generalist_agent(
            mcp_url=url,
            wizard_state=wizard_state,
            chat_history=chat_history,
            user_message=user_message,
            trust_mode=trust_mode,
            registry=registry,
            emit=emit,
            lm=lm,
        )
    )
    try:
        while not drive_task.done() or not out_queue.empty():
            getter = asyncio.create_task(out_queue.get())
            done, _pending = await asyncio.wait({drive_task, getter}, return_when=asyncio.FIRST_COMPLETED)
            if getter in done:
                yield getter.result()
            else:
                getter.cancel()
            if drive_task in done and out_queue.empty():
                break
        reply = await drive_task
        yield {"event": "done", "data": {"assistant_message": reply, "model": model_name}}
    except asyncio.CancelledError:
        drive_task.cancel()
        raise
    except Exception as exc:
        logger.exception("generalist agent failed")
        yield {"event": "error", "data": {"error": _format_agent_error(exc)}}
