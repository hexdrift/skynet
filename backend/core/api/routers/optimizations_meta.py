"""Routes for reading and mutating optimization metadata (logs, payload, name, pin, archive)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from ...constants import (
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
)
from ...models import JobLogEntry, OptimizationPayloadResponse
from ..converters import parse_overview
from ..errors import DomainError
from ..response_limits import (
    AGENT_DEFAULT_LIST,
    AGENT_MAX_LIST,
    AGENT_MAX_LOG_MESSAGE,
    clamp_limit,
    truncate_text,
)

logger = logging.getLogger(__name__)


class RenameRequest(BaseModel):
    """Request body for ``PATCH /optimizations/{id}/name`` — the new display name."""

    name: str = Field(min_length=1, max_length=200)


def create_optimizations_meta_router(*, job_store) -> APIRouter:
    """Build the optimizations-metadata router.

    Args:
        job_store: Job-store instance the routes read from / write to.

    Returns:
        A FastAPI ``APIRouter`` with the metadata routes mounted.
    """
    router = APIRouter()

    @router.get(
        "/optimizations/{optimization_id}/logs",
        response_model=list[JobLogEntry],
        summary="Fetch the chronological log trail for an optimization",
        tags=["agent"],
    )
    def get_job_logs(
        optimization_id: str,
        limit: int | None = Query(
            default=AGENT_DEFAULT_LIST,
            ge=1,
            le=AGENT_MAX_LIST,
            description=(
                f"Max log entries to return (default {AGENT_DEFAULT_LIST}, ceiling {AGENT_MAX_LIST}). "
                "Paginate with offset for more."
            ),
        ),
        offset: int = Query(
            default=0,
            ge=0,
            description="Number of log entries to skip before returning — use with limit for simple pagination",
        ),
        level: str | None = Query(
            default=None, description="Case-insensitive level filter: DEBUG, INFO, WARNING, ERROR, CRITICAL"
        ),
    ) -> list[JobLogEntry]:
        """Return log lines for an optimization in chronological order.

        ``level`` is an exact uppercase match. Returns empty list for jobs
        with no logs yet. Individual log messages are truncated past ~500
        chars so a single line can't evict the agent context; paginate with
        ``offset`` for more. 404 if the optimization is unknown.

        Args:
            optimization_id: Optimization id to fetch logs for.
            limit: Maximum number of log entries to return.
            offset: Number of log entries to skip.
            level: Optional uppercase level filter.

        Returns:
            A list of ``JobLogEntry`` rows ordered by timestamp ascending.

        Raises:
            DomainError: 404 when the optimization is unknown.
        """

        if not job_store.job_exists(optimization_id):
            logger.warning("Optimization logs requested for unknown optimization_id=%s", optimization_id)
            raise DomainError(
                "optimization.not_found",
                status=404,
                optimization_id=optimization_id,
            ) from None

        normalized_level = level.upper() if level else None
        resolved_limit = clamp_limit(limit)
        log_entries = job_store.get_logs(
            optimization_id,
            limit=resolved_limit,
            offset=offset,
            level=normalized_level,
        )
        out: list[JobLogEntry] = []
        for entry in log_entries:
            entry = dict(entry)
            if isinstance(entry.get("message"), str):
                entry["message"] = truncate_text(entry["message"], AGENT_MAX_LOG_MESSAGE)
            out.append(JobLogEntry(**entry))
        return out

    @router.get(
        "/optimizations/{optimization_id}/payload",
        response_model=OptimizationPayloadResponse,
        summary="Retrieve the original submission payload",
    )
    def get_job_payload(optimization_id: str) -> OptimizationPayloadResponse:
        """Return the original submission payload for an optimization.

        Useful for re-running or duplicating an optimization. Includes the
        full dataset, column mapping, code, and kwargs. Note: the stored
        payload may include the original API key the user submitted inline.
        404 if the optimization is unknown or the stored payload is missing.

        Args:
            optimization_id: Optimization id whose payload should be returned.

        Returns:
            The original submission payload wrapped in
            ``OptimizationPayloadResponse``.

        Raises:
            DomainError: 404 when the optimization is unknown or the
                payload is no longer available.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise DomainError(
                "optimization.not_found",
                status=404,
                optimization_id=optimization_id,
            ) from None

        payload = job_data.get("payload")
        if not payload or not isinstance(payload, dict):
            raise DomainError("optimization.payload_unavailable", status=404)

        overview = parse_overview(job_data)
        optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)
        return OptimizationPayloadResponse(
            optimization_id=optimization_id, optimization_type=optimization_type, payload=payload
        )

    @router.patch(
        "/optimizations/{optimization_id}/name",
        status_code=200,
        summary="Rename an optimization's display label",
        tags=["agent"],
    )
    def rename_job(optimization_id: str, req: RenameRequest) -> dict:
        """Update the display name for an optimization.

        Args:
            optimization_id: Optimization id to rename.
            req: New name payload.

        Returns:
            ``{"optimization_id": id, "name": new_name}``.

        Raises:
            DomainError: 404 when the optimization is unknown.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise DomainError(
                "optimization.not_found",
                status=404,
                optimization_id=optimization_id,
            ) from None
        overview = parse_overview(job_data)
        overview[PAYLOAD_OVERVIEW_NAME] = req.name.strip()
        job_store.set_payload_overview(optimization_id, overview)
        return {"optimization_id": optimization_id, "name": req.name.strip()}

    @router.patch(
        "/optimizations/{optimization_id}/pin",
        status_code=200,
        summary="Toggle pinned state for an optimization",
        tags=["agent"],
    )
    def toggle_pin_job(optimization_id: str) -> dict:
        """Toggle the ``pinned`` flag on an optimization.

        Args:
            optimization_id: Optimization id to toggle.

        Returns:
            ``{"optimization_id": id, "pinned": bool}``.

        Raises:
            DomainError: 404 when the optimization is unknown.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise DomainError(
                "optimization.not_found",
                status=404,
                optimization_id=optimization_id,
            ) from None
        overview = parse_overview(job_data)
        current = overview.get("pinned", False)
        overview["pinned"] = not current
        job_store.set_payload_overview(optimization_id, overview)
        return {"optimization_id": optimization_id, "pinned": not current}

    @router.patch(
        "/optimizations/{optimization_id}/archive",
        status_code=200,
        summary="Toggle archived state for an optimization",
        tags=["agent"],
    )
    def toggle_archive_job(optimization_id: str) -> dict:
        """Toggle the ``archived`` flag (soft-hide without deleting).

        Args:
            optimization_id: Optimization id to toggle.

        Returns:
            ``{"optimization_id": id, "archived": bool}``.

        Raises:
            DomainError: 404 when the optimization is unknown.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise DomainError(
                "optimization.not_found",
                status=404,
                optimization_id=optimization_id,
            ) from None
        overview = parse_overview(job_data)
        current = overview.get("archived", False)
        overview["archived"] = not current
        job_store.set_payload_overview(optimization_id, overview)
        return {"optimization_id": optimization_id, "archived": not current}

    return router
