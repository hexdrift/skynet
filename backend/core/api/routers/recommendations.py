"""Routes for the historical-performance recommendation service (PER-11).

``POST /recommendations/similar`` takes the in-progress submission
(dataset schema, signature source, target optimization type) and
returns a ranked list of past jobs whose content-and-code embeddings
come closest. The frontend uses the ranking to suggest optimizer and
model configs that historically performed well on tasks like this.

Phase 1 (this commit) wires the endpoint, request/response shapes, and
background-embedding hook — the service layer returns ``[]`` so the
frontend can start integrating while the embedder is built.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...service_gateway.recommendations import search_similar


class SimilarRequest(BaseModel):
    """Query body for ``POST /recommendations/similar``."""

    signature_code: str | None = Field(
        default=None,
        description="Current DSPy Signature source — the 'task shape' half of the query.",
    )
    metric_code: str | None = Field(
        default=None,
        description="Current metric source; included in the code embedding if present.",
    )
    dataset_schema: dict[str, Any] | None = Field(
        default=None,
        description="Column → dtype/role map used to embed the dataset's structure.",
    )
    optimization_type: str | None = Field(
        default=None,
        description="'run' or 'grid_search' — restricts neighbours to the same kind of job.",
    )
    user_id: str | None = Field(
        default=None,
        description="Optional requester. Reserved for cross-user scoping; ignored in Phase 1.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="How many neighbours to return. Ceiling 20 to keep responses compact.",
    )


class SimilarJob(BaseModel):
    """One neighbour in ``SimilarResponse.results``.

    The extra fields beyond id/type/model/score are what the wizard
    uses for one-click apply: the frontend can populate the submission
    form from ``optimizer_name``, ``optimizer_kwargs``, and
    ``module_name``, and show ``summary_text`` + ``baseline_metric``
    / ``optimized_metric`` as the justification.
    """

    optimization_id: str
    optimization_type: str | None = None
    winning_model: str | None = None
    winning_rank: int | None = None
    score: float = Field(description="Weighted similarity in [0, 1] — higher is closer.")
    baseline_metric: float | None = None
    optimized_metric: float | None = None
    summary_text: str | None = None
    signature_code: str | None = None
    metric_name: str | None = None
    optimizer_name: str | None = None
    optimizer_kwargs: dict[str, Any] = Field(default_factory=dict)
    module_name: str | None = None
    task_name: str | None = None


class SimilarResponse(BaseModel):
    """Envelope returned by ``POST /recommendations/similar``."""

    results: list[SimilarJob]


def create_recommendations_router(*, job_store) -> APIRouter:
    """Build the recommendations router."""
    router = APIRouter()

    @router.post(
        "/recommendations/similar",
        response_model=SimilarResponse,
        status_code=200,
        summary="Find past jobs similar to the current submission",
        tags=["agent"],
    )
    def similar(req: SimilarRequest) -> SimilarResponse:
        """Return up to ``top_k`` past jobs whose embeddings are closest.

        Phase 1 stub: always returns ``{"results": []}``. Phase 2 will
        fill in the real weighted-fusion search against pgvector.
        """
        hits = search_similar(
            job_store=job_store,
            signature_code=req.signature_code,
            metric_code=req.metric_code,
            dataset_schema=req.dataset_schema,
            optimization_type=req.optimization_type,
            user_id=req.user_id,
            top_k=req.top_k,
        )
        return SimilarResponse(results=[SimilarJob(**h) for h in hits])

    return router
