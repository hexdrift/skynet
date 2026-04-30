"""Public anonymous dashboard routes (PER-11 Feature B).

``GET /dashboard/public`` returns the payload the /explore page needs:
a list of points (one per embedded job) with 2D coordinates for the
scatter, precomputed cluster IDs at five granularity levels, and the
per-level cluster counts for slider labelling. No authentication, no
user identifiers in the response.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ...service_gateway.dashboard import fetch_public_dashboard


class PublicDashboardPoint(BaseModel):
    """One scatter-plot point per embedded job.

    Heavy fields like ``signature_code``, ``optimizer_kwargs``, and
    ``metric_name`` were dropped from the public payload — they are not
    consumed by the /explore UI and bloated the bulk response at scale.
    """

    optimization_id: str
    optimization_type: str | None = None
    winning_model: str | None = None
    baseline_metric: float | None = None
    optimized_metric: float | None = None
    summary_text: str | None = None
    task_name: str | None = None
    module_name: str | None = None
    optimizer_name: str | None = None
    created_at: str | None = None
    x: float = 0.0
    y: float = 0.0
    cluster_levels: list[int]


class PublicDashboardMeta(BaseModel):
    """Top-level metadata for the explore payload."""

    count: int
    level_cluster_counts: list[int]


class PublicDashboardResponse(BaseModel):
    """Envelope for ``GET /dashboard/public`` — the cross-user cluster map."""

    points: list[PublicDashboardPoint]
    meta: PublicDashboardMeta


def create_dashboard_router(*, job_store: Any) -> APIRouter:
    """Build the public cross-user dashboard router.

    Args:
        job_store: Backing job store used to fetch the public dashboard payload.

    Returns:
        A configured :class:`APIRouter` exposing ``/dashboard/public``.
    """
    router = APIRouter()

    @router.get(
        "/dashboard/public",
        response_model=PublicDashboardResponse,
        status_code=200,
        summary="Anonymous cross-user cluster map",
    )
    def public_dashboard() -> PublicDashboardResponse:
        """UMAP-projected job points + cluster levels for the /explore page.

        Returns:
            A :class:`PublicDashboardResponse` with one point per embedded
            job and metadata describing the cluster granularity levels.
        """
        data = fetch_public_dashboard(job_store=job_store)
        return PublicDashboardResponse(
            points=[PublicDashboardPoint(**p) for p in data["points"]],
            meta=PublicDashboardMeta(**data["meta"]),
        )

    return router
