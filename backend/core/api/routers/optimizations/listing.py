"""Cross-optimization read routes: list, counts, sidebar, compare."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from ....constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
    PAYLOAD_OVERVIEW_TOTAL_PAIRS,
    PAYLOAD_OVERVIEW_USERNAME,
)
from ....models import (
    OptimizationCountsResponse,
    PaginatedJobsResponse,
)
from ...converters import parse_overview, parse_timestamp, status_to_job_status
from ...errors import DomainError
from ...response_limits import AGENT_DEFAULT_LIST, AGENT_MAX_LIST, clamp_limit
from .._helpers import build_summary
from ..constants import VALID_OPTIMIZATION_TYPES, VALID_STATUSES
from .schemas import (
    CompareJobSnapshot,
    CompareJobsRequest,
    CompareJobsResponse,
    SidebarJobItem,
    SidebarJobsResponse,
)

logger = logging.getLogger(__name__)


def register_listing_routes(router: APIRouter, *, job_store) -> None:
    """Register cross-optimization read routes on ``router``.

    Args:
        router: The router to attach the listing routes to.
        job_store: Job-store the routes read from.
    """

    @router.get(
        "/optimizations",
        response_model=PaginatedJobsResponse,
        summary="List optimizations with filtering and pagination",
        tags=["agent"],
    )
    def list_jobs(
        status: str | None = Query(
            default=None,
            description="Exact-match status filter: pending, validating, running, success, failed, cancelled",
        ),
        username: str | None = Query(default=None, description="Only include optimizations submitted by this user"),
        optimization_type: str | None = Query(
            default=None, description="'run' (single optimization) or 'grid_search' (model-pair sweep)"
        ),
        limit: int = Query(
            default=AGENT_DEFAULT_LIST,
            ge=1,
            le=AGENT_MAX_LIST,
            description=(
                f"Page size (default {AGENT_DEFAULT_LIST}, ceiling {AGENT_MAX_LIST}). "
                "Paginate with offset — the agent context stays small that way."
            ),
        ),
        offset: int = Query(
            default=0,
            ge=0,
            description="Number of optimizations to skip before returning; combine with limit for stable pagination",
        ),
    ) -> PaginatedJobsResponse:
        """Return a page of optimizations ordered by ``created_at`` descending.

        Filters combine with AND. ``limit`` is clamped to keep agent responses
        context-safe; UI callers that genuinely need larger pages hit the
        dedicated ``/optimizations/sidebar`` route.

        Args:
            status: Optional exact-match status filter.
            username: Optional submitter filter.
            optimization_type: Optional ``"run"`` / ``"grid_search"`` filter.
            limit: Page size (clamped to ``AGENT_MAX_LIST``).
            offset: Number of optimizations to skip.

        Returns:
            A ``PaginatedJobsResponse`` carrying summaries and pagination
            counters.

        Raises:
            DomainError: 422 when ``status`` or ``optimization_type`` is
                outside its closed list.
        """
        if status is not None and status not in VALID_STATUSES:
            raise DomainError(
                "filter.invalid_status",
                status=422,
                value=status,
                allowed=sorted(VALID_STATUSES),
            )
        if optimization_type is not None and optimization_type not in VALID_OPTIMIZATION_TYPES:
            raise DomainError(
                "filter.invalid_optimization_type",
                status=422,
                value=optimization_type,
                allowed=sorted(VALID_OPTIMIZATION_TYPES),
            )
        resolved_limit = clamp_limit(limit)
        total = job_store.count_jobs(status=status, username=username, optimization_type=optimization_type)
        rows = job_store.list_jobs(
            status=status,
            username=username,
            optimization_type=optimization_type,
            limit=resolved_limit,
            offset=offset,
        )
        items = [build_summary(job_data) for job_data in rows]
        return PaginatedJobsResponse(items=items, total=total, limit=resolved_limit, offset=offset)

    @router.get(
        "/optimizations/counts",
        response_model=OptimizationCountsResponse,
        summary="Aggregate optimization counts grouped by status",
        tags=["agent"],
    )
    def get_optimization_counts(
        username: str | None = Query(default=None, description="Restrict counts to a single user"),
    ) -> OptimizationCountsResponse:
        """Return backend row counts grouped by status for dashboard stat cards.

        Args:
            username: Optional submitter filter.

        Returns:
            An ``OptimizationCountsResponse`` keyed by status.
        """
        total = job_store.count_jobs(username=username)
        return OptimizationCountsResponse(
            total=total,
            pending=job_store.count_jobs(status="pending", username=username),
            validating=job_store.count_jobs(status="validating", username=username),
            running=job_store.count_jobs(status="running", username=username),
            success=job_store.count_jobs(status="success", username=username),
            failed=job_store.count_jobs(status="failed", username=username),
            cancelled=job_store.count_jobs(status="cancelled", username=username),
        )

    @router.get(
        "/optimizations/sidebar",
        response_model=SidebarJobsResponse,
        summary="Compact optimization list tuned for sidebar navigation",
    )
    def list_jobs_sidebar(
        username: str | None = Query(default=None, description="Restrict the list to a single user's optimizations"),
        limit: int = Query(
            default=50,
            ge=1,
            le=200,
            description="Page size; capped at 200 because the sidebar only renders a finite slice",
        ),
        offset: int = Query(default=0, ge=0, description="Number of optimizations to skip before the returned slice"),
    ) -> SidebarJobsResponse:
        """Return minimal per-optimization fields for the sidebar navigation list.

        No result payload, metrics, logs, or progress. Newest-first; pin
        reordering is client-side.

        Args:
            username: Optional submitter filter.
            limit: Page size (clamped to 200).
            offset: Number of optimizations to skip.

        Returns:
            A ``SidebarJobsResponse`` carrying compact items and total count.
        """
        total = job_store.count_jobs(username=username)
        rows = job_store.list_jobs(username=username, limit=limit, offset=offset)
        items = []
        for row in rows:
            overview = parse_overview(row)
            items.append(
                SidebarJobItem(
                    optimization_id=row["optimization_id"],
                    status=row.get("status", "pending"),
                    name=overview.get(PAYLOAD_OVERVIEW_NAME),
                    module_name=overview.get(PAYLOAD_OVERVIEW_MODULE_NAME),
                    optimizer_name=overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_NAME),
                    model_name=overview.get(PAYLOAD_OVERVIEW_MODEL_NAME),
                    username=overview.get(PAYLOAD_OVERVIEW_USERNAME),
                    created_at=parse_timestamp(row.get("created_at")),
                    pinned=bool(overview.get("pinned", False)),
                    optimization_type=overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE),
                    total_pairs=overview.get(PAYLOAD_OVERVIEW_TOTAL_PAIRS),
                )
            )
        return SidebarJobsResponse(items=items, total=total)

    @router.post(
        "/optimizations/compare",
        response_model=CompareJobsResponse,
        summary="Compare 2–5 optimizations side-by-side",
        tags=["agent"],
    )
    def compare_jobs(req: CompareJobsRequest) -> CompareJobsResponse:
        """Return a compact side-by-side comparison of 2-5 optimizations.

        Reads each optimization's overview and metrics. Duplicate ids are
        deduplicated. Missing ids are returned under ``missing_optimization_ids``
        rather than raising 404.

        Args:
            req: The compare request body listing 2-5 optimization ids.

        Returns:
            A ``CompareJobsResponse`` carrying snapshots, differing fields,
            and missing ids.
        """
        snapshots: list[CompareJobSnapshot] = []
        missing: list[str] = []
        seen: set[str] = set()

        for oid in req.optimization_ids:
            if oid in seen:
                continue
            seen.add(oid)
            try:
                job_data = job_store.get_job(oid)
            except KeyError:
                missing.append(oid)
                continue

            overview = parse_overview(job_data)
            status = status_to_job_status(job_data.get("status", "pending"))
            optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)

            baseline: float | None = None
            optimized_metric: float | None = None
            result_data = job_data.get("result")
            if isinstance(result_data, dict):
                if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
                    best_pair = result_data.get("best_pair")
                    if isinstance(best_pair, dict):
                        baseline = best_pair.get("baseline_test_metric")
                        optimized_metric = best_pair.get("optimized_test_metric")
                else:
                    baseline = result_data.get("baseline_test_metric")
                    optimized_metric = result_data.get("optimized_test_metric")

            improvement = None
            if baseline is not None and optimized_metric is not None:
                improvement = round(optimized_metric - baseline, 6)

            snapshots.append(
                CompareJobSnapshot(
                    optimization_id=oid,
                    status=status.value,
                    name=overview.get(PAYLOAD_OVERVIEW_NAME),
                    optimization_type=optimization_type,
                    module_name=overview.get(PAYLOAD_OVERVIEW_MODULE_NAME),
                    optimizer_name=overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_NAME),
                    model_name=overview.get(PAYLOAD_OVERVIEW_MODEL_NAME),
                    dataset_rows=overview.get("dataset_rows"),
                    baseline_test_metric=baseline,
                    optimized_test_metric=optimized_metric,
                    metric_improvement=improvement,
                )
            )

        differing_fields: list[str] = []
        if len(snapshots) >= 2:
            candidate_fields = [
                "module_name",
                "optimizer_name",
                "model_name",
                "optimization_type",
                "dataset_rows",
            ]
            for field in candidate_fields:
                values = {getattr(s, field) for s in snapshots}
                if len(values) > 1:
                    differing_fields.append(field)

        return CompareJobsResponse(
            jobs=snapshots,
            differing_fields=differing_fields,
            missing_optimization_ids=missing,
        )
