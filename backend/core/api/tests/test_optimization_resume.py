"""Tests for resume: POST /optimizations/{id}/resume and the ``resumable`` flag.

Resume is only offered for a run that stopped mid-optimization with a saved GEPA
checkpoint (terminal failed/cancelled, checkpoint present, attempts below the
cap). Everything else keeps the existing Restart path. These tests pin the
endpoint's preconditions and the in-place re-queue, plus the :func:`is_resumable`
discriminator that drives the Resume-vs-Restart affordance.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...config import settings
from ..routers._helpers import is_pausable, is_resumable
from ..routers.optimizations import create_optimizations_router
from .conftest import bypass_auth
from .mocks import _BaseFakeJobStore


@pytest.fixture
def store() -> _BaseFakeJobStore:
    """Provide a fresh fake job store per test."""
    return _BaseFakeJobStore()


@pytest.fixture
def client(store: _BaseFakeJobStore) -> TestClient:
    """Build a TestClient exposing only the optimizations router over the fake store.

    Args:
        store: Fake job store wired into the router factory.

    Returns:
        A ``TestClient`` over a minimal FastAPI app.
    """
    app = FastAPI()
    app.include_router(create_optimizations_router(job_store=store, get_worker_ref=lambda: None))
    bypass_auth(app)
    return TestClient(app, raise_server_exceptions=False)


def _seed_resumable(store: _BaseFakeJobStore, oid: str, *, status: str = "failed", attempts: int = 0) -> str:
    """Seed a terminal job that has a saved checkpoint — the resumable case."""
    store.seed_job(oid, status=status, attempts=attempts, username="alice")
    store.save_gepa_checkpoint(oid, b"GEPA-STATE", iteration=7)
    return oid


def test_resume_requeues_failed_run_in_place(client: TestClient, store: _BaseFakeJobStore) -> None:
    """A failed run with a checkpoint resumes in place: 202, same id, pending, attempts+1."""
    _seed_resumable(store, "r1", attempts=0)
    resp = client.post("/optimizations/r1/resume")
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["optimization_id"] == "r1"
    assert body["status"] == "pending"
    job = store.get_job("r1")
    assert job["status"] == "pending"
    assert job["attempts"] == 1


def test_resume_allows_cancelled_run(client: TestClient, store: _BaseFakeJobStore) -> None:
    """A cancelled run with a checkpoint is resumable too."""
    _seed_resumable(store, "c1", status="cancelled")
    resp = client.post("/optimizations/c1/resume")
    assert resp.status_code == 202, resp.text


def test_resume_without_checkpoint_is_not_resumable(client: TestClient, store: _BaseFakeJobStore) -> None:
    """A failed run with no checkpoint is a regular failure → 409, keeps Restart."""
    store.seed_job("nf", status="failed", username="alice")
    resp = client.post("/optimizations/nf/resume")
    assert resp.status_code == 409
    assert "resume point" in resp.json()["detail"]


@pytest.mark.parametrize("status", ["running", "pending", "validating", "success"])
def test_resume_rejects_non_terminal_failure(client: TestClient, store: _BaseFakeJobStore, status: str) -> None:
    """Only failed/cancelled runs can be resumed, even with a checkpoint present."""
    oid = f"s_{status}"
    store.seed_job(oid, status=status, username="alice")
    store.save_gepa_checkpoint(oid, b"STATE", iteration=1)
    resp = client.post(f"/optimizations/{oid}/resume")
    assert resp.status_code == 409
    assert "mid-run" in resp.json()["detail"]


def test_resume_blocked_at_attempt_cap(client: TestClient, store: _BaseFakeJobStore) -> None:
    """At ``job_max_attempts`` the run is no longer resumable (shared cap)."""
    _seed_resumable(store, "ex", attempts=settings.job_max_attempts)
    resp = client.post("/optimizations/ex/resume")
    assert resp.status_code == 409
    assert "maximum attempts" in resp.json()["detail"]


def test_resume_unknown_id_404(client: TestClient) -> None:
    """Resuming an unknown optimization is a 404."""
    resp = client.post("/optimizations/ghost/resume")
    assert resp.status_code == 404


def _seed_grid(store: _BaseFakeJobStore, oid: str, *, status: str = "success") -> str:
    """Seed a terminal grid whose pair 0 succeeded and pair 1 failed."""
    store.seed_job(
        oid,
        status=status,
        username="alice",
        payload_overview={"optimization_type": "grid_search"},
        result={
            "pair_results": [
                {"pair_index": 0, "generation_model": "g0", "reflection_model": "r0", "optimized_test_metric": 0.8},
                {"pair_index": 1, "generation_model": "g1", "reflection_model": "r1", "error": "boom"},
            ],
            "total_pairs": 2,
        },
    )
    return oid


def test_grids_are_never_whole_job_resumable(store: _BaseFakeJobStore) -> None:
    """A grid is resumed per pair (in its results), so the top-level flag stays False."""
    _seed_grid(store, "g", status="failed")
    store.save_grid_pair_result("g", 0, {"pair_index": 0})
    store.save_gepa_checkpoint("g", b"S", iteration=1, pair_index=1)
    assert is_resumable(store, store.get_job("g")) is False


def test_restart_grid_pair_reruns_only_that_pair(client: TestClient, store: _BaseFakeJobStore) -> None:
    """Restarting a failed pair seeds every other pair and re-queues the grid in place."""
    _seed_grid(store, "grid1", status="success")
    resp = client.post("/optimizations/grid1/pair/1/restart")
    assert resp.status_code == 202, resp.text
    assert store.get_job("grid1")["status"] == "pending"
    # The other (successful) pair is kept so the runner skips it; the target isn't.
    assert set(store.get_grid_pair_results("grid1")) == {0}


def test_restart_grid_pair_works_on_a_successful_grid(client: TestClient, store: _BaseFakeJobStore) -> None:
    """A failed pair stays restartable even when the grid succeeded overall."""
    _seed_grid(store, "grid2", status="success")
    resp = client.post("/optimizations/grid2/pair/1/restart")
    assert resp.status_code == 202, resp.text


def test_resume_grid_pair_requires_a_checkpoint(client: TestClient, store: _BaseFakeJobStore) -> None:
    """Resuming a pair with no checkpoint is 409 (restart instead); with one, 202."""
    _seed_grid(store, "grid3", status="success")
    resp = client.post("/optimizations/grid3/pair/1/resume")
    assert resp.status_code == 409
    assert "restart" in resp.json()["detail"].lower()
    store.save_gepa_checkpoint("grid3", b"STATE", iteration=1, pair_index=1)
    resp = client.post("/optimizations/grid3/pair/1/resume")
    assert resp.status_code == 202, resp.text


def test_grid_pair_action_rejects_a_single_run(client: TestClient, store: _BaseFakeJobStore) -> None:
    """Per-pair re-run on a non-grid optimization is a 404 (not a grid)."""
    store.seed_job(
        "single",
        status="failed",
        username="alice",
        payload_overview={"optimization_type": "run"},
        result={"baseline_test_metric": 0.5},
    )
    resp = client.post("/optimizations/single/pair/0/restart")
    assert resp.status_code == 404


def test_grid_pair_action_unknown_index_404(client: TestClient, store: _BaseFakeJobStore) -> None:
    """An out-of-range pair index is a 404."""
    _seed_grid(store, "grid4", status="success")
    resp = client.post("/optimizations/grid4/pair/9/restart")
    assert resp.status_code == 404


def test_is_resumable_discriminator(store: _BaseFakeJobStore) -> None:
    """The flag is True only for terminal-failure + checkpoint + attempts under cap."""
    store.seed_job("a", status="failed", attempts=0, username="alice")
    assert is_resumable(store, store.get_job("a")) is False  # no checkpoint
    store.save_gepa_checkpoint("a", b"x", 1)
    assert is_resumable(store, store.get_job("a")) is True

    store.seed_job("b", status="success", attempts=0, username="alice")
    store.save_gepa_checkpoint("b", b"x", 1)
    assert is_resumable(store, store.get_job("b")) is False  # wrong status

    store.seed_job("c", status="failed", attempts=settings.job_max_attempts, username="alice")
    store.save_gepa_checkpoint("c", b"x", 1)
    assert is_resumable(store, store.get_job("c")) is False  # exhausted


def test_pause_running_run_in_place(client: TestClient, store: _BaseFakeJobStore) -> None:
    """Pausing a running run with a checkpoint flips it to ``paused`` in place (200)."""
    store.seed_job("p1", status="running", username="alice")
    store.save_gepa_checkpoint("p1", b"STATE", iteration=3)
    resp = client.post("/optimizations/p1/pause")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "paused"
    job = store.get_job("p1")
    assert job["status"] == "paused"
    assert job.get("completed_at") is not None


def test_pause_without_checkpoint_is_rejected(client: TestClient, store: _BaseFakeJobStore) -> None:
    """A running run with no checkpoint can't be paused yet — 409, would strand the resume."""
    store.seed_job("p2", status="running", username="alice")
    resp = client.post("/optimizations/p2/pause")
    assert resp.status_code == 409
    assert "checkpoint" in resp.json()["detail"].lower()


@pytest.mark.parametrize("status", ["pending", "validating", "failed", "cancelled", "success"])
def test_pause_rejects_non_running(client: TestClient, store: _BaseFakeJobStore, status: str) -> None:
    """Only a running optimization can be paused, even with a checkpoint present."""
    oid = f"p_{status}"
    store.seed_job(oid, status=status, username="alice")
    store.save_gepa_checkpoint(oid, b"STATE", iteration=1)
    resp = client.post(f"/optimizations/{oid}/pause")
    assert resp.status_code == 409
    assert "running" in resp.json()["detail"].lower()


def test_pause_unknown_id_404(client: TestClient) -> None:
    """Pausing an unknown optimization is a 404."""
    assert client.post("/optimizations/ghost/pause").status_code == 404


def test_resume_paused_run_does_not_consume_an_attempt(client: TestClient, store: _BaseFakeJobStore) -> None:
    """A paused run resumes (202) without bumping attempts — manual pause is cap-exempt."""
    _seed_resumable(store, "pr", status="paused", attempts=2)
    resp = client.post("/optimizations/pr/resume")
    assert resp.status_code == 202, resp.text
    job = store.get_job("pr")
    assert job["status"] == "pending"
    assert job["attempts"] == 2  # unchanged: paused resume is exempt from the cap


def test_paused_run_is_resumable_even_at_attempt_cap(store: _BaseFakeJobStore) -> None:
    """A paused run stays resumable at the attempt cap, unlike failed/cancelled."""
    _seed_resumable(store, "pcap", status="paused", attempts=settings.job_max_attempts)
    assert is_resumable(store, store.get_job("pcap")) is True


def test_is_pausable_discriminator(store: _BaseFakeJobStore) -> None:
    """Pausable only for a running single run that already has a saved checkpoint."""
    store.seed_job("rp", status="running", username="alice")
    assert is_pausable(store, store.get_job("rp")) is False  # no checkpoint yet
    store.save_gepa_checkpoint("rp", b"x", 1)
    assert is_pausable(store, store.get_job("rp")) is True

    store.seed_job("fp", status="failed", username="alice")
    store.save_gepa_checkpoint("fp", b"x", 1)
    assert is_pausable(store, store.get_job("fp")) is False  # not running

    _seed_grid(store, "gp", status="running")
    store.save_gepa_checkpoint("gp", b"x", 1, pair_index=0)
    assert is_pausable(store, store.get_job("gp")) is False  # grids pause per the whole-job rule
