"""SSE endpoint for the generalist agent that drives the Skynet wizard. [INTERNAL]

Mirrors the ``code_agent`` router's shape: one streaming POST that emits
reasoning / tool / message events, plus a companion confirm POST so the
client can respond to ``pending_approval`` events (the SSE channel is
server → client only).

All endpoints are hidden from the public Scalar reference (none are in
``_SCALAR_PUBLIC_PATHS``) — wizard-internal flow.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from ...service_gateway.agents.generalist import (
    TrustMode,
    WizardState,
    get_approval_registry,
    run_generalist_agent,
)
from ..errors import DomainError
from ._helpers import sse_from_events

logger = logging.getLogger(__name__)


class ChatTurn(BaseModel):
    """A single prior turn in the agent conversation."""

    role: str = Field(..., description="'user' or 'assistant'.")
    content: str = Field(..., description="Message text.")


class GeneralistAgentRequest(BaseModel):
    """Input for a single generalist-agent turn."""

    user_message: str = Field(..., description="The user's latest Hebrew message.")
    chat_history: list[ChatTurn] = Field(default_factory=list, description="Prior {role, content} turns.")
    wizard_state: dict = Field(
        default_factory=dict,
        description=(
            "Snapshot of the wizard: ``{dataset_ready, columns_configured, "
            "signature_code, metric_code, model_configured}``."
        ),
    )
    trust_mode: TrustMode = Field(
        default="ask",
        description="'ask' (confirm every mutation), 'auto_safe' (confirm destructive only), 'yolo' (never confirm).",
    )


class ConfirmApprovalRequest(BaseModel):
    """Client → server reply to a ``pending_approval`` SSE event."""

    call_id: str = Field(..., description="The id carried by the pending_approval event.")
    approved: bool = Field(..., description="True to proceed with the tool, False to decline.")


class ConfirmApprovalResponse(BaseModel):
    """Ack for an approval confirm call."""

    resolved: bool


def create_generalist_agent_router() -> APIRouter:
    """Mount the ``/optimizations/generalist-agent`` SSE + confirm endpoints.

    Returns:
        A configured :class:`APIRouter` with the generalist-agent endpoints attached.
    """
    router = APIRouter()

    @router.post(
        "/optimizations/generalist-agent",
        summary="Stream generalist-agent events for one user turn",
    )
    async def generalist_agent(req: GeneralistAgentRequest) -> StreamingResponse:
        """Stream the generalist agent's reasoning, tool calls, and reply as SSE.

        Event types: ``reasoning_patch``, ``tool_start``, ``tool_end``,
        ``status_patch``, ``pending_approval``, ``approval_resolved``,
        ``message_patch``, ``done``, ``error``.

        Args:
            req: Request body with user message, chat history, wizard
                snapshot, and trust mode.

        Returns:
            A :class:`StreamingResponse` of Server-Sent Events.
        """

        wizard_state: WizardState = {**req.wizard_state}  # type: ignore[typeddict-item]
        source = run_generalist_agent(
            wizard_state=wizard_state,
            chat_history=[t.model_dump() for t in req.chat_history],
            user_message=req.user_message,
            trust_mode=req.trust_mode,
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
        "/optimizations/generalist-agent/confirm",
        response_model=ConfirmApprovalResponse,
        summary="Resolve a pending generalist-agent approval",
    )
    def confirm_approval(req: ConfirmApprovalRequest) -> ConfirmApprovalResponse:
        """Resolve an outstanding approval from the client.

        Args:
            req: Confirm payload with the ``call_id`` and approval boolean.

        Returns:
            A :class:`ConfirmApprovalResponse` with ``resolved=True`` on success.

        Raises:
            DomainError: 404 when the call id is unknown or already resolved —
                the client should treat that as a race and surface it as a UI
                warning.
        """
        resolved = get_approval_registry().resolve(req.call_id, req.approved)
        if not resolved:
            raise DomainError("agent.approval.unknown_call_id", status=404)
        return ConfirmApprovalResponse(resolved=True)

    return router
