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

    @router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
    def get_analytics_summary(
        optimizer: Optional[str] = Query(default=None, description="Filter by optimizer name"),
        model: Optional[str] = Query(default=None, description="Filter by model name"),
        status: Optional[str] = Query(default=None, description="Filter by job status"),
        username: Optional[str] = Query(default=None, description="Filter by username"),
    ) -> AnalyticsSummaryResponse:
        """Pre-compute dashboard KPIs with optional filters.

        Returns aggregated metrics across all matching jobs including success rate,
        average improvement, average runtime, and dataset statistics.

        Args:
            optimizer: Filter by optimizer name (e.g., 'miprov2', 'gepa').
            model: Filter by model name (exact match on model_name field).
            status: Filter by job status.
            username: Filter by username.

        Returns:
            AnalyticsSummaryResponse: Aggregated KPIs across filtered jobs.
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

    @router.get("/analytics/optimizers", response_model=OptimizerStatsResponse)
    def get_optimizer_stats(
        model: Optional[str] = Query(default=None, description="Filter by model name"),
        status: Optional[str] = Query(default=None, description="Filter by job status"),
        username: Optional[str] = Query(default=None, description="Filter by username"),
    ) -> OptimizerStatsResponse:
        """Pre-compute per-optimizer statistics with optional filters.

        Aggregates metrics grouped by optimizer name, showing success rate,
        average improvement, and average runtime for each optimizer.

        Args:
            model: Filter by model name.
            status: Filter by job status.
            username: Filter by username.

        Returns:
            OptimizerStatsResponse: List of per-optimizer statistics.
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

    @router.get("/analytics/models", response_model=ModelStatsResponse)
    def get_model_stats(
        optimizer: Optional[str] = Query(default=None, description="Filter by optimizer name"),
        status: Optional[str] = Query(default=None, description="Filter by job status"),
        username: Optional[str] = Query(default=None, description="Filter by username"),
    ) -> ModelStatsResponse:
        """Pre-compute per-model statistics with optional filters.

        Aggregates metrics grouped by model name, showing success rate,
        average improvement, and usage count for each model.

        Args:
            optimizer: Filter by optimizer name.
            status: Filter by job status.
            username: Filter by username.

        Returns:
            ModelStatsResponse: List of per-model statistics.
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
