"""Aggregation response models for /analytics/* endpoints."""

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


class DashboardAnalyticsOptimizerAverage(BaseModel):
    """Averaged per-optimizer metric used by the grouped bar charts."""

    name: str
    average: float = 0.0
    count: int = 0


class DashboardAnalyticsTimelineBucket(BaseModel):
    """One-day bucket for the "optimizations per day" timeline."""

    date: str
    count: int = 0


class DashboardAnalyticsResponse(BaseModel):
    """Pre-shaped payload powering the whole analytics dashboard tab."""

    # Matches the `filtered_total` the frontend uses for the
    # "no results" check and the stats-card denominators when a
    # filter is active.
    filtered_total: int = 0

    status_counts: dict[str, int] = Field(default_factory=dict)
    optimizer_counts: dict[str, int] = Field(default_factory=dict)
    job_type_counts: dict[str, int] = Field(default_factory=dict)

    # Model usage — list of {name, value} sorted desc, trimmed to top 8.
    model_usage: list[DashboardAnalyticsNameValue] = Field(default_factory=list)

    success_count: int = 0
    failed_count: int = 0
    running_count: int = 0
    terminal_count: int = 0
    success_rate: float = 0.0
    avg_improvement: float | None = None
    avg_runtime_seconds: float | None = None
    total_dataset_rows: int = 0
    total_pairs_run: int = 0
    grid_search_count: int = 0
    single_run_count: int = 0
    best_improvement: float | None = None

    # Per-optimizer averages (powering avg-improvement and
    # avg-runtime grouped-bar charts). Runtime is in minutes, not
    # seconds — the frontend rendered it that way already.
    improvement_by_optimizer: list[DashboardAnalyticsOptimizerAverage] = Field(default_factory=list)
    runtime_minutes_by_optimizer: list[DashboardAnalyticsOptimizerAverage] = Field(default_factory=list)

    top_improvement: list[DashboardAnalyticsJob] = Field(default_factory=list)
    runtime_distribution: list[DashboardAnalyticsJob] = Field(default_factory=list)
    dataset_vs_improvement: list[DashboardAnalyticsJob] = Field(default_factory=list)
    efficiency: list[DashboardAnalyticsJob] = Field(default_factory=list)
    top_jobs_by_improvement: list[DashboardAnalyticsJob] = Field(default_factory=list)

    timeline: list[DashboardAnalyticsTimelineBucket] = Field(default_factory=list)

    # Filter dropdown option lists (every unique optimizer/model
    # the caller has ever used — the user can pick any of these
    # from the analytics filter UI without needing to scroll the
    # paginated jobs table first).
    available_optimizers: list[str] = Field(default_factory=list)
    available_models: list[str] = Field(default_factory=list)
