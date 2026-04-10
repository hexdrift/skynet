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
from pydantic import BaseModel

from ...constants import (
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_JOB_TYPE,
    PAYLOAD_OVERVIEW_NAME,
)
from ...models import JobLogEntry, OptimizationPayloadResponse
from ..converters import parse_overview

logger = logging.getLogger(__name__)


class RenameRequest(BaseModel):
    name: str


def create_optimizations_meta_router(*, job_store) -> APIRouter:
    """Build the optimizations-metadata router.

    Args:
        job_store: Active job store instance (local or remote).

    Returns:
        APIRouter: Router with five routes — logs, payload, name, pin, archive.
    """
    router = APIRouter()

    @router.get("/optimizations/{optimization_id}/logs", response_model=List[JobLogEntry])
    def get_job_logs(
        optimization_id: str,
        limit: Optional[int] = Query(default=None, ge=1, le=5000, description="Max log entries to return"),
        offset: int = Query(default=0, ge=0, description="Skip N log entries"),
        level: Optional[str] = Query(default=None, description="Filter by log level (e.g. ERROR, WARNING, INFO)"),
    ) -> List[JobLogEntry]:
        """Return the chronological run log for the job.

        Args:
            optimization_id: Identifier for the job returned during submission.
            limit: Maximum number of log entries to return.
            offset: Number of log entries to skip.
            level: Filter by log level (case-insensitive).

        Returns:
            List[JobLogEntry]: Ordered log entries captured during execution.
        """

        if not job_store.job_exists(optimization_id):
            logger.warning("Optimization logs requested for unknown optimization_id=%s", optimization_id)
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.")

        normalized_level = level.upper() if level else None
        log_entries = job_store.get_logs(
            optimization_id, limit=limit, offset=offset, level=normalized_level,
        )
        return [JobLogEntry(**entry) for entry in log_entries]

    @router.get("/optimizations/{optimization_id}/payload", response_model=OptimizationPayloadResponse)
    def get_job_payload(optimization_id: str) -> OptimizationPayloadResponse:
        """Return the original request payload submitted for this job.

        Args:
            optimization_id: Identifier for the job returned during submission.

        Returns:
            OptimizationPayloadResponse: The stored request payload.
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

    @router.patch("/optimizations/{optimization_id}/name", status_code=200)
    def rename_job(optimization_id: str, req: RenameRequest) -> dict:
        """Update the display name of a job."""
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Optimization not found.")
        overview = parse_overview(job_data)
        overview[PAYLOAD_OVERVIEW_NAME] = req.name.strip()
        job_store.set_payload_overview(optimization_id, overview)
        return {"optimization_id": optimization_id, "name": req.name.strip()}

    @router.patch("/optimizations/{optimization_id}/pin", status_code=200)
    def toggle_pin_job(optimization_id: str) -> dict:
        """Toggle the pinned state of a job."""
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Optimization not found.")
        overview = parse_overview(job_data)
        current = overview.get("pinned", False)
        overview["pinned"] = not current
        job_store.set_payload_overview(optimization_id, overview)
        return {"optimization_id": optimization_id, "pinned": not current}

    @router.patch("/optimizations/{optimization_id}/archive", status_code=200)
    def toggle_archive_job(optimization_id: str) -> dict:
        """Toggle the archived state of a job."""
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
