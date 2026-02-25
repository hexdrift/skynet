"""Tests for the logs endpoint pagination and filtering.

GET /jobs/{id}/logs supports limit, offset, and level query parameters.
These tests verify that pagination and level filtering work correctly
for a job that produces many mixed-level log entries.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from fastapi.testclient import TestClient

from core.api.app import create_app
from core.models import RunResponse, SplitCounts


# ---------------------------------------------------------------------------
# Mock service that produces lots of mixed-level logs
# ---------------------------------------------------------------------------

class VerboseService:
    """Service that emits many log entries at various levels."""

    def validate_payload(self, payload) -> None:
        pass

    def run(self, payload, *, artifact_id=None, progress_callback=None) -> RunResponse:
        import logging

        logger = logging.getLogger("dspy")
        # Emit a mix of log levels
        for i in range(20):
            logger.info("Optimizer iteration %d: evaluating candidates", i)
        logger.warning("Rate limit approaching, slowing down")
        for i in range(20, 30):
            logger.info("Optimizer iteration %d: evaluating candidates", i)
        logger.error("API call failed on iteration 28, retrying")
        logger.error("Retry failed: connection timeout after 30s")
        logger.info("Optimization completed despite errors")

        return RunResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name="metric",
            split_counts=SplitCounts(train=1, val=0, test=0),
            baseline_test_metric=0.5,
            optimized_test_metric=0.7,
            metric_improvement=0.2,
            optimization_metadata={},
            details={},
            runtime_seconds=0.1,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_PAYLOAD: Dict[str, Any] = {
    "username": "log_tester",
    "module_name": "demo_module",
    "module_kwargs": {},
    "signature_code": (
        "import dspy\n"
        "class Sig(dspy.Signature):\n"
        "    question: str = dspy.InputField()\n"
        "    answer: str = dspy.OutputField()\n"
    ),
    "metric_code": "def metric(example, pred, trace=None):\n    return 1.0\n",
    "optimizer_name": "demo_optimizer",
    "optimizer_kwargs": {},
    "compile_kwargs": {},
    "dataset": [{"question_col": "q1", "answer_col": "a1"}],
    "column_mapping": {
        "inputs": {"question": "question_col"},
        "outputs": {"answer": "answer_col"},
    },
    "split_fractions": {"train": 1.0, "val": 0.0, "test": 0.0},
    "shuffle": False,
    "seed": 42,
    "model_config": {"name": "dummy-model", "temperature": 0.1},
}


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
# Tests
# ---------------------------------------------------------------------------


def test_logs_pagination_limit(configured_env) -> None:
    """GET /jobs/{id}/logs?limit=5 should return at most 5 entries."""
    app = create_app(service=VerboseService())
    with TestClient(app) as client:
        submit = client.post("/run", json=RUN_PAYLOAD)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]
        _wait_terminal(client, job_id)

        # All logs
        all_logs = client.get(f"/jobs/{job_id}/logs")
        assert all_logs.status_code == 200
        total = len(all_logs.json())
        assert total > 5, f"Expected many logs, got {total}"

        # Request only 5
        limited = client.get(f"/jobs/{job_id}/logs", params={"limit": 5})
        assert limited.status_code == 200
        entries = limited.json()
        assert len(entries) == 5, (
            f"Expected 5 log entries with limit=5, got {len(entries)}"
        )


def test_logs_pagination_offset(configured_env) -> None:
    """GET /jobs/{id}/logs?offset=N should skip the first N entries."""
    app = create_app(service=VerboseService())
    with TestClient(app) as client:
        submit = client.post("/run", json=RUN_PAYLOAD)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]
        _wait_terminal(client, job_id)

        all_logs = client.get(f"/jobs/{job_id}/logs").json()
        total = len(all_logs)

        # Skip first 5, get next 3
        page = client.get(f"/jobs/{job_id}/logs", params={"offset": 5, "limit": 3})
        assert page.status_code == 200
        entries = page.json()
        assert len(entries) == 3, (
            f"Expected 3 entries with offset=5 limit=3, got {len(entries)}"
        )
        # The entries should match the all_logs slice
        assert entries[0]["message"] == all_logs[5]["message"], (
            "Offset entries don't match expected position in full log"
        )


def test_logs_level_filter(configured_env) -> None:
    """GET /jobs/{id}/logs?level=ERROR should return only ERROR-level entries."""
    app = create_app(service=VerboseService())
    with TestClient(app) as client:
        submit = client.post("/run", json=RUN_PAYLOAD)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]
        _wait_terminal(client, job_id)

        # All logs should have a mix of levels
        all_logs = client.get(f"/jobs/{job_id}/logs").json()
        levels = {log["level"] for log in all_logs}
        assert "ERROR" in levels, "Test expects ERROR entries in logs"
        assert "INFO" in levels, "Test expects INFO entries in logs"

        # Filter for errors only
        errors = client.get(f"/jobs/{job_id}/logs", params={"level": "ERROR"})
        assert errors.status_code == 200
        error_entries = errors.json()
        assert len(error_entries) > 0, "Expected at least one ERROR entry"
        assert all(e["level"] == "ERROR" for e in error_entries), (
            f"Level filter not working -- got levels: "
            f"{[e['level'] for e in error_entries]}"
        )
        assert len(error_entries) < len(all_logs), (
            "Filtering by ERROR should return fewer entries than all logs"
        )


def test_logs_default_returns_all(configured_env) -> None:
    """GET /jobs/{id}/logs with no params should return all entries (backwards compat)."""
    app = create_app(service=VerboseService())
    with TestClient(app) as client:
        submit = client.post("/run", json=RUN_PAYLOAD)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]
        _wait_terminal(client, job_id)

        logs = client.get(f"/jobs/{job_id}/logs")
        assert logs.status_code == 200
        entries = logs.json()
        assert isinstance(entries, list)
        assert len(entries) > 10, "Expected many log entries with default (no limit)"
