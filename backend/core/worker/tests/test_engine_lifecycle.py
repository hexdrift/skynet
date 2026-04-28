"""Unit tests for core.worker.engine — lifecycle methods skipped by the prior agent.

Methods tested (no real subprocesses, no real multiprocessing.Queue):
  BackgroundWorker._drain_subprocess_events — drain loop against a fixed-event fake queue
  BackgroundWorker._terminate_run_process   — cancel-flag path and hard-kill timeout path
  BackgroundWorker.submit_job               — payload stored, job enqueued
  BackgroundWorker.dump_thread_stacks       — returns a string without raising
  get_worker                                — singleton contract, pending IDs enqueued
  reset_worker_for_tests                    — clears the module-level singleton

Methods intentionally NOT tested here:
  start() / _worker_loop() / _process_job() — require real threads + real mp.Process
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock, call

import pytest

import core.worker.engine as engine_module
from core.storage.base import JobStore
from core.worker.constants import (
    EVENT_ERROR,
    EVENT_LOG,
    EVENT_PROGRESS,
    EVENT_RESULT,
)
from core.worker.engine import BackgroundWorker, get_worker, reset_worker_for_tests

from .conftest import FakeJobStore
from .mocks import fake_mp_process


@pytest.fixture(autouse=True)
def _reset_global_worker() -> Iterator[None]:
    """Reset the module-level singleton before and after each test."""
    reset_worker_for_tests()
    yield
    reset_worker_for_tests()


@pytest.fixture
def store() -> FakeJobStore:
    """Yield a fresh in-memory job store for a test."""
    return FakeJobStore()


@pytest.fixture
def worker(store: FakeJobStore) -> BackgroundWorker:
    """Build an unstarted BackgroundWorker bound to the test store."""
    return BackgroundWorker(job_store=cast(JobStore, store), num_workers=2, poll_interval=1.0)


def _make_fake_queue(*events: dict) -> queue.Queue:
    """Build a real ``queue.Queue`` prefilled with the given events."""
    q: queue.Queue = queue.Queue()
    for event in events:
        q.put(event)
    return q


def test_drain_returns_none_result_and_none_error_for_empty_queue(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """An empty queue yields ``(None, None)``."""
    store.seed_job("opt-1")
    q = _make_fake_queue()

    result, error = worker._drain_subprocess_events("opt-1", q)

    assert result is None
    assert error is None


def test_drain_routes_progress_event_to_record_progress(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """A progress event is forwarded to ``record_progress``."""
    store.seed_job("opt-1")
    q = _make_fake_queue({"type": EVENT_PROGRESS, "event": "iter_done", "metrics": {"score": 0.8}})

    worker._drain_subprocess_events("opt-1", q)

    assert len(store.record_progress_calls) == 1
    opt_id, evt_name, metrics = store.record_progress_calls[0]
    assert opt_id == "opt-1"
    assert evt_name == "iter_done"
    assert metrics == {"score": 0.8}


def test_drain_routes_log_event_to_append_log(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """A log event is forwarded to ``append_log`` with parsed fields."""
    store.seed_job("opt-1")
    q = _make_fake_queue(
        {
            "type": EVENT_LOG,
            "timestamp": "2024-06-01T12:00:00+00:00",
            "level": "WARNING",
            "logger": "dspy.core",
            "message": "something happened",
        }
    )

    worker._drain_subprocess_events("opt-1", q)

    assert len(store.append_log_calls) == 1
    entry = store.append_log_calls[0]
    assert entry["level"] == "WARNING"
    assert entry["logger_name"] == "dspy.core"
    assert entry["message"] == "something happened"
    assert entry["timestamp"] is not None


def test_drain_parses_log_timestamp_to_datetime(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """ISO timestamp strings are parsed to UTC-aware ``datetime`` values."""
    store.seed_job("opt-1")
    q = _make_fake_queue(
        {
            "type": EVENT_LOG,
            "timestamp": "2024-01-01T00:00:00+00:00",
            "level": "INFO",
            "logger": "dspy",
            "message": "ts test",
        }
    )

    worker._drain_subprocess_events("opt-1", q)

    ts = store.append_log_calls[0]["timestamp"]
    assert isinstance(ts, datetime)
    assert ts.tzinfo is not None
    assert ts == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)


def test_drain_sets_log_timestamp_to_none_on_invalid_timestamp_string(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """An unparseable timestamp string falls back to ``None``."""
    store.seed_job("opt-1")
    q = _make_fake_queue(
        {
            "type": EVENT_LOG,
            "timestamp": "not-a-date",
            "level": "INFO",
            "logger": "dspy",
            "message": "bad ts",
        }
    )

    worker._drain_subprocess_events("opt-1", q)

    assert store.append_log_calls[0]["timestamp"] is None


def test_drain_returns_result_payload_from_result_event(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """A ``result`` event surfaces its payload from the drain call."""
    store.seed_job("opt-1")
    payload = {"baseline_test_metric": 0.5, "optimized_test_metric": 0.7}
    q = _make_fake_queue({"type": EVENT_RESULT, "result": payload})

    result, error = worker._drain_subprocess_events("opt-1", q)

    assert result == payload
    assert error is None


def test_drain_ignores_result_event_when_result_is_not_dict(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """A non-dict ``result`` payload is ignored."""
    store.seed_job("opt-1")
    q = _make_fake_queue({"type": EVENT_RESULT, "result": "not-a-dict"})

    result, _error = worker._drain_subprocess_events("opt-1", q)

    assert result is None


def test_drain_returns_error_payload_from_error_event(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """An ``error`` event surfaces its payload from the drain call."""
    store.seed_job("opt-1")
    q = _make_fake_queue({"type": EVENT_ERROR, "error": "boom", "traceback": "Traceback..."})

    result, error = worker._drain_subprocess_events("opt-1", q)

    assert result is None
    assert error is not None
    assert error["error"] == "boom"
    assert error["traceback"] == "Traceback..."


def test_drain_processes_all_events_in_a_mixed_sequence(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """Drain handles a mixed sequence of progress/log/result events."""
    store.seed_job("opt-1")
    q = _make_fake_queue(
        {"type": EVENT_PROGRESS, "event": "step_a", "metrics": {}},
        {"type": EVENT_LOG, "timestamp": None, "level": "INFO", "logger": "dspy", "message": "log line"},
        {"type": EVENT_RESULT, "result": {"val": 99}},
    )

    result, error = worker._drain_subprocess_events("opt-1", q)

    assert result == {"val": 99}
    assert error is None
    assert len(store.record_progress_calls) == 1
    assert len(store.append_log_calls) == 1


def test_drain_last_result_event_wins_when_multiple_present(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """The most recently seen result payload is the one returned."""
    store.seed_job("opt-1")
    q = _make_fake_queue(
        {"type": EVENT_RESULT, "result": {"val": 1}},
        {"type": EVENT_RESULT, "result": {"val": 2}},
    )

    result, _ = worker._drain_subprocess_events("opt-1", q)

    assert result == {"val": 2}


def test_drain_silently_ignores_unknown_event_types(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """Drain silently ignores events of unknown ``type``."""
    store.seed_job("opt-1")
    q = _make_fake_queue({"type": "totally_unknown", "data": "ignored"})

    result, error = worker._drain_subprocess_events("opt-1", q)

    assert result is None
    assert error is None
    assert store.record_progress_calls == []
    assert store.append_log_calls == []


def test_drain_swallows_record_progress_store_error(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """Drain does not propagate exceptions from ``record_progress``."""
    store.seed_job("opt-1")
    store.record_progress = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("DB error"))  # type: ignore[method-assign]
    q = _make_fake_queue({"type": EVENT_PROGRESS, "event": "e", "metrics": {}})

    # Must not raise.
    worker._drain_subprocess_events("opt-1", q)


def test_drain_swallows_append_log_store_error(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """Drain does not propagate exceptions from ``append_log``."""
    store.seed_job("opt-1")
    store.append_log = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("DB error"))  # type: ignore[method-assign]
    q = _make_fake_queue({"type": EVENT_LOG, "timestamp": None, "level": "INFO", "logger": "dspy", "message": "hi"})

    # Must not raise.
    worker._drain_subprocess_events("opt-1", q)


def test_terminate_run_process_calls_terminate_then_join(
    worker: BackgroundWorker,
) -> None:
    """``_terminate_run_process`` issues terminate + join on a graceful exit."""
    # is_alive() is called twice: once before kill check, once for final log.
    # Return False on first call → skip kill; False on second call → log "terminated".
    proc = fake_mp_process(is_alive=[False, False])

    worker._terminate_run_process(proc, "opt-1")

    proc.terminate.assert_called_once()
    assert any(c == call(timeout=3.0) for c in proc.join.call_args_list)


def test_terminate_run_process_calls_kill_when_process_survives_terminate(
    worker: BackgroundWorker,
) -> None:
    """``_terminate_run_process`` escalates to ``kill`` if the process is still alive."""
    # Still alive at first is_alive() check (before kill); dead after kill's join.
    proc = fake_mp_process(is_alive=[True, False])

    worker._terminate_run_process(proc, "opt-1")

    proc.kill.assert_called_once()


def test_terminate_run_process_does_not_call_kill_when_terminate_succeeds(
    worker: BackgroundWorker,
) -> None:
    """``_terminate_run_process`` skips ``kill`` when terminate succeeds."""
    # Return False on the first is_alive() — process already dead after terminate+join.
    proc = fake_mp_process(is_alive=[False, False])

    worker._terminate_run_process(proc, "opt-1")

    proc.kill.assert_not_called()


def test_terminate_run_process_does_not_raise_when_stuck_process_never_dies(
    worker: BackgroundWorker,
) -> None:
    """``_terminate_run_process`` does not raise when the process never dies."""
    proc = fake_mp_process(is_alive=True)

    # Should not raise.
    worker._terminate_run_process(proc, "opt-stuck")

    proc.terminate.assert_called_once()
    proc.kill.assert_called_once()


def test_terminate_run_process_skips_kill_when_process_has_no_kill_method(
    worker: BackgroundWorker,
) -> None:
    """``_terminate_run_process`` skips ``kill`` when the process lacks the method."""
    proc = MagicMock(spec=["terminate", "join", "is_alive"])
    # still alive after terminate
    proc.is_alive.side_effect = [True, True, False]

    # MagicMock with spec= won't have 'kill', so hasattr returns False.
    # _terminate_run_process uses hasattr(run_process, 'kill'), so no kill call.
    worker._terminate_run_process(proc, "opt-1")

    assert not hasattr(proc, "kill")


def test_submit_job_stores_payload_in_job_store(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """``submit_job`` writes the dumped payload onto the job row."""
    store.seed_job("opt-1")
    payload = MagicMock()
    payload.model_dump.return_value = {"key": "value"}

    worker.submit_job("opt-1", payload)

    assert store._jobs["opt-1"]["payload"] == {"key": "value"}


def test_submit_job_calls_model_dump_with_json_mode_and_alias(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """``submit_job`` serialises with ``mode="json"`` and ``by_alias=True``."""
    store.seed_job("opt-1")
    payload = MagicMock()
    payload.model_dump.return_value = {}

    worker.submit_job("opt-1", payload)

    payload.model_dump.assert_called_once_with(mode="json", by_alias=True)


def test_submit_job_leaves_row_pending_for_db_claim(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """``submit_job`` leaves the row pending so any pod's worker can claim it.

    The DB-backed claim queue replaces the old in-memory enqueue: the next
    worker tick — on this pod or a peer — picks the job up via
    ``claim_next_job``.
    """
    store.seed_job("opt-1")
    payload = MagicMock()
    payload.model_dump.return_value = {}

    pre_status = store._jobs["opt-1"]["status"]

    worker.submit_job("opt-1", payload)

    # Status is unchanged: ``submit_job`` only writes the payload — it does
    # not transition to ``running``/``validating``. Pickup happens later on
    # the next worker tick via ``claim_next_job``.
    assert store._jobs["opt-1"]["status"] == pre_status
    # The local hint queue is intentionally not used by ``submit_job`` so two
    # pods can balance load via ``claim_next_job``.
    assert "opt-1" not in worker._pending_jobs


def test_submit_job_creates_cancel_event(
    worker: BackgroundWorker,
    store: FakeJobStore,
) -> None:
    """``submit_job`` registers a ``threading.Event`` as the cancel signal."""
    store.seed_job("opt-1")
    payload = MagicMock()
    payload.model_dump.return_value = {}

    worker.submit_job("opt-1", payload)

    assert "opt-1" in worker._cancel_events
    assert isinstance(worker._cancel_events["opt-1"], threading.Event)


def test_dump_thread_stacks_returns_string_without_raising(
    worker: BackgroundWorker,
) -> None:
    """``dump_thread_stacks`` returns a string and never raises."""
    result = worker.dump_thread_stacks()

    assert isinstance(result, str)


def test_dump_thread_stacks_returns_empty_string_when_no_threads_started(
    worker: BackgroundWorker,
) -> None:
    """An unstarted worker produces an empty thread dump."""
    result = worker.dump_thread_stacks()

    assert result == ""


def test_dump_thread_stacks_includes_thread_name_when_threads_are_running() -> None:
    """A running worker includes its thread names in the dump."""
    store = FakeJobStore()
    w = BackgroundWorker(job_store=cast(JobStore, store), num_workers=1, poll_interval=0.05)
    w.start()
    try:
        result = w.dump_thread_stacks()
        assert "dspy-worker-0" in result
    finally:
        w.stop(timeout=2.0)


def test_get_worker_returns_a_background_worker_instance(
    store: FakeJobStore,
) -> None:
    """``get_worker`` returns a ``BackgroundWorker`` singleton."""
    w = get_worker(cast(JobStore, store))

    assert isinstance(w, BackgroundWorker)
    w.stop(timeout=2.0)


def test_get_worker_returns_same_instance_on_repeated_calls(
    store: FakeJobStore,
) -> None:
    """Repeated ``get_worker`` calls return the same singleton."""
    w1 = get_worker(cast(JobStore, store))
    w2 = get_worker(cast(JobStore, store))

    assert w1 is w2
    w1.stop(timeout=2.0)


def test_get_worker_enqueues_pending_optimization_ids(
    store: FakeJobStore,
) -> None:
    """``get_worker`` re-enqueues IDs passed via ``pending_optimization_ids``."""
    w = get_worker(cast(JobStore, store), pending_optimization_ids=["opt-a", "opt-b"])

    assert "opt-a" in w._pending_jobs or "opt-a" in w._processing_jobs or "opt-a" in w._cancel_events
    w.stop(timeout=2.0)


def test_reset_worker_for_tests_clears_module_global(
    store: FakeJobStore,
) -> None:
    """``reset_worker_for_tests`` clears the module-level singleton."""
    get_worker(cast(JobStore, store))

    reset_worker_for_tests()

    assert engine_module._worker is None


def test_reset_worker_for_tests_is_idempotent_when_no_worker_exists() -> None:
    """Calling ``reset_worker_for_tests`` twice does not raise."""
    reset_worker_for_tests()
    reset_worker_for_tests()  # second call — still should not raise


def test_get_worker_creates_new_instance_after_reset(
    store: FakeJobStore,
) -> None:
    """``get_worker`` returns a fresh instance after a reset."""
    w1 = get_worker(cast(JobStore, store))
    w1.stop(timeout=2.0)
    reset_worker_for_tests()

    w2 = get_worker(cast(JobStore, store))

    assert w2 is not w1
    w2.stop(timeout=2.0)


def test_init_falls_back_to_1_0_when_cancel_poll_interval_is_not_a_float(
    store: FakeJobStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Init falls back to ``1.0`` when ``cancel_poll_interval`` cannot be parsed."""
    # Patch settings on the engine module so ``str(settings.cancel_poll_interval)``
    # returns a value that ``float()`` cannot parse — exercising the
    # ``except ValueError`` fallback in ``BackgroundWorker.__init__``.
    class _FakeSettings:
        cancel_poll_interval = "not-a-float"
        job_run_start_method = "fork"

    monkeypatch.setattr(engine_module, "settings", _FakeSettings())

    # Must not raise; must use 1.0 as the fallback.
    w = BackgroundWorker(job_store=cast(JobStore, store), num_workers=1, poll_interval=1.0)
    assert w._cancel_poll_interval == 1.0


def test_resolve_mp_context_raises_and_falls_back_on_bogus_method(
    store: FakeJobStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_resolve_mp_context`` falls back to a default context for bad methods."""
    class _FakeSettings:
        cancel_poll_interval = 1.0
        job_run_start_method = "bogus_method"

    monkeypatch.setattr(engine_module, "settings", _FakeSettings())

    # mp.get_context("bogus_method") raises ValueError.
    ctx = BackgroundWorker._resolve_mp_context()
    # The fallback context must be valid (non-None) and support get_start_method().
    assert ctx is not None
    assert ctx.get_start_method() in ("fork", "spawn", "forkserver")


def test_resolve_mp_context_emits_warning_for_bogus_method(
    store: FakeJobStore,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``_resolve_mp_context`` warns when an unknown start method is configured."""
    class _FakeSettings:
        cancel_poll_interval = 1.0
        job_run_start_method = "definitely_invalid"

    monkeypatch.setattr(engine_module, "settings", _FakeSettings())

    with caplog.at_level("WARNING", logger="core.worker.engine"):
        BackgroundWorker._resolve_mp_context()

    assert any("definitely_invalid" in msg for msg in caplog.messages)


def test_resolve_mp_context_emits_warning_for_non_fork_method(
    store: FakeJobStore,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``_resolve_mp_context`` warns when a non-fork method is configured."""
    class _FakeSettings:
        cancel_poll_interval = 1.0
        job_run_start_method = "spawn"

    monkeypatch.setattr(engine_module, "settings", _FakeSettings())

    with caplog.at_level("WARNING", logger="core.worker.engine"):
        BackgroundWorker._resolve_mp_context()

    # spawn is a valid method — the second warning about registry callables fires.
    assert any("spawn" in msg for msg in caplog.messages)


def test_stop_sets_all_cancel_events(store: FakeJobStore) -> None:
    """stop() must set every cancel event so running jobs can detect shutdown promptly."""
    w = BackgroundWorker(job_store=cast(JobStore, store), num_workers=1, poll_interval=0.05)
    w.start()
    try:
        # Register several cancel events manually (as submit_job / enqueue_job would).
        event_a = threading.Event()
        event_b = threading.Event()
        event_c = threading.Event()
        with w._queue_lock:
            w._cancel_events["job-a"] = event_a
            w._cancel_events["job-b"] = event_b
            w._cancel_events["job-c"] = event_c

        w.stop(timeout=2.0)

        assert event_a.is_set(), "event_a must be set after stop()"
        assert event_b.is_set(), "event_b must be set after stop()"
        assert event_c.is_set(), "event_c must be set after stop()"
    except Exception:
        w.stop(timeout=1.0)
        raise
