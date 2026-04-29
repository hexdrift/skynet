"""Tests for analytics summary, optimizer/model stats, and dashboard payload models."""

from __future__ import annotations

import pytest

from core.models.analytics import (
    AnalyticsSummaryResponse,
    DashboardAnalyticsJob,
    DashboardAnalyticsNameValue,
    DashboardAnalyticsOptimizerAverage,
    DashboardAnalyticsResponse,
    DashboardAnalyticsTimelineBucket,
    ModelStatsItem,
    ModelStatsResponse,
    OptimizerStatsItem,
    OptimizerStatsResponse,
)


def test_analytics_summary_defaults_zeroed() -> None:
    """Verify AnalyticsSummaryResponse defaults all numeric counters to 0/None."""
    s = AnalyticsSummaryResponse()

    assert s.total_jobs == 0
    assert s.success_count == 0
    assert s.failed_count == 0
    assert s.cancelled_count == 0
    assert s.pending_count == 0
    assert s.running_count == 0
    assert s.success_rate == pytest.approx(0.0)
    assert s.avg_improvement is None
    assert s.max_improvement is None
    assert s.min_improvement is None
    assert s.avg_runtime is None
    assert s.total_dataset_rows == 0
    assert s.total_pairs == 0
    assert s.completed_pairs == 0
    assert s.failed_pairs == 0
    assert s.truncated is False


def test_analytics_summary_round_trips_values() -> None:
    """Verify AnalyticsSummaryResponse persists provided values."""
    s = AnalyticsSummaryResponse(
        total_jobs=10,
        success_count=7,
        failed_count=2,
        cancelled_count=1,
        success_rate=0.7,
        avg_improvement=0.1,
        truncated=True,
    )

    assert s.total_jobs == 10
    assert s.success_count == 7
    assert s.success_rate == pytest.approx(0.7)
    assert s.avg_improvement == pytest.approx(0.1)
    assert s.truncated is True


def test_optimizer_stats_item_defaults() -> None:
    """Verify OptimizerStatsItem defaults numeric fields and accepts a name."""
    item = OptimizerStatsItem(name="gepa")

    assert item.name == "gepa"
    assert item.total_jobs == 0
    assert item.success_count == 0
    assert item.avg_improvement is None
    assert item.success_rate == pytest.approx(0.0)
    assert item.avg_runtime is None


def test_optimizer_stats_response_defaults_empty_items() -> None:
    """Verify OptimizerStatsResponse defaults to an empty items list."""
    r = OptimizerStatsResponse()

    assert r.items == []
    assert r.truncated is False


def test_optimizer_stats_response_persists_items() -> None:
    """Verify OptimizerStatsResponse stores nested OptimizerStatsItem entries."""
    r = OptimizerStatsResponse(items=[OptimizerStatsItem(name="gepa", total_jobs=3)])

    assert len(r.items) == 1
    assert r.items[0].total_jobs == 3


def test_model_stats_item_defaults() -> None:
    """Verify ModelStatsItem defaults numeric fields and accepts a name."""
    item = ModelStatsItem(name="gpt-4o")

    assert item.name == "gpt-4o"
    assert item.total_jobs == 0
    assert item.success_count == 0
    assert item.use_count == 0


def test_model_stats_response_persists_items() -> None:
    """Verify ModelStatsResponse stores nested ModelStatsItem entries."""
    r = ModelStatsResponse(items=[ModelStatsItem(name="gpt-4o", use_count=5)])

    assert len(r.items) == 1
    assert r.items[0].use_count == 5


def test_dashboard_analytics_job_defaults() -> None:
    """Verify DashboardAnalyticsJob requires only optimization_id and status."""
    j = DashboardAnalyticsJob(optimization_id="abc123", status="success")

    assert j.optimization_id == "abc123"
    assert j.status == "success"
    assert j.name is None
    assert j.optimizer_name is None
    assert j.model_name is None
    assert j.optimization_type is None


def test_dashboard_analytics_job_full_population() -> None:
    """Verify DashboardAnalyticsJob persists every optional field when supplied."""
    j = DashboardAnalyticsJob(
        optimization_id="abc123",
        status="success",
        name="my-job",
        optimizer_name="gepa",
        model_name="gpt-4o",
        baseline_test_metric=0.5,
        optimized_test_metric=0.8,
        metric_improvement=0.3,
        elapsed_seconds=120.0,
        dataset_rows=100,
        optimization_type="run",
        best_pair_label="g1/r1",
        created_at="2026-04-28T10:00:00Z",
    )

    assert j.optimization_type == "run"
    assert j.metric_improvement == pytest.approx(0.3)


def test_dashboard_analytics_name_value_defaults_zero() -> None:
    """Verify DashboardAnalyticsNameValue defaults the value to 0.0."""
    nv = DashboardAnalyticsNameValue(name="series")

    assert nv.value == pytest.approx(0.0)


def test_dashboard_analytics_optimizer_average_defaults() -> None:
    """Verify DashboardAnalyticsOptimizerAverage defaults numeric fields."""
    a = DashboardAnalyticsOptimizerAverage(name="gepa")

    assert a.average == pytest.approx(0.0)
    assert a.count == 0


def test_dashboard_analytics_timeline_bucket_defaults_zero() -> None:
    """Verify DashboardAnalyticsTimelineBucket defaults count to 0."""
    b = DashboardAnalyticsTimelineBucket(date="2026-04-28")

    assert b.date == "2026-04-28"
    assert b.count == 0


def test_dashboard_analytics_response_defaults() -> None:
    """Verify DashboardAnalyticsResponse defaults every aggregate to its empty/zero shape."""
    r = DashboardAnalyticsResponse()

    assert r.filtered_total == 0
    assert r.status_counts == {}
    assert r.optimizer_counts == {}
    assert r.job_type_counts == {}
    assert r.model_usage == []
    assert r.success_count == 0
    assert r.success_rate == pytest.approx(0.0)
    assert r.improvement_by_optimizer == []
    assert r.runtime_minutes_by_optimizer == []
    assert r.top_improvement == []
    assert r.runtime_distribution == []
    assert r.dataset_vs_improvement == []
    assert r.efficiency == []
    assert r.top_jobs_by_improvement == []
    assert r.timeline == []
    assert r.available_optimizers == []
    assert r.available_models == []
    assert r.truncated is False


def test_dashboard_analytics_response_nested_payloads() -> None:
    """Verify DashboardAnalyticsResponse stores nested model collections."""
    r = DashboardAnalyticsResponse(
        filtered_total=2,
        model_usage=[DashboardAnalyticsNameValue(name="gpt-4o", value=5.0)],
        improvement_by_optimizer=[DashboardAnalyticsOptimizerAverage(name="gepa", average=0.2, count=2)],
        timeline=[DashboardAnalyticsTimelineBucket(date="2026-04-28", count=2)],
        top_improvement=[DashboardAnalyticsJob(optimization_id="a", status="success")],
    )

    assert r.filtered_total == 2
    assert r.model_usage[0].name == "gpt-4o"
    assert r.improvement_by_optimizer[0].count == 2
    assert r.timeline[0].count == 2
    assert r.top_improvement[0].optimization_id == "a"
