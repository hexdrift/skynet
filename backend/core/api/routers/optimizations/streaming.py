"""Server-sent-event streams for the optimizations dashboard and per-job view. [MIXED]

Public dev surface (in ``_SCALAR_PUBLIC_PATHS``):
- ``GET /optimizations/{id}/stream`` — live progress for a single job.

Internal (dashboard plumbing, hidden from public docs):
- ``GET /optimizations/stream`` — fan-out stream for the dashboard.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from ...auth import AuthenticatedUser, get_authenticated_user, is_admin
from ...errors import DomainError
from .._helpers import job_owner, sse_from_events
from ._local import stream_dashboard_snapshots, stream_job_updates

logger = logging.getLogger(__name__)

AuthenticatedUserDep = Annotated[AuthenticatedUser, Depends(get_authenticated_user)]

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def register_dashboard_stream(router: APIRouter, *, job_store) -> None:
    """Register the ``GET /optimizations/stream`` dashboard SSE route.

    Must be registered before any ``/optimizations/{optimization_id}`` route
    so FastAPI's literal-first matcher does not shadow it.

    Args:
        router: The router to attach the dashboard stream route to.
        job_store: Job-store the underlying generator reads from.
    """

    @router.get(
        "/optimizations/stream",
        summary="Stream live dashboard updates (all active optimizations) as SSE",
    )
    async def stream_dashboard(current_user: AuthenticatedUserDep):
        """Stream live dashboard snapshots of all active optimizations as SSE.

        Polls pending/validating/running rows every 3 seconds and yields a JSON
        snapshot per tick. Non-admins see only their own active jobs; admins
        see everyone. When no jobs in scope are active the generator emits
        ``event: idle`` and closes the stream.

        Args:
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            A streaming ``StreamingResponse`` with ``text/event-stream`` body.
        """
        owner_filter = None if is_admin(current_user) else current_user.username
        return StreamingResponse(
            sse_from_events(stream_dashboard_snapshots(job_store, owner_filter=owner_filter)),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )


def register_job_stream(router: APIRouter, *, job_store) -> None:
    """Register the ``GET /optimizations/{id}/stream`` per-job SSE route.

    Args:
        router: The router to attach the per-job stream route to.
        job_store: Job-store the underlying generator reads from.
    """

    @router.get(
        "/optimizations/{optimization_id}/stream",
        summary="Stream one optimization's live status updates as SSE",
    )
    async def stream_job(optimization_id: str, current_user: AuthenticatedUserDep):
        """Stream one optimization's live status updates as SSE.

        Emits a status + metrics snapshot every 2 seconds and terminates with
        ``event: done`` once the optimization reaches a terminal state.

        Args:
            optimization_id: Optimization id to follow.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            A streaming ``StreamingResponse`` with ``text/event-stream`` body.

        Raises:
            DomainError: 404 if the optimization id is unknown or the
                non-admin caller doesn't own it.
        """
        loop = asyncio.get_running_loop()
        try:
            raw = await loop.run_in_executor(None, job_store.get_job, optimization_id)
        except KeyError:
            raw = None
        if raw is None:
            raise DomainError("optimization.not_found", status=404, optimization_id=optimization_id) from None
        if not is_admin(current_user):
            owner = job_owner(raw)
            if owner is None or owner != current_user.username:
                raise DomainError("optimization.not_found", status=404, optimization_id=optimization_id)

        return StreamingResponse(
            sse_from_events(stream_job_updates(job_store, optimization_id)),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )
