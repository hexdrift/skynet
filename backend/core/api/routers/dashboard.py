"""Public anonymous dashboard routes (PER-11 Feature B). [INTERNAL]

``GET /dashboard/public`` returns the full corpus point list. ``POST
/dashboard/search`` runs semantic + structured search and returns ranked
results plus the matched-id set the list view uses to scope filters.

Hidden from the public Scalar reference (none are in
``_SCALAR_PUBLIC_PATHS``) — the response shapes are bound to the /explore
view, not a stable dev contract.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ...service_gateway.dashboard import (
    POPULAR_QUERIES_LIMIT_DEFAULT,
    SEARCH_PAGE_SIZE_DEFAULT,
    SEARCH_PAGE_SIZE_MAX,
    SEARCH_SORT_RELEVANCE,
    SEARCH_SORTS,
    fetch_popular_queries,
    fetch_public_dashboard,
    record_public_search_query,
    search_optimizations,
)
from ..auth import get_authenticated_user


class PublicDashboardPoint(BaseModel):
    """One point in the public optimization corpus.

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


class PublicDashboardResponse(BaseModel):
    """Envelope for ``GET /dashboard/public`` — the cross-user optimization corpus."""

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
    # at SEARCH_MATCHED_IDS_CAP.
    matched_ids: list[str]
    # Which dispatch branch the gateway took. The /explore UI surfaces this
    # on every result row so users see whether they got embedding-ranked or
    # ILIKE-matched hits.
    search_type: Literal["semantic", "lexical"] | None = None


class SearchLogRequest(BaseModel):
    """Body for ``POST /dashboard/search/log`` — one explicitly-committed query.

    Sent by the /explore UI only on an explicit commit (Enter or opening a
    result), never on debounced typing, so trending counts reflect intent
    rather than every half-typed prefix.
    """

    query: str


class PopularQuery(BaseModel):
    """One trending public search query and how often it was run."""

    query: str
    count: int


class PopularQueriesResponse(BaseModel):
    """Envelope for ``GET /dashboard/search/popular`` — trending public queries."""

    queries: list[PopularQuery]


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
        summary="Anonymous cross-user corpus",
    )
    def public_dashboard() -> PublicDashboardResponse:
        """Public corpus points for the /explore page.

        Returns:
            A :class:`PublicDashboardResponse` with one point per public
            success-state job.
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
        http_request: Request,
        request: SearchRequest,
        authorization: str | None = Header(default=None),
    ) -> SearchResponse:
        """Rank embedded jobs by pgvector similarity (or recency / gain).

        Args:
            http_request: Incoming request, forwarded to
                ``get_authenticated_user`` so the PAT branch can reach
                ``app.state.job_store`` when ``owner_username`` is set.
            request: The query, filters, sort, and paging parameters.
            authorization: Bearer token, required only when ``owner_username``
                is set so the mine corpus can include the user's private rows.

        Returns:
            Ranked page plus the full matched-id set for explore-page dimming.

        Raises:
            HTTPException: When ``owner_username`` is set but the request is
                unauthenticated or targets a different user than the session.
        """
        sort = request.sort if request.sort in SEARCH_SORTS else SEARCH_SORT_RELEVANCE
        owner_username = _resolve_owner_username(
            http_request, request.owner_username, authorization
        )
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

    @router.post(
        "/dashboard/search/log",
        status_code=204,
        summary="Record an explicitly-committed public search query",
    )
    def log_search_query(request: SearchLogRequest) -> None:
        """Record one public query for trending on an explicit commit.

        Fire-and-forget from the /explore UI (Enter or opening a result). The
        gateway normalizes and best-effort writes the row; failures are
        swallowed so logging never affects the user.

        Args:
            request: The committed query to record.
        """
        record_public_search_query(job_store, request.query)

    @router.get(
        "/dashboard/search/popular",
        response_model=PopularQueriesResponse,
        status_code=200,
        summary="Trending public search queries",
    )
    def popular_searches() -> PopularQueriesResponse:
        """Most-run public-corpus search queries over a recent window.

        Returns:
            A :class:`PopularQueriesResponse` ranked by occurrence count, most
            popular first. Empty until the public corpus has been searched.
        """
        rows = fetch_popular_queries(
            job_store=job_store, limit=POPULAR_QUERIES_LIMIT_DEFAULT
        )
        return PopularQueriesResponse(queries=[PopularQuery(**r) for r in rows])

    return router


def _resolve_owner_username(
    request: Request, requested: str | None, authorization: str | None
) -> str | None:
    """Verify a requested owner scope matches the authenticated session.

    Args:
        request: Incoming request, forwarded to ``get_authenticated_user`` so
            the PAT branch can reach ``app.state.job_store``.
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
    user = get_authenticated_user(request, authorization=authorization)
    normalized = requested.strip().lower()
    if not normalized:
        return None
    if normalized != user.username:
        raise HTTPException(status_code=403, detail="auth.owner_mismatch")
    return normalized
