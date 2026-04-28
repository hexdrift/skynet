"""Router-level tests using a fake job store and FastAPI TestClient.

These don't touch Postgres, don't call OpenAI, and don't spin up the real
worker — they exercise the extracted router factories in isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from .mocks import FakeJobStore


def test_get_job_logs_404_for_unknown_id(client: TestClient) -> None:
    """Requesting logs for an unknown job returns 404."""
    # NB: router_app fixture intentionally skips the app-level exception
    # handler that converts HTTPException -> {"error": ..., "detail": ...}.
    # Unit tests assert the status code only; full envelope shape is covered
    # by the live-server regression gate.
    r = client.get("/optimizations/missing/logs")
    assert r.status_code == 404


def test_get_job_logs_returns_entries(client: TestClient, job_store: FakeJobStore) -> None:
    """Seeded log entries are surfaced verbatim by the logs endpoint."""
    job_store.seed_job("job1")
    job_store._logs["job1"] = [
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": "INFO",
            "logger": "test",
            "message": "hello",
        }
    ]
    r = client.get("/optimizations/job1/logs")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["message"] == "hello"


def test_get_job_payload_404_for_unknown_id(client: TestClient) -> None:
    """A payload request against an unknown id returns 404."""
    r = client.get("/optimizations/nope/payload")
    assert r.status_code == 404


def test_get_job_payload_requires_payload_field(client: TestClient, job_store: FakeJobStore) -> None:
    """A job that exists but has no stored payload returns 404."""
    job_store.seed_job("job2", payload=None)
    r = client.get("/optimizations/job2/payload")
    assert r.status_code == 404


def test_get_job_payload_returns_when_present(client: TestClient, job_store: FakeJobStore) -> None:
    """A job with a stored payload returns that payload alongside metadata."""
    job_store.seed_job(
        "job3",
        payload={"dataset": [{"q": 1}]},
        payload_overview={"job_type": "run"},
    )
    r = client.get("/optimizations/job3/payload")
    assert r.status_code == 200
    body = r.json()
    assert body["optimization_id"] == "job3"
    assert body["optimization_type"] == "run"
    assert body["payload"]["dataset"] == [{"q": 1}]


def test_rename_job_validates_length(client: TestClient, job_store: FakeJobStore) -> None:
    """An empty rename payload is rejected by length validation (422)."""
    job_store.seed_job("rn1", payload_overview={})
    r = client.patch("/optimizations/rn1/name", json={"name": ""})
    assert r.status_code == 422  # min_length=1 fails


def test_rename_job_happy_path(client: TestClient, job_store: FakeJobStore) -> None:
    """Renaming a job updates the response and the underlying overview."""
    job_store.seed_job("rn2", payload_overview={})
    r = client.patch("/optimizations/rn2/name", json={"name": "my renamed job"})
    assert r.status_code == 200
    assert r.json()["name"] == "my renamed job"
    assert job_store._jobs["rn2"]["payload_overview"]["name"] == "my renamed job"


def test_rename_job_rejects_oversized(client: TestClient, job_store: FakeJobStore) -> None:
    """Names longer than the allowed maximum are rejected with 422."""
    job_store.seed_job("rn3", payload_overview={})
    r = client.patch("/optimizations/rn3/name", json={"name": "x" * 201})
    assert r.status_code == 422


def test_toggle_pin_flips_state(client: TestClient, job_store: FakeJobStore) -> None:
    """Toggling pin twice returns to the original false state."""
    job_store.seed_job("pin1", payload_overview={})
    r1 = client.patch("/optimizations/pin1/pin")
    assert r1.status_code == 200
    assert r1.json()["pinned"] is True
    r2 = client.patch("/optimizations/pin1/pin")
    assert r2.json()["pinned"] is False


def test_toggle_archive_flips_state(client: TestClient, job_store: FakeJobStore) -> None:
    """Toggling archive twice returns to the original false state."""
    job_store.seed_job("arc1", payload_overview={})
    r1 = client.patch("/optimizations/arc1/archive")
    assert r1.status_code == 200
    assert r1.json()["archived"] is True
    r2 = client.patch("/optimizations/arc1/archive")
    assert r2.json()["archived"] is False


def test_analytics_summary_empty_returns_zeros(client: TestClient) -> None:
    """An empty job store yields a zeroed-out analytics summary."""
    r = client.get("/analytics/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["total_jobs"] == 0
    assert body["success_count"] == 0
    assert body["success_rate"] == 0.0


def test_analytics_summary_counts_success(client: TestClient, job_store: FakeJobStore) -> None:
    """Successful and failed jobs roll up into per-status counters."""
    job_store.seed_job(
        "a1",
        status="success",
        payload_overview={"job_type": "run", "dataset_rows": 10},
        result={"baseline_test_metric": 0.5, "optimized_test_metric": 0.8},
    )
    job_store.seed_job(
        "a2",
        status="failed",
        payload_overview={"job_type": "run", "dataset_rows": 5},
    )
    r = client.get("/analytics/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["total_jobs"] == 2
    assert body["success_count"] == 1
    assert body["failed_count"] == 1
    assert body["total_dataset_rows"] == 15


def test_analytics_optimizers_empty(client: TestClient) -> None:
    """An empty job store returns an empty optimizers list."""
    r = client.get("/analytics/optimizers")
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_analytics_models_empty(client: TestClient) -> None:
    """An empty job store returns an empty models list."""
    r = client.get("/analytics/models")
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_analytics_summary_running_and_validating_fold_into_running_count(
    client: TestClient, job_store: FakeJobStore
) -> None:
    """``running`` and ``validating`` are both folded into the running counter."""
    job_store.seed_job("r1", status="running")
    job_store.seed_job("r2", status="validating")
    job_store.seed_job("r3", status="pending")
    r = client.get("/analytics/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["running_count"] == 2
    assert body["pending_count"] == 1


def test_analytics_summary_grid_search_aggregates_pair_counts(client: TestClient, job_store: FakeJobStore) -> None:
    """Grid-search jobs surface pair-level totals in the analytics summary."""
    job_store.seed_job(
        "gs1",
        status="success",
        payload_overview={"optimization_type": "grid_search", "total_pairs": 4},
        result={
            "best_pair": {
                "baseline_test_metric": 0.4,
                "optimized_test_metric": 0.7,
            },
            "completed_pairs": 3,
            "failed_pairs": 1,
        },
    )
    r = client.get("/analytics/summary")
    body = r.json()
    assert body["total_pairs"] == 4
    assert body["completed_pairs"] == 3
    assert body["failed_pairs"] == 1


def test_analytics_summary_success_rate_calculation(client: TestClient, job_store: FakeJobStore) -> None:
    """``success_rate`` is the ratio of successes to terminal jobs."""
    # success_rate = success_count / (success_count + failed_count)
    for i in range(3):
        job_store.seed_job(f"s{i}", status="success", payload_overview={"job_type": "run"})
    job_store.seed_job("f1", status="failed", payload_overview={"job_type": "run"})
    r = client.get("/analytics/summary")
    body = r.json()
    assert body["success_count"] == 3
    assert body["failed_count"] == 1
    assert body["success_rate"] == pytest.approx(0.75, rel=1e-4)


def test_analytics_optimizers_aggregates_correctly(client: TestClient, job_store: FakeJobStore) -> None:
    """Per-optimizer aggregates expose totals, success rate, and improvement."""
    job_store.seed_job(
        "opt1",
        status="success",
        payload_overview={"job_type": "run", "optimizer_name": "gepa"},
        result={"baseline_test_metric": 0.5, "optimized_test_metric": 0.8},
    )
    job_store.seed_job(
        "opt2",
        status="failed",
        payload_overview={"job_type": "run", "optimizer_name": "gepa"},
    )
    r = client.get("/analytics/optimizers")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["name"] == "gepa"
    assert item["total_jobs"] == 2
    assert item["success_count"] == 1
    assert item["success_rate"] == pytest.approx(0.5, rel=1e-4)
    assert item["avg_improvement"] == pytest.approx(0.3, abs=1e-5)


def test_analytics_models_aggregates_correctly(client: TestClient, job_store: FakeJobStore) -> None:
    """Per-model aggregates expose totals, use count, and average improvement."""
    job_store.seed_job(
        "m1",
        status="success",
        payload_overview={"job_type": "run", "model_name": "gpt-4o-mini"},
        result={"baseline_test_metric": 0.6, "optimized_test_metric": 0.9},
    )
    job_store.seed_job(
        "m2",
        status="success",
        payload_overview={"job_type": "run", "model_name": "gpt-4o-mini"},
        result={"baseline_test_metric": 0.5, "optimized_test_metric": 0.7},
    )
    r = client.get("/analytics/models")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["name"] == "gpt-4o-mini"
    assert item["total_jobs"] == 2
    assert item["use_count"] == 2
    assert item["avg_improvement"] == pytest.approx(0.25, abs=1e-5)


def test_analytics_dashboard_empty_store(client: TestClient) -> None:
    """An empty store yields a zeroed dashboard payload."""
    r = client.get("/analytics/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["filtered_total"] == 0
    assert body["success_count"] == 0
    assert body["timeline"] == []


def test_analytics_dashboard_populates_optimizer_counts(client: TestClient, job_store: FakeJobStore) -> None:
    """Dashboard ``optimizer_counts`` aggregate jobs across statuses."""
    job_store.seed_job(
        "d1",
        status="success",
        payload_overview={"optimization_type": "run", "optimizer_name": "gepa"},
    )
    job_store.seed_job(
        "d2",
        status="pending",
        payload_overview={"optimization_type": "run", "optimizer_name": "gepa"},
    )
    r = client.get("/analytics/dashboard")
    body = r.json()
    assert body["optimizer_counts"].get("gepa") == 2


def test_analytics_dashboard_date_filter_excludes_other_days(client: TestClient, job_store: FakeJobStore) -> None:
    """The ``date`` filter restricts results to that day."""
    job_store.seed_job(
        "dated",
        status="success",
        created_at="2024-03-15T10:00:00+00:00",
        started_at="2024-03-15T10:00:00+00:00",
        completed_at="2024-03-15T10:01:00+00:00",
        payload_overview={"optimization_type": "run"},
    )
    r = client.get("/analytics/dashboard?date=2024-03-16")
    assert r.json()["filtered_total"] == 0


def test_logs_level_filter_returns_only_matching_level(client: TestClient, job_store: FakeJobStore) -> None:
    """The ``?level=`` query filter returns only entries matching that level."""
    job_store.seed_job("lvl1")
    job_store._logs["lvl1"] = [
        {"timestamp": "2024-01-01T00:00:00+00:00", "level": "INFO", "logger": "x", "message": "info msg"},
        {"timestamp": "2024-01-01T00:00:01+00:00", "level": "ERROR", "logger": "x", "message": "err msg"},
    ]
    r = client.get("/optimizations/lvl1/logs?level=ERROR")
    assert r.status_code == 200
    entries = r.json()
    assert all(e["level"] == "ERROR" for e in entries)


def test_rename_job_404_for_missing_job(client: TestClient) -> None:
    """Renaming an unknown job returns 404."""
    r = client.patch("/optimizations/no-such-id/name", json={"name": "renamed"})
    assert r.status_code == 404


def test_pin_job_404_for_missing_job(client: TestClient) -> None:
    """Pinning an unknown job returns 404."""
    r = client.patch("/optimizations/no-such-id/pin")
    assert r.status_code == 404


def test_archive_job_404_for_missing_job(client: TestClient) -> None:
    """Archiving an unknown job returns 404."""
    r = client.patch("/optimizations/no-such-id/archive")
    assert r.status_code == 404


def test_rename_job_trims_whitespace(client: TestClient, job_store: FakeJobStore) -> None:
    """Surrounding whitespace is stripped from the new job name."""
    job_store.seed_job("trim1", payload_overview={})
    r = client.patch("/optimizations/trim1/name", json={"name": "  spaced  "})
    assert r.status_code == 200
    assert r.json()["name"] == "spaced"


def test_toggle_pin_third_call_returns_true_again(client: TestClient, job_store: FakeJobStore) -> None:
    """Pin toggling is symmetric across three consecutive calls."""
    job_store.seed_job("pin2", payload_overview={})
    client.patch("/optimizations/pin2/pin")  # → True
    client.patch("/optimizations/pin2/pin")  # → False
    r = client.patch("/optimizations/pin2/pin")  # → True
    assert r.json()["pinned"] is True
