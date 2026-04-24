"""Tests for the shared helpers used by multiple domain routers."""

from __future__ import annotations

import base64  # noqa: F401 — used in _make_run_result_b64
import pickle
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

# noinspection PyProtectedMember
from ..routers import _helpers as _helpers_mod  # noqa: SLF001
# noinspection PyProtectedMember
from ..routers._helpers import (  # noqa: SLF001
    TERMINAL_STATUSES,
    VALID_OPTIMIZATION_TYPES,
    VALID_STATUSES,
    build_summary,
    clear_program_cache,
    enforce_user_quota,
    load_program,
    strip_api_key,
)
from ...constants import TQDM_REMAINING_KEY
from ...models import OptimizationStatus
from .mocks import load_fixture


def test_strip_api_key_removes_nested() -> None:
    """strip_api_key removes the nested extra.api_key and preserves all other fields."""
    out = strip_api_key({"name": "gpt", "extra": {"api_key": "sk-secret", "region": "us"}})
    assert "api_key" not in out["extra"]
    assert out["extra"] == {"region": "us"}
    assert out["name"] == "gpt"


def test_strip_api_key_passthrough_without_extra() -> None:
    """strip_api_key returns the dict unchanged when there is no extra key."""
    out = strip_api_key({"name": "gpt"})
    assert out == {"name": "gpt"}


def test_strip_api_key_does_not_mutate_input() -> None:
    """strip_api_key does not modify the original dict (returns a shallow copy)."""
    src = {"name": "gpt", "extra": {"api_key": "sk-x"}}
    strip_api_key(src)
    assert src == {"name": "gpt", "extra": {"api_key": "sk-x"}}


def test_valid_statuses_match_enum() -> None:
    """VALID_STATUSES contains exactly the values of the OptimizationStatus enum."""
    assert {s.value for s in OptimizationStatus} == VALID_STATUSES


def test_terminal_statuses_are_finite() -> None:
    """TERMINAL_STATUSES contains exactly success, failed, and canceled."""
    assert {
        OptimizationStatus.success,
        OptimizationStatus.failed,
        OptimizationStatus.cancelled,
    } == TERMINAL_STATUSES


def test_valid_job_types_covers_run_and_grid() -> None:
    """VALID_OPTIMIZATION_TYPES contains exactly 'run' and 'grid_search'."""
    assert {"run", "grid_search"} == VALID_OPTIMIZATION_TYPES


def test_build_summary_on_pending_job_without_result() -> None:
    """build_summary returns a valid summary for a pending job that has no result yet."""
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
            "optimizer_name": "gepa",
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
    """build_summary derives metric_improvement from the fixture result's baseline and optimized metrics."""
    now = datetime.now(timezone.utc)
    fixture_result = load_fixture("jobs/success_single_gepa.detail.json")["result"]
    job_data = {
        "optimization_id": "job42",
        "status": "success",
        "created_at": now.isoformat(),
        "started_at": now.isoformat(),
        "completed_at": now.isoformat(),
        "payload_overview": {
            "job_type": "run",
            "module_name": "predict",
            "optimizer_name": "gepa",
            "username": "bob",
        },
        "result": fixture_result,
        "latest_metrics": {},
        "progress_count": 0,
        "log_count": 0,
    }
    summary = build_summary(job_data)
    assert summary.baseline_test_metric == 52.89
    assert summary.optimized_test_metric == 75.9
    assert summary.metric_improvement == pytest.approx(23.01, abs=1e-2)


def test_build_summary_grid_search_uses_best_pair_metrics() -> None:
    """build_summary uses the best_pair metrics and sets best_pair_label for grid-search jobs."""
    now = datetime.now(timezone.utc).isoformat()
    fixture_grid_result = load_fixture("jobs/success_grid.detail.json")["grid_result"]
    job_data = {
        "optimization_id": "gs1",
        "status": "success",
        "created_at": now,
        "started_at": now,
        "completed_at": now,
        "payload_overview": {
            "optimization_type": "grid_search",
            "module_name": fixture_grid_result["module_name"],
            "optimizer_name": fixture_grid_result["optimizer_name"],
            "username": "carol",
        },
        "result": fixture_grid_result,
        "latest_metrics": {},
        "progress_count": 0,
        "log_count": 0,
    }
    summary = build_summary(job_data)

    best_pair = fixture_grid_result["best_pair"]
    assert summary.baseline_test_metric == best_pair["baseline_test_metric"]
    assert summary.optimized_test_metric == best_pair["optimized_test_metric"]
    assert summary.metric_improvement == pytest.approx(best_pair["metric_improvement"], abs=1e-6)
    gen = best_pair["generation_model"]
    ref = best_pair["reflection_model"]
    assert summary.best_pair_label == f"{gen} + {ref}"
    assert summary.completed_pairs == fixture_grid_result["completed_pairs"]
    assert summary.failed_pairs == fixture_grid_result["failed_pairs"]


def test_build_summary_grid_search_live_counters_from_latest_metrics() -> None:
    """When result is absent, completed_pairs/failed_pairs fall back to latest_metrics."""
    now = datetime.now(timezone.utc).isoformat()
    job_data = {
        "optimization_id": "gs2",
        "status": "running",
        "created_at": now,
        "started_at": now,
        "completed_at": None,
        "payload_overview": {"optimization_type": "grid_search"},
        "result": None,
        "latest_metrics": {"completed_so_far": 2, "failed_so_far": 1},
        "progress_count": 0,
        "log_count": 0,
    }
    summary = build_summary(job_data)

    assert summary.completed_pairs == 2
    assert summary.failed_pairs == 1


def test_build_summary_estimated_remaining_set_for_running_job() -> None:
    """build_summary formats estimated_remaining from the tqdm remaining key for running jobs."""
    now = datetime.now(timezone.utc).isoformat()
    job_data = {
        "optimization_id": "r1",
        "status": "running",
        "created_at": now,
        "started_at": now,
        "completed_at": None,
        "payload_overview": {},
        "result": None,
        "latest_metrics": {TQDM_REMAINING_KEY: 90},
        "progress_count": 0,
        "log_count": 0,
    }
    summary = build_summary(job_data)

    assert summary.estimated_remaining == "00:01:30"


def test_build_summary_estimated_remaining_absent_for_finished_job() -> None:
    """build_summary returns None for estimated_remaining when the job is already finished."""
    now = datetime.now(timezone.utc).isoformat()
    fixture_result = load_fixture("jobs/success_single_gepa.detail.json")["result"]
    job_data = {
        "optimization_id": "r2",
        "status": "success",
        "created_at": now,
        "started_at": now,
        "completed_at": now,
        "payload_overview": {},
        "result": fixture_result,
        "latest_metrics": {TQDM_REMAINING_KEY: 999},
        "progress_count": 0,
        "log_count": 0,
    }
    summary = build_summary(job_data)

    assert summary.estimated_remaining is None


class _MinimalJobStore:
    def __init__(self, count: int) -> None:
        self._count = count

    def count_jobs(self, *, username: str | None = None, **_: object) -> int:
        return self._count


def test_enforce_user_quota_allows_user_below_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """enforce_user_quota does not raise when the user's job count is below the cap."""
    monkeypatch.setattr(_helpers_mod.settings.__class__, "get_user_quota", lambda self, u: 100)
    store = _MinimalJobStore(42)
    enforce_user_quota(store, "alice")  # should not raise


def test_enforce_user_quota_rejects_user_at_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """enforce_user_quota raises HTTPException 409 when the user's job count equals the cap."""
    monkeypatch.setattr(_helpers_mod.settings.__class__, "get_user_quota", lambda self, u: 100)
    store = _MinimalJobStore(100)
    with pytest.raises(HTTPException) as exc:
        enforce_user_quota(store, "alice")
    assert exc.value.status_code == 409
    assert "100" in exc.value.detail


def test_enforce_user_quota_rejects_user_over_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """enforce_user_quota raises HTTPException 409 when the user's job count exceeds the cap."""
    monkeypatch.setattr(_helpers_mod.settings.__class__, "get_user_quota", lambda self, u: 100)
    store = _MinimalJobStore(250)
    with pytest.raises(HTTPException) as exc:
        enforce_user_quota(store, "alice")
    assert exc.value.status_code == 409


def test_enforce_user_quota_none_quota_bypasses_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """enforce_user_quota does not raise when get_user_quota returns None (unlimited)."""
    monkeypatch.setattr(_helpers_mod.settings.__class__, "get_user_quota", lambda self, u: None)
    store = _MinimalJobStore(9999)
    enforce_user_quota(store, "admin")  # should not raise


def _make_run_result_b64(obj: object) -> str:
    """Return a base64-encoded pickle of *obj*."""
    return base64.b64encode(pickle.dumps(obj)).decode()


def _run_job_data(optimization_id: str, program_obj: object) -> dict:
    """Build a minimal success-status job dict with a pickled program artifact."""
    now = datetime.now(timezone.utc).isoformat()
    artifact_b64 = _make_run_result_b64(program_obj)
    return {
        "optimization_id": optimization_id,
        "status": "success",
        "created_at": now,
        "started_at": now,
        "completed_at": now,
        "payload_overview": {"optimization_type": "run"},
        "payload": {},
        "result": {
            "module_name": "MyModule",
            "optimizer_name": "GEPA",
            "metric_name": "accuracy",
            "split_counts": {"train": 70, "val": 15, "test": 15},
            "baseline_test_metric": 0.5,
            "optimized_test_metric": 0.8,
            "program_artifact": {"program_pickle_base64": artifact_b64},
        },
        "latest_metrics": {},
        "message": None,
    }


class _JobStoreWithDelete:
    """Minimal store that supports get_job and delete_job for cache tests."""

    def __init__(self) -> None:
        self._jobs: dict = {}

    def seed(self, optimization_id: str, job_data: dict) -> None:
        self._jobs[optimization_id] = job_data

    def get_job(self, optimization_id: str) -> dict:
        if optimization_id not in self._jobs:
            raise KeyError(optimization_id)
        return dict(self._jobs[optimization_id])

    def delete_job(self, optimization_id: str) -> None:
        self._jobs.pop(optimization_id, None)


@pytest.fixture(autouse=True)
def _clear_program_cache_helpers() -> None:
    """Clear the module-level program cache before and after each test."""
    clear_program_cache()
    yield
    clear_program_cache()


def test_load_program_deleted_job_raises_404_before_cache() -> None:
    """If a job is deleted from the store and never cached, load_program raises 404."""
    store = _JobStoreWithDelete()
    # Job is never seeded — get_job will raise KeyError.
    with pytest.raises(HTTPException) as exc_info:
        load_program(store, "missing-job")
    assert exc_info.value.status_code == 404


def test_load_program_deleted_job_raises_404_even_when_cache_has_entry() -> None:
    """load_program always calls get_job BEFORE consulting the cache.
    So deleting a job from the store raises 404 on the NEXT call even if the
    program was cached from a prior call.  The cache does NOT act as a
    'serve from stale' fallback — it only avoids re-deserializing the pickle.
    """
    store = _JobStoreWithDelete()
    job_data = _run_job_data("job-then-deleted", object())
    store.seed("job-then-deleted", job_data)

    # First call succeeds and populates the cache.
    program, _, _ = load_program(store, "job-then-deleted")
    assert "job-then-deleted" in _helpers_mod._program_cache  # noqa: SLF001

    # Delete the job from the store.
    store.delete_job("job-then-deleted")

    # Second call still raises 404 because get_job is called first.
    with pytest.raises(HTTPException) as exc_info:
        load_program(store, "job-then-deleted")
    assert exc_info.value.status_code == 404


def test_load_program_cache_avoids_repeated_pickle_deserialisation() -> None:
    """When a job exists in the store and the program is already cached,
    load_program returns the SAME (identity-equal) object on every call,
    proving the cache is used and pickle.loads is not called again.
    """
    store = _JobStoreWithDelete()
    store.seed("job-cache-hit", _run_job_data("job-cache-hit", object()))

    first_call_program, _, _ = load_program(store, "job-cache-hit")
    second_call_program, _, _ = load_program(store, "job-cache-hit")

    # Both calls must return the same object instance (from cache).
    assert first_call_program is second_call_program


def test_load_program_call_exception_propagates_and_cache_entry_is_retained() -> None:
    """When the cached program's __call__ raises, the exception propagates to the
    caller.  The cache entry itself is NOT evicted — load_program does not call
    the program; the cache is a plain dict and is only written on first load.
    This test documents that calling the program is the caller's responsibility.
    """
    # Inject a raising callable directly into the module-level cache.
    class _RaisingProgram:
        def __call__(self, *args, **kwargs):
            raise RuntimeError("program exploded")

    raiser = _RaisingProgram()
    _helpers_mod._program_cache["direct-inject"] = raiser  # noqa: SLF001

    # Simulate the caller invoking the cached program — the RuntimeError propagates.
    with pytest.raises(RuntimeError, match="program exploded"):
        _helpers_mod._program_cache["direct-inject"]()  # noqa: SLF001

    # The cache entry must still be present after the failed call.
    assert "direct-inject" in _helpers_mod._program_cache  # noqa: SLF001
