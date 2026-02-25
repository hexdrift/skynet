from __future__ import annotations

import logging
import signal
import time
from typing import Callable

from fastapi.testclient import TestClient

from core.api.app import create_app
from core.models import RunResponse, SplitCounts
from core.storage.local import LocalDBJobStore
from core.worker import reset_worker_for_tests


class TqdmProgressService:
    """Service that emits tqdm-like progress metrics with remaining time."""

    def validate_payload(self, payload) -> None:
        time.sleep(0.05)

    def run(self, payload, *, artifact_id=None, progress_callback=None) -> RunResponse:
        if progress_callback:
            progress_callback("optimizer_progress", {
                "tqdm_total": 100,
                "tqdm_n": 30,
                "tqdm_elapsed": 3.0,
                "tqdm_rate": 10.0,
                "tqdm_remaining": 7.0,
                "tqdm_percent": 30.0,
                "tqdm_desc": "GEPA Optimization",
            })
            time.sleep(0.1)
            progress_callback("optimizer_progress", {
                "tqdm_total": 100,
                "tqdm_n": 80,
                "tqdm_elapsed": 8.0,
                "tqdm_rate": 10.0,
                "tqdm_remaining": 2.0,
                "tqdm_percent": 80.0,
                "tqdm_desc": "GEPA Optimization",
            })
        time.sleep(0.1)
        return RunResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name="metric",
            split_counts=SplitCounts(train=1, val=0, test=0),
            optimization_metadata={"source": "tqdm_progress_service"},
            details={"ok": True},
            runtime_seconds=0.3,
        )


class FastSuccessService:
    def validate_payload(self, payload) -> None:
        # Keep validating state observable in status polling.
        time.sleep(0.05)

    def run(self, payload, *, artifact_id=None, progress_callback=None) -> RunResponse:
        logger = logging.getLogger("dspy")
        logger.info("start job=%s", artifact_id)
        if progress_callback:
            progress_callback("optimizer_progress", {"step": 1})
        time.sleep(0.1)
        logger.info("finish job=%s", artifact_id)
        return RunResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name="metric",
            split_counts=SplitCounts(train=1, val=0, test=0),
            optimization_metadata={"source": "fast_success_service"},
            details={"ok": True},
            runtime_seconds=0.15,
        )


class SlowService:
    def __init__(self, sleep_seconds: float = 10.0) -> None:
        self._sleep_seconds = sleep_seconds

    def validate_payload(self, payload) -> None:
        return None

    def run(self, payload, *, artifact_id=None, progress_callback=None) -> RunResponse:
        logging.getLogger("dspy").info("slow start job=%s", artifact_id)
        time.sleep(self._sleep_seconds)
        return RunResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name="metric",
            split_counts=SplitCounts(train=1, val=0, test=0),
            optimization_metadata={"source": "slow_service"},
            details={"ok": True},
            runtime_seconds=self._sleep_seconds,
        )


def make_payload(*, username: str = "alice") -> dict:
    return {
        "username": username,
        "module_name": "demo_module",
        "module_kwargs": {},
        "signature_code": (
            "import dspy\n"
            "class Sig(dspy.Signature):\n"
            "    question: str = dspy.InputField()\n"
            "    answer: str = dspy.OutputField()\n"
        ),
        "metric_code": (
            "def metric(example, pred, trace=None):\n"
            "    return 1.0\n"
        ),
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
        "model_config": {"name": "dummy-model"},
    }


def _wait_until(predicate: Callable[[], bool], timeout: float = 5.0, interval: float = 0.05) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _wait_for_job_status(client: TestClient, job_id: str, target: str, timeout: float = 8.0) -> bool:
    def _match() -> bool:
        response = client.get(f"/jobs/{job_id}/summary")
        if response.status_code != 200:
            return False
        return response.json()["status"] == target

    return _wait_until(_match, timeout=timeout)


def test_happy_path_completion(configured_env) -> None:
    app = create_app(service=FastSuccessService())
    with TestClient(app) as client:
        submit = client.post("/run", json=make_payload(username="happy"))
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        statuses = [submit.json()["status"]]
        deadline = time.time() + 8
        while time.time() < deadline:
            summary = client.get(f"/jobs/{job_id}/summary")
            assert summary.status_code == 200
            status = summary.json()["status"]
            if status != statuses[-1]:
                statuses.append(status)
            if status == "success":
                break
            time.sleep(0.02)

        assert statuses[0] == "pending"
        assert "validating" in statuses
        assert "running" in statuses
        assert statuses[-1] == "success"

        detail = client.get(f"/jobs/{job_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["status"] == "success"
        assert body["result"] is not None
        assert body["result"]["metric_name"] == "metric"


def test_pending_cancellation_marks_job_cancelled(configured_env, monkeypatch) -> None:
    monkeypatch.setenv("WORKER_POLL_INTERVAL", "1.0")
    app = create_app(service=FastSuccessService())
    with TestClient(app) as client:
        submit = client.post("/run", json=make_payload(username="pending_cancel"))
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        cancel = client.post(f"/jobs/{job_id}/cancel")
        assert cancel.status_code == 200

        detail = client.get(f"/jobs/{job_id}")
        assert detail.status_code == 200
        assert detail.json()["status"] == "cancelled"


def test_running_cancellation_is_bounded_and_clears_active_job(configured_env) -> None:
    app = create_app(service=SlowService(sleep_seconds=20.0))
    with TestClient(app) as client:
        submit = client.post("/run", json=make_payload(username="running_cancel"))
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        assert _wait_for_job_status(client, job_id, "running", timeout=8.0)

        t0 = time.time()
        cancel = client.post(f"/jobs/{job_id}/cancel")
        assert cancel.status_code == 200

        cancelled = _wait_for_job_status(client, job_id, "cancelled", timeout=2.0)
        elapsed = time.time() - t0
        assert cancelled, "Cancelled running job should reach 'cancelled' status quickly"
        assert elapsed <= 2.0

        assert _wait_until(lambda: client.get("/queue").json()["active_jobs"] == 0, timeout=2.0)


def test_pending_jobs_recovered_and_requeued_on_startup(configured_env) -> None:
    store = LocalDBJobStore()
    job_id = "recovered-pending-job"
    payload = make_payload(username="recover_pending")
    store.create_job(job_id)
    store.update_job(job_id, payload=payload, status="pending")

    app = create_app(service=FastSuccessService())
    with TestClient(app) as client:
        assert _wait_for_job_status(client, job_id, "success", timeout=8.0)


def test_orphaned_running_jobs_marked_failed_on_startup(configured_env) -> None:
    store = LocalDBJobStore()
    job_id = "orphan-running-job"
    store.create_job(job_id)
    store.update_job(job_id, status="running", message="was running before restart")

    app = create_app(service=FastSuccessService())
    with TestClient(app) as client:
        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        assert "interrupted by service restart" in (body.get("message") or "")


def test_jobs_listing_has_embedded_counts_and_username_filter(configured_env) -> None:
    app = create_app(service=FastSuccessService())
    with TestClient(app) as client:
        job_ids = []
        for username in ["user_a", "user_a", "user_b"]:
            submit = client.post("/run", json=make_payload(username=username))
            assert submit.status_code == 201
            job_id = submit.json()["job_id"]
            job_ids.append(job_id)

        for job_id in job_ids:
            assert _wait_for_job_status(client, job_id, "success", timeout=8.0)

        page_1 = client.get("/jobs", params={"limit": 2, "offset": 0})
        page_2 = client.get("/jobs", params={"limit": 2, "offset": 2})
        assert page_1.status_code == 200
        assert page_2.status_code == 200
        p1 = page_1.json()
        p2 = page_2.json()
        assert "items" in p1
        assert "total" in p1
        assert p1["total"] >= 3
        assert len(p1["items"]) <= 2
        assert len(p2["items"]) <= 2

        for row in p1["items"] + p2["items"]:
            assert "progress_count" in row
            assert "log_count" in row
            assert isinstance(row["progress_count"], int)
            assert isinstance(row["log_count"], int)

        filtered = client.get("/jobs", params={"username": "user_a", "limit": 10, "offset": 0})
        assert filtered.status_code == 200
        assert filtered.json()["items"]
        assert all(item.get("username") == "user_a" for item in filtered.json()["items"])


def test_sigterm_handler_restored_after_lifespan(configured_env) -> None:
    previous_handler = signal.getsignal(signal.SIGTERM)
    app = create_app(service=FastSuccessService())
    with TestClient(app):
        pass
    with TestClient(app):
        pass
    restored_handler = signal.getsignal(signal.SIGTERM)
    assert restored_handler == previous_handler


def test_health_reflects_worker_liveness(configured_env) -> None:
    app = create_app(service=FastSuccessService())
    with TestClient(app) as client:
        healthy = client.get("/health")
        assert healthy.status_code == 200
        assert healthy.json()["status"] == "ok"

        reset_worker_for_tests()

        unhealthy = client.get("/health")
        assert unhealthy.status_code == 503


def test_estimated_remaining_from_tqdm_progress(configured_env) -> None:
    """Verify tqdm_remaining flows through progress events and clears on completion."""
    app = create_app(service=TqdmProgressService())
    with TestClient(app) as client:
        submit = client.post("/run", json=make_payload(username="tqdm_test"))
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        assert _wait_for_job_status(client, job_id, "success", timeout=8.0)

        # Completed job: estimated_remaining should be null (not stale tqdm value)
        detail = client.get(f"/jobs/{job_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["estimated_remaining"] is None

        # latest_metrics should still contain the raw tqdm_remaining value
        metrics = body.get("latest_metrics", {})
        assert "tqdm_remaining" in metrics
        assert metrics["tqdm_remaining"] == 2.0

        # elapsed should be HH:MM:SS
        assert isinstance(body["elapsed"], str)
        assert ":" in body["elapsed"]

        # Summary endpoint: also null for completed job
        summary = client.get(f"/jobs/{job_id}/summary")
        assert summary.status_code == 200
        assert summary.json()["estimated_remaining"] is None

        # Jobs listing: also null for completed job
        listing = client.get("/jobs", params={"username": "tqdm_test"})
        assert listing.status_code == 200
        jobs = listing.json()["items"]
        assert len(jobs) >= 1
        assert jobs[0]["estimated_remaining"] is None


def test_tqdm_proxy_computes_remaining_from_rate() -> None:
    """Unit test: _TqdmProxy computes remaining seconds from total, n, rate."""
    from core.service_gateway.progress import _TqdmProxy

    captured = []

    def callback(event, metrics):
        captured.append(metrics)

    class FakeBar:
        total = 100
        n = 40
        desc = "GEPA test"
        unit = "rollouts"

        def update(self, n=1):
            pass

        @property
        def format_dict(self):
            return {"elapsed": 4.0, "rate": 10.0}

    bar = FakeBar()
    proxy = _TqdmProxy(bar, callback)
    # Constructor emits once; check it
    assert len(captured) == 1
    first = captured[0]
    assert first["tqdm_remaining"] == 6.0  # (100-40)/10
    assert first["tqdm_percent"] == 40.0

    # Advance the bar and emit again
    bar.n = 90
    proxy.update(50)
    assert len(captured) == 2
    second = captured[1]
    assert second["tqdm_remaining"] == 1.0  # (100-90)/10

    # When rate is zero, remaining should be None
    bar.n = 50
    bar.format_dict_override = {"elapsed": 5.0, "rate": 0}

    class ZeroRateBar:
        total = 100
        n = 50
        desc = "GEPA zero"
        unit = "rollouts"

        @property
        def format_dict(self):
            return {"elapsed": 5.0, "rate": 0}

        def update(self, n=1):
            pass

    zero_captured = []
    zero_proxy = _TqdmProxy(ZeroRateBar(), lambda e, m: zero_captured.append(m))
    assert zero_captured[0]["tqdm_remaining"] is None


class FailingRunService:
    """Service that always raises during run()."""

    def validate_payload(self, payload) -> None:
        pass

    def run(self, payload, *, artifact_id=None, progress_callback=None):
        raise ValueError("Dataset column mismatch: expected 'question' but got 'query'")


def test_artifact_on_failed_job_shows_error(configured_env) -> None:
    """Artifact endpoint should say the job failed and include the error message."""
    app = create_app(service=FailingRunService())
    with TestClient(app) as client:
        submit = client.post("/run", json=make_payload(username="fail_art"))
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        assert _wait_for_job_status(client, job_id, "failed", timeout=8.0)

        art = client.get(f"/jobs/{job_id}/artifact")
        assert art.status_code == 409
        detail = art.json()["detail"]
        assert "failed" in detail.lower()
        assert "column mismatch" in detail.lower()


def test_artifact_on_cancelled_job_says_cancelled(configured_env) -> None:
    """Artifact endpoint should clearly say the job was cancelled."""
    app = create_app(service=FastSuccessService())
    with TestClient(app) as client:
        submit = client.post("/run", json=make_payload(username="cancel_art"))
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        cancel = client.post(f"/jobs/{job_id}/cancel")
        assert cancel.status_code == 200

        art = client.get(f"/jobs/{job_id}/artifact")
        assert art.status_code == 409
        assert "cancelled" in art.json()["detail"].lower()


def test_failed_job_has_traceback_in_logs(configured_env) -> None:
    """When a job fails, the subprocess traceback should be in the job logs."""
    app = create_app(service=FailingRunService())
    with TestClient(app) as client:
        submit = client.post("/run", json=make_payload(username="traceback_test"))
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        assert _wait_for_job_status(client, job_id, "failed", timeout=8.0)

        logs = client.get(f"/jobs/{job_id}/logs")
        assert logs.status_code == 200
        entries = logs.json()
        error_entries = [e for e in entries if e["level"] == "ERROR"]
        assert error_entries, "Failed job should have ERROR-level log entries with traceback"
        traceback_text = " ".join(e["message"] for e in error_entries)
        assert "Traceback" in traceback_text or "ValueError" in traceback_text


def test_payload_retrieval(configured_env) -> None:
    """GET /jobs/{id}/payload returns the original submitted payload."""
    app = create_app(service=FastSuccessService())
    with TestClient(app) as client:
        original = make_payload(username="payload_test")
        submit = client.post("/run", json=original)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        resp = client.get(f"/jobs/{job_id}/payload")
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == job_id
        payload = body["payload"]
        assert payload["username"] == "payload_test"
        assert payload["module_name"] == original["module_name"]
        assert payload["signature_code"] == original["signature_code"]
        assert payload["metric_code"] == original["metric_code"]
        assert payload["dataset"] == original["dataset"]
        assert payload["column_mapping"] == original["column_mapping"]


def test_payload_retrieval_unknown_job(configured_env) -> None:
    """GET /jobs/{id}/payload returns 404 for unknown job."""
    app = create_app(service=FastSuccessService())
    with TestClient(app) as client:
        resp = client.get("/jobs/nonexistent-job-id/payload")
        assert resp.status_code == 404
