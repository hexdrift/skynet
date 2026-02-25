"""Tests for input validation and API error handling edge cases."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from conftest import make_payload
from core.api.app import create_app
from core.models import RunResponse, SplitCounts


class StubService:
    """Minimal service that passes validation and completes instantly."""

    def validate_payload(self, payload) -> None:
        pass

    def run(self, payload, *, artifact_id=None, progress_callback=None) -> RunResponse:
        return RunResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name="metric",
            split_counts=SplitCounts(train=1, val=0, test=0),
            optimization_metadata={},
            details={},
            runtime_seconds=0.01,
        )


def _wait_terminal(client, job_id, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/jobs/{job_id}/summary")
        if resp.status_code == 200:
            status = resp.json()["status"]
            if status in ("success", "failed", "cancelled"):
                return status
        time.sleep(0.05)
    return None


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------


def test_empty_dataset_422(configured_env) -> None:
    """Empty dataset list triggers Pydantic validator and returns 422."""
    app = create_app(service=StubService())
    with TestClient(app) as client:
        payload = make_payload()
        payload["dataset"] = []
        resp = client.post("/run", json=payload)
        assert resp.status_code == 422


def test_missing_required_fields_422(configured_env) -> None:
    """Payload with only username and no other fields returns 422."""
    app = create_app(service=StubService())
    with TestClient(app) as client:
        resp = client.post("/run", json={"username": "test"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "invalid_request"
        assert isinstance(body["detail"], list)
        assert len(body["detail"]) > 0
        assert all("field" in issue for issue in body["detail"])


@pytest.mark.parametrize("fractions", [
    {"train": 0.5, "val": 0.5, "test": 0.5},  # sum > 1
    {"train": 0.3, "val": 0.1, "test": 0.1},  # sum < 1
    {"train": -0.1, "val": 0.6, "test": 0.5},  # negative
])
def test_invalid_split_fractions_422(configured_env, fractions) -> None:
    """Split fractions that don't sum to 1.0 or are negative return 422."""
    app = create_app(service=StubService())
    with TestClient(app) as client:
        payload = make_payload()
        payload["split_fractions"] = fractions
        resp = client.post("/run", json=payload)
        assert resp.status_code == 422


def test_column_mapping_missing_fields_422(configured_env) -> None:
    """Column mapping without inputs or outputs returns 422."""
    app = create_app(service=StubService())
    with TestClient(app) as client:
        payload = make_payload()
        payload["column_mapping"] = {}
        resp = client.post("/run", json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Filter validation
# ---------------------------------------------------------------------------


def test_invalid_status_filter_422(configured_env) -> None:
    """GET /jobs?status=bogus returns 422."""
    app = create_app(service=StubService())
    with TestClient(app) as client:
        resp = client.get("/jobs", params={"status": "bogus"})
        assert resp.status_code == 422


def test_invalid_job_type_filter_422(configured_env) -> None:
    """GET /jobs?job_type=bogus returns 422."""
    app = create_app(service=StubService())
    with TestClient(app) as client:
        resp = client.get("/jobs", params={"job_type": "bogus"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Cancel / delete edge cases
# ---------------------------------------------------------------------------


def test_cancel_terminal_job_409(configured_env) -> None:
    """Cancelling an already-completed job returns 409."""
    app = create_app(service=StubService())
    with TestClient(app) as client:
        resp = client.post("/run", json=make_payload())
        job_id = resp.json()["job_id"]
        _wait_terminal(client, job_id)

        cancel = client.post(f"/jobs/{job_id}/cancel")
        assert cancel.status_code == 409


def test_delete_active_job_409(configured_env, monkeypatch) -> None:
    """Deleting a pending job returns 409."""
    monkeypatch.setenv("WORKER_POLL_INTERVAL", "5.0")
    app = create_app(service=StubService())
    with TestClient(app) as client:
        resp = client.post("/run", json=make_payload())
        job_id = resp.json()["job_id"]

        delete = client.delete(f"/jobs/{job_id}")
        assert delete.status_code == 409


def test_delete_nonexistent_job_404(configured_env) -> None:
    """Deleting a nonexistent job returns 404."""
    app = create_app(service=StubService())
    with TestClient(app) as client:
        resp = client.delete("/jobs/does-not-exist")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 404 on unknown job across all sub-endpoints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path_suffix", [
    "",
    "/summary",
    "/logs",
    "/payload",
    "/artifact",
    "/grid-result",
])
def test_nonexistent_job_endpoints_404(configured_env, path_suffix) -> None:
    """All job sub-endpoints return 404 for unknown job IDs."""
    app = create_app(service=StubService())
    with TestClient(app) as client:
        resp = client.get(f"/jobs/nonexistent-id{path_suffix}")
        assert resp.status_code == 404, f"Expected 404 for /jobs/nonexistent-id{path_suffix}, got {resp.status_code}"
