"""Public anonymous dashboard routes (PER-11 Feature B). [INTERNAL]

``GET /dashboard/public`` returns the full corpus scatter map. ``POST
/dashboard/search`` runs semantic + structured search and returns ranked
results plus the matched-id set the map uses to dim non-matches.

Hidden from the public Scalar reference (none are in
``_SCALAR_PUBLIC_PATHS``) — the response shapes are bound to the /explore
view, not a stable dev contract.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ...service_gateway.dashboard import (
    SEARCH_PAGE_SIZE_DEFAULT,
    SEARCH_PAGE_SIZE_MAX,
    SEARCH_SORT_RELEVANCE,
    SEARCH_SORTS,
    fetch_public_dashboard,
    search_optimizations,
)
from ..auth import get_authenticated_user


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
    # Older optimization_ids that share this point's identity (same task
    # signature + module + optimizer + type). Empty when the leader is
    # unique. Used by the explore UI to offer a "compare with previous
    # runs" CTA so users can still inspect what dedup hid.
    siblings: list[str] = []
    # Identifies a comparable ML task (signature + metric + dataset). Two
    # points sharing this value were trained on the same task — the
    # frontend groups them as variations under one dot.
    task_fingerprint: str | None = None
    # Stronger key: same task AND byte-identical train/val/test splits.
    # Backend uses this for dedup; one ``compare_fingerprint`` = one leader.
    compare_fingerprint: str | None = None
    # False for successful jobs that haven't been embedded yet — they
    # appear in the corpus count and in lexical search results, but the
    # frontend should not render them on the scatter map (x/y are stubs).
    has_coordinates: bool = True


class PublicDashboardResponse(BaseModel):
    """Envelope for ``GET /dashboard/public`` — the cross-user scatter map."""

    points: list[PublicDashboardPoint]


class SearchRequest(BaseModel):
    """Free-text + structured filter query for ``POST /dashboard/search``.

    Empty ``query`` is allowed when filters or a non-relevance ``sort`` are
    provided. ``date_to`` is treated as inclusive (whole day).
    """

    query: str | None = None
    models: list[str] | None = None
    optimizers: list[str] | None = None
    optimization_types: list[str] | None = None
    date_from: date | None = None
    date_to: date | None = None
    sort: str = SEARCH_SORT_RELEVANCE
    page: int = Field(default=1, ge=1)
    size: int = Field(default=SEARCH_PAGE_SIZE_DEFAULT, ge=1, le=SEARCH_PAGE_SIZE_MAX)
    # When set, scope the search to that user's own jobs (including private
    # rows) instead of the cross-user public corpus. The route handler
    # verifies the requested owner matches the authenticated session before
    # forwarding it to the gateway.
    owner_username: str | None = None


class SearchResult(BaseModel):
    """One row in the ranked list view.

    ``relevance`` is the cosine similarity (``1 - distance``) when the
    request is ranked by relevance; ``null`` for recency / gain ranking.
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
    relevance: float | None = None


class SearchResponse(BaseModel):
    """Envelope for ``POST /dashboard/search``."""

    results: list[SearchResult]
    total: int
    # Every ``optimization_id`` that satisfies the query + filters, capped
    # at SEARCH_MATCHED_IDS_CAP. Used by the map view to dim non-matches.
    matched_ids: list[str]
    # Which dispatch branch the gateway took. The /explore UI surfaces this
    # on every result row so users see whether they got embedding-ranked or
    # ILIKE-matched hits.
    search_type: Literal["semantic", "lexical"] | None = None


def create_dashboard_router(*, job_store: Any) -> APIRouter:
    """Build the public cross-user dashboard router.

    Args:
        job_store: Backing job store used to fetch the public dashboard payload.

    Returns:
        A configured :class:`APIRouter` exposing ``/dashboard/public``
        and ``/dashboard/search``.
    """
    router = APIRouter()

    @router.get(
        "/dashboard/public",
        response_model=PublicDashboardResponse,
        status_code=200,
        summary="Anonymous cross-user scatter map",
    )
    def public_dashboard() -> PublicDashboardResponse:
        """UMAP-projected job points for the /explore page.

        Returns:
            A :class:`PublicDashboardResponse` with one point per embedded job.
        """
        data = fetch_public_dashboard(job_store=job_store)
        return PublicDashboardResponse(
            points=[PublicDashboardPoint(**p) for p in data["points"]],
        )

    @router.post(
        "/dashboard/search",
        response_model=SearchResponse,
        status_code=200,
        summary="Semantic + structured search across optimizations",
        tags=["agent"],
    )
    def public_search(
        request: SearchRequest,
        authorization: str | None = Header(default=None),
    ) -> SearchResponse:
        """Rank embedded jobs by pgvector similarity (or recency / gain).

        Args:
            request: The query, filters, sort, and paging parameters.
            authorization: Bearer token, required only when ``owner_username``
                is set so the mine corpus can include the user's private rows.

        Returns:
            Ranked page plus the full matched-id set for map dimming.

        Raises:
            HTTPException: When ``owner_username`` is set but the request is
                unauthenticated or targets a different user than the session.
        """
        sort = request.sort if request.sort in SEARCH_SORTS else SEARCH_SORT_RELEVANCE
        owner_username = _resolve_owner_username(request.owner_username, authorization)
        data = search_optimizations(
            job_store=job_store,
            query=request.query,
            models=request.models,
            optimizers=request.optimizers,
            optimization_types=request.optimization_types,
            date_from=request.date_from,
            date_to=request.date_to,
            sort=sort,
            page=request.page,
            size=request.size,
            owner_username=owner_username,
        )
        return SearchResponse(
            results=[SearchResult(**r) for r in data["results"]],
            total=int(data["total"]),
            matched_ids=list(data["matched_ids"]),
            search_type=data.get("search_type"),
        )

    return router


def _resolve_owner_username(
    requested: str | None, authorization: str | None
) -> str | None:
    """Verify a requested owner scope matches the authenticated session.

    Args:
        requested: The ``owner_username`` value from the request body, or None
            when the caller is searching the public corpus.
        authorization: Raw ``Authorization`` header.

    Returns:
        The trusted username to forward to the gateway, or None for public.

    Raises:
        HTTPException: 401 when authentication is missing or invalid; 403 when
            the authenticated user does not match the requested owner.
    """
    if requested is None:
        return None
    user = get_authenticated_user(authorization=authorization)
    normalized = requested.strip().lower()
    if not normalized:
        return None
    if normalized != user.username:
        raise HTTPException(status_code=403, detail="auth.owner_mismatch")
    return normalized
