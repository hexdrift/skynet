"""Aggregation response models for /analytics/* endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .common import OptimizationType


class AnalyticsSummaryResponse(BaseModel):
    """Pre-computed KPIs across all filtered jobs."""

    total_jobs: int = 0
    success_count: int = 0
    failed_count: int = 0
    cancelled_count: int = 0
    pending_count: int = 0
    running_count: int = 0
    success_rate: float = 0.0
    avg_improvement: float | None = None
    max_improvement: float | None = None
    min_improvement: float | None = None
    avg_runtime: float | None = None
    total_dataset_rows: int = 0
    total_pairs: int = 0
    completed_pairs: int = 0
    failed_pairs: int = 0
    # True when the underlying scan hit the per-request job cap and the
    # aggregation may be incomplete; the dashboard surfaces a banner.
    truncated: bool = False


class OptimizerStatsItem(BaseModel):
    """Per-optimizer aggregated statistics."""

    name: str
    total_jobs: int = 0
    success_count: int = 0
    avg_improvement: float | None = None
    success_rate: float = 0.0
    avg_runtime: float | None = None


class OptimizerStatsResponse(BaseModel):
    """Response payload for /analytics/optimizers endpoint."""

    items: list[OptimizerStatsItem] = Field(default_factory=list)
    # See AnalyticsSummaryResponse.truncated.
    truncated: bool = False


class ModelStatsItem(BaseModel):
    """Per-model aggregated statistics."""

    name: str
    total_jobs: int = 0
    success_count: int = 0
    avg_improvement: float | None = None
    success_rate: float = 0.0
    use_count: int = 0


class ModelStatsResponse(BaseModel):
    """Response payload for /analytics/models endpoint."""

    items: list[ModelStatsItem] = Field(default_factory=list)
    # See AnalyticsSummaryResponse.truncated.
    truncated: bool = False


class DashboardAnalyticsJob(BaseModel):
    """Compact optimization reference used in dashboard top-N lists."""

    optimization_id: str
    name: str | None = None
    optimizer_name: str | None = None
    model_name: str | None = None
    status: str
    baseline_test_metric: float | None = None
    optimized_test_metric: float | None = None
    metric_improvement: float | None = None
    elapsed_seconds: float | None = None
    dataset_rows: int | None = None
    optimization_type: OptimizationType | None = None
    best_pair_label: str | None = None
    created_at: str | None = None


class DashboardAnalyticsNameValue(BaseModel):
    """Generic ``(label, numeric value)`` row for chart series."""

    name: str
    value: float = 0.0


class DashboardAnalyticsRangeBucket(BaseModel):
    """Histogram bucket counting runs whose value fell in ``[lower, upper)``."""

    # ``None`` marks an open end: the first bucket has no lower bound and the
    # last has no upper bound, so every value lands somewhere.
    lower: float | None = None
    upper: float | None = None
    count: int = 0
    # Mean improvement (percentage points) of the successful runs in the
    # bucket; only populated for the dataset-size breakdown.
    avg_improvement: float | None = None


class DashboardAnalyticsOptimizerStat(BaseModel):
    """Per-optimizer roll-up powering the optimizer comparison table."""

    name: str
    count: int = 0
    success_count: int = 0
    success_rate: float = 0.0
    avg_improvement: float | None = None
    avg_runtime_minutes: float | None = None


class DashboardAnalyticsModelStat(BaseModel):
    """Per-model roll-up powering the model comparison list."""

    name: str
    count: int = 0
    success_count: int = 0
    success_rate: float = 0.0
    avg_improvement: float | None = None


class DashboardAnalyticsTimelineBucket(BaseModel):
    """One calendar bucket (day, week or month) of the submissions timeline."""

    # ISO date of the bucket start; the response's ``timeline_granularity``
    # says whether it covers a day, an ISO week or a calendar month.
    date: str
    count: int = 0
    success_count: int = 0
    failed_count: int = 0


class DashboardAnalyticsResponse(BaseModel):
    """Pre-shaped payload powering the whole analytics dashboard tab."""

    # Matches the `filtered_total` the frontend uses for the
    # "no results" check and the stats-card denominators when a
    # filter is active.
    filtered_total: int = 0

    status_counts: dict[str, int] = Field(default_factory=dict)
    optimizer_counts: dict[str, int] = Field(default_factory=dict)
    job_type_counts: dict[str, int] = Field(default_factory=dict)

    # Owner usage — runs per owning username, sorted desc, trimmed to top 8.
    # Powers the control panel's "by owner" breakdown; clicking a bar scopes
    # the other charts to that owner via the `owner` filter param.
    owner_usage: list[DashboardAnalyticsNameValue] = Field(default_factory=list)

    # Access usage — runs per caller access tier (mine/owner/editor/viewer).
    # Powers the "by access" breakdown; clicking a bar scopes the other charts
    # to that tier via the `access` filter param. Empty when no caller context.
    access_usage: list[DashboardAnalyticsNameValue] = Field(default_factory=list)

    # Module (DSPy program type) usage across the filtered runs.
    module_counts: dict[str, int] = Field(default_factory=dict)

    success_count: int = 0
    failed_count: int = 0
    running_count: int = 0
    terminal_count: int = 0
    success_rate: float = 0.0
    # Improvement aggregates are in percentage points: ratio-scale metrics
    # (|delta| <= 1) are scaled by 100 so the dashboard can mix metric kinds.
    avg_improvement: float | None = None
    median_improvement: float | None = None
    best_improvement: float | None = None
    avg_runtime_seconds: float | None = None
    total_dataset_rows: int = 0
    total_pairs_run: int = 0
    grid_search_count: int = 0
    single_run_count: int = 0

    # Fixed-edge distributions that stay readable at any run count: how
    # improvements, runtimes and dataset sizes spread across the filtered set.
    improvement_histogram: list[DashboardAnalyticsRangeBucket] = Field(default_factory=list)
    runtime_histogram: list[DashboardAnalyticsRangeBucket] = Field(default_factory=list)
    dataset_size_buckets: list[DashboardAnalyticsRangeBucket] = Field(default_factory=list)

    optimizer_stats: list[DashboardAnalyticsOptimizerStat] = Field(default_factory=list)
    model_stats: list[DashboardAnalyticsModelStat] = Field(default_factory=list)

    top_jobs_by_improvement: list[DashboardAnalyticsJob] = Field(default_factory=list)

    timeline: list[DashboardAnalyticsTimelineBucket] = Field(default_factory=list)
    # "day", "week" or "month" — chosen from the span of the filtered runs so
    # the timeline never degenerates into hundreds of one-run bars.
    timeline_granularity: str = "day"

    # Filter dropdown option lists (every unique optimizer/model
    # the caller has ever used — the user can pick any of these
    # from the analytics filter UI without needing to scroll the
    # paginated jobs table first).
    available_optimizers: list[str] = Field(default_factory=list)
    available_models: list[str] = Field(default_factory=list)

    # See AnalyticsSummaryResponse.truncated.
    truncated: bool = False
