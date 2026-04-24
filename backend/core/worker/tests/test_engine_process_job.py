"""Unit tests for BackgroundWorker._process_job — error branches.

All subprocess/multiprocessing calls are mocked; no real child processes
are spawned.  FakeJobStore from conftest is used as the in-memory store.
"""

from __future__ import annotations

import inspect
import json
from unittest.mock import MagicMock, patch

import pytest

from .. import engine as engine_module
from ..engine import BackgroundWorker, reset_worker_for_tests
from ..subprocess_runner import EVENT_RESULT

from .conftest import FakeJobStore
from .mocks import REAL_GRID_PAYLOAD, REAL_RUN_PAYLOAD, make_mp_context


@pytest.fixture(autouse=True)
def _reset_global_worker() -> None:
    """Ensure the module-level singleton is cleared before and after each test."""
    reset_worker_for_tests()
    yield
    reset_worker_for_tests()


@pytest.fixture
def store() -> FakeJobStore:
    """Return a fresh FakeJobStore for each test."""
    return FakeJobStore()


@pytest.fixture
def worker(store: FakeJobStore) -> BackgroundWorker:
    """Return an unstarted single-worker BackgroundWorker."""
    return BackgroundWorker(job_store=store, num_workers=1, poll_interval=1.0)



def test_process_job_raises_when_payload_is_none(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """A None payload causes _process_job to set status=failed without raising."""
    store.seed_job("opt-1", payload=None)
    worker.enqueue_job("opt-1")

    with patch("core.worker.engine.notify_job_completed"):
        worker._process_job("opt-1", 0)  # must not raise — error handled internally

    assert store._jobs["opt-1"]["status"] == "failed"


def test_process_job_raises_when_payload_is_empty_dict(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """An empty-dict payload causes _process_job to set status=failed without raising."""
    store.seed_job("opt-1", payload={})
    worker.enqueue_job("opt-1")

    with patch("core.worker.engine.notify_job_completed"):
        worker._process_job("opt-1", 0)  # must not raise — error handled internally

    assert store._jobs["opt-1"]["status"] == "failed"



def test_process_job_parses_json_string_payload_overview(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """When payload_overview is a JSON-encoded string it must be decoded, not treated as dict."""
    overview_str = json.dumps({"optimization_type": "run", "username": "alice"})
    store.seed_job(
        "opt-2",
        payload=REAL_RUN_PAYLOAD,
        payload_overview=overview_str,
    )
    worker.enqueue_job("opt-2")

    ctx, proc = make_mp_context(
        exitcode=0,
        result_events=[{"type": EVENT_RESULT, "result": {"baseline_test_metric": 0.5, "optimized_test_metric": 0.7}}],
    )
    worker._mp_ctx = ctx
    worker._mp_start_method = "spawn"

    with patch("core.worker.engine.notify_job_completed"), \
         patch.object(worker, "_get_service") as mock_svc:
        mock_svc.return_value.validate_payload = MagicMock()
        mock_svc.return_value.validate_grid_search_payload = MagicMock()
        worker._process_job("opt-2", 0)

    # If the JSON-string branch worked, job succeeded (not failed due to bad overview).
    assert store._jobs["opt-2"]["status"] == "success"


def test_process_job_handles_invalid_json_string_payload_overview_gracefully(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """An unparseable payload_overview string must fall back to {} (no crash)."""
    store.seed_job(
        "opt-3",
        payload=REAL_RUN_PAYLOAD,
        payload_overview="not-json-at-all",
    )
    worker.enqueue_job("opt-3")

    ctx, proc = make_mp_context(
        exitcode=0,
        result_events=[{"type": EVENT_RESULT, "result": {"baseline_test_metric": 0.5, "optimized_test_metric": 0.7}}],
    )
    worker._mp_ctx = ctx
    worker._mp_start_method = "spawn"

    with patch("core.worker.engine.notify_job_completed"), \
         patch.object(worker, "_get_service") as mock_svc:
        mock_svc.return_value.validate_payload = MagicMock()
        worker._process_job("opt-3", 0)

    assert store._jobs["opt-3"]["status"] == "success"



def test_process_job_sets_status_failed_on_nonzero_exit_without_result(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """A non-zero subprocess exit code with no result event sets status=failed."""
    store.seed_job("opt-4", payload=REAL_RUN_PAYLOAD)
    worker.enqueue_job("opt-4")

    # Exit code 1, no result events → RuntimeError caught by BaseException handler
    ctx, proc = make_mp_context(exitcode=1, result_events=[])
    worker._mp_ctx = ctx
    worker._mp_start_method = "spawn"

    with patch("core.worker.engine.notify_job_completed"), \
         patch.object(worker, "_get_service") as mock_svc:
        mock_svc.return_value.validate_payload = MagicMock()
        worker._process_job("opt-4", 0)  # must not raise — error handled internally

    assert store._jobs["opt-4"]["status"] == "failed"



def test_process_job_sets_status_failed_when_subprocess_sends_no_result(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """Exit code 0 with an empty event queue (no result) sets status=failed."""
    store.seed_job("opt-5", payload=REAL_RUN_PAYLOAD)
    worker.enqueue_job("opt-5")

    # Exit code 0 but queue is empty → no result_dict → RuntimeError caught internally
    ctx, proc = make_mp_context(exitcode=0, result_events=[])
    worker._mp_ctx = ctx
    worker._mp_start_method = "spawn"

    with patch("core.worker.engine.notify_job_completed"), \
         patch.object(worker, "_get_service") as mock_svc:
        mock_svc.return_value.validate_payload = MagicMock()
        worker._process_job("opt-5", 0)  # must not raise — error handled internally

    assert store._jobs["opt-5"]["status"] == "failed"



def test_process_job_grid_search_all_pairs_failed_sets_status_failed(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """A grid-search result with completed_pairs=0 sets status=failed."""
    payload = REAL_GRID_PAYLOAD
    store.seed_job(
        "opt-6",
        payload=payload,
        payload_overview={"optimization_type": "grid_search", "username": "bob"},
    )
    worker.enqueue_job("opt-6")

    grid_result = {
        "completed_pairs": 0,
        "total_pairs": 3,
        "pair_results": [
            {"error": "model timeout"},
            {"error": "out of memory"},
            {"error": "model timeout"},
        ],
    }
    ctx, proc = make_mp_context(
        exitcode=0,
        result_events=[{"type": EVENT_RESULT, "result": grid_result}],
    )
    worker._mp_ctx = ctx
    worker._mp_start_method = "spawn"

    with patch("core.worker.engine.notify_job_completed"), \
         patch.object(worker, "_get_service") as mock_svc:
        mock_svc.return_value.validate_grid_search_payload = MagicMock()
        worker._process_job("opt-6", 0)

    assert store._jobs["opt-6"]["status"] == "failed"
    assert "model timeout" in store._jobs["opt-6"]["message"]


def test_process_job_grid_search_all_pairs_failed_message_includes_first_error(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """The failure message includes the first error string from pair_results."""
    payload = REAL_GRID_PAYLOAD
    store.seed_job(
        "opt-7",
        payload=payload,
        payload_overview={"optimization_type": "grid_search", "username": "bob"},
    )
    worker.enqueue_job("opt-7")

    grid_result = {
        "completed_pairs": 0,
        "total_pairs": 2,
        "pair_results": [{"error": "first error detail"}, {"error": "second error"}],
    }
    ctx, proc = make_mp_context(
        exitcode=0,
        result_events=[{"type": EVENT_RESULT, "result": grid_result}],
    )
    worker._mp_ctx = ctx
    worker._mp_start_method = "spawn"

    with patch("core.worker.engine.notify_job_completed"), \
         patch.object(worker, "_get_service") as mock_svc:
        mock_svc.return_value.validate_grid_search_payload = MagicMock()
        worker._process_job("opt-7", 0)

    assert "first error detail" in store._jobs["opt-7"]["message"]



def test_process_job_handles_key_error_when_job_deleted_mid_run(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """When get_job raises KeyError (job deleted), _process_job must log and return cleanly."""
    store.seed_job("opt-8", payload=REAL_RUN_PAYLOAD)
    worker.enqueue_job("opt-8")

    good_result = {"baseline_test_metric": 0.5, "optimized_test_metric": 0.7}
    ctx, proc = make_mp_context(
        exitcode=0,
        result_events=[{"type": EVENT_RESULT, "result": good_result}],
    )
    worker._mp_ctx = ctx
    worker._mp_start_method = "spawn"

    original_get_job = store.get_job
    call_count = {"n": 0}

    def _get_job_side_effect(opt_id: str):
        call_count["n"] += 1
        # First call (load payload): return normally.
        # Second call (post-result status check): raise KeyError.
        if call_count["n"] >= 2:
            raise KeyError(opt_id)
        return original_get_job(opt_id)

    store.get_job = _get_job_side_effect

    # Must NOT raise even though get_job raises KeyError on the second call.
    with patch("core.worker.engine.notify_job_completed"), \
         patch.object(worker, "_get_service") as mock_svc:
        mock_svc.return_value.validate_payload = MagicMock()
        worker._process_job("opt-8", 0)  # must not raise



def test_process_job_cancellation_error_notifies_cancelled(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """CancellationError fired *after* overview is assigned → notify called with status='cancelled'.

    We trigger cancel at the second _check_cancel() (after validation) by setting the event
    inside validate_payload, which is called after overview is assigned.
    """
    store.seed_job("opt-9", payload=REAL_RUN_PAYLOAD)
    worker.enqueue_job("opt-9")

    notify_mock = MagicMock()

    def _set_cancel_then_validate(*args, **kwargs):
        worker._cancel_events["opt-9"].set()

    with patch("core.worker.engine.notify_job_completed", notify_mock), \
         patch.object(worker, "_get_service") as mock_svc:
        mock_svc.return_value.validate_payload.side_effect = _set_cancel_then_validate
        worker._process_job("opt-9", 0)

    # notify_job_completed must have been called with status='cancelled'.
    call_kwargs = notify_mock.call_args_list
    assert any(kw.get("status") == "cancelled" for _, kw in call_kwargs)


def test_process_job_cancellation_error_uses_hebrew_message(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """The Hebrew cancellation message must appear in the engine code path."""
    from core.i18n import CANCELLATION_REASON
    source = inspect.getsource(engine_module)
    assert "CANCELLATION_REASON" in source
    assert CANCELLATION_REASON == "בוטלה על ידי המשתמש"


def test_process_job_generic_exception_sets_status_failed(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """A generic exception during validation results in status=failed without re-raising."""
    store.seed_job("opt-10", payload=REAL_RUN_PAYLOAD)
    worker.enqueue_job("opt-10")

    ctx, proc = make_mp_context(exitcode=0, result_events=[])
    worker._mp_ctx = ctx
    worker._mp_start_method = "spawn"

    with patch("core.worker.engine.notify_job_completed"), \
         patch.object(worker, "_get_service") as mock_svc:
        # validate_payload raises a generic exception (after overview is assigned)
        mock_svc.return_value.validate_payload.side_effect = RuntimeError("boom")
        worker._process_job("opt-10", 0)  # must not raise — error handled internally

    assert store._jobs["opt-10"]["status"] == "failed"


def test_process_job_system_exit_sets_status_failed_and_reraises(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """SystemExit must set status='failed' and then re-raise (is_shutdown=True path)."""
    store.seed_job("opt-11", payload=REAL_RUN_PAYLOAD)
    worker.enqueue_job("opt-11")

    ctx, proc = make_mp_context(exitcode=0, result_events=[])
    worker._mp_ctx = ctx
    worker._mp_start_method = "spawn"

    with patch("core.worker.engine.notify_job_completed"), \
         patch.object(worker, "_get_service") as mock_svc:
        mock_svc.return_value.validate_payload.side_effect = SystemExit(1)
        with pytest.raises(SystemExit):
            worker._process_job("opt-11", 0)

    assert store._jobs["opt-11"]["status"] == "failed"


def test_process_job_keyboard_interrupt_sets_status_failed_and_reraises(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """KeyboardInterrupt (is_shutdown=True) must set status='failed' and re-raise."""
    store.seed_job("opt-12", payload=REAL_RUN_PAYLOAD)
    worker.enqueue_job("opt-12")

    ctx, proc = make_mp_context(exitcode=0, result_events=[])
    worker._mp_ctx = ctx
    worker._mp_start_method = "spawn"

    with patch("core.worker.engine.notify_job_completed"), \
         patch.object(worker, "_get_service") as mock_svc:
        mock_svc.return_value.validate_payload.side_effect = KeyboardInterrupt()
        with pytest.raises(KeyboardInterrupt):
            worker._process_job("opt-12", 0)

    assert store._jobs["opt-12"]["status"] == "failed"
