"""Authenticated on-premise Explorer routes. [INTERNAL]

The Explorer exposes the caller's runs, named shares, and runs that owners
explicitly published to the deployment-wide corpus. Every route requires an
authenticated account; there is no anonymous corpus.

Hidden from the public Scalar reference (none are in
``_SCALAR_PUBLIC_PATHS``) — the response shapes are bound to the /explore
view, not a stable dev contract.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ...service_gateway.dashboard import (
    FACET_LIMIT_DEFAULT,
    FACET_LIMIT_MAX,
    POPULAR_QUERIES_LIMIT_DEFAULT,
    SEARCH_PAGE_SIZE_DEFAULT,
    SEARCH_PAGE_SIZE_MAX,
    SEARCH_SORT_RELEVANCE,
    SEARCH_SORTS,
    fetch_corpus_facets,
    fetch_popular_queries,
    fetch_public_dashboard,
    record_public_search_query,
    search_optimizations,
)
from ..auth import AuthenticatedUser, get_authenticated_user

AuthenticatedUserDep = Annotated[AuthenticatedUser, Depends(get_authenticated_user)]


class PublicDashboardPoint(BaseModel):
    """Represent one explicitly published optimization in Explorer."""

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


class PublicDashboardResponse(BaseModel):
    """Envelope for the authenticated deployment-wide corpus."""

    points: list[PublicDashboardPoint]


class FacetOption(BaseModel):
    """One filter value in a facet dimension with its contextual run count."""

    value: str
    count: int


class FacetTotals(BaseModel):
    """Distinct values still available per dimension, beyond the ones listed."""

    models: int = 0
    optimizers: int = 0
    modules: int = 0
    types: int = 0


class FacetsResponse(BaseModel):
    """Filter options with run counts for one corpus scope (``GET /dashboard/facets``).

    Each list holds the busiest model / optimizer / module / run-type values
    in the requested scope (capped per dimension, optionally narrowed by a
    value search), each with the number of runs it would leave when combined
    with every other active filter. ``totals`` says how many distinct values
    remain available per dimension, so the /explore filter drawer can show
    "top 8 of 1,240" and offer search for the rest instead of listing them.
    """

    models: list[FacetOption] = []
    optimizers: list[FacetOption] = []
    modules: list[FacetOption] = []
    types: list[FacetOption] = []
    totals: FacetTotals = FacetTotals()


class SearchRequest(BaseModel):
    """Free-text + structured filter query for ``POST /dashboard/search``.

    Empty ``query`` is allowed when filters or a non-relevance ``sort`` are
    provided. ``date_to`` is treated as inclusive (whole day).
    """

    query: str | None = None
    models: list[str] | None = None
    optimizers: list[str] | None = None
    optimization_types: list[str] | None = None
    tasks: list[str] | None = None
    modules: list[str] | None = None
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
    # When set (and ``owner_username`` is not), scope the search to runs shared
    # with that user via a member grant. Same session-match verification as
    # ``owner_username`` — a caller may only query runs shared with themselves.
    shared_with_username: str | None = None


class SearchResult(BaseModel):
    """One row in the ranked list view.

    ``relevance`` is the cosine similarity (``1 - distance``) when the
    request is ranked by relevance; ``null`` for date ranking.
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
    # Which dispatch branch the gateway took: BM25-ranked or ILIKE-matched.
    search_type: Literal["lexical", "bm25"] | None = None


class SearchLogRequest(BaseModel):
    """Carry one explicitly committed public-corpus query."""

    query: str


class PopularQuery(BaseModel):
    """Represent one frequently used public-corpus query."""

    query: str
    count: int


class PopularQueriesResponse(BaseModel):
    """Envelope for recent popular public-corpus queries."""

    queries: list[PopularQuery]


def create_dashboard_router(*, job_store: Any) -> APIRouter:
    """Build the authenticated Explorer router.

    Args:
        job_store: Backing job store used to search accessible optimizations.

    Returns:
        A configured :class:`APIRouter` exposing facets and search routes.
    """
    router = APIRouter()

    @router.get(
        "/dashboard/public",
        response_model=PublicDashboardResponse,
        status_code=200,
        summary="Authenticated deployment-wide corpus",
    )
    def public_dashboard(current_user: AuthenticatedUserDep) -> PublicDashboardResponse:
        """Return runs that owners explicitly published inside the deployment.

        Args:
            current_user: Authenticated account permitted to use Explorer.

        Returns:
            Published corpus points.
        """
        del current_user
        data = fetch_public_dashboard(job_store=job_store)
        return PublicDashboardResponse(
            points=[PublicDashboardPoint(**point) for point in data["points"]]
        )

    @router.get(
        "/dashboard/facets",
        response_model=FacetsResponse,
        status_code=200,
        summary="Filter options with contextual run counts for one corpus scope",
    )
    def corpus_facets(
        current_user: AuthenticatedUserDep,
        owner_username: str | None = None,
        shared_with_username: str | None = None,
        models: Annotated[list[str] | None, Query()] = None,
        optimizers: Annotated[list[str] | None, Query()] = None,
        optimization_types: Annotated[list[str] | None, Query()] = None,
        modules: Annotated[list[str] | None, Query()] = None,
        date_from: date | None = None,
        date_to: date | None = None,
        q: str | None = None,
        limit: Annotated[int, Query(ge=1, le=FACET_LIMIT_MAX)] = FACET_LIMIT_DEFAULT,
        dim: Literal["models", "optimizers", "modules", "types"] | None = None,
    ) -> FacetsResponse:
        """Busiest filter values with contextual run counts for the requested corpus.

        Lets each /explore tab list options drawn from its own scope rather
        than the published corpus. The active filters are passed back in so
        every option's count reflects the other dimensions' selections (the
        same conjunctive semantics ``/dashboard/search`` applies). Scope is
        resolved with the same session-match check as ``/dashboard/search``:
        a caller may only ask for their own (mine) or shared-with-them options.

        Args:
            current_user: Authenticated caller.
            owner_username: When set, scope to the caller's own jobs.
            shared_with_username: When set (and ``owner_username`` is not),
                scope to jobs shared with the caller.
            models: Active model filter (repeatable query param).
            optimizers: Active optimizer filter.
            optimization_types: Active run-type filter.
            modules: Active DSPy module filter.
            date_from: Inclusive lower bound on ``created_at``.
            date_to: Inclusive upper bound on ``created_at``.
            q: Optional case-insensitive substring to match values against
                (the picker's value search).
            limit: Maximum values returned per dimension.
            dim: Restrict the work to one dimension — the one whose picker is
                open; the others come back empty.

        Returns:
            A :class:`FacetsResponse` with the top values, counts, and
            per-dimension totals for the scope.

        Raises:
            HTTPException: When a scope is set but the request is
                unauthenticated or targets a different user than the session.
        """
        resolved_owner = _resolve_owner_username(owner_username, current_user)
        resolved_shared = (
            None
            if resolved_owner is not None
            else _resolve_owner_username(shared_with_username, current_user)
        )
        data = fetch_corpus_facets(
            job_store=job_store,
            owner_username=resolved_owner,
            shared_with_username=resolved_shared,
            models=models,
            optimizers=optimizers,
            optimization_types=optimization_types,
            modules=modules,
            date_from=date_from,
            date_to=date_to,
            value_query=q,
            limit=limit,
            dimension=dim,
        )
        return FacetsResponse(
            models=[FacetOption(**o) for o in data["models"]],
            optimizers=[FacetOption(**o) for o in data["optimizers"]],
            modules=[FacetOption(**o) for o in data["modules"]],
            types=[FacetOption(**o) for o in data["types"]],
            totals=FacetTotals(**data["totals"]),
        )

    @router.post(
        "/dashboard/search",
        response_model=SearchResponse,
        status_code=200,
        summary="Text + structured search across optimizations",
        tags=["agent"],
    )
    def public_search(
        request: SearchRequest,
        current_user: AuthenticatedUserDep,
    ) -> SearchResponse:
        """Rank jobs by BM25 relevance when available, else match them lexically.

        Args:
            request: The query, filters, sort, and paging parameters.
            current_user: Authenticated caller.

        Returns:
            Ranked page plus the full matched-id set for explore-page dimming.

        Raises:
            HTTPException: When ``owner_username`` is set but the request is
                unauthenticated or targets a different user than the session.
        """
        sort = request.sort if request.sort in SEARCH_SORTS else SEARCH_SORT_RELEVANCE
        owner_username = _resolve_owner_username(request.owner_username, current_user)
        shared_with_username = (
            None
            if owner_username is not None
            else _resolve_owner_username(request.shared_with_username, current_user)
        )
        data = search_optimizations(
            job_store=job_store,
            query=request.query,
            models=request.models,
            optimizers=request.optimizers,
            optimization_types=request.optimization_types,
            tasks=request.tasks,
            modules=request.modules,
            date_from=request.date_from,
            date_to=request.date_to,
            sort=sort,
            page=request.page,
            size=request.size,
            owner_username=owner_username,
            shared_with_username=shared_with_username,
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
        summary="Record an explicitly committed public-corpus query",
    )
    def log_search_query(
        request: SearchLogRequest,
        current_user: AuthenticatedUserDep,
    ) -> None:
        """Record a deliberate public-corpus search for local trend analysis.

        Args:
            request: Committed query.
            current_user: Authenticated caller.
        """
        del current_user
        record_public_search_query(job_store, request.query)

    @router.get(
        "/dashboard/search/popular",
        response_model=PopularQueriesResponse,
        status_code=200,
        summary="Popular authenticated public-corpus queries",
    )
    def popular_searches(current_user: AuthenticatedUserDep) -> PopularQueriesResponse:
        """Return frequently committed searches within this deployment.

        Args:
            current_user: Authenticated caller.

        Returns:
            Popular queries ordered by occurrence count.
        """
        del current_user
        rows = fetch_popular_queries(
            job_store=job_store,
            limit=POPULAR_QUERIES_LIMIT_DEFAULT,
        )
        return PopularQueriesResponse(queries=[PopularQuery(**row) for row in rows])

    return router


def _resolve_owner_username(
    requested: str | None, user: AuthenticatedUser
) -> str | None:
    """Verify a requested user-scope matches the authenticated session.

    Backs both the ``owner_username`` (mine) and ``shared_with_username``
    (shared-with-me) scopes: a caller may only ask for runs scoped to their
    own session, so the requested username must equal the authenticated user.

    Args:
        requested: The requested scope username from the request body.
        user: Authenticated caller whose identity bounds the scope.

    Returns:
        The trusted username to forward to the gateway, or ``None``.

    Raises:
        HTTPException: 401 when authentication is missing or invalid; 403 when
            the authenticated user does not match the requested owner.
    """
    if requested is None:
        return None
    normalized = requested.strip().lower()
    if not normalized:
        return None
    if normalized != user.username:
        raise HTTPException(status_code=403, detail="auth.owner_mismatch")
    return normalized
