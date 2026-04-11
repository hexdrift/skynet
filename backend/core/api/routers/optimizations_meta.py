"""Routes for reading and mutating optimization metadata.

Contains the simple per-optimization endpoints that depend only on the job
store: log retrieval, payload inspection, and the three PATCH endpoints that
toggle/rename display metadata (name, pin, archive).

Separated from ``app.py`` as the pilot for the domain-router pattern. Heavier
optimization endpoints (summary, dataset, cancel, delete, streams, etc.) still
live in ``app.py`` and will follow the same template.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ...constants import (
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_JOB_TYPE,
    PAYLOAD_OVERVIEW_NAME,
)
from ...models import JobLogEntry, OptimizationPayloadResponse
from ..converters import parse_overview

logger = logging.getLogger(__name__)


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def create_optimizations_meta_router(*, job_store) -> APIRouter:
    """Build the optimizations-metadata router.

    Args:
        job_store: Active job store instance (local or remote).

    Returns:
        APIRouter: Router with five routes — logs, payload, name, pin, archive.
    """
    router = APIRouter()

    @router.get(
        "/optimizations/{optimization_id}/logs",
        response_model=List[JobLogEntry],
        summary="Fetch the chronological log trail for an optimization",
    )
    def get_job_logs(
        optimization_id: str,
        limit: Optional[int] = Query(default=None, ge=1, le=5000, description="Maximum number of log entries to return; omit to return everything captured (subject to the 5000-entry ceiling)"),
        offset: int = Query(default=0, ge=0, description="Number of log entries to skip before returning — use with limit for simple pagination"),
        level: Optional[str] = Query(default=None, description="Case-insensitive level filter: DEBUG, INFO, WARNING, ERROR, CRITICAL"),
    ) -> List[JobLogEntry]:
        """Return every log line captured while the optimization ran, in order.

        The worker writes structured log entries (``timestamp``, ``level``,
        ``message``, optional ``pair_index`` for grid searches) to the job
        store as the optimization progresses. This endpoint is what the
        "Logs" tab in the UI polls to tail the run in near real time.

        Behavior:
            - Returns an empty list for jobs that haven't produced any log
              lines yet (e.g. a job still in ``pending``).
            - ``level`` is an exact match after uppercasing. Passing "info"
              returns only INFO-level entries, not INFO-and-above.
            - Pagination via ``offset``/``limit`` is stable under the
              natural timestamp ordering, but new log lines appended by the
              worker after the query ran will not appear mid-response.

        Returns HTTP 404 if the optimization ID is unknown.
        """

        if not job_store.job_exists(optimization_id):
            logger.warning("Optimization logs requested for unknown optimization_id=%s", optimization_id)
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.")

        normalized_level = level.upper() if level else None
        log_entries = job_store.get_logs(
            optimization_id, limit=limit, offset=offset, level=normalized_level,
        )
        return [JobLogEntry(**entry) for entry in log_entries]

    @router.get(
        "/optimizations/{optimization_id}/payload",
        response_model=OptimizationPayloadResponse,
        summary="Retrieve the original submission payload",
    )
    def get_job_payload(optimization_id: str) -> OptimizationPayloadResponse:
        """Return the exact request body the user submitted when the job was
        created — the dataset, column mapping, signature code, metric code,
        optimizer kwargs, everything.

        Used by the "Duplicate" / "Re-run with changes" UX flow so users can
        pop a new submit wizard prefilled with everything from a previous
        run. Also useful for reproducing a run exactly, or for auditing
        what was actually submitted vs. what the overview card shows.

        The response includes ``optimization_type`` (``run`` or ``grid_search``)
        so the client can decide which wizard to open.

        Errors:
            - 404 if the optimization ID is unknown.
            - 404 if the payload was not stored (very old jobs predate the
              feature) — the error detail says "Payload not available".

        Security note: ``model_settings.api_key`` is stripped from the
        stored overview, but the original payload stored here is the
        *complete* submission including any keys the user supplied inline.
        Access to this endpoint should be treated accordingly.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.")

        payload = job_data.get("payload")
        if not payload or not isinstance(payload, dict):
            raise HTTPException(
                status_code=404,
                detail="Payload not available for this job.",
            )

        overview = parse_overview(job_data)
        optimization_type = overview.get(PAYLOAD_OVERVIEW_JOB_TYPE, OPTIMIZATION_TYPE_RUN)
        return OptimizationPayloadResponse(optimization_id=optimization_id, optimization_type=optimization_type, payload=payload)

    @router.patch(
        "/optimizations/{optimization_id}/name",
        status_code=200,
        summary="Rename an optimization's display label",
    )
    def rename_job(optimization_id: str, req: RenameRequest) -> dict:
        """Update the human-friendly display name shown on dashboard cards
        and in the sidebar.

        Only the display name is changed. The UUID, stored payload, result
        artifact, and everything else stay untouched. Lets users rename a
        run after the fact — e.g. a job submitted as "test1" can become
        "prod MIPRO v2 run" once it finishes successfully.

        Validation: the new name is required (1-200 characters) and leading
        and trailing whitespace is trimmed server-side. Passing an empty or
        whitespace-only string is rejected by Pydantic with a 422.

        Returns ``{"optimization_id": ..., "name": ...}`` on success, 404
        if the optimization doesn't exist.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Optimization not found.")
        overview = parse_overview(job_data)
        overview[PAYLOAD_OVERVIEW_NAME] = req.name.strip()
        job_store.set_payload_overview(optimization_id, overview)
        return {"optimization_id": optimization_id, "name": req.name.strip()}

    @router.patch(
        "/optimizations/{optimization_id}/pin",
        status_code=200,
        summary="Toggle pinned state for an optimization",
    )
    def toggle_pin_job(optimization_id: str) -> dict:
        """Flip the ``pinned`` flag on an optimization's overview.

        Pinned jobs surface at the top of the dashboard sidebar so
        important runs don't get lost as newer jobs are submitted. This is
        a pure toggle — the endpoint reads the current flag and writes the
        opposite. There is no explicit "pin" or "unpin" parameter.

        Idempotency: two calls in a row return the job to its original
        state. If the UI needs a specific final state it must read the
        returned ``pinned`` value and call again if needed.

        Returns ``{"optimization_id": ..., "pinned": <new_state>}``.
        404 if the optimization doesn't exist.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Optimization not found.")
        overview = parse_overview(job_data)
        current = overview.get("pinned", False)
        overview["pinned"] = not current
        job_store.set_payload_overview(optimization_id, overview)
        return {"optimization_id": optimization_id, "pinned": not current}

    @router.patch(
        "/optimizations/{optimization_id}/archive",
        status_code=200,
        summary="Toggle archived state for an optimization",
    )
    def toggle_archive_job(optimization_id: str) -> dict:
        """Flip the ``archived`` flag on an optimization's overview.

        Archiving hides a job from the default sidebar view without
        deleting it. It's the soft-delete equivalent: the job, its logs,
        and its artifact all remain on disk and can still be fetched by
        ID. The UI offers a "Show archived" toggle to bring them back.

        Like ``/pin``, this is a pure toggle — no explicit state parameter.
        Use ``DELETE /optimizations/{id}`` for actual removal.

        Returns ``{"optimization_id": ..., "archived": <new_state>}``.
        404 if the optimization doesn't exist.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Optimization not found.")
        overview = parse_overview(job_data)
        current = overview.get("archived", False)
        overview["archived"] = not current
        job_store.set_payload_overview(optimization_id, overview)
        return {"optimization_id": optimization_id, "archived": not current}

    return router
