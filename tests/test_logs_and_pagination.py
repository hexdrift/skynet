"""Tests for log pagination edge cases and job listing filters."""
from __future__ import annotations

import time
from typing import Any, Dict

from fastapi.testclient import TestClient

from conftest import make_payload
from core.api.app import create_app
from core.models import RunResponse, SplitCounts


class VerboseService:
    """Service that emits many log entries at various levels."""

    def validate_payload(self, payload) -> None:
        pass

    def run(self, payload, *, artifact_id=None, progress_callback=None) -> RunResponse:
        import logging

        logger = logging.getLogger("dspy")
        for i in range(20):
            logger.info("Iteration %d", i)
        logger.warning("Rate limit approaching")
        logger.error("API call failed")
        logger.error("Retry failed")

        return RunResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name="metric",
            split_counts=SplitCounts(train=1, val=0, test=0),
            optimization_metadata={},
            details={},
            runtime_seconds=0.1,
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


def _submit_and_wait(client, payload=None):
    """Submit a job and wait for it to complete. Returns job_id."""
    resp = client.post("/run", json=payload or make_payload())
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]
    _wait_terminal(client, job_id)
    return job_id


def test_logs_offset_beyond_total_returns_empty(configured_env) -> None:
    """Requesting logs with offset > total count returns empty list."""
    app = create_app(service=VerboseService())
    with TestClient(app) as client:
        job_id = _submit_and_wait(client)

        all_logs = client.get(f"/jobs/{job_id}/logs").json()
        total = len(all_logs)
        assert total > 0

        resp = client.get(f"/jobs/{job_id}/logs", params={"offset": total + 100})
        assert resp.status_code == 200
        assert resp.json() == []


def test_logs_level_filter_case_insensitive(configured_env) -> None:
    """Level filter should work regardless of case (error, ERROR, Error)."""
    app = create_app(service=VerboseService())
    with TestClient(app) as client:
        job_id = _submit_and_wait(client)

        upper = client.get(f"/jobs/{job_id}/logs", params={"level": "ERROR"}).json()
        lower = client.get(f"/jobs/{job_id}/logs", params={"level": "error"}).json()
        mixed = client.get(f"/jobs/{job_id}/logs", params={"level": "Error"}).json()

        assert len(upper) > 0
        assert len(upper) == len(lower) == len(mixed)


def test_jobs_listing_offset_beyond_total_returns_empty_items(configured_env) -> None:
    """GET /jobs?offset=999 returns empty items but correct total."""
    app = create_app(service=VerboseService())
    with TestClient(app) as client:
        _submit_and_wait(client)

        resp = client.get("/jobs", params={"offset": 999})
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] >= 1


def test_jobs_listing_filter_by_job_type(configured_env) -> None:
    """GET /jobs?job_type=run returns only run jobs."""
    app = create_app(service=VerboseService())
    with TestClient(app) as client:
        _submit_and_wait(client)

        run_jobs = client.get("/jobs", params={"job_type": "run"})
        assert run_jobs.status_code == 200
        assert run_jobs.json()["total"] >= 1

        grid_jobs = client.get("/jobs", params={"job_type": "grid_search"})
        assert grid_jobs.status_code == 200
        assert grid_jobs.json()["total"] == 0
