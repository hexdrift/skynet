"""Routes for dashboard analytics and per-model / per-optimizer aggregation."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from ...constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_DATASET_ROWS,
    PAYLOAD_OVERVIEW_JOB_TYPE,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
    PAYLOAD_OVERVIEW_TOTAL_PAIRS,
)
from ...models import (
    AnalyticsSummaryResponse,
    ModelStatsItem,
    ModelStatsResponse,
    OptimizerStatsItem,
    OptimizerStatsResponse,
)
from ..converters import parse_overview


def create_analytics_router(*, job_store) -> APIRouter:
    """Build the analytics router.

    Args:
        job_store: Active job store instance used to read all jobs for
            aggregation.

    Returns:
        APIRouter: Router with ``/analytics/summary``, ``/analytics/optimizers``
        and ``/analytics/models``.
    """
    router = APIRouter()

    @router.get(
        "/analytics/summary",
        response_model=AnalyticsSummaryResponse,
        summary="Dashboard KPIs across all optimization jobs",
    )
    def get_analytics_summary(
        optimizer: Optional[str] = Query(default=None, description="Exact-match optimizer name (e.g. 'miprov2', 'gepa', 'copro')"),
        model: Optional[str] = Query(default=None, description="Exact-match model name, compared against the primary model used by the job"),
        status: Optional[str] = Query(default=None, description="Job status filter: pending, running, success, failed, cancelled"),
        username: Optional[str] = Query(default=None, description="Only include jobs submitted by this username"),
    ) -> AnalyticsSummaryResponse:
        """Return a single aggregated KPI snapshot powering the dashboard header.

        Computes every headline number the dashboard needs in one round-trip:
        total jobs, per-status counts, overall success rate, improvement
        statistics (min/avg/max delta between baseline and optimized test
        metric), average runtime, total dataset rows processed, and — for
        grid-search jobs — total/completed/failed pair counts.

        Behavior notes:
            - Iterates every job the caller can see (hard cap 10,000).
              Filters are applied in Python because several of them operate
              on the embedded ``overview`` payload, not top-level columns.
            - Improvement = ``optimized_test_metric - baseline_test_metric``.
              Only ``success`` jobs with numeric metrics contribute.
            - For grid-search jobs the ``best_pair`` is used as the
              representative result, not the aggregate across all pairs.
            - ``running_count`` folds in ``validating`` jobs so the UI
              shows a single "in progress" number.
            - All filters combine with AND. Passing no filters returns the
              global numbers across every job the user is allowed to see.
        """
        # Fetch all jobs (no pagination for analytics)
        all_jobs = job_store.list_jobs(
            status=status,
            username=username,
            limit=10000,  # Large limit to get all jobs
            offset=0,
        )

        # Apply additional filters that aren't natively supported by list_jobs
        filtered_jobs = []
        for job_data in all_jobs:
            overview = parse_overview(job_data)

            # Filter by optimizer
            if optimizer and overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_NAME) != optimizer:
                continue

            # Filter by model (check model_name field)
            if model and overview.get(PAYLOAD_OVERVIEW_MODEL_NAME) != model:
                continue

            filtered_jobs.append((job_data, overview))

        # Initialize counters
        total = len(filtered_jobs)
        status_counts = {"success": 0, "failed": 0, "cancelled": 0, "pending": 0, "running": 0, "validating": 0}
        improvements = []
        runtimes = []
        total_dataset_rows = 0
        total_pairs = 0
        completed_pairs = 0
        failed_pairs = 0

        # Aggregate metrics
        for job_data, overview in filtered_jobs:
            job_status = job_data.get("status", "pending")
            status_counts[job_status] = status_counts.get(job_status, 0) + 1

            # Dataset rows
            rows = overview.get(PAYLOAD_OVERVIEW_DATASET_ROWS)
            if isinstance(rows, int):
                total_dataset_rows += rows

            # Grid search specific
            optimization_type = overview.get(PAYLOAD_OVERVIEW_JOB_TYPE, OPTIMIZATION_TYPE_RUN)
            if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
                pairs = overview.get(PAYLOAD_OVERVIEW_TOTAL_PAIRS)
                if isinstance(pairs, int):
                    total_pairs += pairs

            # Only process completed jobs for metrics
            if job_status != "success":
                continue

            result_data = job_data.get("result")
            if not result_data or not isinstance(result_data, dict):
                continue

            # Extract metrics based on job type
            if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
                # Grid search: use best pair metrics
                best_pair = result_data.get("best_pair")
                if isinstance(best_pair, dict):
                    baseline = best_pair.get("baseline_test_metric")
                    optimized = best_pair.get("optimized_test_metric")
                    if isinstance(baseline, (int, float)) and isinstance(optimized, (int, float)):
                        improvements.append(optimized - baseline)

                    runtime = best_pair.get("runtime_seconds")
                    if isinstance(runtime, (int, float)):
                        runtimes.append(runtime)

                # Aggregate pair counters
                comp = result_data.get("completed_pairs")
                fail = result_data.get("failed_pairs")
                if isinstance(comp, int):
                    completed_pairs += comp
                if isinstance(fail, int):
                    failed_pairs += fail
            else:
                # Regular run: use direct metrics
                baseline = result_data.get("baseline_test_metric")
                optimized = result_data.get("optimized_test_metric")
                if isinstance(baseline, (int, float)) and isinstance(optimized, (int, float)):
                    improvements.append(optimized - baseline)

                runtime = result_data.get("runtime_seconds")
                if isinstance(runtime, (int, float)):
                    runtimes.append(runtime)

        # Compute aggregate statistics
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
        )

    @router.get(
        "/analytics/optimizers",
        response_model=OptimizerStatsResponse,
        summary="Per-optimizer aggregated statistics",
    )
    def get_optimizer_stats(
        model: Optional[str] = Query(default=None, description="Exact-match model name to scope the stats to a single model"),
        status: Optional[str] = Query(default=None, description="Restrict aggregation to a single status bucket"),
        username: Optional[str] = Query(default=None, description="Only include jobs submitted by this username"),
    ) -> OptimizerStatsResponse:
        """Group every job by optimizer name and return one row per optimizer.

        Powers the dashboard's "Optimizer performance" table, letting users
        compare the optimizers they've used side by side.

        Each row contains:
            - ``name``: canonical optimizer identifier
            - ``total_jobs``: how many jobs used this optimizer under the filter
            - ``success_count``: subset that finished successfully
            - ``success_rate``: ``success_count / total_jobs`` (0.0-1.0)
            - ``avg_improvement``: average ``optimized - baseline`` test metric
              across successful jobs; ``null`` if no numeric metrics exist
            - ``avg_runtime``: mean wall-clock seconds for successful jobs;
              ``null`` if unavailable

        Rows are returned sorted by ``total_jobs`` descending, so the most
        frequently used optimizer is first. Jobs without a declared
        optimizer name are excluded from the aggregation entirely.
        """
        # Fetch all jobs
        all_jobs = job_store.list_jobs(
            status=status,
            username=username,
            limit=10000,
            offset=0,
        )

        # Group by optimizer
        optimizer_data = {}  # optimizer_name -> {jobs, improvements, runtimes}

        for job_data in all_jobs:
            overview = parse_overview(job_data)

            # Filter by model
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
                    optimization_type = overview.get(PAYLOAD_OVERVIEW_JOB_TYPE, OPTIMIZATION_TYPE_RUN)

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

        # Build response items
        items = []
        for optimizer_name, stats in optimizer_data.items():
            total = stats["total"]
            success_count = stats["success"]
            success_rate = (success_count / total) if total > 0 else 0.0
            avg_improvement = (
                sum(stats["improvements"]) / len(stats["improvements"])
                if stats["improvements"] else None
            )
            avg_runtime = (
                sum(stats["runtimes"]) / len(stats["runtimes"])
                if stats["runtimes"] else None
            )

            items.append(OptimizerStatsItem(
                name=optimizer_name,
                total_jobs=total,
                success_count=success_count,
                avg_improvement=round(avg_improvement, 6) if avg_improvement is not None else None,
                success_rate=round(success_rate, 4),
                avg_runtime=round(avg_runtime, 2) if avg_runtime is not None else None,
            ))

        # Sort by total jobs descending
        items.sort(key=lambda x: x.total_jobs, reverse=True)

        return OptimizerStatsResponse(items=items)

    @router.get(
        "/analytics/models",
        response_model=ModelStatsResponse,
        summary="Per-model aggregated statistics",
    )
    def get_model_stats(
        optimizer: Optional[str] = Query(default=None, description="Exact-match optimizer name to scope the stats"),
        status: Optional[str] = Query(default=None, description="Restrict aggregation to a single status bucket"),
        username: Optional[str] = Query(default=None, description="Only include jobs submitted by this username"),
    ) -> ModelStatsResponse:
        """Group every job by model name and return one row per model.

        Powers the dashboard's "Model performance" table. Answers the
        question "which model worked best on my workloads?".

        Each row contains:
            - ``name``: model identifier as stored on the job overview
            - ``total_jobs``: jobs that used this model under the filter
            - ``success_count``: subset that finished successfully
            - ``success_rate``: 0.0-1.0
            - ``avg_improvement``: average ``optimized - baseline`` test metric
              across successful jobs; ``null`` when no numeric metrics exist
            - ``use_count``: total usages, equal to ``total_jobs`` today but
              reserved separately in case future work tracks non-primary
              model usages (e.g. judges or decoders) as well

        Rows are returned sorted by ``use_count`` descending. Jobs without
        a declared primary model are excluded.
        """
        # Fetch all jobs
        all_jobs = job_store.list_jobs(
            status=status,
            username=username,
            limit=10000,
            offset=0,
        )

        # Group by model
        model_data = {}  # model_name -> {jobs, improvements, runtimes}

        for job_data in all_jobs:
            overview = parse_overview(job_data)

            # Filter by optimizer
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
                    optimization_type = overview.get(PAYLOAD_OVERVIEW_JOB_TYPE, OPTIMIZATION_TYPE_RUN)

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

        # Build response items
        items = []
        for model_name, stats in model_data.items():
            total = stats["total"]
            success_count = stats["success"]
            success_rate = (success_count / total) if total > 0 else 0.0
            avg_improvement = (
                sum(stats["improvements"]) / len(stats["improvements"])
                if stats["improvements"] else None
            )

            items.append(ModelStatsItem(
                name=model_name,
                total_jobs=total,
                success_count=success_count,
                avg_improvement=round(avg_improvement, 6) if avg_improvement is not None else None,
                success_rate=round(success_rate, 4),
                use_count=stats["use_count"],
            ))

        # Sort by use count descending
        items.sort(key=lambda x: x.use_count, reverse=True)

        return ModelStatsResponse(items=items)

    return router
