"""Routes for dashboard analytics and per-model / per-optimizer aggregation. [INTERNAL]

All endpoints are hidden from the public Scalar reference (none are in
``_SCALAR_PUBLIC_PATHS``). They power the in-app analytics dashboard
only — a public dev re-implementing them client-side from /optimizations
is more reliable than depending on the aggregation shapes we ship today.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from statistics import median
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ...constants import (
    COMPOSITION_WORKFLOW,
    OPTIMIZATION_TYPE_GRID_SEARCH,
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_DATASET_ROWS,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
    PAYLOAD_OVERVIEW_TOTAL_PAIRS,
)
from ...i18n import t
from ...models import (
    AnalyticsSummaryResponse,
    DashboardAnalyticsJob,
    DashboardAnalyticsModelStat,
    DashboardAnalyticsNameValue,
    DashboardAnalyticsOptimizerStat,
    DashboardAnalyticsRangeBucket,
    DashboardAnalyticsResponse,
    DashboardAnalyticsTimelineBucket,
    ModelStatsItem,
    ModelStatsResponse,
    OptimizationSummaryResponse,
    OptimizerStatsItem,
    OptimizerStatsResponse,
)
from ...models.common import OptimizationStatus
from ..auth import AuthenticatedUser, get_authenticated_user, is_admin
from ..converters import parse_overview
from ._helpers import build_summary, grant_roles_for

logger = logging.getLogger(__name__)

AuthenticatedUserDep = Annotated[AuthenticatedUser, Depends(get_authenticated_user)]


def _scope_analytics_username(current_user: AuthenticatedUser, requested: str | None) -> str | None:
    """Resolve the username an analytics aggregation may read.

    Non-admins are confined to their own runs: a missing or self-matching
    ``requested`` resolves to their own username, and any other value is refused
    so the aggregation can't leak another user's KPIs. Admins keep the
    cross-user view — ``None`` aggregates across everyone, an explicit username
    scopes to that user.

    Args:
        current_user: The authenticated caller.
        requested: Client-supplied ``username`` query param.

    Returns:
        The trusted username to forward to the store, or None to aggregate
        across all users (admins only).

    Raises:
        HTTPException: 403 when a non-admin requests another user's stats.
    """
    normalized = (requested or "").strip().lower()
    if is_admin(current_user):
        return normalized or None
    if normalized and normalized != current_user.username:
        raise HTTPException(status_code=403, detail="auth.owner_mismatch")
    return current_user.username


def _summary_to_analytics_job(s: OptimizationSummaryResponse) -> DashboardAnalyticsJob:
    """Convert a dashboard summary to its compact analytics projection.

    Args:
        s: The optimization summary to project.

    Returns:
        A :class:`DashboardAnalyticsJob` populated from ``s``.
    """
    status_value = s.status.value if isinstance(s.status, OptimizationStatus) else str(s.status)
    created_at_str: str | None = None
    if s.created_at is not None:
        created_at_str = s.created_at.isoformat() if isinstance(s.created_at, datetime) else str(s.created_at)
    return DashboardAnalyticsJob(
        optimization_id=s.optimization_id,
        name=s.name,
        optimizer_name=s.optimizer_name,
        model_name=s.model_name,
        status=status_value,
        baseline_test_metric=s.baseline_test_metric,
        optimized_test_metric=s.optimized_test_metric,
        metric_improvement=s.metric_improvement,
        elapsed_seconds=s.elapsed_seconds,
        dataset_rows=s.dataset_rows,
        optimization_type=s.optimization_type,
        best_pair_label=s.best_pair_label,
        created_at=created_at_str,
    )


# Bucket edges for the dashboard histograms. Improvement is in percentage
# points, runtime in minutes, dataset size in rows; the first bucket is open
# below the first edge and the last is open above the final edge.
_IMPROVEMENT_EDGES_POINTS: tuple[float, ...] = (0.0, 5.0, 10.0, 20.0, 30.0)
_RUNTIME_EDGES_MINUTES: tuple[float, ...] = (1.0, 5.0, 15.0, 30.0, 60.0, 120.0)
_DATASET_ROW_EDGES: tuple[float, ...] = (50.0, 100.0, 250.0, 500.0, 1000.0)

# Timeline granularity thresholds (days between first and last run).
_TIMELINE_DAY_MAX_SPAN = 60
_TIMELINE_WEEK_MAX_SPAN = 400

# Job-type bucket for single runs whose program is a multi-node workflow;
# they share ``optimization_type == "run"`` with plain single-module runs.
_JOB_TYPE_WORKFLOW = "workflow"


def _improvement_points(value: float) -> float:
    """Normalize a raw metric delta to percentage points.

    Ratio-scale metrics (accuracy in ``0..1``) are scaled by 100 so they can
    be aggregated alongside metrics already expressed in points.

    Args:
        value: Raw ``optimized - baseline`` delta.

    Returns:
        The delta in percentage points.
    """
    return value * 100 if abs(value) <= 1 else value


def _job_type_key(summary: OptimizationSummaryResponse) -> str:
    """Return the dashboard job-type bucket for a run.

    Args:
        summary: The run's dashboard summary.

    Returns:
        The ``optimization_type``, except that single runs of a multi-node
        workflow program report :data:`_JOB_TYPE_WORKFLOW`.
    """
    job_type = summary.optimization_type or OPTIMIZATION_TYPE_RUN
    if job_type == OPTIMIZATION_TYPE_RUN and summary.composition == COMPOSITION_WORKFLOW:
        return _JOB_TYPE_WORKFLOW
    return job_type


def _in_bucket(value: float | None, lower: float | None, upper: float | None) -> bool:
    """Report whether ``value`` falls inside the half-open ``[lower, upper)`` range.

    Mirrors :func:`_range_buckets` so a histogram bar's edges can be echoed
    back as a filter and select exactly the runs that bar counted.

    Args:
        value: The measured value, or None when the run has no measurement.
        lower: Inclusive lower edge, or None for an open start.
        upper: Exclusive upper edge, or None for an open end.

    Returns:
        False when the value is missing or outside the range.
    """
    if value is None:
        return False
    if lower is not None and value < lower:
        return False
    return upper is None or value < upper


def _created_at_utc(value: datetime | str | None) -> datetime | None:
    """Coerce a summary's ``created_at`` to an aware UTC datetime.

    Args:
        value: The summary's ``created_at`` (datetime or ISO string).

    Returns:
        An aware UTC datetime, or None when the value is missing/unparseable.
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _range_buckets(
    samples: list[tuple[float, float | None]],
    edges: tuple[float, ...],
) -> list[DashboardAnalyticsRangeBucket]:
    """Bucket ``(value, improvement)`` samples into fixed ``[lower, upper)`` ranges.

    Args:
        samples: Pairs of the bucketed value and the run's improvement in
            points (None when the run has no improvement figure).
        edges: Ascending interior bucket edges.

    Returns:
        One bucket per range, open-ended at both extremes, in ascending order.
    """
    bounds: list[tuple[float | None, float | None]] = [(None, edges[0])]
    bounds.extend((edges[i], edges[i + 1]) for i in range(len(edges) - 1))
    bounds.append((edges[-1], None))
    buckets: list[DashboardAnalyticsRangeBucket] = []
    for lower, upper in bounds:
        members = [
            improvement
            for value, improvement in samples
            if (lower is None or value >= lower) and (upper is None or value < upper)
        ]
        improvements = [v for v in members if v is not None]
        buckets.append(
            DashboardAnalyticsRangeBucket(
                lower=lower,
                upper=upper,
                count=len(members),
                avg_improvement=round(sum(improvements) / len(improvements), 2) if improvements else None,
            )
        )
    return buckets


def _timeline_granularity(first: date_type, last: date_type) -> str:
    """Pick the coarsest timeline bucket that still shows a trend.

    Args:
        first: Earliest run date in the filtered set.
        last: Latest run date in the filtered set.

    Returns:
        ``"day"``, ``"week"`` or ``"month"``.
    """
    span_days = (last - first).days
    if span_days <= _TIMELINE_DAY_MAX_SPAN:
        return "day"
    if span_days <= _TIMELINE_WEEK_MAX_SPAN:
        return "week"
    return "month"


def _bucket_start(day: date_type, granularity: str) -> date_type:
    """Snap a date to the start of its timeline bucket.

    Args:
        day: Any calendar date.
        granularity: ``"day"``, ``"week"`` (ISO, Monday start) or ``"month"``.

    Returns:
        The first date of the bucket containing ``day``.
    """
    if granularity == "week":
        return day - timedelta(days=day.weekday())
    if granularity == "month":
        return day.replace(day=1)
    return day


def _next_bucket(start: date_type, granularity: str) -> date_type:
    """Return the start of the bucket following ``start``.

    Args:
        start: A bucket start date.
        granularity: ``"day"``, ``"week"`` or ``"month"``.

    Returns:
        The next bucket's start date.
    """
    if granularity == "week":
        return start + timedelta(days=7)
    if granularity == "month":
        return (start.replace(day=1) + timedelta(days=32)).replace(day=1)
    return start + timedelta(days=1)


def _build_timeline(
    dated: list[tuple[date_type, str]],
) -> tuple[list[DashboardAnalyticsTimelineBucket], str]:
    """Bucket runs by calendar period, filling empty periods with zeros.

    Args:
        dated: ``(created date, status)`` pairs for every filtered run.

    Returns:
        The contiguous bucket list and the granularity it was built at.
    """
    if not dated:
        return [], "day"
    first = min(day for day, _ in dated)
    last = max(day for day, _ in dated)
    granularity = _timeline_granularity(first, last)
    counts: dict[date_type, list[int]] = {}
    for day, status_value in dated:
        row = counts.setdefault(_bucket_start(day, granularity), [0, 0, 0])
        row[0] += 1
        if status_value == OptimizationStatus.success.value:
            row[1] += 1
        elif status_value == OptimizationStatus.failed.value:
            row[2] += 1
    timeline: list[DashboardAnalyticsTimelineBucket] = []
    cursor = _bucket_start(first, granularity)
    end = _bucket_start(last, granularity)
    while cursor <= end:
        total, ok, failed = counts.get(cursor, [0, 0, 0])
        timeline.append(
            DashboardAnalyticsTimelineBucket(
                date=cursor.isoformat(),
                count=total,
                success_count=ok,
                failed_count=failed,
            )
        )
        cursor = _next_bucket(cursor, granularity)
    return timeline, granularity


_ACTIVE_STATUSES = frozenset({"pending", "validating", "running"})
_TERMINAL_SUCCESS_OR_FAILED = frozenset({"success", "failed"})

# Hard cap on jobs scanned per analytics request. Past this size the
# response surfaces ``truncated=True`` so the frontend can warn the user
# the aggregation is incomplete.
_ANALYTICS_JOB_HARD_CAP = 10000

# Analytics KPIs may lag live runs by up to this long. The dashboard fires
# several of these endpoints per load and re-polls on its own cadence, so a
# short window collapses the repeated 10k-row scans without visibly stale
# numbers.
_ANALYTICS_CACHE_TTL_SECONDS = 30.0
# Bounded by distinct (scope, filter) combinations seen within one TTL; the
# cache is wiped rather than evicted piecemeal if it somehow exceeds this.
_ANALYTICS_SCAN_CACHE_MAX_KEYS = 256


def create_analytics_router(*, job_store) -> APIRouter:
    """Build the analytics router.

    Args:
        job_store: Backing job store used by the analytics aggregations.

    Returns:
        A configured :class:`APIRouter` with the analytics endpoints attached.
    """
    router = APIRouter()

    # Every analytics endpoint starts from the same up-to-10k-row job scan.
    # Cache the raw rows per (scan kind, resolved scope, status) for a short
    # TTL so one dashboard load hits the DB once instead of four times. The
    # cache is per-router (per job_store binding) and the rows are shared
    # across requests — aggregations must treat them as read-only.
    scan_cache: dict[tuple[Any, ...], tuple[float, list[dict[str, Any]]]] = {}
    scan_lock = threading.Lock()

    def cached_scan(
        key: tuple[Any, ...],
        run: Callable[[], list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """Return the cached job scan for ``key``, re-running it after the TTL.

        Args:
            key: Scan identity — scan kind, resolved username scope, status.
            run: Zero-arg callable issuing the store query on a miss.

        Returns:
            The cached or freshly fetched job rows (treat as read-only).
        """
        now = time.monotonic()
        with scan_lock:
            hit = scan_cache.get(key)
            if hit is not None and hit[0] > now:
                return hit[1]
        rows = run()
        with scan_lock:
            if len(scan_cache) >= _ANALYTICS_SCAN_CACHE_MAX_KEYS:
                scan_cache.clear()
            scan_cache[key] = (now + _ANALYTICS_CACHE_TTL_SECONDS, rows)
        return rows

    def kpi_job_scan(username: str | None, status: str | None) -> list[dict[str, Any]]:
        """Fetch (cached) the job rows the KPI rollups aggregate over.

        Prefers the store's skinny analytics scan, which prunes ``result``
        down to its scalar metrics inside the SELECT — the full blob (multi-MB
        per grid run) never reaches this process, so a 10k-row scan costs KBs
        instead of the cache holding hundreds of MB. Stores without the method
        (in-memory/test doubles) keep the plain list scan.

        Args:
            username: Resolved username scope (None aggregates across users).
            status: Optional status filter.

        Returns:
            The cached or freshly fetched job rows (treat as read-only).
        """
        skinny = getattr(job_store, "scan_jobs_for_analytics", None)

        def run() -> list[dict[str, Any]]:
            """Issue the store query on a cache miss."""
            if skinny is not None:
                return skinny(status=status, username=username, limit=_ANALYTICS_JOB_HARD_CAP)
            return job_store.list_jobs(
                status=status,
                username=username,
                limit=_ANALYTICS_JOB_HARD_CAP,
                offset=0,
                # These rollups read overview/result fields only — skip the
                # progress/log count-folding, whose IN(...) aggregate scans
                # cost real time at the 10k-row cap.
                with_counts=False,
            )

        return cached_scan(("list", username, status), run)

    @router.get(
        "/analytics/summary",
        response_model=AnalyticsSummaryResponse,
        summary="Dashboard KPIs across all optimizations",
        tags=["agent"],
    )
    def get_analytics_summary(
        current_user: AuthenticatedUserDep,
        optimizer: str | None = Query(default=None, description="Exact-match optimizer name (e.g. 'gepa')"),
        model: str | None = Query(
            default=None,
            description=("Exact-match model name, compared against the primary model used by the optimization"),
        ),
        status: str | None = Query(
            default=None, description="Optimization status filter: pending, running, success, failed, cancelled"
        ),
        username: str | None = Query(default=None, description="Only include optimizations submitted by this username"),
    ) -> AnalyticsSummaryResponse:
        """Return aggregated KPIs across optimizations.

        Caps at :data:`_ANALYTICS_JOB_HARD_CAP` jobs per request and surfaces
        ``truncated=True`` when the cap is hit. ``running_count`` folds in
        ``validating`` status. For grid searches the ``best_pair`` is used
        as the representative result.

        Args:
            optimizer: Exact-match optimizer name filter.
            model: Exact-match primary model name filter.
            status: Optimization status filter.
            username: Restrict to optimizations submitted by this user.
            current_user: The authenticated caller (scopes the aggregation).

        Returns:
            A populated :class:`AnalyticsSummaryResponse` envelope.
        """
        username = _scope_analytics_username(current_user, username)
        all_jobs = kpi_job_scan(username, status)
        truncated = len(all_jobs) >= _ANALYTICS_JOB_HARD_CAP

        filtered_jobs = []
        for job_data in all_jobs:
            overview = parse_overview(job_data)

            if optimizer and overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_NAME) != optimizer:
                continue

            if model and overview.get(PAYLOAD_OVERVIEW_MODEL_NAME) != model:
                continue

            filtered_jobs.append((job_data, overview))

        total = len(filtered_jobs)
        status_counts = {"success": 0, "failed": 0, "cancelled": 0, "pending": 0, "running": 0, "validating": 0}
        improvements = []
        runtimes = []
        total_dataset_rows = 0
        total_pairs = 0
        completed_pairs = 0
        failed_pairs = 0

        for job_data, overview in filtered_jobs:
            job_status = job_data.get("status", "pending")
            status_counts[job_status] = status_counts.get(job_status, 0) + 1

            rows = overview.get(PAYLOAD_OVERVIEW_DATASET_ROWS)
            if isinstance(rows, int):
                total_dataset_rows += rows

            optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)
            if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
                pairs = overview.get(PAYLOAD_OVERVIEW_TOTAL_PAIRS)
                if isinstance(pairs, int):
                    total_pairs += pairs

            if job_status != "success":
                continue

            result_data = job_data.get("result")
            if not result_data or not isinstance(result_data, dict):
                continue

            if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
                best_pair = result_data.get("best_pair")
                if isinstance(best_pair, dict):
                    baseline = best_pair.get("baseline_test_metric")
                    optimized = best_pair.get("optimized_test_metric")
                    if isinstance(baseline, (int, float)) and isinstance(optimized, (int, float)):
                        improvements.append(optimized - baseline)

                    runtime = best_pair.get("runtime_seconds")
                    if isinstance(runtime, (int, float)):
                        runtimes.append(runtime)

                comp = result_data.get("completed_pairs")
                fail = result_data.get("failed_pairs")
                if isinstance(comp, int):
                    completed_pairs += comp
                if isinstance(fail, int):
                    failed_pairs += fail
            else:
                baseline = result_data.get("baseline_test_metric")
                optimized = result_data.get("optimized_test_metric")
                if isinstance(baseline, (int, float)) and isinstance(optimized, (int, float)):
                    improvements.append(optimized - baseline)

                runtime = result_data.get("runtime_seconds")
                if isinstance(runtime, (int, float)):
                    runtimes.append(runtime)

        success_count = status_counts["success"]
        success_rate = (success_count / total) if total > 0 else 0.0
        avg_improvement = (sum(improvements) / len(improvements)) if improvements else None
        max_improvement = max(improvements) if improvements else None
        min_improvement = min(improvements) if improvements else None
        avg_runtime = (sum(runtimes) / len(runtimes)) if runtimes else None

        return AnalyticsSummaryResponse(
            total_jobs=total,
            success_count=success_count,
            failed_count=status_counts["failed"],
            cancelled_count=status_counts["cancelled"],
            pending_count=status_counts["pending"],
            running_count=status_counts.get("running", 0) + status_counts.get("validating", 0),
            success_rate=round(success_rate, 4),
            avg_improvement=round(avg_improvement, 6) if avg_improvement is not None else None,
            max_improvement=round(max_improvement, 6) if max_improvement is not None else None,
            min_improvement=round(min_improvement, 6) if min_improvement is not None else None,
            avg_runtime=round(avg_runtime, 2) if avg_runtime is not None else None,
            total_dataset_rows=total_dataset_rows,
            total_pairs=total_pairs,
            completed_pairs=completed_pairs,
            failed_pairs=failed_pairs,
            truncated=truncated,
        )

    @router.get(
        "/analytics/optimizers",
        response_model=OptimizerStatsResponse,
        summary="Per-optimizer aggregated statistics",
        tags=["agent"],
    )
    def get_optimizer_stats(
        current_user: AuthenticatedUserDep,
        model: str | None = Query(
            default=None, description="Exact-match model name to scope the stats to a single model"
        ),
        status: str | None = Query(default=None, description="Restrict aggregation to a single status bucket"),
        username: str | None = Query(default=None, description="Only include jobs submitted by this username"),
    ) -> OptimizerStatsResponse:
        """Return per-optimizer aggregated statistics.

        Rows sorted by ``total_jobs`` descending. Jobs without an optimizer
        name are excluded.

        Args:
            model: Exact-match model name filter.
            status: Restrict aggregation to a single status bucket.
            username: Only include jobs submitted by this user.
            current_user: The authenticated caller (scopes the aggregation).

        Returns:
            A populated :class:`OptimizerStatsResponse` envelope.
        """
        username = _scope_analytics_username(current_user, username)
        all_jobs = kpi_job_scan(username, status)
        truncated = len(all_jobs) >= _ANALYTICS_JOB_HARD_CAP

        # optimizer_name -> {total, success, improvements, runtimes}
        optimizer_data: dict[str, dict[str, Any]] = {}

        for job_data in all_jobs:
            overview = parse_overview(job_data)

            if model and overview.get(PAYLOAD_OVERVIEW_MODEL_NAME) != model:
                continue

            optimizer_name = overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_NAME)
            if not optimizer_name:
                continue

            if optimizer_name not in optimizer_data:
                optimizer_data[optimizer_name] = {
                    "total": 0,
                    "success": 0,
                    "improvements": [],
                    "runtimes": [],
                }

            stats = optimizer_data[optimizer_name]
            stats["total"] += 1

            job_status = job_data.get("status", "pending")
            if job_status == "success":
                stats["success"] += 1

                result_data = job_data.get("result")
                if result_data and isinstance(result_data, dict):
                    optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)

                    if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
                        best_pair = result_data.get("best_pair")
                        if isinstance(best_pair, dict):
                            baseline = best_pair.get("baseline_test_metric")
                            optimized = best_pair.get("optimized_test_metric")
                            if isinstance(baseline, (int, float)) and isinstance(optimized, (int, float)):
                                stats["improvements"].append(optimized - baseline)

                            runtime = best_pair.get("runtime_seconds")
                            if isinstance(runtime, (int, float)):
                                stats["runtimes"].append(runtime)
                    else:
                        baseline = result_data.get("baseline_test_metric")
                        optimized = result_data.get("optimized_test_metric")
                        if isinstance(baseline, (int, float)) and isinstance(optimized, (int, float)):
                            stats["improvements"].append(optimized - baseline)

                        runtime = result_data.get("runtime_seconds")
                        if isinstance(runtime, (int, float)):
                            stats["runtimes"].append(runtime)

        items: list[OptimizerStatsItem] = []
        for optimizer_name, stats in optimizer_data.items():
            total = int(stats["total"])
            success_count = int(stats["success"])
            success_rate = (success_count / total) if total > 0 else 0.0
            improvements_list: list[float] = stats["improvements"]
            runtimes_list: list[float] = stats["runtimes"]
            avg_improvement = sum(improvements_list) / len(improvements_list) if improvements_list else None
            avg_runtime = sum(runtimes_list) / len(runtimes_list) if runtimes_list else None

            items.append(
                OptimizerStatsItem(
                    name=optimizer_name,
                    total_jobs=total,
                    success_count=success_count,
                    avg_improvement=round(avg_improvement, 6) if avg_improvement is not None else None,
                    success_rate=round(success_rate, 4),
                    avg_runtime=round(avg_runtime, 2) if avg_runtime is not None else None,
                )
            )

        items.sort(key=lambda x: x.total_jobs, reverse=True)

        return OptimizerStatsResponse(items=items, truncated=truncated)

    @router.get(
        "/analytics/models",
        response_model=ModelStatsResponse,
        summary="Per-model aggregated statistics",
        tags=["agent"],
    )
    def get_model_stats(
        current_user: AuthenticatedUserDep,
        optimizer: str | None = Query(default=None, description="Exact-match optimizer name to scope the stats"),
        status: str | None = Query(default=None, description="Restrict aggregation to a single status bucket"),
        username: str | None = Query(default=None, description="Only include jobs submitted by this username"),
    ) -> ModelStatsResponse:
        """Return per-model aggregated statistics.

        Rows sorted by ``use_count`` descending. Jobs without a declared
        model are excluded.

        Args:
            optimizer: Exact-match optimizer name filter.
            status: Restrict aggregation to a single status bucket.
            username: Only include jobs submitted by this user.
            current_user: The authenticated caller (scopes the aggregation).

        Returns:
            A populated :class:`ModelStatsResponse` envelope.
        """
        username = _scope_analytics_username(current_user, username)
        all_jobs = kpi_job_scan(username, status)
        truncated = len(all_jobs) >= _ANALYTICS_JOB_HARD_CAP

        # model_name -> {total, success, improvements, use_count}
        model_data: dict[str, dict[str, Any]] = {}

        for job_data in all_jobs:
            overview = parse_overview(job_data)

            if optimizer and overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_NAME) != optimizer:
                continue

            model_name = overview.get(PAYLOAD_OVERVIEW_MODEL_NAME)
            if not model_name:
                continue

            if model_name not in model_data:
                model_data[model_name] = {
                    "total": 0,
                    "success": 0,
                    "improvements": [],
                    "use_count": 0,
                }

            stats = model_data[model_name]
            stats["total"] += 1
            stats["use_count"] += 1

            job_status = job_data.get("status", "pending")
            if job_status == "success":
                stats["success"] += 1

                result_data = job_data.get("result")
                if result_data and isinstance(result_data, dict):
                    optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)

                    if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
                        best_pair = result_data.get("best_pair")
                        if isinstance(best_pair, dict):
                            baseline = best_pair.get("baseline_test_metric")
                            optimized = best_pair.get("optimized_test_metric")
                            if isinstance(baseline, (int, float)) and isinstance(optimized, (int, float)):
                                stats["improvements"].append(optimized - baseline)
                    else:
                        baseline = result_data.get("baseline_test_metric")
                        optimized = result_data.get("optimized_test_metric")
                        if isinstance(baseline, (int, float)) and isinstance(optimized, (int, float)):
                            stats["improvements"].append(optimized - baseline)

        model_items: list[ModelStatsItem] = []
        for model_name, stats in model_data.items():
            total = int(stats["total"])
            success_count = int(stats["success"])
            success_rate = (success_count / total) if total > 0 else 0.0
            improvements_list = stats["improvements"]
            avg_improvement = sum(improvements_list) / len(improvements_list) if improvements_list else None

            model_items.append(
                ModelStatsItem(
                    name=model_name,
                    total_jobs=total,
                    success_count=success_count,
                    avg_improvement=round(avg_improvement, 6) if avg_improvement is not None else None,
                    success_rate=round(success_rate, 4),
                    use_count=int(stats["use_count"]),
                )
            )

        model_items.sort(key=lambda x: x.use_count, reverse=True)

        return ModelStatsResponse(items=model_items, truncated=truncated)

    @router.get(
        "/analytics/dashboard",
        response_model=DashboardAnalyticsResponse,
        summary="Full pre-shaped dashboard analytics payload",
    )
    def get_dashboard_analytics(
        current_user: AuthenticatedUserDep,
        optimizer: str | None = Query(default=None, description="Exact-match optimizer name filter"),
        model: str | None = Query(default=None, description="Exact-match primary model name filter"),
        status: str | None = Query(default=None, description="Optimization status filter"),
        username: str | None = Query(default=None, description="Only include optimizations owned by this user"),
        optimization_id: str | None = Query(default=None, description="Limit the aggregation to a single optimization"),
        date: str | None = Query(default=None, description="YYYY-MM-DD day filter on created_at"),
        date_to: str | None = Query(
            default=None,
            description="YYYY-MM-DD inclusive end of a created_at range that starts at `date`",
        ),
        days: int | None = Query(
            default=None,
            ge=1,
            le=3650,
            description="Only include optimizations created within the last N days",
        ),
        include_shared: bool = Query(
            default=False,
            description="Fold runs shared with `username` into the aggregation (Drive-style sharing).",
        ),
        owner: str | None = Query(default=None, description="Restrict the aggregation to runs owned by this username"),
        access: str | None = Query(
            default=None,
            description="Restrict to a caller access tier: 'mine', 'owner', 'editor', or 'viewer'.",
        ),
        job_type: str | None = Query(
            default=None,
            description="Job-type bucket filter: 'run', 'grid_search' or 'workflow'.",
        ),
        module: str | None = Query(default=None, description="Exact-match module name filter"),
        improvement_min: float | None = Query(
            default=None, description="Inclusive lower bound on improvement, in percentage points"
        ),
        improvement_max: float | None = Query(
            default=None, description="Exclusive upper bound on improvement, in percentage points"
        ),
        runtime_min: float | None = Query(
            default=None, ge=0, description="Inclusive lower bound on run time, in minutes"
        ),
        runtime_max: float | None = Query(
            default=None, ge=0, description="Exclusive upper bound on run time, in minutes"
        ),
        dataset_min: float | None = Query(default=None, ge=0, description="Inclusive lower bound on dataset rows"),
        dataset_max: float | None = Query(default=None, ge=0, description="Exclusive upper bound on dataset rows"),
    ) -> DashboardAnalyticsResponse:
        """Return a pre-shaped payload for the whole analytics dashboard.

        Caps at :data:`_ANALYTICS_JOB_HARD_CAP` jobs per request and surfaces
        ``truncated=True`` when the cap is hit. Improvement aggregates are in
        percentage points (see :func:`_improvement_points`); the per-job
        ``metric_improvement`` on the leaderboard stays raw. When
        ``include_shared`` is set the job set is the union of ``username``'s
        owned and shared-with-them runs; ``owner`` then narrows the
        aggregation to a single owner within that set (powering the "by
        owner" breakdown's click-through).

        Args:
            optimizer: Exact-match optimizer name filter.
            model: Exact-match primary model name filter.
            status: Optimization status filter.
            username: Only include optimizations owned by this user.
            optimization_id: Limit the aggregation to a single optimization.
            date: ``YYYY-MM-DD`` day filter on ``created_at``, or the range
                start when ``date_to`` is given.
            date_to: Inclusive ``YYYY-MM-DD`` end of the ``created_at`` range.
            days: Only include runs created within the last ``days`` days.
            include_shared: Union in runs shared with ``username``.
            owner: Restrict the aggregation to runs owned by this username.
            access: Restrict to a caller access tier (mine/owner/editor/viewer).
            job_type: Restrict to one job-type bucket (run/grid_search/workflow).
            module: Exact-match module name filter.
            improvement_min: Inclusive lower bound on improvement (points).
            improvement_max: Exclusive upper bound on improvement (points).
            runtime_min: Inclusive lower bound on run time (minutes).
            runtime_max: Exclusive upper bound on run time (minutes).
            dataset_min: Inclusive lower bound on dataset rows.
            dataset_max: Exclusive upper bound on dataset rows.
            current_user: The authenticated caller (scopes the aggregation).

        Returns:
            A populated :class:`DashboardAnalyticsResponse` envelope.
        """
        username = _scope_analytics_username(current_user, username)
        if include_shared and username and hasattr(job_store, "list_jobs_visible_to"):
            all_jobs_raw = cached_scan(
                ("visible", username, status),
                lambda: job_store.list_jobs_visible_to(
                    username,
                    status=status,
                    limit=_ANALYTICS_JOB_HARD_CAP,
                    offset=0,
                    with_counts=False,
                ),
            )
        else:
            all_jobs_raw = cached_scan(
                ("dashboard_list", username, status),
                lambda: job_store.list_jobs(
                    status=status,
                    username=username,
                    limit=_ANALYTICS_JOB_HARD_CAP,
                    offset=0,
                    with_counts=False,
                ),
            )
        truncated = len(all_jobs_raw) >= _ANALYTICS_JOB_HARD_CAP
        since = datetime.now(UTC) - timedelta(days=days) if days else None

        # Build summaries up front so every downstream filter and
        # aggregation works against the same view the dashboard would
        # receive from /optimizations.
        summaries: list = []
        available_optimizers: set[str] = set()
        available_models: set[str] = set()
        for job_data in all_jobs_raw:
            try:
                summary = build_summary(job_data)
            except Exception:
                # Isolation boundary: skip unparseable job rows so one bad row
                # can't break the dashboard. Log so silent corruption is visible.
                logger.warning(
                    "analytics dashboard skipped unparseable job %s",
                    job_data.get("optimization_id", "<unknown>"),
                    exc_info=True,
                )
                continue
            if summary.optimizer_name:
                available_optimizers.add(summary.optimizer_name)
            if summary.model_name:
                available_models.add(summary.model_name)
            if optimizer and summary.optimizer_name != optimizer:
                continue
            if model and summary.model_name != model:
                continue
            if owner and (summary.username or "") != owner:
                continue
            if optimization_id and summary.optimization_id != optimization_id:
                continue
            if job_type and _job_type_key(summary) != job_type:
                continue
            if module and summary.module_name != module:
                continue
            if (improvement_min is not None or improvement_max is not None) and not _in_bucket(
                None if summary.metric_improvement is None else _improvement_points(summary.metric_improvement),
                improvement_min,
                improvement_max,
            ):
                continue
            if (runtime_min is not None or runtime_max is not None) and not _in_bucket(
                None if summary.elapsed_seconds is None else summary.elapsed_seconds / 60.0,
                runtime_min,
                runtime_max,
            ):
                continue
            if (dataset_min is not None or dataset_max is not None) and not _in_bucket(
                float(summary.dataset_rows) if summary.dataset_rows else None,
                dataset_min,
                dataset_max,
            ):
                continue
            if date or date_to or since:
                created = _created_at_utc(summary.created_at)
                if created is None:
                    continue
                day = created.date().isoformat()
                if date and (day < date if date_to else day != date):
                    continue
                if date_to and day > date_to:
                    continue
                if since and created < since:
                    continue
            summaries.append(summary)

        # Resolve each run's access tier for the caller so the dashboard can
        # break down and filter by "mine vs shared vs grant tier". Owned runs
        # are "mine"; the rest carry their grant role. Needs a caller identity
        # (``username``); admin/all-user views have no per-caller tier.
        access_by_id: dict[str, str] = {}
        if username:
            caller_norm = username.strip().lower()
            grant_roles = grant_roles_for(job_store, [s.optimization_id for s in summaries], caller_norm)
            for s in summaries:
                owner_name = (s.username or "").strip().lower()
                access_by_id[s.optimization_id] = (
                    "mine" if owner_name == caller_norm else grant_roles.get(s.optimization_id, "")
                )
            if access:
                summaries = [s for s in summaries if access_by_id.get(s.optimization_id) == access]

        filtered_total = len(summaries)

        status_counts: dict[str, int] = {}
        for s in summaries:
            key = s.status.value if isinstance(s.status, OptimizationStatus) else str(s.status)
            status_counts[key] = status_counts.get(key, 0) + 1

        success_items = [s for s in summaries if s.status == OptimizationStatus.success]
        failed_items = [s for s in summaries if s.status == OptimizationStatus.failed]
        running_count = sum(1 for s in summaries if s.status in _ACTIVE_STATUSES)
        success_count = len(success_items)
        failed_count = len(failed_items)
        terminal_count = sum(1 for s in summaries if s.status in _TERMINAL_SUCCESS_OR_FAILED)

        optimizer_counts: dict[str, int] = {}
        job_type_counts: dict[str, int] = {}
        module_counts: dict[str, int] = {}
        total_dataset_rows = 0
        total_pairs_run = 0
        grid_search_count = 0
        single_run_count = 0
        for s in summaries:
            opt = s.optimizer_name or t("analytics.other_bucket")
            optimizer_counts[opt] = optimizer_counts.get(opt, 0) + 1
            type_key = _job_type_key(s)
            job_type_counts[type_key] = job_type_counts.get(type_key, 0) + 1
            if s.module_name:
                module_counts[s.module_name] = module_counts.get(s.module_name, 0) + 1
            if s.dataset_rows:
                total_dataset_rows += s.dataset_rows
            if s.optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
                grid_search_count += 1
                if s.total_pairs:
                    total_pairs_run += s.total_pairs
            else:
                single_run_count += 1
                total_pairs_run += 1

        owner_counter: Counter = Counter()
        for s in summaries:
            if s.username:
                owner_counter[s.username] += 1
        owner_usage = [
            DashboardAnalyticsNameValue(name=name, value=count) for name, count in owner_counter.most_common(8)
        ]

        access_counter: Counter = Counter()
        for s in summaries:
            tier = access_by_id.get(s.optimization_id)
            if tier:
                access_counter[tier] += 1
        access_usage = [
            DashboardAnalyticsNameValue(name=name, value=count) for name, count in access_counter.most_common()
        ]

        points_by_id = {
            s.optimization_id: _improvement_points(s.metric_improvement)
            for s in success_items
            if s.metric_improvement is not None
        }
        improvement_points = list(points_by_id.values())
        avg_improvement = sum(improvement_points) / len(improvement_points) if improvement_points else None
        median_improvement = median(improvement_points) if improvement_points else None
        best_improvement = max(improvement_points) if improvement_points else None
        success_rate = (success_count / terminal_count) if terminal_count else 0.0

        runtimes = [s.elapsed_seconds for s in success_items if s.elapsed_seconds is not None]
        avg_runtime_seconds = (sum(runtimes) / len(runtimes)) if runtimes else None

        improvement_histogram = _range_buckets([(v, v) for v in improvement_points], _IMPROVEMENT_EDGES_POINTS)
        runtime_histogram = _range_buckets(
            [
                (s.elapsed_seconds / 60.0, points_by_id.get(s.optimization_id))
                for s in success_items
                if s.elapsed_seconds is not None
            ],
            _RUNTIME_EDGES_MINUTES,
        )
        dataset_size_buckets = _range_buckets(
            [(float(s.dataset_rows), points_by_id.get(s.optimization_id)) for s in success_items if s.dataset_rows],
            _DATASET_ROW_EDGES,
        )

        def _model_key(s: OptimizationSummaryResponse) -> str | None:
            """Return the run's primary model, falling back to the grid's best pair.

            Args:
                s: The optimization summary.

            Returns:
                The model name, or None when the run recorded none.
            """
            if s.model_name:
                return s.model_name
            return s.best_pair_label.split(" + ")[0] if s.best_pair_label else None

        def _group_stats(key_of: Callable[[OptimizationSummaryResponse], str | None]) -> dict[str, dict[str, Any]]:
            """Roll the filtered runs up by ``key_of`` for the comparison tables.

            Args:
                key_of: Extracts the grouping key (optimizer / model) from a run.

            Returns:
                Per-key counts, success/terminal tallies and success-only
                improvement/runtime samples, in first-seen order.
            """
            groups: dict[str, dict[str, Any]] = {}
            for s in summaries:
                key = key_of(s)
                if not key:
                    continue
                g = groups.setdefault(
                    key, {"count": 0, "success": 0, "terminal": 0, "improvements": [], "runtimes": []}
                )
                g["count"] += 1
                if s.status in _TERMINAL_SUCCESS_OR_FAILED:
                    g["terminal"] += 1
                if s.status != OptimizationStatus.success:
                    continue
                g["success"] += 1
                if s.optimization_id in points_by_id:
                    g["improvements"].append(points_by_id[s.optimization_id])
                if s.elapsed_seconds is not None:
                    g["runtimes"].append(s.elapsed_seconds)
            return groups

        optimizer_stats = [
            DashboardAnalyticsOptimizerStat(
                name=name,
                count=g["count"],
                success_count=g["success"],
                success_rate=round(g["success"] / g["terminal"], 4) if g["terminal"] else 0.0,
                avg_improvement=round(sum(g["improvements"]) / len(g["improvements"]), 2)
                if g["improvements"]
                else None,
                avg_runtime_minutes=round(sum(g["runtimes"]) / len(g["runtimes"]) / 60.0, 2) if g["runtimes"] else None,
            )
            for name, g in sorted(_group_stats(lambda s: s.optimizer_name).items(), key=lambda kv: -kv[1]["count"])
        ]
        model_stats = [
            DashboardAnalyticsModelStat(
                name=name,
                count=g["count"],
                success_count=g["success"],
                success_rate=round(g["success"] / g["terminal"], 4) if g["terminal"] else 0.0,
                avg_improvement=round(sum(g["improvements"]) / len(g["improvements"]), 2)
                if g["improvements"]
                else None,
            )
            for name, g in sorted(_group_stats(_model_key).items(), key=lambda kv: -kv[1]["count"])[:12]
        ]

        ranked = sorted(
            (s for s in success_items if s.optimization_id in points_by_id),
            key=lambda s: points_by_id[s.optimization_id],
            reverse=True,
        )
        top_jobs_by_improvement = [_summary_to_analytics_job(s) for s in ranked[:10]]

        dated: list[tuple[date_type, str]] = []
        for s in summaries:
            created = _created_at_utc(s.created_at)
            if created is None:
                continue
            status_value = s.status.value if isinstance(s.status, OptimizationStatus) else str(s.status)
            dated.append((created.date(), status_value))
        timeline, timeline_granularity = _build_timeline(dated)

        return DashboardAnalyticsResponse(
            filtered_total=filtered_total,
            status_counts=status_counts,
            optimizer_counts=optimizer_counts,
            job_type_counts=job_type_counts,
            owner_usage=owner_usage,
            access_usage=access_usage,
            module_counts=module_counts,
            success_count=success_count,
            failed_count=failed_count,
            running_count=running_count,
            terminal_count=terminal_count,
            success_rate=round(success_rate, 4),
            avg_improvement=round(avg_improvement, 2) if avg_improvement is not None else None,
            median_improvement=round(median_improvement, 2) if median_improvement is not None else None,
            best_improvement=round(best_improvement, 2) if best_improvement is not None else None,
            avg_runtime_seconds=round(avg_runtime_seconds, 2) if avg_runtime_seconds is not None else None,
            total_dataset_rows=total_dataset_rows,
            total_pairs_run=total_pairs_run,
            grid_search_count=grid_search_count,
            single_run_count=single_run_count,
            improvement_histogram=improvement_histogram,
            runtime_histogram=runtime_histogram,
            dataset_size_buckets=dataset_size_buckets,
            optimizer_stats=optimizer_stats,
            model_stats=model_stats,
            top_jobs_by_improvement=top_jobs_by_improvement,
            timeline=timeline,
            timeline_granularity=timeline_granularity,
            available_optimizers=sorted(available_optimizers),
            available_models=sorted(available_models),
            truncated=truncated,
        )

    return router
