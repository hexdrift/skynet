"""Probe the API from a real user's perspective to find UX pain points.

Focuses on error handling consistency, message clarity, and core flow gaps.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi.testclient import TestClient

from core.api.app import create_app
from core.models import RunResponse, SplitCounts


# ---------------------------------------------------------------------------
# Mock services
# ---------------------------------------------------------------------------
class HappyService:
    """Completes successfully with realistic progress events."""

    def validate_payload(self, payload) -> None:
        pass

    def run(self, payload, *, artifact_id=None, progress_callback=None) -> RunResponse:
        logger = logging.getLogger("dspy")
        logger.info("Starting optimization")

        if progress_callback:
            progress_callback("dataset_splits_ready", {"train": 3, "val": 1, "test": 1})
            time.sleep(0.05)
            progress_callback("baseline_evaluated", {"baseline_test_metric": 0.5})
            time.sleep(0.05)
            for i in range(3):
                progress_callback("optimizer_progress", {
                    "tqdm_total": 30, "tqdm_n": (i + 1) * 10,
                    "tqdm_elapsed": (i + 1) * 1.0,
                })
                time.sleep(0.05)
            progress_callback("optimized_evaluated", {"optimized_test_metric": 0.8})

        return RunResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name="metric",
            split_counts=SplitCounts(train=3, val=1, test=1),
            baseline_test_metric=0.5,
            optimized_test_metric=0.8,
            metric_improvement=0.3,
            runtime_seconds=0.3,
        )


class SlowService:
    """Takes longer so we can observe intermediate state."""

    def validate_payload(self, payload) -> None:
        pass

    def run(self, payload, *, artifact_id=None, progress_callback=None) -> RunResponse:
        if progress_callback:
            progress_callback("dataset_splits_ready", {"train": 3, "val": 1, "test": 1})
        time.sleep(0.3)
        if progress_callback:
            progress_callback("optimizer_progress", {"tqdm_total": 10, "tqdm_n": 5})
        time.sleep(0.3)
        if progress_callback:
            progress_callback("optimized_evaluated", {"optimized_test_metric": 0.7})

        return RunResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name="metric",
            split_counts=SplitCounts(train=3, val=1, test=1),
            baseline_test_metric=0.4,
            optimized_test_metric=0.7,
            metric_improvement=0.3,
            runtime_seconds=0.6,
        )


class FailingService:
    """Fails during execution with a realistic error."""

    def validate_payload(self, payload) -> None:
        pass

    def run(self, payload, *, artifact_id=None, progress_callback=None) -> RunResponse:
        if progress_callback:
            progress_callback("dataset_splits_ready", {"train": 3, "val": 1, "test": 1})
        raise RuntimeError("litellm.RateLimitError: Rate limit exceeded for model gpt-4o-mini")


VALID_PAYLOAD: Dict[str, Any] = {
    "username": "tester",
    "module_name": "cot",
    "signature_code": (
        "import dspy\n"
        "class Sig(dspy.Signature):\n"
        "    question: str = dspy.InputField()\n"
        "    answer: str = dspy.OutputField()\n"
    ),
    "metric_code": "def metric(example, pred, trace=None):\n    return 1.0\n",
    "optimizer_name": "dspy.BootstrapFewShot",
    "optimizer_kwargs": {},
    "compile_kwargs": {},
    "dataset": [{"q_col": "q1", "a_col": "a1"}, {"q_col": "q2", "a_col": "a2"}],
    "column_mapping": {"inputs": {"question": "q_col"}, "outputs": {"answer": "a_col"}},
    "split_fractions": {"train": 1.0, "val": 0.0, "test": 0.0},
    "shuffle": False,
    "seed": 42,
    "model_config": {"name": "openai/gpt-4o-mini"},
}


def _wait_terminal(client, job_id, timeout=12):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/jobs/{job_id}/summary")
        if resp.json()["status"] in ("success", "failed", "cancelled"):
            return resp.json()
        time.sleep(0.05)
    return client.get(f"/jobs/{job_id}/summary").json()


# ---------------------------------------------------------------------------
# GAP 1: Error response format inconsistency
# ---------------------------------------------------------------------------
def test_error_responses_have_consistent_shape(configured_env):
    """Every error response should have both 'error' and 'detail' keys.

    Currently 404/409 responses from HTTPException only have 'detail',
    while 400/422 validation responses have both 'error' and 'detail'.
    API consumers cannot write a single error handler.
    """
    app = create_app(service=HappyService())

    with TestClient(app) as client:
        # Complete a job first (needed for 409 tests)
        submit = client.post("/run", json=VALID_PAYLOAD)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]
        _wait_terminal(client, job_id)

        error_cases = [
            # (description, method, url, expected_status)
            ("nonexistent job detail", "GET", "/jobs/no-such-id", 404),
            ("nonexistent job summary", "GET", "/jobs/no-such-id/summary", 404),
            ("nonexistent job logs", "GET", "/jobs/no-such-id/logs", 404),
            ("nonexistent job artifact", "GET", "/jobs/no-such-id/artifact", 404),
            ("cancel completed job", "POST", f"/jobs/{job_id}/cancel", 409),
            ("delete running job submit", "DELETE", f"/jobs/{job_id}", None),  # might be 200 if terminal
        ]

        for desc, method, url, expected_status in error_cases:
            if method == "GET":
                resp = client.get(url)
            elif method == "POST":
                resp = client.post(url)
            elif method == "DELETE":
                resp = client.delete(url)
            else:
                continue

            if expected_status and resp.status_code != expected_status:
                continue  # skip if status doesn't match (e.g. delete succeeded)

            if resp.status_code >= 400:
                body = resp.json()
                assert "detail" in body, f"[{desc}] Missing 'detail' in {resp.status_code} response"
                assert "error" in body, (
                    f"[{desc}] Missing 'error' key in {resp.status_code} response. "
                    f"Body: {body}. "
                    f"API consumers need a consistent error shape."
                )


# ---------------------------------------------------------------------------
# GAP 2: message field shows internal event names during execution
# ---------------------------------------------------------------------------
def test_message_field_is_human_readable_during_execution(configured_env):
    """While a job is running, the message field should show a status
    message like 'Running optimization', not internal event names like
    'optimizer_progress' or 'dataset_splits_ready'.

    The progress event names belong in progress_events, not in the
    top-level message field that users read for status.
    """
    app = create_app(service=SlowService())

    with TestClient(app) as client:
        submit = client.post("/run", json=VALID_PAYLOAD)
        job_id = submit.json()["job_id"]

        # Collect messages while running
        internal_event_names = {
            "dataset_splits_ready",
            "baseline_evaluated",
            "optimizer_progress",
            "optimized_evaluated",
            "grid_pair_started",
            "grid_pair_completed",
            "grid_pair_failed",
        }
        leaked_messages = set()

        deadline = time.time() + 12
        while time.time() < deadline:
            resp = client.get(f"/jobs/{job_id}/summary")
            sbody = resp.json()
            msg = sbody.get("message")
            if msg and msg in internal_event_names:
                leaked_messages.add(msg)
            if sbody["status"] in ("success", "failed"):
                break
            time.sleep(0.05)

        assert not leaked_messages, (
            f"Internal event names leaked into job message field: {leaked_messages}. "
            f"The message field should show user-friendly status text, "
            f"not raw event identifiers."
        )


# ---------------------------------------------------------------------------
# GAP 3: Failed job error message visibility
# ---------------------------------------------------------------------------
def test_failed_job_gives_actionable_error_info(configured_env):
    """When a job fails, the user should be able to understand what went
    wrong from the job detail and logs, without needing to check server logs.
    """
    app = create_app(service=FailingService())

    with TestClient(app) as client:
        submit = client.post("/run", json=VALID_PAYLOAD)
        job_id = submit.json()["job_id"]

        result = _wait_terminal(client, job_id)
        assert result["status"] == "failed"

        # The message should contain the actual error
        assert result["message"] is not None
        assert len(result["message"]) > 0
        # Should mention the actual problem, not just "unknown error"
        assert "unknown" not in result["message"].lower() or "rate" in result["message"].lower()

        # Full job detail should also have the error
        detail = client.get(f"/jobs/{job_id}").json()
        assert detail["status"] == "failed"
        assert detail["message"] is not None

        # Logs should have ERROR entries with traceback
        logs = client.get(f"/jobs/{job_id}/logs", params={"level": "ERROR"}).json()
        # There should be at least one ERROR log with traceback info
        assert len(logs) > 0, (
            "Failed job has no ERROR-level logs. "
            "Users need the traceback to debug failures."
        )
        error_text = " ".join(log["message"] for log in logs)
        assert "RateLimitError" in error_text or "Rate limit" in error_text, (
            f"ERROR logs don't contain the actual error. Logs: {[l['message'][:100] for l in logs]}"
        )
