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


def test_pending_cancellation_deletes_job_and_leaves_no_orphans(configured_env, monkeypatch) -> None:
    monkeypatch.setenv("WORKER_POLL_INTERVAL", "1.0")
    app = create_app(service=FastSuccessService())
    with TestClient(app) as client:
        submit = client.post("/run", json=make_payload(username="pending_cancel"))
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        cancel = client.post(f"/jobs/{job_id}/cancel")
        assert cancel.status_code == 200

        assert _wait_until(lambda: client.get(f"/jobs/{job_id}").status_code == 404, timeout=2.0)

    store = LocalDBJobStore()
    assert not store.job_exists(job_id)
    assert store.get_progress_count(job_id) == 0
    assert store.get_log_count(job_id) == 0


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

        deleted = _wait_until(lambda: client.get(f"/jobs/{job_id}").status_code == 404, timeout=2.0)
        elapsed = time.time() - t0
        assert deleted, "Cancelled running job should be deleted quickly"
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
        assert len(page_1.json()) <= 2
        assert len(page_2.json()) <= 2

        for row in page_1.json() + page_2.json():
            assert "progress_count" in row
            assert "log_count" in row
            assert isinstance(row["progress_count"], int)
            assert isinstance(row["log_count"], int)

        filtered = client.get("/jobs", params={"username": "user_a", "limit": 10, "offset": 0})
        assert filtered.status_code == 200
        assert filtered.json()
        assert all(item.get("username") == "user_a" for item in filtered.json())


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
