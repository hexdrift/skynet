"""Aggregation response models for /analytics/* endpoints."""
from typing import List, Optional

from pydantic import BaseModel, Field


class AnalyticsSummaryResponse(BaseModel):
    """Pre-computed KPIs across all filtered jobs."""

    total_jobs: int = 0
    success_count: int = 0
    failed_count: int = 0
    cancelled_count: int = 0
    pending_count: int = 0
    running_count: int = 0
    success_rate: float = 0.0
    avg_improvement: Optional[float] = None
    max_improvement: Optional[float] = None
    min_improvement: Optional[float] = None
    avg_runtime: Optional[float] = None
    total_dataset_rows: int = 0
    total_pairs: int = 0
    completed_pairs: int = 0
    failed_pairs: int = 0


class OptimizerStatsItem(BaseModel):
    """Per-optimizer aggregated statistics."""

    name: str
    total_jobs: int = 0
    success_count: int = 0
    avg_improvement: Optional[float] = None
    success_rate: float = 0.0
    avg_runtime: Optional[float] = None


class OptimizerStatsResponse(BaseModel):
    """Response payload for /analytics/optimizers endpoint."""

    items: List[OptimizerStatsItem] = Field(default_factory=list)


class ModelStatsItem(BaseModel):
    """Per-model aggregated statistics."""

    name: str
    total_jobs: int = 0
    success_count: int = 0
    avg_improvement: Optional[float] = None
    success_rate: float = 0.0
    use_count: int = 0


class ModelStatsResponse(BaseModel):
    """Response payload for /analytics/models endpoint."""

    items: List[ModelStatsItem] = Field(default_factory=list)


class DashboardAnalyticsJob(BaseModel):
    """Compact job reference used in dashboard top-N lists.

    Holds only the fields the dashboard charts and ranked tables
    need to render a row — identifier, name, status, the two test
    metrics, timing, dataset size and job type. The full
    ``OptimizationSummaryResponse`` is avoided deliberately so the
    /analytics/dashboard payload stays small.
    """

    optimization_id: str
    name: Optional[str] = None
    optimizer_name: Optional[str] = None
    model_name: Optional[str] = None
    status: str
    baseline_test_metric: Optional[float] = None
    optimized_test_metric: Optional[float] = None
    metric_improvement: Optional[float] = None
    elapsed_seconds: Optional[float] = None
    dataset_rows: Optional[int] = None
    optimization_type: Optional[str] = None
    best_pair_label: Optional[str] = None
    created_at: Optional[str] = None


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
    """Pre-shaped payload powering the whole analytics dashboard tab.

    One GET replaces the old client-side "fetch every page then
    aggregate in the browser" loop. Every field corresponds to a
    chart, KPI or table on the analytics tab.

    Status distribution, optimizer distribution and job-type
    distribution come back as ``{name: count}`` dictionaries. All the
    top-N ranked lists (``top_improvement``, ``runtime_distribution``,
    ``dataset_vs_improvement``, ``efficiency``,
    ``top_jobs_by_improvement``) are already sorted and trimmed by
    the backend. The frontend only has to re-shape them into the
    Hebrew-keyed objects the chart components expect.
    """

    # Matches the `filtered_total` the frontend uses for the
    # "no results" check and the stats-card denominators when a
    # filter is active.
    filtered_total: int = 0

    # Status / optimizer / job-type distributions — {name: count}.
    status_counts: dict[str, int] = Field(default_factory=dict)
    optimizer_counts: dict[str, int] = Field(default_factory=dict)
    job_type_counts: dict[str, int] = Field(default_factory=dict)

    # Model usage — list of {name, value} sorted desc, trimmed to top 8.
    model_usage: List[DashboardAnalyticsNameValue] = Field(default_factory=list)

    success_count: int = 0
    failed_count: int = 0
    running_count: int = 0
    terminal_count: int = 0
    success_rate: float = 0.0
    avg_improvement: Optional[float] = None
    avg_runtime_seconds: Optional[float] = None
    total_dataset_rows: int = 0
    total_pairs_run: int = 0
    grid_search_count: int = 0
    single_run_count: int = 0
    best_improvement: Optional[float] = None

    # Per-optimizer averages (powering avg-improvement and
    # avg-runtime grouped-bar charts). Runtime is in minutes, not
    # seconds — the frontend rendered it that way already.
    improvement_by_optimizer: List[DashboardAnalyticsOptimizerAverage] = Field(
        default_factory=list
    )
    runtime_minutes_by_optimizer: List[DashboardAnalyticsOptimizerAverage] = Field(
        default_factory=list
    )

    top_improvement: List[DashboardAnalyticsJob] = Field(default_factory=list)
    runtime_distribution: List[DashboardAnalyticsJob] = Field(default_factory=list)
    dataset_vs_improvement: List[DashboardAnalyticsJob] = Field(default_factory=list)
    efficiency: List[DashboardAnalyticsJob] = Field(default_factory=list)
    top_jobs_by_improvement: List[DashboardAnalyticsJob] = Field(default_factory=list)

    # Timeline bucket series, last 14 days with a job count each.
    timeline: List[DashboardAnalyticsTimelineBucket] = Field(default_factory=list)

    # Filter dropdown option lists (every unique optimizer/model
    # the caller has ever used — the user can pick any of these
    # from the analytics filter UI without needing to scroll the
    # paginated jobs table first).
    available_optimizers: List[str] = Field(default_factory=list)
    available_models: List[str] = Field(default_factory=list)
