"""Production end-to-end tests using real OpenAI LLM calls.

No mocks. Real API calls. Real PostgreSQL. Real job lifecycle.
Tests every scenario a real user would encounter.

Requires:
    - OPENAI_API_KEY in backend/.env
    - Backend server running on localhost:8000
    - PostgreSQL running with skynet database

Run:
    cd backend && ../.venv/bin/python -m pytest tests/test_llm_integration.py -v
"""
from __future__ import annotations

import json
import time
from typing import Optional

import requests
import pytest

from conftest import requires_llm

BASE_URL = "http://localhost:8000"


def _server_available() -> bool:
    """Check if the backend server is running."""
    try:
        return requests.get(f"{BASE_URL}/health", timeout=2).status_code == 200
    except Exception:
        return False


requires_server = pytest.mark.skipif(
    not _server_available(),
    reason="Backend server not running on localhost:8000 — start with: cd backend && ../.venv/bin/python main.py",
)


def _wait_for_terminal(job_id: str, timeout: float = 180) -> dict:
    """Poll a job until it reaches a terminal status.

    Args:
        job_id: The job identifier.
        timeout: Maximum seconds to wait.

    Returns:
        The job detail response dict.

    Raises:
        TimeoutError: If the job doesn't finish in time.
    """
    terminal = {"success", "failed", "cancelled"}
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(f"{BASE_URL}/jobs/{job_id}", timeout=10)
        data = r.json()
        if data.get("status") in terminal:
            return data
        time.sleep(3)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout}s (last status: {data.get('status')})")


def _submit_run_job(username: str = "e2e-test", model: str = "gpt-4o-mini") -> str:
    """Submit a real optimization job and return the job ID.

    Args:
        username: Username for the job.
        model: LLM model to use.

    Returns:
        The job ID string.
    """
    payload = {
        "username": username,
        "module_name": "predict",
        "signature_code": (
            "import dspy\n"
            "class QA(dspy.Signature):\n"
            '    """Answer the math question with just the number."""\n'
            "    question: str = dspy.InputField()\n"
            "    answer: str = dspy.OutputField()\n"
        ),
        "metric_code": (
            "def metric(example, pred, trace=None):\n"
            "    return example.answer.strip() == pred.answer.strip()\n"
        ),
        "optimizer_name": "miprov2",
        "dataset": [
            {"question": "What is 2+2?", "answer": "4"},
            {"question": "What is 3+3?", "answer": "6"},
            {"question": "What is 5+5?", "answer": "10"},
            {"question": "What is 1+1?", "answer": "2"},
            {"question": "What is 4+4?", "answer": "8"},
        ],
        "column_mapping": {"inputs": {"question": "question"}, "outputs": {"answer": "answer"}},
        "split_fractions": {"train": 0.6, "val": 0.2, "test": 0.2},
        "shuffle": False,
        "seed": 42,
        "model_config": {"name": model, "temperature": 0.1, "max_tokens": 64},
    }
    r = requests.post(f"{BASE_URL}/run", json=payload, timeout=10)
    assert r.status_code == 201, f"Submit failed ({r.status_code}): {r.text}"
    return r.json()["job_id"]


def _cleanup(job_id: str) -> None:
    """Delete a job, ignoring errors."""
    try:
        requests.delete(f"{BASE_URL}/jobs/{job_id}", timeout=5)
    except Exception:
        pass


# ════════════════════════════════════════════
# 1. FULL JOB LIFECYCLE
# ════════════════════════════════════════════

@requires_llm
@requires_server
class TestFullJobLifecycle:
    """Complete optimization lifecycle with real LLM."""

    def test_submit_returns_pending(self):
        """POST /run returns 201 with status=pending."""
        job_id = _submit_run_job(username="lifecycle-submit")
        r = requests.get(f"{BASE_URL}/jobs/{job_id}", timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] in ("pending", "validating", "running")
        _cleanup(job_id)

    def test_job_completes_successfully(self):
        """Job reaches success status with optimization results."""
        job_id = _submit_run_job(username="lifecycle-complete")
        data = _wait_for_terminal(job_id)

        assert data["status"] == "success", f"Job failed: {data.get('message')}"
        result = data.get("result")
        assert result is not None, "No result object"
        assert result.get("baseline_test_metric") is not None, "Missing baseline metric"
        assert result.get("optimized_test_metric") is not None, "Missing optimized metric"
        assert result.get("metric_improvement") is not None, "Missing improvement"
        assert result.get("runtime_seconds") is not None, "Missing runtime"
        assert result["runtime_seconds"] > 0
        _cleanup(job_id)

    def test_optimized_prompt_generated(self):
        """Successful job produces an optimized prompt with instructions and demos."""
        job_id = _submit_run_job(username="lifecycle-prompt")
        data = _wait_for_terminal(job_id)
        assert data["status"] == "success"

        artifact = data["result"]["program_artifact"]
        assert artifact is not None, "No artifact"

        prompt = artifact.get("optimized_prompt")
        assert prompt is not None, "No optimized prompt"
        assert len(prompt.get("instructions", "")) > 10, "Instructions too short"
        assert len(prompt.get("input_fields", [])) > 0, "No input fields"
        assert len(prompt.get("output_fields", [])) > 0, "No output fields"
        assert len(prompt.get("formatted_prompt", "")) > 20, "Formatted prompt too short"
        _cleanup(job_id)

    def test_artifact_downloadable(self):
        """GET /jobs/{id}/artifact returns pickle and metadata."""
        job_id = _submit_run_job(username="lifecycle-artifact")
        _wait_for_terminal(job_id)

        r = requests.get(f"{BASE_URL}/jobs/{job_id}/artifact", timeout=10)
        assert r.status_code == 200

        artifact = r.json().get("program_artifact")
        assert artifact is not None
        assert artifact.get("program_pickle_base64") is not None
        assert len(artifact["program_pickle_base64"]) > 100, "Pickle too small"
        assert artifact.get("metadata") is not None
        deps = artifact["metadata"].get("dependency_versions", {})
        assert "python" in deps
        assert "dspy" in deps
        _cleanup(job_id)

    def test_logs_populated(self):
        """Completed job has meaningful log entries."""
        job_id = _submit_run_job(username="lifecycle-logs")
        data = _wait_for_terminal(job_id)

        logs = data.get("logs", [])
        assert len(logs) > 5, f"Too few logs: {len(logs)}"

        # Check log structure
        for log in logs[:3]:
            assert "timestamp" in log
            assert "level" in log
            assert "message" in log
            assert log["level"] in ("DEBUG", "INFO", "WARNING", "ERROR")

        # Should have INFO-level optimizer messages
        info_logs = [l for l in logs if l["level"] == "INFO"]
        assert len(info_logs) > 0, "No INFO logs"
        _cleanup(job_id)

    def test_payload_preserved(self):
        """GET /jobs/{id}/payload returns the original request."""
        job_id = _submit_run_job(username="lifecycle-payload")

        r = requests.get(f"{BASE_URL}/jobs/{job_id}/payload", timeout=10)
        assert r.status_code == 200

        payload = r.json()["payload"]
        assert payload["username"] == "lifecycle-payload"
        assert payload["module_name"] == "predict"
        assert payload["optimizer_name"] == "miprov2"
        assert payload["model_config"]["name"] == "gpt-4o-mini"
        assert len(payload["dataset"]) == 5
        assert payload["column_mapping"]["inputs"]["question"] == "question"
        assert payload["column_mapping"]["outputs"]["answer"] == "answer"

        _wait_for_terminal(job_id)
        _cleanup(job_id)

    def test_delete_after_success(self):
        """DELETE removes the job and subsequent GET returns 404."""
        job_id = _submit_run_job(username="lifecycle-delete")
        _wait_for_terminal(job_id)

        r = requests.delete(f"{BASE_URL}/jobs/{job_id}", timeout=10)
        assert r.status_code == 200
        assert r.json()["deleted"] is True

        r = requests.get(f"{BASE_URL}/jobs/{job_id}", timeout=10)
        assert r.status_code == 404


# ════════════════════════════════════════════
# 2. SSE STREAMING
# ════════════════════════════════════════════

@requires_llm
@requires_server
class TestSSEStreaming:
    """Real-time streaming via Server-Sent Events."""

    def test_stream_receives_events_during_run(self):
        """SSE stream delivers status events while job is running."""
        job_id = _submit_run_job(username="sse-events")

        events = []
        try:
            r = requests.get(f"{BASE_URL}/jobs/{job_id}/stream", stream=True, timeout=60)
            for line in r.iter_lines(decode_unicode=True):
                if line and line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    events.append(data)
                    if data.get("status") in ("success", "failed", "cancelled"):
                        break
                if line and line.startswith("event: done"):
                    break
                if len(events) >= 10:
                    break
        except Exception:
            pass

        assert len(events) > 0, "No SSE events received"
        assert events[0]["job_id"] == job_id
        assert events[0]["status"] is not None

        _wait_for_terminal(job_id)
        _cleanup(job_id)

    def test_stream_completed_job_sends_done(self):
        """SSE stream on an already-completed job sends one event then done."""
        job_id = _submit_run_job(username="sse-completed")
        _wait_for_terminal(job_id)

        events = []
        done_received = False
        try:
            r = requests.get(f"{BASE_URL}/jobs/{job_id}/stream", stream=True, timeout=10)
            for line in r.iter_lines(decode_unicode=True):
                if line and line.startswith("data:"):
                    events.append(json.loads(line[5:].strip()))
                if line and line.startswith("event: done"):
                    done_received = True
                    break
        except Exception:
            pass

        assert len(events) >= 1, "Should receive at least one status event"
        assert events[0]["status"] in ("success", "failed"), f"Unexpected status: {events[0]['status']}"
        assert done_received, "Should receive 'done' event"
        _cleanup(job_id)

    def test_stream_nonexistent_job_returns_404(self):
        """SSE stream on nonexistent job returns 404."""
        r = requests.get(f"{BASE_URL}/jobs/fake-id-12345/stream", timeout=5)
        assert r.status_code == 404


# ════════════════════════════════════════════
# 3. CANCEL & ERROR HANDLING
# ════════════════════════════════════════════

@requires_llm
@requires_server
class TestCancelAndErrors:
    """Job cancellation and error scenarios."""

    def test_cancel_active_job(self):
        """Cancel a job while it's running."""
        job_id = _submit_run_job(username="cancel-active")
        time.sleep(2)

        r = requests.post(f"{BASE_URL}/jobs/{job_id}/cancel", timeout=10)
        # May be 200 (cancelled) or 409 (already finished fast)
        assert r.status_code in (200, 409)

        data = _wait_for_terminal(job_id, timeout=30)
        assert data["status"] in ("cancelled", "success", "failed")
        _cleanup(job_id)

    def test_cancel_terminal_job_returns_409(self):
        """Cancel on already-finished job returns 409."""
        job_id = _submit_run_job(username="cancel-terminal")
        _wait_for_terminal(job_id)

        r = requests.post(f"{BASE_URL}/jobs/{job_id}/cancel", timeout=10)
        assert r.status_code == 409
        _cleanup(job_id)

    def test_delete_active_job_returns_409(self):
        """Cannot delete a job that hasn't finished."""
        job_id = _submit_run_job(username="delete-active")

        # Try to delete immediately
        r = requests.delete(f"{BASE_URL}/jobs/{job_id}", timeout=10)
        assert r.status_code == 409, f"Expected 409, got {r.status_code}"

        _wait_for_terminal(job_id)
        _cleanup(job_id)

    def test_artifact_before_completion_returns_409(self):
        """GET /artifact on a running job returns 409."""
        job_id = _submit_run_job(username="artifact-early")

        r = requests.get(f"{BASE_URL}/jobs/{job_id}/artifact", timeout=10)
        assert r.status_code == 409

        _wait_for_terminal(job_id)
        _cleanup(job_id)


# ════════════════════════════════════════════
# 4. FILTERING & SEARCH
# ════════════════════════════════════════════

@requires_llm
@requires_server
class TestFilteringAndSearch:
    """Job listing, filtering, and pagination."""

    def test_filter_by_username(self):
        """Jobs are filterable by username."""
        unique = f"filter-user-{int(time.time())}"
        job_id = _submit_run_job(username=unique)

        r = requests.get(f"{BASE_URL}/jobs?username={unique}", timeout=10)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        assert all(item["username"] == unique for item in items)

        _wait_for_terminal(job_id)
        _cleanup(job_id)

    def test_filter_by_status(self):
        """Jobs are filterable by status."""
        job_id = _submit_run_job(username="filter-status")
        _wait_for_terminal(job_id)

        final_status = requests.get(f"{BASE_URL}/jobs/{job_id}", timeout=10).json()["status"]
        r = requests.get(f"{BASE_URL}/jobs?status={final_status}", timeout=10)
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(item["status"] == final_status for item in items)
        _cleanup(job_id)

    def test_filter_by_job_type(self):
        """Jobs are filterable by type."""
        job_id = _submit_run_job(username="filter-type")

        r = requests.get(f"{BASE_URL}/jobs?job_type=run", timeout=10)
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(item["job_type"] == "run" for item in items)

        _wait_for_terminal(job_id)
        _cleanup(job_id)

    def test_pagination(self):
        """Pagination limit and offset work correctly."""
        job_id = _submit_run_job(username="filter-page")

        r = requests.get(f"{BASE_URL}/jobs?limit=1", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) <= 1
        assert data["limit"] == 1

        r = requests.get(f"{BASE_URL}/jobs?offset=99999", timeout=10)
        assert r.status_code == 200
        assert len(r.json()["items"]) == 0

        _wait_for_terminal(job_id)
        _cleanup(job_id)

    def test_no_results_for_unknown_user(self):
        """Unknown username returns empty results."""
        r = requests.get(f"{BASE_URL}/jobs?username=nobody-exists-xyz-123", timeout=10)
        assert r.status_code == 200
        assert r.json()["total"] == 0
        assert r.json()["items"] == []


# ════════════════════════════════════════════
# 5. CONCURRENT JOBS
# ════════════════════════════════════════════

@requires_llm
@requires_server
class TestConcurrentJobs:
    """Multiple jobs running simultaneously."""

    def test_two_concurrent_jobs(self):
        """Two jobs submitted back-to-back both complete."""
        job1 = _submit_run_job(username="concurrent-1")
        job2 = _submit_run_job(username="concurrent-2")

        # Both should be tracked
        r = requests.get(f"{BASE_URL}/queue", timeout=10)
        assert r.status_code == 200
        queue = r.json()
        assert queue["pending_jobs"] + queue["active_jobs"] >= 0  # sanity

        data1 = _wait_for_terminal(job1)
        data2 = _wait_for_terminal(job2)

        # Both reached terminal
        assert data1["status"] in ("success", "failed")
        assert data2["status"] in ("success", "failed")

        _cleanup(job1)
        _cleanup(job2)


# ════════════════════════════════════════════
# 6. VALIDATION (real API, not mocked)
# ════════════════════════════════════════════

@requires_llm
@requires_server
class TestValidationWithRealAPI:
    """Input validation on the live server."""

    def test_empty_dataset_rejected(self):
        """POST /run with empty dataset returns 422."""
        payload = {
            "username": "validation-empty",
            "module_name": "predict",
            "signature_code": "import dspy\nclass S(dspy.Signature):\n    q: str = dspy.InputField()\n    a: str = dspy.OutputField()",
            "metric_code": "def metric(e, p, t=None): return 1.0",
            "optimizer_name": "miprov2",
            "dataset": [],
            "column_mapping": {"inputs": {"q": "q"}, "outputs": {"a": "a"}},
            "model_config": {"name": "gpt-4o-mini"},
        }
        r = requests.post(f"{BASE_URL}/run", json=payload, timeout=10)
        assert r.status_code == 422

    def test_missing_required_fields_rejected(self):
        """POST /run with missing fields returns 422."""
        r = requests.post(f"{BASE_URL}/run", json={"username": "test"}, timeout=10)
        assert r.status_code == 422

    def test_invalid_temperature_rejected(self):
        """POST /run with temperature > 2.0 returns 422."""
        payload = {
            "username": "validation-temp",
            "module_name": "predict",
            "signature_code": "import dspy\nclass S(dspy.Signature):\n    q: str = dspy.InputField()\n    a: str = dspy.OutputField()",
            "metric_code": "def metric(e, p, t=None): return 1.0",
            "optimizer_name": "miprov2",
            "dataset": [{"q": "hi", "a": "bye"}],
            "column_mapping": {"inputs": {"q": "q"}, "outputs": {"a": "a"}},
            "model_config": {"name": "gpt-4o-mini", "temperature": 5.0},
        }
        r = requests.post(f"{BASE_URL}/run", json=payload, timeout=10)
        assert r.status_code == 422

    def test_invalid_split_fractions_rejected(self):
        """POST /run with split fractions that don't sum to 1.0 returns 422."""
        payload = {
            "username": "validation-split",
            "module_name": "predict",
            "signature_code": "import dspy\nclass S(dspy.Signature):\n    q: str = dspy.InputField()\n    a: str = dspy.OutputField()",
            "metric_code": "def metric(e, p, t=None): return 1.0",
            "optimizer_name": "miprov2",
            "dataset": [{"q": "hi", "a": "bye"}],
            "column_mapping": {"inputs": {"q": "q"}, "outputs": {"a": "a"}},
            "split_fractions": {"train": 0.5, "val": 0.5, "test": 0.5},
            "model_config": {"name": "gpt-4o-mini"},
        }
        r = requests.post(f"{BASE_URL}/run", json=payload, timeout=10)
        assert r.status_code == 422

    def test_nonexistent_job_returns_404(self):
        """All endpoints return 404 for nonexistent jobs."""
        fake = "does-not-exist-12345"
        for path in ["", "/summary", "/logs", "/payload", "/artifact", "/grid-result"]:
            r = requests.get(f"{BASE_URL}/jobs/{fake}{path}", timeout=5)
            assert r.status_code == 404, f"GET /jobs/{fake}{path} returned {r.status_code}"

        r = requests.post(f"{BASE_URL}/jobs/{fake}/cancel", timeout=5)
        assert r.status_code == 404

        r = requests.delete(f"{BASE_URL}/jobs/{fake}", timeout=5)
        assert r.status_code == 404


# ════════════════════════════════════════════
# 6. SERVING OPTIMIZED PROGRAMS
# ════════════════════════════════════════════

@requires_llm
@requires_server
class TestServingEndpoints:
    """Test serving inference on optimized programs."""

    @pytest.fixture(scope="class")
    def completed_job_id(self) -> str:
        """Submit a job and wait for it to complete.

        Returns:
            str: Job ID of a successfully completed optimization.
        """
        job_id = _submit_run_job(username="serve-test")
        data = _wait_for_terminal(job_id)
        assert data["status"] == "success", f"Job failed: {data.get('message')}"
        return job_id

    def test_serve_info_returns_signature(self, completed_job_id: str):
        """GET /serve/{id}/info returns program metadata."""
        r = requests.get(f"{BASE_URL}/serve/{completed_job_id}/info", timeout=10)
        assert r.status_code == 200
        info = r.json()

        assert info["job_id"] == completed_job_id
        assert info["module_name"] == "predict"
        assert info["optimizer_name"] == "miprov2"
        assert "question" in info["input_fields"]
        assert "answer" in info["output_fields"]
        assert info["model_name"]  # not empty

    def test_serve_inference_returns_answer(self, completed_job_id: str):
        """POST /serve/{id} runs inference and returns outputs."""
        r = requests.post(
            f"{BASE_URL}/serve/{completed_job_id}",
            json={"inputs": {"question": "What is 7+3?"}},
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()

        assert data["job_id"] == completed_job_id
        assert "answer" in data["outputs"]
        assert data["outputs"]["answer"]  # not empty
        assert data["input_fields"] == ["question"]
        assert data["output_fields"] == ["answer"]
        assert data["model_used"]

    def test_serve_with_model_override(self, completed_job_id: str):
        """POST /serve/{id} with model_config_override uses the specified model."""
        r = requests.post(
            f"{BASE_URL}/serve/{completed_job_id}",
            json={
                "inputs": {"question": "What is 10+10?"},
                "model_config_override": {"name": "gpt-4o-mini", "temperature": 0.0, "max_tokens": 32},
            },
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["model_used"] == "gpt-4o-mini"
        assert "answer" in data["outputs"]

    def test_serve_missing_input_field(self, completed_job_id: str):
        """POST /serve/{id} with missing required input returns 400."""
        r = requests.post(
            f"{BASE_URL}/serve/{completed_job_id}",
            json={"inputs": {"wrong_field": "hello"}},
            timeout=10,
        )
        assert r.status_code == 400
        assert "missing" in r.json()["detail"].lower() or "Missing" in r.json()["detail"]

    def test_serve_empty_inputs_rejected(self, completed_job_id: str):
        """POST /serve/{id} with empty inputs returns 422."""
        r = requests.post(
            f"{BASE_URL}/serve/{completed_job_id}",
            json={"inputs": {}},
            timeout=10,
        )
        assert r.status_code == 422

    def test_serve_nonexistent_job_returns_404(self):
        """POST /serve/{id} for nonexistent job returns 404."""
        r = requests.post(
            f"{BASE_URL}/serve/does-not-exist-serve",
            json={"inputs": {"question": "hello"}},
            timeout=10,
        )
        assert r.status_code == 404

    def test_serve_info_nonexistent_returns_404(self):
        """GET /serve/{id}/info for nonexistent job returns 404."""
        r = requests.get(f"{BASE_URL}/serve/does-not-exist-serve/info", timeout=10)
        assert r.status_code == 404

    def test_serve_pending_job_returns_409(self):
        """Serving a job that hasn't finished returns 409."""
        job_id = _submit_run_job(username="serve-pending")
        # Immediately try to serve before it completes
        r = requests.post(
            f"{BASE_URL}/serve/{job_id}",
            json={"inputs": {"question": "hello"}},
            timeout=10,
        )
        assert r.status_code == 409
        # Clean up
        requests.post(f"{BASE_URL}/jobs/{job_id}/cancel", timeout=5)
        time.sleep(1)
        _cleanup(job_id)

    def test_serve_multiple_queries(self, completed_job_id: str):
        """Multiple sequential queries work (program cache is reused)."""
        questions = ["What is 1+1?", "What is 9+9?", "What is 100+200?"]
        for q in questions:
            r = requests.post(
                f"{BASE_URL}/serve/{completed_job_id}",
                json={"inputs": {"question": q}},
                timeout=30,
            )
            assert r.status_code == 200
            assert r.json()["outputs"]["answer"]  # not empty


# ════════════════════════════════════════════
# 7. GRID SEARCH LIFECYCLE
# ════════════════════════════════════════════

@requires_llm
@requires_server
class TestGridSearchLifecycle:
    """Full grid search job lifecycle with real LLM."""

    @pytest.fixture(scope="class")
    def grid_job(self) -> dict:
        """Submit a grid search job and wait for completion.

        Returns:
            dict: Final job status response.
        """
        payload = {
            "username": "grid-lifecycle",
            "module_name": "predict",
            "signature_code": (
                "import dspy\n"
                "class QA(dspy.Signature):\n"
                '    """Answer the math question."""\n'
                "    question: str = dspy.InputField()\n"
                "    answer: str = dspy.OutputField()\n"
            ),
            "metric_code": (
                "def metric(example, pred, trace=None):\n"
                "    return example.answer.strip() == pred.answer.strip()\n"
            ),
            "optimizer_name": "miprov2",
            "dataset": [
                {"question": "What is 2+2?", "answer": "4"},
                {"question": "What is 3+3?", "answer": "6"},
                {"question": "What is 5+5?", "answer": "10"},
                {"question": "What is 1+1?", "answer": "2"},
                {"question": "What is 4+4?", "answer": "8"},
            ],
            "column_mapping": {"inputs": {"question": "question"}, "outputs": {"answer": "answer"}},
            "split_fractions": {"train": 0.6, "val": 0.2, "test": 0.2},
            "shuffle": False,
            "generation_models": [{"name": "gpt-4o-mini", "temperature": 0.1, "max_tokens": 64}],
            "reflection_models": [{"name": "gpt-4o-mini", "temperature": 0.1, "max_tokens": 64}],
        }
        r = requests.post(f"{BASE_URL}/grid-search", json=payload, timeout=10)
        assert r.status_code == 201
        job_id = r.json()["job_id"]
        assert r.json()["job_type"] == "grid_search"

        data = _wait_for_terminal(job_id)
        assert data["status"] == "success", f"Grid search failed: {data.get('message')}"
        return data

    def test_grid_result_has_pair_results(self, grid_job: dict):
        """Grid search result includes pair_results with metrics."""
        job_id = grid_job["job_id"]
        r = requests.get(f"{BASE_URL}/jobs/{job_id}/grid-result", timeout=10)
        assert r.status_code == 200
        gr = r.json()
        assert gr["total_pairs"] == 1
        assert gr["completed_pairs"] == 1
        assert gr["failed_pairs"] == 0
        assert len(gr["pair_results"]) == 1
        pair = gr["pair_results"][0]
        assert pair["generation_model"] == "gpt-4o-mini"
        assert pair["reflection_model"] == "gpt-4o-mini"
        assert pair["error"] is None

    def test_grid_result_has_best_pair(self, grid_job: dict):
        """Grid search identifies a best pair."""
        job_id = grid_job["job_id"]
        r = requests.get(f"{BASE_URL}/jobs/{job_id}/grid-result", timeout=10)
        best = r.json()["best_pair"]
        assert best is not None
        assert best["optimized_test_metric"] is not None

    def test_grid_artifact_rejected(self, grid_job: dict):
        """GET /artifact on grid search job is rejected (per-pair artifacts instead)."""
        r = requests.get(f"{BASE_URL}/jobs/{grid_job['job_id']}/artifact", timeout=5)
        assert r.status_code in (404, 409)  # Backend may return either

    def test_serve_grid_job_returns_409(self, grid_job: dict):
        """POST /serve on grid search job returns 409."""
        r = requests.post(
            f"{BASE_URL}/serve/{grid_job['job_id']}",
            json={"inputs": {"question": "hi"}},
            timeout=10,
        )
        assert r.status_code == 409

    def test_serve_info_grid_job_returns_409(self, grid_job: dict):
        """GET /serve/info on grid search job returns 409."""
        r = requests.get(f"{BASE_URL}/serve/{grid_job['job_id']}/info", timeout=10)
        assert r.status_code == 409

    def test_grid_job_cleanup(self, grid_job: dict):
        """Delete grid search job."""
        _cleanup(grid_job["job_id"])
        r = requests.get(f"{BASE_URL}/jobs/{grid_job['job_id']}", timeout=5)
        assert r.status_code == 404


# ════════════════════════════════════════════
# 8. CODE VALIDATION EDGE CASES
# ════════════════════════════════════════════

@requires_server
class TestCodeValidation:
    """Test malformed signature/metric code rejection."""

    _BASE = {
        "username": "code-val",
        "module_name": "predict",
        "optimizer_name": "miprov2",
        "dataset": [{"q": "hi", "a": "bye"}],
        "column_mapping": {"inputs": {"q": "q"}, "outputs": {"a": "a"}},
        "model_config": {"name": "gpt-4o-mini"},
    }

    def test_syntax_error_in_signature(self):
        """Signature with syntax error returns 400."""
        payload = {**self._BASE, "signature_code": "class Broken(\n", "metric_code": "def metric(e,p,t=None): return 1.0"}
        r = requests.post(f"{BASE_URL}/run", json=payload, timeout=10)
        assert r.status_code == 400
        assert "syntax" in r.json()["detail"].lower()

    def test_syntax_error_in_metric(self):
        """Metric with syntax error returns 400."""
        payload = {
            **self._BASE,
            "signature_code": "import dspy\nclass S(dspy.Signature):\n    q: str = dspy.InputField()\n    a: str = dspy.OutputField()",
            "metric_code": "def metric(e, p, t=None)\n    return 1.0",
        }
        r = requests.post(f"{BASE_URL}/run", json=payload, timeout=10)
        assert r.status_code == 400
        assert "syntax" in r.json()["detail"].lower()

    def test_no_signature_class_returns_400(self):
        """Signature code without a Signature subclass returns 400."""
        payload = {
            **self._BASE,
            "signature_code": "x = 42",
            "metric_code": "def metric(e,p,t=None): return 1.0",
        }
        r = requests.post(f"{BASE_URL}/run", json=payload, timeout=10)
        assert r.status_code == 400
        assert "Signature" in r.json()["detail"]

    def test_no_metric_callable_returns_400(self):
        """Metric code without a callable returns 400."""
        payload = {
            **self._BASE,
            "signature_code": "import dspy\nclass S(dspy.Signature):\n    q: str = dspy.InputField()\n    a: str = dspy.OutputField()",
            "metric_code": "x = 42",
        }
        r = requests.post(f"{BASE_URL}/run", json=payload, timeout=10)
        assert r.status_code == 400
        assert "metric" in r.json()["detail"].lower()

    def test_invalid_column_mapping_returns_400(self):
        """Column mapping referencing nonexistent columns returns 400."""
        payload = {
            **self._BASE,
            "signature_code": "import dspy\nclass S(dspy.Signature):\n    q: str = dspy.InputField()\n    a: str = dspy.OutputField()",
            "metric_code": "def metric(e,p,t=None): return 1.0",
            "column_mapping": {"inputs": {"q": "q"}, "outputs": {"a": "nonexistent"}},
        }
        r = requests.post(f"{BASE_URL}/run", json=payload, timeout=10)
        assert r.status_code == 400
        assert "nonexistent" in r.json()["detail"]

    def test_gepa_without_reflection_fails(self):
        """GEPA without reflection_model_config fails at runtime."""
        payload = {
            **self._BASE,
            "optimizer_name": "gepa",
            "signature_code": "import dspy\nclass S(dspy.Signature):\n    q: str = dspy.InputField()\n    a: str = dspy.OutputField()",
            "metric_code": "def metric(g,p,t=None,pn=None,pt=None): return 1.0",
        }
        r = requests.post(f"{BASE_URL}/run", json=payload, timeout=10)
        # Job is accepted but will fail because GEPA needs reflection model
        if r.status_code == 400:
            assert "reflection" in r.json()["detail"].lower()
        else:
            assert r.status_code == 201
            job_id = r.json()["job_id"]
            data = _wait_for_terminal(job_id, timeout=60)
            assert data["status"] == "failed"
            assert "reflection" in (data.get("message") or "").lower()
            _cleanup(job_id)


# ════════════════════════════════════════════
# 9. LOG FILTERING AND PAGINATION
# ════════════════════════════════════════════

@requires_llm
@requires_server
class TestLogFiltering:
    """Test log endpoint filtering and pagination."""

    @pytest.fixture(scope="class")
    def job_with_logs(self) -> str:
        """Submit a job and wait for completion to get logs."""
        job_id = _submit_run_job(username="log-filter")
        _wait_for_terminal(job_id)
        return job_id

    def test_logs_with_limit(self, job_with_logs: str):
        """GET /logs with limit returns at most N entries."""
        r = requests.get(f"{BASE_URL}/jobs/{job_with_logs}/logs?limit=3", timeout=5)
        assert r.status_code == 200
        assert len(r.json()) <= 3

    def test_logs_with_offset(self, job_with_logs: str):
        """GET /logs with offset skips entries."""
        all_logs = requests.get(f"{BASE_URL}/jobs/{job_with_logs}/logs", timeout=5).json()
        offset_logs = requests.get(f"{BASE_URL}/jobs/{job_with_logs}/logs?offset=2", timeout=5).json()
        assert len(offset_logs) == max(0, len(all_logs) - 2)

    def test_logs_filter_by_level(self, job_with_logs: str):
        """GET /logs with level=INFO only returns INFO logs."""
        r = requests.get(f"{BASE_URL}/jobs/{job_with_logs}/logs?level=INFO", timeout=5)
        assert r.status_code == 200
        for log in r.json():
            assert log["level"] == "INFO"

    def test_logs_filter_warning(self, job_with_logs: str):
        """GET /logs with level=WARNING returns only warnings."""
        r = requests.get(f"{BASE_URL}/jobs/{job_with_logs}/logs?level=WARNING", timeout=5)
        assert r.status_code == 200
        for log in r.json():
            assert log["level"] == "WARNING"

    def test_log_cleanup(self, job_with_logs: str):
        _cleanup(job_with_logs)


# ════════════════════════════════════════════
# 10. COMBINED FILTERS AND EDGE CASES
# ════════════════════════════════════════════

@requires_llm
@requires_server
class TestCombinedFilters:
    """Test multi-parameter filtering on job listing."""

    @pytest.fixture(scope="class")
    def two_jobs(self) -> list:
        """Submit two jobs with different configs."""
        job1 = _submit_run_job(username="filter-a")
        job2 = _submit_run_job(username="filter-b")
        _wait_for_terminal(job1)
        _wait_for_terminal(job2)
        return [job1, job2]

    def test_combined_status_and_username(self, two_jobs: list):
        """Filter by status=success AND username returns correct subset."""
        r = requests.get(f"{BASE_URL}/jobs?status=success&username=filter-a", timeout=5)
        assert r.status_code == 200
        items = r.json()["items"]
        for item in items:
            assert item["username"] == "filter-a"
            assert item["status"] == "success"

    def test_combined_type_and_status(self, two_jobs: list):
        """Filter by job_type=run AND status=success."""
        r = requests.get(f"{BASE_URL}/jobs?job_type=run&status=success", timeout=5)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["job_type"] == "run"
            assert item["status"] == "success"

    def test_pagination_with_limit_1(self, two_jobs: list):
        """Paginate with limit=1 returns one item with correct total."""
        r = requests.get(f"{BASE_URL}/jobs?username=filter-a&limit=1", timeout=5)
        data = r.json()
        assert len(data["items"]) <= 1
        assert data["total"] >= 1

    def test_offset_beyond_total(self, two_jobs: list):
        """Offset beyond total returns empty items."""
        r = requests.get(f"{BASE_URL}/jobs?offset=9999", timeout=5)
        assert r.status_code == 200
        assert len(r.json()["items"]) == 0

    def test_cleanup(self, two_jobs: list):
        for jid in two_jobs:
            _cleanup(jid)
