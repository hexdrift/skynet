"""Tests for RunResponse, PairResult, and GridSearchResponse models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.models.artifacts import ProgramArtifact
from core.models.common import SplitCounts
from core.models.results import GridSearchResponse, PairResult, RunResponse
from core.models.telemetry import JobLogEntry


def _split_counts() -> SplitCounts:
    """Return a SplitCounts fixture for result tests.

    Returns:
        A SplitCounts with 7 train / 2 val / 1 test rows.
    """
    return SplitCounts(train=7, val=2, test=1)


def test_run_response_minimal_construction() -> None:
    """Verify RunResponse accepts the minimum required fields and defaults the rest."""
    r = RunResponse(
        module_name="predict",
        optimizer_name="gepa",
        metric_name="accuracy",
        split_counts=_split_counts(),
    )

    assert r.module_name == "predict"
    assert r.optimizer_name == "gepa"
    assert r.metric_name == "accuracy"
    assert r.baseline_test_metric is None
    assert r.optimized_test_metric is None
    assert r.metric_improvement is None
    assert r.optimization_metadata == {}
    assert r.details == {}
    assert r.program_artifact is None
    assert r.runtime_seconds is None
    assert r.num_lm_calls is None
    assert r.avg_response_time_ms is None
    assert r.run_log == []
    assert r.baseline_test_results == []
    assert r.optimized_test_results == []


def test_run_response_persists_metric_values() -> None:
    """Verify RunResponse stores baseline/optimized/improvement metrics."""
    r = RunResponse(
        module_name="predict",
        optimizer_name="gepa",
        metric_name="accuracy",
        split_counts=_split_counts(),
        baseline_test_metric=0.5,
        optimized_test_metric=0.8,
        metric_improvement=0.3,
        runtime_seconds=120.0,
        num_lm_calls=42,
    )

    assert r.baseline_test_metric == pytest.approx(0.5)
    assert r.optimized_test_metric == pytest.approx(0.8)
    assert r.metric_improvement == pytest.approx(0.3)
    assert r.runtime_seconds == pytest.approx(120.0)
    assert r.num_lm_calls == 42


def test_run_response_persists_run_log() -> None:
    """Verify RunResponse round-trips a populated run_log."""
    log = JobLogEntry(timestamp=datetime.now(tz=UTC), level="INFO", logger="dspy", message="hi")
    r = RunResponse(
        module_name="predict",
        optimizer_name="gepa",
        metric_name=None,
        split_counts=_split_counts(),
        run_log=[log],
    )

    assert len(r.run_log) == 1
    assert r.run_log[0].message == "hi"


def test_run_response_persists_artifact() -> None:
    """Verify RunResponse stores a nested ProgramArtifact."""
    r = RunResponse(
        module_name="predict",
        optimizer_name="gepa",
        metric_name=None,
        split_counts=_split_counts(),
        program_artifact=ProgramArtifact(path="/p"),
    )

    assert r.program_artifact is not None
    assert r.program_artifact.path == "/p"


def test_pair_result_minimal_construction() -> None:
    """Verify PairResult accepts required indexes/model names and defaults metrics."""
    pair = PairResult(pair_index=0, generation_model="g", reflection_model="r")

    assert pair.pair_index == 0
    assert pair.generation_model == "g"
    assert pair.reflection_model == "r"
    assert pair.generation_reasoning_effort is None
    assert pair.reflection_reasoning_effort is None
    assert pair.metric_improvement is None
    assert pair.error is None
    assert pair.baseline_test_results == []
    assert pair.optimized_test_results == []


def test_pair_result_persists_error_and_metrics() -> None:
    """Verify PairResult stores an error string and metric values."""
    pair = PairResult(
        pair_index=2,
        generation_model="g",
        reflection_model="r",
        baseline_test_metric=0.4,
        optimized_test_metric=0.6,
        metric_improvement=0.2,
        runtime_seconds=10.0,
        num_lm_calls=5,
        error="boom",
    )

    assert pair.error == "boom"
    assert pair.baseline_test_metric == pytest.approx(0.4)
    assert pair.metric_improvement == pytest.approx(0.2)


def test_grid_search_response_minimal_construction() -> None:
    """Verify GridSearchResponse accepts required fields and defaults pair lists."""
    resp = GridSearchResponse(
        module_name="predict",
        optimizer_name="gepa",
        split_counts=_split_counts(),
        total_pairs=4,
    )

    assert resp.module_name == "predict"
    assert resp.optimizer_name == "gepa"
    assert resp.metric_name is None
    assert resp.total_pairs == 4
    assert resp.completed_pairs == 0
    assert resp.failed_pairs == 0
    assert resp.pair_results == []
    assert resp.best_pair is None
    assert resp.runtime_seconds is None


def test_grid_search_response_persists_pair_results() -> None:
    """Verify GridSearchResponse stores pair_results and best_pair."""
    pair = PairResult(pair_index=0, generation_model="g", reflection_model="r", metric_improvement=0.5)
    resp = GridSearchResponse(
        module_name="predict",
        optimizer_name="gepa",
        metric_name="accuracy",
        split_counts=_split_counts(),
        total_pairs=1,
        completed_pairs=1,
        pair_results=[pair],
        best_pair=pair,
    )

    assert len(resp.pair_results) == 1
    assert resp.completed_pairs == 1
    assert resp.best_pair is not None
    assert resp.best_pair.metric_improvement == pytest.approx(0.5)
