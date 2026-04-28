"""Server-sent-event streams for the optimizations dashboard and per-job view."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from starlette.responses import StreamingResponse

from ...errors import DomainError
from .._helpers import sse_from_events
from ._local import stream_dashboard_snapshots, stream_job_updates

logger = logging.getLogger(__name__)

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
    async def stream_dashboard():
        """Stream live dashboard snapshots of all active optimizations as SSE.

        Polls pending/validating/running rows every 3 seconds and yields a JSON
        snapshot per tick. When no optimizations are active the generator emits
        ``event: idle`` and closes the stream.

        Returns:
            A streaming ``StreamingResponse`` with ``text/event-stream`` body.
        """
        return StreamingResponse(
            sse_from_events(stream_dashboard_snapshots(job_store)),
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
    async def stream_job(optimization_id: str):
        """Stream one optimization's live status updates as SSE.

        Emits a status + metrics snapshot every 2 seconds and terminates with
        ``event: done`` once the optimization reaches a terminal state.

        Args:
            optimization_id: Optimization id to follow.

        Returns:
            A streaming ``StreamingResponse`` with ``text/event-stream`` body.

        Raises:
            DomainError: 404 if the optimization id is unknown (pre-flight
                check).
        """
        loop = asyncio.get_running_loop()
        try:
            raw = await loop.run_in_executor(None, job_store.get_job, optimization_id)
        except KeyError:
            raw = None
        if raw is None:
            raise DomainError("optimization.not_found", status=404, optimization_id=optimization_id) from None

        return StreamingResponse(
            sse_from_events(stream_job_updates(job_store, optimization_id)),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )
