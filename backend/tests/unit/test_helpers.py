"""Tests for the shared helpers used by multiple domain routers."""
from __future__ import annotations

import pytest

from core.api.routers._helpers import (
    _TERMINAL_STATUSES,
    _VALID_JOB_TYPES,
    _VALID_STATUSES,
    build_summary,
    strip_api_key,
)


def test_strip_api_key_removes_nested() -> None:
    out = strip_api_key({"name": "gpt", "extra": {"api_key": "sk-secret", "region": "us"}})
    assert "api_key" not in out["extra"]
    assert out["extra"] == {"region": "us"}
    assert out["name"] == "gpt"


def test_strip_api_key_passthrough_without_extra() -> None:
    out = strip_api_key({"name": "gpt"})
    assert out == {"name": "gpt"}


def test_strip_api_key_does_not_mutate_input() -> None:
    src = {"name": "gpt", "extra": {"api_key": "sk-x"}}
    strip_api_key(src)
    assert src == {"name": "gpt", "extra": {"api_key": "sk-x"}}


def test_valid_statuses_match_enum() -> None:
    from core.models import OptimizationStatus
    assert _VALID_STATUSES == {s.value for s in OptimizationStatus}


def test_terminal_statuses_are_finite() -> None:
    from core.models import OptimizationStatus
    assert _TERMINAL_STATUSES == {
        OptimizationStatus.success,
        OptimizationStatus.failed,
        OptimizationStatus.cancelled,
    }


def test_valid_job_types_covers_run_and_grid() -> None:
    assert _VALID_JOB_TYPES == {"run", "grid_search"}


def test_build_summary_on_pending_job_without_result() -> None:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    job_data = {
        "optimization_id": "abc123",
        "status": "pending",
        "created_at": now.isoformat(),
        "started_at": None,
        "completed_at": None,
        "payload_overview": {
            "job_type": "run",
            "module_name": "predict",
            "optimizer_name": "miprov2",
            "model_name": "gpt-4o-mini",
            "username": "alice",
        },
        "result": None,
        "latest_metrics": {},
        "progress_count": 0,
        "log_count": 0,
    }
    summary = build_summary(job_data)
    assert summary.optimization_id == "abc123"
    assert summary.status.value == "pending"
    assert summary.baseline_test_metric is None
    assert summary.metric_improvement is None


def test_build_summary_computes_improvement() -> None:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    job_data = {
        "optimization_id": "job42",
        "status": "success",
        "created_at": now.isoformat(),
        "started_at": now.isoformat(),
        "completed_at": now.isoformat(),
        "payload_overview": {
            "job_type": "run",
            "module_name": "predict",
            "optimizer_name": "miprov2",
            "username": "bob",
        },
        "result": {
            "baseline_test_metric": 0.60,
            "optimized_test_metric": 0.85,
        },
        "latest_metrics": {},
        "progress_count": 0,
        "log_count": 0,
    }
    summary = build_summary(job_data)
    assert summary.baseline_test_metric == 0.60
    assert summary.optimized_test_metric == 0.85
    assert summary.metric_improvement == pytest.approx(0.25, rel=1e-6)
