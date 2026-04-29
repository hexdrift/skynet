"""Routes for dashboard analytics and per-model / per-optimizer aggregation."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from ...constants import (
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
    DashboardAnalyticsNameValue,
    DashboardAnalyticsOptimizerAverage,
    DashboardAnalyticsResponse,
    DashboardAnalyticsTimelineBucket,
    ModelStatsItem,
    ModelStatsResponse,
    OptimizationSummaryResponse,
    OptimizerStatsItem,
    OptimizerStatsResponse,
)
from ...models.common import OptimizationStatus
from ..converters import parse_overview
from ._helpers import build_summary

logger = logging.getLogger(__name__)


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


_ACTIVE_STATUSES = frozenset({"pending", "validating", "running"})
_TERMINAL_SUCCESS_OR_FAILED = frozenset({"success", "failed"})

# Hard cap on jobs scanned per analytics request. Past this size the
# response surfaces ``truncated=True`` so the frontend can warn the user
# the aggregation is incomplete.
_ANALYTICS_JOB_HARD_CAP = 10000


def create_analytics_router(*, job_store) -> APIRouter:
    """Build the analytics router.

    Args:
        job_store: Backing job store used by the analytics aggregations.

    Returns:
        A configured :class:`APIRouter` with the analytics endpoints attached.
    """
    router = APIRouter()

    @router.get(
        "/analytics/summary",
        response_model=AnalyticsSummaryResponse,
        summary="Dashboard KPIs across all optimizations",
        tags=["agent"],
    )
    def get_analytics_summary(
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

        Returns:
            A populated :class:`AnalyticsSummaryResponse` envelope.
        """
        all_jobs = job_store.list_jobs(
            status=status,
            username=username,
            limit=_ANALYTICS_JOB_HARD_CAP,
            offset=0,
        )
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

        Returns:
            A populated :class:`OptimizerStatsResponse` envelope.
        """
        all_jobs = job_store.list_jobs(
            status=status,
            username=username,
            limit=_ANALYTICS_JOB_HARD_CAP,
            offset=0,
        )
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

        Returns:
            A populated :class:`ModelStatsResponse` envelope.
        """
        all_jobs = job_store.list_jobs(
            status=status,
            username=username,
            limit=_ANALYTICS_JOB_HARD_CAP,
            offset=0,
        )
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
        optimizer: str | None = Query(default=None, description="Exact-match optimizer name filter"),
        model: str | None = Query(default=None, description="Exact-match primary model name filter"),
        status: str | None = Query(default=None, description="Optimization status filter"),
        username: str | None = Query(default=None, description="Only include optimizations owned by this user"),
        optimization_id: str | None = Query(default=None, description="Limit the aggregation to a single optimization"),
        date: str | None = Query(default=None, description="YYYY-MM-DD day filter on created_at"),
    ) -> DashboardAnalyticsResponse:
        """Return a pre-shaped payload for the whole analytics dashboard.

        Caps at :data:`_ANALYTICS_JOB_HARD_CAP` jobs per request and surfaces
        ``truncated=True`` when the cap is hit. Improvements are raw floats;
        the frontend normalizes ratios.

        Args:
            optimizer: Exact-match optimizer name filter.
            model: Exact-match primary model name filter.
            status: Optimization status filter.
            username: Only include optimizations owned by this user.
            optimization_id: Limit the aggregation to a single optimization.
            date: ``YYYY-MM-DD`` day filter on ``created_at``.

        Returns:
            A populated :class:`DashboardAnalyticsResponse` envelope.
        """
        all_jobs_raw = job_store.list_jobs(
            status=status,
            username=username,
            limit=_ANALYTICS_JOB_HARD_CAP,
            offset=0,
        )
        truncated = len(all_jobs_raw) >= _ANALYTICS_JOB_HARD_CAP

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
            if optimization_id and summary.optimization_id != optimization_id:
                continue
            if date:
                created = summary.created_at
                if created is None:
                    continue
                created_day = created.strftime("%Y-%m-%d") if hasattr(created, "strftime") else str(created)[:10]
                if created_day != date:
                    continue
            summaries.append(summary)

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
        total_dataset_rows = 0
        total_pairs_run = 0
        grid_search_count = 0
        single_run_count = 0
        for s in summaries:
            opt = s.optimizer_name or t("analytics.other_bucket")
            optimizer_counts[opt] = optimizer_counts.get(opt, 0) + 1
            job_type = s.optimization_type or OPTIMIZATION_TYPE_RUN
            job_type_counts[job_type] = job_type_counts.get(job_type, 0) + 1
            if s.dataset_rows:
                total_dataset_rows += s.dataset_rows
            if job_type == OPTIMIZATION_TYPE_GRID_SEARCH:
                grid_search_count += 1
                if s.total_pairs:
                    total_pairs_run += s.total_pairs
            else:
                single_run_count += 1
                total_pairs_run += 1

        model_counter: Counter = Counter()
        for s in summaries:
            m = s.model_name or (s.best_pair_label.split(" + ")[0] if s.best_pair_label else None)
            if m:
                model_counter[m] += 1
        model_usage = [
            DashboardAnalyticsNameValue(name=name, value=count) for name, count in model_counter.most_common(8)
        ]

        improvements = [(s, s.metric_improvement) for s in success_items if s.metric_improvement is not None]
        numeric_improvements = [v for _, v in improvements]
        avg_improvement = sum(numeric_improvements) / len(numeric_improvements) if numeric_improvements else None
        best_improvement = max(numeric_improvements) if numeric_improvements else None
        success_rate = (success_count / terminal_count) if terminal_count else 0.0

        runtimes = [s.elapsed_seconds for s in success_items if s.elapsed_seconds is not None]
        avg_runtime_seconds = (sum(runtimes) / len(runtimes)) if runtimes else None

        opt_improvements: dict[str, list[float]] = {}
        opt_runtimes: dict[str, list[float]] = {}
        for s in success_items:
            name = s.optimizer_name
            if not name:
                continue
            if s.metric_improvement is not None:
                opt_improvements.setdefault(name, []).append(s.metric_improvement)
            if s.elapsed_seconds is not None:
                opt_runtimes.setdefault(name, []).append(s.elapsed_seconds)
        improvement_by_optimizer = [
            DashboardAnalyticsOptimizerAverage(
                name=name,
                average=round(sum(vals) / len(vals), 6),
                count=len(vals),
            )
            for name, vals in opt_improvements.items()
        ]
        runtime_minutes_by_optimizer = [
            DashboardAnalyticsOptimizerAverage(
                name=name,
                average=round((sum(vals) / len(vals)) / 60.0, 2),
                count=len(vals),
            )
            for name, vals in opt_runtimes.items()
        ]

        top_improvement_items = [s for s in success_items if s.optimized_test_metric is not None][:10]
        top_improvement = [_summary_to_analytics_job(s) for s in top_improvement_items]

        runtime_distribution_items = [s for s in success_items if s.elapsed_seconds is not None][:15]
        runtime_distribution = [_summary_to_analytics_job(s) for s in runtime_distribution_items]

        dvs_items = [s for s in success_items if s.dataset_rows is not None and s.metric_improvement is not None]
        dataset_vs_improvement = [_summary_to_analytics_job(s) for s in dvs_items]

        eff_items: list[tuple[float, Any]] = []
        for s in success_items:
            if s.metric_improvement is None or s.elapsed_seconds is None or s.elapsed_seconds <= 0:
                continue
            delta = s.metric_improvement
            if abs(delta) <= 1:
                delta = delta * 100
            efficiency = (delta / s.elapsed_seconds) * 60.0
            eff_items.append((efficiency, s))
        eff_items.sort(key=lambda pair: pair[0], reverse=True)
        efficiency = [_summary_to_analytics_job(s) for _, s in eff_items[:10]]

        ranked = sorted(
            improvements,
            key=lambda pair: pair[1] if abs(pair[1]) > 1 else pair[1] * 100,
            reverse=True,
        )
        top_jobs_by_improvement = [_summary_to_analytics_job(s) for s, _ in ranked[:5]]

        timeline_buckets: dict[str, int] = {}
        for s in summaries:
            created = s.created_at
            if created is None:
                continue
            day = created.strftime("%Y-%m-%d") if hasattr(created, "strftime") else str(created)[:10]
            timeline_buckets[day] = timeline_buckets.get(day, 0) + 1
        timeline_entries = sorted(timeline_buckets.items())[-14:]
        timeline = [DashboardAnalyticsTimelineBucket(date=d, count=c) for d, c in timeline_entries]

        return DashboardAnalyticsResponse(
            filtered_total=filtered_total,
            status_counts=status_counts,
            optimizer_counts=optimizer_counts,
            job_type_counts=job_type_counts,
            model_usage=model_usage,
            success_count=success_count,
            failed_count=failed_count,
            running_count=running_count,
            terminal_count=terminal_count,
            success_rate=round(success_rate, 4),
            avg_improvement=round(avg_improvement, 6) if avg_improvement is not None else None,
            avg_runtime_seconds=round(avg_runtime_seconds, 2) if avg_runtime_seconds is not None else None,
            total_dataset_rows=total_dataset_rows,
            total_pairs_run=total_pairs_run,
            grid_search_count=grid_search_count,
            single_run_count=single_run_count,
            best_improvement=round(best_improvement, 6) if best_improvement is not None else None,
            improvement_by_optimizer=improvement_by_optimizer,
            runtime_minutes_by_optimizer=runtime_minutes_by_optimizer,
            top_improvement=top_improvement,
            runtime_distribution=runtime_distribution,
            dataset_vs_improvement=dataset_vs_improvement,
            efficiency=efficiency,
            top_jobs_by_improvement=top_jobs_by_improvement,
            timeline=timeline,
            available_optimizers=sorted(available_optimizers),
            available_models=sorted(available_models),
            truncated=truncated,
        )

    return router
