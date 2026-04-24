"""Public anonymous dashboard routes (PER-11 Feature B).

``GET /dashboard/public`` returns the payload the /explore page needs:
a list of points (one per embedded job) with 2D coordinates for the
scatter. No authentication, no user identifiers in the response — the
frontend renders this as a public feed of activity.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...service_gateway.dashboard import fetch_public_dashboard


class PublicDashboardPoint(BaseModel):
    """One scatter-plot point per embedded job.

    ``x`` / ``y`` flatten the storage columns ``projection_x`` / ``projection_y``
    (``JobEmbedding``, PCA-projected to 2D). The API deliberately hides the
    ``projection_`` prefix — it's a DB implementation detail, not part of the
    public plotting contract.
    """

    optimization_id: str
    optimization_type: str | None = None
    winning_model: str | None = None
    winning_rank: int | None = None
    is_recommendable: bool = False
    baseline_metric: float | None = None
    optimized_metric: float | None = None
    summary_text: str | None = None
    signature_code: str | None = None
    metric_name: str | None = None
    task_name: str | None = None
    module_name: str | None = None
    optimizer_name: str | None = None
    optimizer_kwargs: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    x: float = 0.0
    y: float = 0.0


class PublicDashboardResponse(BaseModel):
    points: list[PublicDashboardPoint]


def create_dashboard_router(*, job_store: Any) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/dashboard/public",
        response_model=PublicDashboardResponse,
        status_code=200,
        summary="Anonymous cross-user cluster map",
    )
    def public_dashboard() -> PublicDashboardResponse:
        """PCA-projected job points for the /explore page."""
        data = fetch_public_dashboard(job_store=job_store)
        return PublicDashboardResponse(
            points=[PublicDashboardPoint(**p) for p in data["points"]],
        )

    return router
