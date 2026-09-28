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


def test_get_job_payload_redacts_api_keys_under_wire_aliases(client: TestClient, job_store: FakeJobStore) -> None:
    """Payloads stored with ``by_alias=True`` still have every inline api_key scrubbed."""
    secret_config = {"name": "openai/gpt-4o-mini", "extra": {"api_key": "sk-secret", "api_base": "http://gw"}}
    job_store.seed_job(
        "job-alias",
        payload={
            "model_config": secret_config,
            "reflection_model_config": secret_config,
            "task_model_config": secret_config,
            "generation_models": [secret_config],
            "reflection_models": [secret_config],
        },
        payload_overview={"job_type": "run"},
    )
    r = client.get("/optimizations/job-alias/payload")
    assert r.status_code == 200
    payload = r.json()["payload"]
    assert "sk-secret" not in r.text
    for field in ("model_config", "reflection_model_config", "task_model_config"):
        assert payload[field]["extra"] == {"api_base": "http://gw"}
    for field in ("generation_models", "reflection_models"):
        assert payload[field][0]["extra"] == {"api_base": "http://gw"}


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


def test_rename_job_syncs_embedding_task_name(
    client: TestClient, job_store: FakeJobStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Renaming propagates the trimmed new name to the embedding-row snapshot."""
    job_store.seed_job("rn-sync", payload_overview={})
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "core.api.routers.optimizations_meta.set_embedding_task_name",
        lambda store, opt_id, name: calls.append((opt_id, name)),
    )
    r = client.patch("/optimizations/rn-sync/name", json={"name": "  fresh name  "})
    assert r.status_code == 200
    assert calls == [("rn-sync", "fresh name")]


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
    assert r.json() == {"items": [], "truncated": False}


def test_analytics_models_empty(client: TestClient) -> None:
    """An empty job store returns an empty models list."""
    r = client.get("/analytics/models")
    assert r.status_code == 200
    assert r.json() == {"items": [], "truncated": False}


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


def test_analytics_dashboard_days_filter_excludes_older_runs(client, job_store):
    """Verify ``days`` drops runs created before the cutoff."""
    job_store.seed_job("old", created_at="2020-01-01T10:00:00+00:00")
    job_store.seed_job("new")
    resp = client.get("/analytics/dashboard?days=7")

    assert resp.status_code == 200
    assert resp.json()["filtered_total"] == 1


def test_analytics_dashboard_histograms_cover_every_run(client, job_store):
    """Verify the improvement histogram is open-ended and sums to the successful runs."""
    for i, improvement in enumerate([-0.1, 0.02, 0.5, 12.0, 45.0]):
        job_store.seed_job(
            f"job{i}",
            status="success",
            result={"baseline_test_metric": 50.0, "optimized_test_metric": 50.0 + improvement},
        )
    resp = client.get("/analytics/dashboard")

    assert resp.status_code == 200
    body = resp.json()
    histogram = body["improvement_histogram"]
    assert histogram[0]["lower"] is None
    assert histogram[-1]["upper"] is None
    assert sum(b["count"] for b in histogram) == 5
    assert histogram[0]["count"] == 1
    assert histogram[-1]["count"] == 2
    assert body["median_improvement"] == pytest.approx(12.0)
    assert body["best_improvement"] == pytest.approx(50.0)


def test_analytics_dashboard_optimizer_stats_roll_up_success_rate(client, job_store):
    """Verify per-optimizer stats count runs and compute success over terminal runs."""
    job_store.seed_job("a", payload_overview={"optimizer_name": "gepa"})
    job_store.seed_job("b", status="failed", payload_overview={"optimizer_name": "gepa"})
    job_store.seed_job("c", status="running", payload_overview={"optimizer_name": "gepa"})
    resp = client.get("/analytics/dashboard")

    assert resp.status_code == 200
    stats = resp.json()["optimizer_stats"]
    assert [s["name"] for s in stats] == ["gepa"]
    assert stats[0]["count"] == 3
    assert stats[0]["success_count"] == 1
    assert stats[0]["success_rate"] == pytest.approx(0.5)


def test_analytics_dashboard_timeline_uses_days_for_short_spans(client, job_store):
    """Verify a short span buckets by day and fills the gap with zero buckets."""
    job_store.seed_job("a", created_at="2024-03-01T10:00:00+00:00")
    job_store.seed_job("b", status="failed", created_at="2024-03-03T10:00:00+00:00")
    resp = client.get("/analytics/dashboard")

    body = resp.json()
    assert body["timeline_granularity"] == "day"
    assert [b["date"] for b in body["timeline"]] == ["2024-03-01", "2024-03-02", "2024-03-03"]
    assert body["timeline"][0]["success_count"] == 1
    assert body["timeline"][1]["count"] == 0
    assert body["timeline"][2]["failed_count"] == 1


def test_analytics_dashboard_timeline_widens_to_weeks_for_medium_spans(client, job_store):
    """Verify a multi-month span buckets by ISO week (Monday start)."""
    job_store.seed_job("a", created_at="2024-01-03T10:00:00+00:00")
    job_store.seed_job("b", created_at="2024-06-01T10:00:00+00:00")
    body = client.get("/analytics/dashboard").json()

    assert body["timeline_granularity"] == "week"
    assert body["timeline"][0]["date"] == "2024-01-01"
    assert body["timeline"][-1]["date"] == "2024-05-27"


def test_analytics_dashboard_timeline_widens_to_months_for_long_spans(client, job_store):
    """Verify a multi-year span buckets by calendar month."""
    job_store.seed_job("a", created_at="2022-01-15T10:00:00+00:00")
    job_store.seed_job("b", created_at="2024-06-01T10:00:00+00:00")
    body = client.get("/analytics/dashboard").json()

    assert body["timeline_granularity"] == "month"
    assert body["timeline"][0]["date"] == "2022-01-01"
    assert body["timeline"][-1]["date"] == "2024-06-01"
    assert len(body["timeline"]) == 30


def test_analytics_dashboard_date_to_widens_day_filter_to_a_range(client, job_store):
    """Verify ``date`` + ``date_to`` keep every run inside the inclusive range."""
    job_store.seed_job("before", created_at="2024-03-03T10:00:00+00:00")
    job_store.seed_job("start", created_at="2024-03-04T10:00:00+00:00")
    job_store.seed_job("end", created_at="2024-03-10T23:00:00+00:00")
    job_store.seed_job("after", created_at="2024-03-11T00:30:00+00:00")
    body = client.get("/analytics/dashboard?date=2024-03-04&date_to=2024-03-10").json()

    assert body["filtered_total"] == 2


def test_analytics_dashboard_job_type_filter_matches_histogram_buckets(client, job_store):
    """Verify ``job_type`` narrows to one bucket, including the derived workflow bucket."""
    job_store.seed_job("single", payload_overview={"optimization_type": "run"})
    job_store.seed_job("grid", payload_overview={"optimization_type": "grid_search"})
    job_store.seed_job("flow", payload_overview={"optimization_type": "run", "composition": "workflow"})

    assert client.get("/analytics/dashboard?job_type=grid_search").json()["filtered_total"] == 1
    workflow = client.get("/analytics/dashboard?job_type=workflow").json()
    assert workflow["filtered_total"] == 1
    assert workflow["job_type_counts"] == {"workflow": 1}


def test_analytics_dashboard_module_filter(client, job_store):
    """Verify ``module`` keeps only runs of that module."""
    job_store.seed_job("cot", payload_overview={"module_name": "chain_of_thought"})
    job_store.seed_job("predict", payload_overview={"module_name": "predict"})
    body = client.get("/analytics/dashboard?module=predict").json()

    assert body["filtered_total"] == 1
    assert body["module_counts"] == {"predict": 1}


def test_analytics_dashboard_improvement_range_echoes_histogram_edges(client, job_store):
    """Verify an improvement bucket's ``[lower, upper)`` edges select exactly its runs."""
    for i, improvement in enumerate([0.02, 0.05, 0.1, 0.3]):
        job_store.seed_job(
            f"job{i}",
            result={"baseline_test_metric": 0.5, "optimized_test_metric": 0.5 + improvement},
        )
    job_store.seed_job("no-result", status="failed")
    body = client.get("/analytics/dashboard?improvement_min=5&improvement_max=10").json()

    assert body["filtered_total"] == 1
    assert body["best_improvement"] == pytest.approx(5.0)
    open_ended = client.get("/analytics/dashboard?improvement_min=10").json()
    assert open_ended["filtered_total"] == 2


def test_analytics_dashboard_runtime_and_dataset_ranges(client, job_store):
    """Verify run-time (minutes) and dataset-row ranges drop runs outside or without a value."""
    job_store.seed_job(
        "fast",
        started_at="2024-03-01T10:00:00+00:00",
        completed_at="2024-03-01T10:02:00+00:00",
        payload_overview={"dataset_rows": 40},
    )
    job_store.seed_job(
        "slow",
        started_at="2024-03-01T10:00:00+00:00",
        completed_at="2024-03-01T10:40:00+00:00",
        payload_overview={"dataset_rows": 400},
    )
    job_store.seed_job("pending", status="pending", started_at=None, completed_at=None)

    assert client.get("/analytics/dashboard?runtime_min=1&runtime_max=5").json()["filtered_total"] == 1
    assert client.get("/analytics/dashboard?runtime_min=30").json()["filtered_total"] == 1
    assert client.get("/analytics/dashboard?dataset_max=50").json()["filtered_total"] == 1
    assert client.get("/analytics/dashboard?dataset_min=250&dataset_max=500").json()["filtered_total"] == 1
