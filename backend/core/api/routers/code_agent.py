"""Streaming endpoint for the submit-wizard AI code agent. [INTERNAL]

All endpoints are hidden from the public Scalar reference (none are in
``_SCALAR_PUBLIC_PATHS``). Used by the wizard UI to author DSPy code
interactively — not part of the dev integration surface.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from ...service_gateway.agents.code import run_code_agent
from ..errors import DomainError
from ._helpers import sse_from_events

logger = logging.getLogger(__name__)


class ChatTurn(BaseModel):
    """A single prior turn in the agent conversation."""

    role: str = Field(..., description="'user' or 'assistant'.")
    content: str = Field(..., description="Message text.")


class CodeAgentRequest(BaseModel):
    """Input for streaming code generation.

    The server only needs the dataset's columns + roles + a small sample
    (not the full dataset); payloads stay under ~20 KB even for wide schemas.
    ``user_message`` toggles mode: empty triggers the non-agentic seed,
    non-empty invokes the ReAct chat agent (which also sees ``chat_history``
    and the current editor contents in ``prior_signature`` / ``prior_metric``).
    """

    dataset_columns: list[str] = Field(..., min_length=1, description="All column names in the dataset.")
    column_roles: dict[str, str] = Field(..., description="Column → 'input'|'output'|'ignore'.")
    column_kinds: dict[str, str] = Field(
        default_factory=dict,
        description="Input column → 'text'|'image'. Image columns get a dspy.Image typed InputField.",
    )
    sample_rows: list[dict] = Field(default_factory=list, description="Up to 5 sample rows.")
    user_message: str = Field(default="", description="User's latest message. Empty triggers seed mode.")
    chat_history: list[ChatTurn] = Field(
        default_factory=list,
        description="Prior {role, content} turns; seen by the chat agent only.",
    )
    prior_signature: str = Field(default="", description="Current signature code in the editor.")
    prior_metric: str = Field(default="", description="Current metric code in the editor.")
    prior_signature_validation: str = Field(
        default="",
        description=(
            "Short summary of the latest validation result for the current "
            "signature ('OK' / 'errors: ...' / empty). Surfaced to the chat "
            "agent so follow-up edits can target real errors."
        ),
    )
    prior_metric_validation: str = Field(
        default="",
        description=("Short summary of the latest validation result for the current metric."),
    )
    initial_signature: str = Field(
        default="",
        description=(
            "The original signature code from the very first version — used by "
            "the chat agent to honor revert requests. May equal prior_signature "
            "when no edits have happened yet."
        ),
    )
    initial_metric: str = Field(
        default="",
        description=(
            "The original metric code from the very first version — used by "
            "the chat agent to honor revert requests. May equal prior_metric "
            "when no edits have happened yet."
        ),
    )


class EditCodeRequest(BaseModel):
    """Compact input for the MCP-exposed ``edit_code`` tool.

    This is a narrower, MCP-friendly projection of :class:`CodeAgentRequest`.
    The generalist agent only needs to state its goal, the current editor
    contents, and enough dataset context to drive the code agent — not the
    full chat history or validation-state scaffolding used by the wizard.
    """

    goal: str = Field(
        ...,
        min_length=1,
        description=("What to change. Non-empty; empty triggers seed mode on the SSE endpoint."),
    )
    current_signature: str = Field(default="", description="Current signature code (may be empty on first call).")
    current_metric: str = Field(default="", description="Current metric code (may be empty on first call).")
    dataset_columns: list[str] = Field(..., min_length=1, description="All column names in the dataset.")
    column_roles: dict[str, str] = Field(..., description="Column → 'input'|'output'|'ignore'.")
    column_kinds: dict[str, str] = Field(
        default_factory=dict,
        description="Input column → 'text'|'image'.",
    )
    sample_rows: list[dict] = Field(default_factory=list, description="Up to 5 sample rows.")


class EditCodeResponse(BaseModel):
    """Final output from a blocking ``edit_code`` call."""

    signature_code: str
    metric_code: str
    assistant_message: str = ""


def create_code_agent_router() -> APIRouter:
    """Mount the ``POST /optimizations/ai-generate-code`` SSE endpoint.

    Returns:
        A configured :class:`APIRouter` with the code-agent endpoints attached.
    """
    router = APIRouter()

    @router.post(
        "/optimizations/ai-generate-code",
        summary="Stream AI-generated signature + metric code",
    )
    async def ai_generate_code(req: CodeAgentRequest) -> StreamingResponse:
        """Stream DSPy code-agent events as SSE.

        Event types:

        * ``signature_patch`` / ``metric_patch`` — ``{"chunk": "<token>"}``
          (seed mode only)
        * ``reasoning_patch`` — ``{"chunk": "<token>"}`` (both modes)
        * ``tool_start`` — ``{"id", "tool", "reason"}`` (chat mode)
        * ``signature_replace`` / ``metric_replace`` — ``{"code"}``
        * ``tool_end`` — ``{"id", "tool", "status"}``
        * ``message_patch`` — ``{"chunk": "<token>"}`` (chat mode reply stream)
        * ``done`` — ``{"signature_code", "metric_code", "assistant_message"}``
        * ``error`` — ``{"error": "<message>"}``

        Args:
            req: Request body controlling code-agent inputs and chat history.

        Returns:
            A :class:`StreamingResponse` of Server-Sent Events.
        """

        source = run_code_agent(
            dataset_columns=req.dataset_columns,
            column_roles=req.column_roles,
            column_kinds=req.column_kinds,
            sample_rows=req.sample_rows,
            user_message=req.user_message,
            chat_history=[t.model_dump() for t in req.chat_history],
            prior_signature=req.prior_signature,
            prior_metric=req.prior_metric,
            prior_signature_validation=req.prior_signature_validation,
            prior_metric_validation=req.prior_metric_validation,
            initial_signature=req.initial_signature,
            initial_metric=req.initial_metric,
        )
        return StreamingResponse(
            sse_from_events(source),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post(
        "/optimizations/edit-code",
        response_model=EditCodeResponse,
        summary="Delegate signature + metric editing to the code agent",
        tags=["agent"],
    )
    async def edit_code(req: EditCodeRequest) -> EditCodeResponse:
        """Run the code agent to completion and return the final code.

        Consumes the same event stream as the SSE endpoint but blocks until
        the ``done`` event, so a ReAct tool call sees a single request /
        response. Streaming updates remain available to human-driven UIs via
        ``POST /optimizations/ai-generate-code``.

        Args:
            req: Compact MCP-friendly input: goal plus current editor contents.

        Returns:
            An :class:`EditCodeResponse` with the final signature, metric, and
            optional assistant message.

        Raises:
            DomainError: 502 when the code agent emits an ``error`` event.
        """
        final_signature = req.current_signature
        final_metric = req.current_metric
        assistant_message = ""

        async for event in run_code_agent(
            dataset_columns=req.dataset_columns,
            column_roles=req.column_roles,
            column_kinds=req.column_kinds,
            sample_rows=req.sample_rows,
            user_message=req.goal,
            chat_history=[],
            prior_signature=req.current_signature,
            prior_metric=req.current_metric,
        ):
            name = event["event"]
            data = event["data"]
            if name == "done":
                final_signature = data.get("signature_code", final_signature)
                final_metric = data.get("metric_code", final_metric)
                assistant_message = data.get("assistant_message", "")
            elif name == "error":
                raise DomainError(
                    "code_agent.upstream_failed",
                    status=502,
                    error=str(data.get("error", "code agent failed")),
                )

        return EditCodeResponse(
            signature_code=final_signature,
            metric_code=final_metric,
            assistant_message=assistant_message,
        )

    return router
