"""Router-level tests using a fake job store and FastAPI TestClient.

These don't touch Postgres, don't call OpenAI, and don't spin up the real
worker — they exercise the extracted router factories in isolation.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from tests.unit.conftest import FakeJobStore


# ── /optimizations_meta router ─────────────────────────────────────────────

def test_get_job_logs_404_for_unknown_id(client: TestClient) -> None:
    # NB: router_app fixture intentionally skips the app-level exception
    # handler that converts HTTPException -> {"error": ..., "detail": ...}.
    # Unit tests assert the status code only; full envelope shape is covered
    # by the live-server regression gate.
    r = client.get("/optimizations/missing/logs")
    assert r.status_code == 404


def test_get_job_logs_returns_entries(client: TestClient, job_store: FakeJobStore) -> None:
    job_store.seed_job("job1")
    # Inject a log entry directly into the fake
    job_store._logs["job1"] = [
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
    r = client.get("/optimizations/nope/payload")
    assert r.status_code == 404


def test_get_job_payload_requires_payload_field(client: TestClient, job_store: FakeJobStore) -> None:
    # Job without payload -> 404 "Payload not available"
    job_store.seed_job("job2", payload=None)
    r = client.get("/optimizations/job2/payload")
    assert r.status_code == 404


def test_get_job_payload_returns_when_present(client: TestClient, job_store: FakeJobStore) -> None:
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


# ── Rename + pin + archive (PATCH) ─────────────────────────────────────────

def test_rename_job_validates_length(client: TestClient, job_store: FakeJobStore) -> None:
    job_store.seed_job("rn1", payload_overview={})
    r = client.patch("/optimizations/rn1/name", json={"name": ""})
    assert r.status_code == 422  # min_length=1 fails


def test_rename_job_happy_path(client: TestClient, job_store: FakeJobStore) -> None:
    job_store.seed_job("rn2", payload_overview={})
    r = client.patch("/optimizations/rn2/name", json={"name": "my renamed job"})
    assert r.status_code == 200
    assert r.json()["name"] == "my renamed job"
    # Persisted to overview
    assert job_store._jobs["rn2"]["payload_overview"]["name"] == "my renamed job"


def test_rename_job_rejects_oversized(client: TestClient, job_store: FakeJobStore) -> None:
    job_store.seed_job("rn3", payload_overview={})
    r = client.patch("/optimizations/rn3/name", json={"name": "x" * 201})
    assert r.status_code == 422


def test_toggle_pin_flips_state(client: TestClient, job_store: FakeJobStore) -> None:
    job_store.seed_job("pin1", payload_overview={})
    r1 = client.patch("/optimizations/pin1/pin")
    assert r1.status_code == 200
    assert r1.json()["pinned"] is True
    r2 = client.patch("/optimizations/pin1/pin")
    assert r2.json()["pinned"] is False


def test_toggle_archive_flips_state(client: TestClient, job_store: FakeJobStore) -> None:
    job_store.seed_job("arc1", payload_overview={})
    r1 = client.patch("/optimizations/arc1/archive")
    assert r1.status_code == 200
    assert r1.json()["archived"] is True
    r2 = client.patch("/optimizations/arc1/archive")
    assert r2.json()["archived"] is False


# ── /analytics router ───────────────────────────────────────────────────────

def test_analytics_summary_empty_returns_zeros(client: TestClient) -> None:
    r = client.get("/analytics/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["total_jobs"] == 0
    assert body["success_count"] == 0
    assert body["success_rate"] == 0.0


def test_analytics_summary_counts_success(client: TestClient, job_store: FakeJobStore) -> None:
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
    r = client.get("/analytics/optimizers")
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_analytics_models_empty(client: TestClient) -> None:
    r = client.get("/analytics/models")
    assert r.status_code == 200
    assert r.json() == {"items": []}
