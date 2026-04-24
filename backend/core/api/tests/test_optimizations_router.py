from __future__ import annotations

import base64
import json
import pickle
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ..routers.optimizations import create_optimizations_router
from .mocks import _BaseFakeJobStore, real_grid_response_dict
from ...models.artifacts import ProgramArtifact
from ...models.common import SplitCounts
from ...models.results import RunResponse

# _ExtendedFakeJobStore is just _BaseFakeJobStore (which already has bulk-delete).
_ExtendedFakeJobStore = _BaseFakeJobStore

@pytest.fixture
def store() -> _ExtendedFakeJobStore:
    return _ExtendedFakeJobStore()

@pytest.fixture
def opt_client(store: _ExtendedFakeJobStore) -> TestClient:
    app = FastAPI()
    app.include_router(create_optimizations_router(job_store=store, get_worker_ref=lambda: None))
    return TestClient(app, raise_server_exceptions=False)

def test_list_jobs_returns_empty_when_store_is_empty(opt_client: TestClient) -> None:
    """GET /optimizations returns total=0 and an empty items list when no jobs exist."""
    resp = opt_client.get("/optimizations")

    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["items"] == []

def test_list_jobs_invalid_status_returns_422(opt_client: TestClient) -> None:
    """GET /optimizations returns 422 when the status query param is not a valid enum value."""
    resp = opt_client.get("/optimizations?status=bogus")

    assert resp.status_code == 422

def test_list_jobs_invalid_optimization_type_returns_422(opt_client: TestClient) -> None:
    """GET /optimizations returns 422 when optimization_type is not 'run' or 'grid_search'."""
    resp = opt_client.get("/optimizations?optimization_type=bad_type")

    assert resp.status_code == 422

def test_list_jobs_valid_status_filter_returns_matching_jobs(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations?status=success returns only jobs with the matching status."""
    store.seed_job("j1", status="success")
    store.seed_job("j2", status="failed")

    resp = opt_client.get("/optimizations?status=success")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["optimization_id"] == "j1"

def test_get_job_returns_404_for_unknown_id(opt_client: TestClient) -> None:
    """GET /optimizations/{id} returns 404 for an unknown optimization id."""
    resp = opt_client.get("/optimizations/does-not-exist")

    assert resp.status_code == 404

def test_get_job_returns_200_for_existing_job(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id} returns 200 with the job's optimization_id."""
    store.seed_job("abc", status="success")

    resp = opt_client.get("/optimizations/abc")

    assert resp.status_code == 200
    assert resp.json()["optimization_id"] == "abc"

def test_get_job_returns_304_when_etag_matches(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id} returns 304 when the If-None-Match ETag matches the current response."""
    store.seed_job("e1", status="success")

    first = opt_client.get("/optimizations/e1")
    etag = first.headers.get("etag")
    assert etag is not None

    second = opt_client.get("/optimizations/e1", headers={"if-none-match": etag})

    assert second.status_code == 304

def test_get_summary_returns_404_for_unknown_id(opt_client: TestClient) -> None:
    """GET /optimizations/{id}/summary returns 404 for an unknown job."""
    resp = opt_client.get("/optimizations/missing/summary")

    assert resp.status_code == 404

def test_get_summary_returns_200_for_existing_job(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/summary returns 200 with the correct optimization_id."""
    store.seed_job("s1")

    resp = opt_client.get("/optimizations/s1/summary")

    assert resp.status_code == 200
    assert resp.json()["optimization_id"] == "s1"

def test_cancel_job_returns_404_for_unknown_id(opt_client: TestClient) -> None:
    """POST /optimizations/{id}/cancel returns 404 for an unknown job."""
    resp = opt_client.post("/optimizations/ghost/cancel")

    assert resp.status_code == 404

def test_cancel_job_returns_409_when_already_terminal(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """POST /optimizations/{id}/cancel returns 409 when the job is already in a terminal state."""
    store.seed_job("done", status="success")

    resp = opt_client.post("/optimizations/done/cancel")

    assert resp.status_code == 409

@pytest.mark.parametrize("terminal_status", ["success", "failed", "cancelled"])
def test_cancel_job_returns_409_for_all_terminal_statuses(
    opt_client: TestClient,
    store: _ExtendedFakeJobStore,
    terminal_status: str,
) -> None:
    """POST /optimizations/{id}/cancel returns 409 for all terminal statuses (success/failed/cancelled)."""
    store.seed_job(f"j_{terminal_status}", status=terminal_status)

    resp = opt_client.post(f"/optimizations/j_{terminal_status}/cancel")

    assert resp.status_code == 409

def test_cancel_job_returns_200_and_sets_cancelled_for_pending(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """POST /optimizations/{id}/cancel returns 200 and status=cancelled for a pending job."""
    store.seed_job("active", status="pending")

    resp = opt_client.post("/optimizations/active/cancel")

    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

def test_cancel_job_updates_store_status(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """POST /optimizations/{id}/cancel persists status=cancelled in the job store."""
    store.seed_job("running_job", status="running")

    opt_client.post("/optimizations/running_job/cancel")

    assert store.get_job("running_job")["status"] == "cancelled"

def test_delete_job_returns_404_for_unknown_id(opt_client: TestClient) -> None:
    """DELETE /optimizations/{id} returns 404 for an unknown job."""
    resp = opt_client.delete("/optimizations/ghost")

    assert resp.status_code == 404

def test_delete_job_returns_409_for_active_job(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """DELETE /optimizations/{id} returns 409 for a job that is currently running."""
    store.seed_job("live", status="running")

    resp = opt_client.delete("/optimizations/live")

    assert resp.status_code == 409

@pytest.mark.parametrize("active_status", ["pending", "validating", "running"])
def test_delete_job_returns_409_for_non_terminal_statuses(
    opt_client: TestClient,
    store: _ExtendedFakeJobStore,
    active_status: str,
) -> None:
    """DELETE /optimizations/{id} returns 409 for all non-terminal statuses."""
    store.seed_job(f"j_{active_status}", status=active_status)

    resp = opt_client.delete(f"/optimizations/j_{active_status}")

    assert resp.status_code == 409

def test_delete_job_returns_200_and_removes_terminal_job(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """DELETE /optimizations/{id} returns 200 with deleted=True and removes the job from the store."""
    store.seed_job("done", status="success")

    resp = opt_client.delete("/optimizations/done")

    assert resp.status_code == 200
    body = resp.json()
    assert body["optimization_id"] == "done"
    assert body["deleted"] is True
    assert not store.job_exists("done")

def test_bulk_delete_empty_list_returns_zero_deleted(opt_client: TestClient) -> None:
    """POST /optimizations/bulk-delete with an empty list returns empty deleted and skipped arrays."""
    resp = opt_client.post("/optimizations/bulk-delete", json={"optimization_ids": []})

    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] == []
    assert body["skipped"] == []

def test_bulk_delete_missing_ids_are_skipped(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """POST /optimizations/bulk-delete returns skipped entries with reason=not_found for unknown ids."""
    resp = opt_client.post(
        "/optimizations/bulk-delete",
        json={"optimization_ids": ["ghost1", "ghost2"]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] == []
    assert {s["reason"] for s in body["skipped"]} == {"not_found"}

def test_bulk_delete_active_ids_are_skipped_with_status_reason(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """POST /optimizations/bulk-delete skips active jobs with reason set to their current status."""
    store.seed_job("r1", status="running")

    resp = opt_client.post(
        "/optimizations/bulk-delete",
        json={"optimization_ids": ["r1"]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] == []
    assert body["skipped"][0]["reason"] == "running"

def test_bulk_delete_deletes_terminal_jobs(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """POST /optimizations/bulk-delete removes all terminal jobs and returns their ids in deleted."""
    store.seed_job("t1", status="success")
    store.seed_job("t2", status="failed")

    resp = opt_client.post(
        "/optimizations/bulk-delete",
        json={"optimization_ids": ["t1", "t2"]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert set(body["deleted"]) == {"t1", "t2"}
    assert body["skipped"] == []
    assert not store.job_exists("t1")
    assert not store.job_exists("t2")

def test_bulk_delete_deduplicates_ids(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """POST /optimizations/bulk-delete deduplicates the input list so a job is deleted at most once."""
    store.seed_job("dup", status="success")

    resp = opt_client.post(
        "/optimizations/bulk-delete",
        json={"optimization_ids": ["dup", "dup", "dup"]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] == ["dup"]
    assert body["skipped"] == []

def test_bulk_delete_mixed_batch_reports_partial_results(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """POST /optimizations/bulk-delete reports partial success with per-id reasons for skipped items."""
    store.seed_job("ok", status="cancelled")
    store.seed_job("busy", status="pending")

    resp = opt_client.post(
        "/optimizations/bulk-delete",
        json={"optimization_ids": ["ok", "busy", "missing"]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] == ["ok"]
    skip_reasons = {s["optimization_id"]: s["reason"] for s in body["skipped"]}
    assert skip_reasons["busy"] == "pending"
    assert skip_reasons["missing"] == "not_found"

def test_artifact_returns_404_for_unknown_job(opt_client: TestClient) -> None:
    """GET /optimizations/{id}/artifact returns 404 for an unknown job."""
    resp = opt_client.get("/optimizations/ghost/artifact")

    assert resp.status_code == 404

def test_artifact_returns_409_for_pending_job(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/artifact returns 409 for a pending job."""
    store.seed_job("p", status="pending")

    resp = opt_client.get("/optimizations/p/artifact")

    assert resp.status_code == 409

def test_artifact_returns_409_for_failed_job(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/artifact returns 409 for a failed job."""
    store.seed_job("f", status="failed", message="OOM")

    resp = opt_client.get("/optimizations/f/artifact")

    assert resp.status_code == 409

def test_artifact_returns_409_for_cancelled_job(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/artifact returns 409 for a cancelled job."""
    store.seed_job("c", status="cancelled")

    resp = opt_client.get("/optimizations/c/artifact")

    assert resp.status_code == 409

def test_artifact_returns_404_for_grid_search_job(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/artifact returns 404 for a grid-search job (no single artifact)."""
    store.seed_job("gs", status="success", payload_overview={"optimization_type": "grid_search"})

    resp = opt_client.get("/optimizations/gs/artifact")

    assert resp.status_code == 404

def test_grid_result_returns_404_for_unknown_job(opt_client: TestClient) -> None:
    """GET /optimizations/{id}/grid-result returns 404 for an unknown job."""
    resp = opt_client.get("/optimizations/ghost/grid-result")

    assert resp.status_code == 404

def test_grid_result_returns_404_for_non_grid_search_job(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/grid-result returns 404 for a single-run job."""
    store.seed_job("run_job", status="success", payload_overview={"optimization_type": "run"})

    resp = opt_client.get("/optimizations/run_job/grid-result")

    assert resp.status_code == 404

def test_grid_result_returns_409_for_still_running_grid(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/grid-result returns 409 when the grid-search is still running."""
    store.seed_job("gs", status="running", payload_overview={"optimization_type": "grid_search"})

    resp = opt_client.get("/optimizations/gs/grid-result")

    assert resp.status_code == 409

def test_counts_empty_store_returns_all_zeros(opt_client: TestClient) -> None:
    """GET /optimizations/counts returns all-zero counts when no jobs exist."""
    resp = opt_client.get("/optimizations/counts")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    for key in ("pending", "validating", "running", "success", "failed", "cancelled"):
        assert body[key] == 0

def test_counts_reflects_mixed_statuses(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/counts accurately reflects per-status counts for a mixed-status store."""
    store.seed_job("j1", status="success")
    store.seed_job("j2", status="success")
    store.seed_job("j3", status="failed")
    store.seed_job("j4", status="pending")

    resp = opt_client.get("/optimizations/counts")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 4
    assert body["success"] == 2
    assert body["failed"] == 1
    assert body["pending"] == 1
    assert body["running"] == 0
    assert body["cancelled"] == 0

def test_counts_username_filter_restricts_to_single_user(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/counts?username= returns counts only for the specified user's jobs."""
    store.seed_job("alice_job", status="success", payload_overview={"username": "alice"})
    store.seed_job("bob_job", status="failed", payload_overview={"username": "bob"})

    resp = opt_client.get("/optimizations/counts?username=alice")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["success"] == 1
    assert body["failed"] == 0

def test_sidebar_empty_store_returns_empty_items(opt_client: TestClient) -> None:
    """GET /optimizations/sidebar returns an empty items list and total=0 when no jobs exist."""
    resp = opt_client.get("/optimizations/sidebar")

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0

def test_sidebar_returns_minimal_fields_per_job(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/sidebar returns per-job entries with id, status, name, optimizer, and model."""
    store.seed_job(
        "s1",
        status="running",
        payload_overview={"name": "My Run", "optimizer_name": "gepa", "model_name": "gpt-4o"},
    )

    resp = opt_client.get("/optimizations/sidebar")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["optimization_id"] == "s1"
    assert item["status"] == "running"
    assert "name" in item
    assert "optimizer_name" in item
    assert "model_name" in item

def test_sidebar_limit_caps_returned_items(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/sidebar?limit= caps the number of returned items while total reflects the full count."""
    for i in range(5):
        store.seed_job(f"job_{i}", status="success")

    resp = opt_client.get("/optimizations/sidebar?limit=2")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5

def test_sidebar_pinned_flag_is_propagated(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/sidebar reflects the pinned flag from each job's payload_overview."""
    store.seed_job("pinned_job", status="success", payload_overview={"pinned": True})
    store.seed_job("normal_job", status="success", payload_overview={"pinned": False})

    resp = opt_client.get("/optimizations/sidebar")

    assert resp.status_code == 200
    items = {item["optimization_id"]: item for item in resp.json()["items"]}
    assert items["pinned_job"]["pinned"] is True
    assert items["normal_job"]["pinned"] is False

def test_sidebar_username_filter_restricts_results(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/sidebar?username= returns only jobs belonging to the specified user."""
    store.seed_job("alice_1", status="success", payload_overview={"username": "alice"})
    store.seed_job("alice_2", status="running", payload_overview={"username": "alice"})
    store.seed_job("bob_1", status="failed", payload_overview={"username": "bob"})

    resp = opt_client.get("/optimizations/sidebar?username=alice")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    ids = {item["optimization_id"] for item in body["items"]}
    assert ids == {"alice_1", "alice_2"}

def test_dashboard_stream_returns_text_event_stream_content_type(opt_client: TestClient) -> None:
    """GET /optimizations/stream responds with Content-Type: text/event-stream."""
    # With no active jobs the generator emits one data event then an idle event and closes.
    with opt_client.stream("GET", "/optimizations/stream") as resp:
        assert "text/event-stream" in resp.headers["content-type"]

def test_dashboard_stream_first_event_has_active_jobs_key(opt_client: TestClient) -> None:
    """The first SSE event from /optimizations/stream contains active_jobs and active_count keys."""
    with opt_client.stream("GET", "/optimizations/stream") as resp:
        for chunk in resp.iter_lines():
            if chunk.startswith("data:"):
                payload = json.loads(chunk[len("data:"):].strip())
                assert "active_jobs" in payload
                assert "active_count" in payload
                break  # read one event then stop

def test_dashboard_stream_empty_store_sends_idle_event(opt_client: TestClient) -> None:
    """GET /optimizations/stream emits an idle event and closes when there are no active jobs."""
    # With no active jobs the generator emits one data event then an idle event
    # and closes — no sleep between events, so this completes quickly.
    events: list[dict] = []
    idle_seen = False
    with opt_client.stream("GET", "/optimizations/stream") as resp:
        for chunk in resp.iter_lines():
            if chunk.startswith("data:"):
                events.append(json.loads(chunk[len("data:"):].strip()))
            if chunk.startswith("event: idle"):
                idle_seen = True

    # There should be exactly one data event (active_count=0) followed by idle.
    assert len(events) >= 1
    assert events[0]["active_count"] == 0
    assert idle_seen

def test_job_stream_returns_404_for_unknown_job(opt_client: TestClient) -> None:
    """GET /optimizations/{id}/stream returns 404 for an unknown job id."""
    resp = opt_client.get("/optimizations/no-such-id/stream")

    assert resp.status_code == 404

def test_job_stream_returns_text_event_stream_for_known_job(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/stream returns 200 with text/event-stream content type for a known job."""
    store.seed_job("done_job", status="success")

    with opt_client.stream("GET", "/optimizations/done_job/stream") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

def test_job_stream_first_event_contains_expected_fields(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """The first SSE event from /optimizations/{id}/stream contains optimization_id, status, and metric fields."""
    store.seed_job("done_job2", status="success")

    with opt_client.stream("GET", "/optimizations/done_job2/stream") as resp:
        for chunk in resp.iter_lines():
            if chunk.startswith("data:"):
                payload = json.loads(chunk[len("data:"):].strip())
                assert payload["optimization_id"] == "done_job2"
                assert "status" in payload
                assert "latest_metrics" in payload
                assert "log_count" in payload
                assert "progress_count" in payload
                break

def _make_run_response_dict(**kwargs) -> dict:
    """Build a minimal serialised RunResponse dict, accepting overrides."""
    base = RunResponse(
        module_name="predict",
        optimizer_name="BootstrapFewShot",
        metric_name="accuracy",
        split_counts=SplitCounts(train=7, val=1, test=2),
    ).model_dump()
    base.update(kwargs)
    return base

def _make_grid_response_dict(**kwargs) -> dict:
    """Return a real captured GridSearchResponse dict from fixture."""
    base = real_grid_response_dict()
    base.update(kwargs)
    return base

def _seed_job_with_dataset(
    store: _ExtendedFakeJobStore,
    optimization_id: str = "ds1",
    num_rows: int = 10,
    **extra_payload,
) -> None:
    """Seed a job whose payload contains a dataset, column_mapping, and split_fractions."""
    dataset = [{"q": f"q{i}", "a": f"a{i}"} for i in range(num_rows)]
    payload = {
        "dataset": dataset,
        "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
        "split_fractions": {"train": 0.7, "val": 0.15, "test": 0.15},
        "shuffle": False,
        **extra_payload,
    }
    store.seed_job(optimization_id, status="success", payload=payload)

# Module-level picklable program stubs used by evaluate-examples tests.

class _SuccessProg:
    """Returns a MagicMock-compatible object with an 'answer' attribute."""

    def __call__(self, **kwargs):
        class _Pred:
            answer = "x"

        return _Pred()

class _ErrorProg:
    """Always raises RuntimeError when called."""

    def __call__(self, **kwargs):
        raise RuntimeError("program blew up")

def test_dataset_returns_404_when_payload_missing(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/dataset returns 404 when the job has no payload."""
    store.seed_job("nopayload", status="success", payload=None)

    resp = opt_client.get("/optimizations/nopayload/dataset")

    assert resp.status_code == 404

def test_dataset_returns_404_when_payload_not_a_dict(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/dataset returns 404 when the payload is not a dict."""
    store.seed_job("badpayload", status="success", payload="not-a-dict")

    resp = opt_client.get("/optimizations/badpayload/dataset")

    assert resp.status_code == 404

def test_dataset_returns_404_when_dataset_empty(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/dataset returns 404 when the dataset list is empty."""
    store.seed_job(
        "emptyds",
        status="success",
        payload={
            "dataset": [],
            "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
        },
    )

    resp = opt_client.get("/optimizations/emptyds/dataset")

    assert resp.status_code == 404

def test_dataset_returns_404_when_dataset_not_a_list(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/dataset returns 404 when the dataset field is not a list."""
    store.seed_job(
        "notlist",
        status="success",
        payload={
            "dataset": "not-a-list",
            "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
        },
    )

    resp = opt_client.get("/optimizations/notlist/dataset")

    assert resp.status_code == 404

def test_dataset_returns_500_when_column_mapping_invalid(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/dataset returns 500 when the column_mapping cannot be validated."""
    # empty inputs violates ColumnMapping._ensure_non_empty
    store.seed_job(
        "badmap",
        status="success",
        payload={
            "dataset": [{"q": "hi"}],
            "column_mapping": {"inputs": {}, "outputs": {}},
        },
    )

    resp = opt_client.get("/optimizations/badmap/dataset")

    assert resp.status_code == 500

def test_dataset_split_fractions_fallback_when_invalid(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/dataset falls back to default 0.7/0.15/0.15 split when fractions are invalid."""
    # invalid fractions (sum != 1.0) → falls back to SplitFractions defaults (0.7/0.15/0.15)
    store.seed_job(
        "badfrac",
        status="success",
        payload={
            "dataset": [{"q": f"q{i}", "a": f"a{i}"} for i in range(10)],
            "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
            "split_fractions": {"train": 0.5, "val": 0.5, "test": 0.5},
            "shuffle": False,
        },
    )

    resp = opt_client.get("/optimizations/badfrac/dataset")

    assert resp.status_code == 200
    body = resp.json()
    # defaults: 0.7 → 7 train, floor(10*0.15)=1 val, 2 test
    assert body["split_counts"]["train"] == 7

def test_dataset_deterministic_shuffle_produces_stable_splits(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/dataset returns the same split on repeated calls (deterministic shuffle)."""
    _seed_job_with_dataset(store, "det1", num_rows=10)

    body1 = opt_client.get("/optimizations/det1/dataset").json()
    body2 = opt_client.get("/optimizations/det1/dataset").json()

    sc = body1["split_counts"]
    assert sc["train"] + sc["val"] + sc["test"] == 10
    # Two calls with the same derived seed must yield identical splits
    assert body1["splits"]["train"] == body2["splits"]["train"]

def test_dataset_split_counts_match_stored_fractions(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/dataset split_counts correctly apply the stored split fractions."""
    _seed_job_with_dataset(store, "frac2", num_rows=20, shuffle=False)

    body = opt_client.get("/optimizations/frac2/dataset").json()

    sc = body["split_counts"]
    # floor(0.7*20)=14, floor(0.15*20)=3, remainder=3
    assert sc["train"] == 14
    assert sc["val"] == 3
    assert sc["test"] == 3

def test_evaluate_examples_404_when_payload_missing(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """POST /optimizations/{id}/evaluate-examples returns 404 when the job has no payload."""
    store.seed_job("nopayload_eval", status="success", payload=None)

    resp = opt_client.post(
        "/optimizations/nopayload_eval/evaluate-examples",
        json={"indices": [0], "program_type": "optimized"},
    )

    assert resp.status_code == 404

def test_evaluate_examples_400_when_metric_code_empty(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """POST /optimizations/{id}/evaluate-examples returns 400 when metric_code is empty."""
    store.seed_job(
        "nometric",
        status="success",
        payload={
            "dataset": [{"q": "hi", "a": "yes"}],
            "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
            "metric_code": "",
        },
    )

    resp = opt_client.post(
        "/optimizations/nometric/evaluate-examples",
        json={"indices": [0], "program_type": "optimized"},
    )

    assert resp.status_code == 400

def test_evaluate_examples_400_when_no_model_config(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """POST /optimizations/{id}/evaluate-examples returns 400 when no model_config is available."""
    store.seed_job(
        "nomodel",
        status="success",
        payload={
            "dataset": [{"q": "hi", "a": "yes"}],
            "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
            "metric_code": "def metric(ex, pred): return 1.0",
            "model_config": None,
        },
        payload_overview={},
    )

    resp = opt_client.post(
        "/optimizations/nomodel/evaluate-examples",
        json={"indices": [0], "program_type": "optimized"},
    )

    assert resp.status_code == 400

def test_evaluate_examples_409_when_result_empty_optimized(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """POST /optimizations/{id}/evaluate-examples returns 409 when program_type=optimized but result is None."""
    store.seed_job(
        "noresult",
        status="success",
        payload={
            "dataset": [{"q": "hi", "a": "yes"}],
            "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
            "metric_code": "def metric(ex, pred): return 1.0",
            "model_config": {"name": "gpt-4o"},
        },
        result=None,
    )

    resp = opt_client.post(
        "/optimizations/noresult/evaluate-examples",
        json={"indices": [0], "program_type": "optimized"},
    )

    assert resp.status_code == 409

def test_evaluate_examples_409_when_artifact_missing(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """POST /optimizations/{id}/evaluate-examples returns 409 when the result has no program artifact."""
    result_data = _make_run_response_dict(program_artifact=None)
    store.seed_job(
        "noartifact",
        status="success",
        payload={
            "dataset": [{"q": "hi", "a": "yes"}],
            "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
            "metric_code": "def metric(ex, pred): return 1.0",
            "model_config": {"name": "gpt-4o"},
        },
        result=result_data,
    )

    resp = opt_client.post(
        "/optimizations/noartifact/evaluate-examples",
        json={"indices": [0], "program_type": "optimized"},
    )

    assert resp.status_code == 409

def test_evaluate_examples_baseline_branch_calls_module_factory(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """baseline path: DspyService._get_module_factory + build_language_model are invoked."""
    fake_prediction = MagicMock()
    fake_prediction.answer = "yes"
    fake_program = MagicMock(return_value=fake_prediction)
    fake_module_factory = MagicMock(return_value=fake_program)

    store.seed_job(
        "baseline1",
        status="success",
        payload={
            "dataset": [{"q": "hello", "a": "world"}],
            "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
            "metric_code": "def metric(ex, pred): return 1.0",
            "model_config": {"name": "gpt-4o"},
            "signature_code": "",
            "module_name": "predict",
            "module_kwargs": {},
        },
    )

    with (
        patch("core.api.routers.optimizations.build_language_model", return_value=MagicMock()),
        patch("core.api.routers.optimizations.load_metric_from_code", return_value=lambda ex, pred: 1.0),
        patch("core.api.routers.optimizations.load_signature_from_code", return_value=MagicMock()),
        patch(
            "core.api.routers.optimizations.resolve_module_factory",
            return_value=(fake_module_factory, True),
        ),
        patch("dspy.context"),
    ):
        resp = opt_client.post(
            "/optimizations/baseline1/evaluate-examples",
            json={"indices": [0], "program_type": "baseline"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["program_type"] == "baseline"
    assert len(body["results"]) == 1

def test_evaluate_examples_metric_raises_records_zero_score(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """When metric raises, score falls back to 0.0 and the row still appears without an error key."""
    artifact_b64 = base64.b64encode(pickle.dumps(_SuccessProg())).decode()
    result_data = _make_run_response_dict(
        program_artifact=ProgramArtifact(program_pickle_base64=artifact_b64).model_dump()
    )
    store.seed_job(
        "metricfail",
        status="success",
        payload={
            "dataset": [{"q": "hello", "a": "world"}],
            "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
            "metric_code": "def metric(ex, pred): raise ValueError('oops')",
            "model_config": {"name": "gpt-4o"},
        },
        result=result_data,
    )

    def _boom(ex, pred):
        raise ValueError("oops")

    with (
        patch("core.service_gateway.language_models.build_language_model", return_value=MagicMock()),
        patch("core.service_gateway.data.load_metric_from_code", return_value=_boom),
        patch("dspy.context"),
    ):
        resp = opt_client.post(
            "/optimizations/metricfail/evaluate-examples",
            json={"indices": [0], "program_type": "optimized"},
        )

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["score"] == 0.0
    assert "error" not in results[0]

def test_evaluate_examples_program_raises_records_error(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """When program itself raises, error key is set and subsequent rows are also processed."""
    artifact_b64 = base64.b64encode(pickle.dumps(_ErrorProg())).decode()
    result_data = _make_run_response_dict(
        program_artifact=ProgramArtifact(program_pickle_base64=artifact_b64).model_dump()
    )
    store.seed_job(
        "progfail",
        status="success",
        payload={
            "dataset": [{"q": "hello", "a": "world"}, {"q": "world", "a": "hello"}],
            "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
            "metric_code": "def metric(ex, pred): return 1.0",
            "model_config": {"name": "gpt-4o"},
        },
        result=result_data,
    )

    with (
        patch("core.service_gateway.language_models.build_language_model", return_value=MagicMock()),
        patch("core.service_gateway.data.load_metric_from_code", return_value=lambda ex, pred: 1.0),
        patch("dspy.context"),
    ):
        resp = opt_client.post(
            "/optimizations/progfail/evaluate-examples",
            json={"indices": [0, 1], "program_type": "optimized"},
        )

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 2
    for r in results:
        assert r["score"] == 0.0
        assert r["pass"] is False
        assert "program blew up" in r["error"]

def test_test_results_409_when_no_result(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/test-results returns 409 when the job has no result yet."""
    store.seed_job("nores", status="success", result=None)

    resp = opt_client.get("/optimizations/nores/test-results")

    assert resp.status_code == 409

def test_test_results_happy_path_returns_baseline_and_optimized(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/test-results returns baseline and optimized result arrays."""
    result_data = _make_run_response_dict(
        baseline_test_results=[{"index": 0, "score": 0.4, "pass": False}],
        optimized_test_results=[{"index": 0, "score": 0.9, "pass": True}],
    )
    store.seed_job(
        "tr1",
        status="success",
        result=result_data,
        payload={
            "dataset": [{"q": f"q{i}", "a": f"a{i}"} for i in range(10)],
            "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
            "split_fractions": {"train": 0.7, "val": 0.15, "test": 0.15},
            "shuffle": False,
        },
    )

    resp = opt_client.get("/optimizations/tr1/test-results")

    assert resp.status_code == 200
    body = resp.json()
    assert "baseline" in body and "optimized" in body
    assert len(body["baseline"]) == 1 and len(body["optimized"]) == 1
    # both seq_idx=0 → same global index
    assert body["baseline"][0]["index"] == body["optimized"][0]["index"]

def test_test_results_index_remapping_uses_test_split(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """seq_idx 0 in stored results must remap to the first global index of the test split."""
    result_data = _make_run_response_dict(
        baseline_test_results=[{"index": 0, "score": 0.5, "pass": True}],
        optimized_test_results=[{"index": 0, "score": 0.8, "pass": True}],
    )
    store.seed_job(
        "remap1",
        status="success",
        result=result_data,
        payload={
            "dataset": list(range(10)),
            "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
            "split_fractions": {"train": 0.7, "val": 0.15, "test": 0.15},
            "shuffle": False,
            "seed": None,
        },
    )

    body = opt_client.get("/optimizations/remap1/test-results").json()

    # shuffle=False → ordered=[0..9], train_end=7, val_end=8, test_indices=[8,9]
    assert body["baseline"][0]["index"] == 8
    assert body["optimized"][0]["index"] == 8

def test_pair_test_results_409_when_not_grid_search(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/pair/{n}/test-results returns 409 for a non-grid-search job."""
    store.seed_job("notgs", status="success", payload_overview={"optimization_type": "run"})

    resp = opt_client.get("/optimizations/notgs/pair/0/test-results")

    assert resp.status_code == 409

def test_pair_test_results_409_when_status_not_success(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/pair/{n}/test-results returns 409 when the grid-search is not successful."""
    store.seed_job(
        "gsrunning2",
        status="running",
        payload_overview={"optimization_type": "grid_search"},
    )

    resp = opt_client.get("/optimizations/gsrunning2/pair/0/test-results")

    assert resp.status_code == 409

def test_pair_test_results_404_for_out_of_range_pair_index(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/pair/{n}/test-results returns 404 when the pair index is out of range."""
    result_data = _make_grid_response_dict()
    store.seed_job(
        "gsood",
        status="success",
        payload_overview={"optimization_type": "grid_search"},
        result=result_data,
        payload={
            "dataset": [{"q": f"q{i}", "a": f"a{i}"} for i in range(10)],
            "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
            "split_fractions": {"train": 0.7, "val": 0.15, "test": 0.15},
            "shuffle": False,
        },
    )

    resp = opt_client.get("/optimizations/gsood/pair/99/test-results")

    assert resp.status_code == 404

def test_pair_test_results_happy_path(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/pair/{n}/test-results returns remapped baseline and optimized results."""
    result_data = _make_grid_response_dict()
    store.seed_job(
        "gs_happy",
        status="success",
        payload_overview={"optimization_type": "grid_search"},
        result=result_data,
        payload={
            "dataset": [{"q": f"q{i}", "a": f"a{i}"} for i in range(10)],
            "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
            "split_fractions": {"train": 0.7, "val": 0.15, "test": 0.15},
            "shuffle": False,
        },
    )

    resp = opt_client.get("/optimizations/gs_happy/pair/0/test-results")

    assert resp.status_code == 200
    body = resp.json()
    assert "baseline" in body and "optimized" in body
    # fixture has 3 test results per pair; 10-row dataset → 2 test slots → all 3 remapped
    assert len(body["baseline"]) == 3 and len(body["optimized"]) == 3
    # shuffle=False, train_end=7, val_end=8 → test_indices=[8,9]; seq_idx=0 → global 8
    assert body["baseline"][0]["index"] == 8

def test_artifact_returns_500_when_result_blob_is_corrupted(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """GET /optimizations/{id}/artifact returns 500 when the stored result dict is not a valid RunResponse."""
    # A dict that passes isinstance(result_data, dict) but fails RunResponse.model_validate
    corrupt_result = {"garbage": True, "not_a_valid_run_response": 42}
    store.seed_job("corrupted", status="success", result=corrupt_result)

    resp = opt_client.get("/optimizations/corrupted/artifact")

    assert resp.status_code == 500


def test_delete_pair_returns_404_for_unknown_job(opt_client: TestClient) -> None:
    """DELETE /optimizations/{id}/pair/{n} returns 404 for an unknown job id."""
    resp = opt_client.delete("/optimizations/missing/pair/0")

    assert resp.status_code == 404


def test_delete_pair_returns_404_for_non_grid_search(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """DELETE /optimizations/{id}/pair/{n} returns 404 when the job is not a grid search."""
    store.seed_job(
        "run_job",
        status="success",
        payload_overview={"optimization_type": "run"},
    )

    resp = opt_client.delete("/optimizations/run_job/pair/0")

    assert resp.status_code == 404


def test_delete_pair_returns_409_when_job_not_terminal(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """DELETE /optimizations/{id}/pair/{n} returns 409 when the grid search is still running."""
    store.seed_job(
        "gs_running",
        status="running",
        payload_overview={"optimization_type": "grid_search"},
    )

    resp = opt_client.delete("/optimizations/gs_running/pair/0")

    assert resp.status_code == 409


def test_delete_pair_returns_404_for_missing_pair_index(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """DELETE /optimizations/{id}/pair/{n} returns 404 when the pair_index is not in pair_results."""
    result_data = _make_grid_response_dict()
    store.seed_job(
        "gs_missing_pair",
        status="success",
        payload_overview={"optimization_type": "grid_search"},
        result=result_data,
    )

    resp = opt_client.delete("/optimizations/gs_missing_pair/pair/99")

    assert resp.status_code == 404


def test_delete_pair_happy_path_removes_pair_and_recomputes_counts(
    opt_client: TestClient, store: _ExtendedFakeJobStore
) -> None:
    """DELETE /optimizations/{id}/pair/{n} removes the pair and returns the updated grid result."""
    result_data = _make_grid_response_dict()
    original_total = result_data["total_pairs"]
    removed_index = result_data["pair_results"][0]["pair_index"]

    store.seed_job(
        "gs_delete_ok",
        status="success",
        payload_overview={"optimization_type": "grid_search"},
        result=result_data,
    )

    resp = opt_client.delete(f"/optimizations/gs_delete_ok/pair/{removed_index}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_pairs"] == original_total - 1
    remaining_indices = [pr["pair_index"] for pr in body["pair_results"]]
    assert removed_index not in remaining_indices

    stored = store.get_job("gs_delete_ok")
    stored_indices = [pr["pair_index"] for pr in stored["result"]["pair_results"]]
    assert removed_index not in stored_indices
