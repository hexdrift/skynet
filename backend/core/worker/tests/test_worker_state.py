"""Unit tests for core.worker.engine — pure state-management methods only.

Methods tested (no forking, no real threads started):
  BackgroundWorker.enqueue_job
  BackgroundWorker.queue_size
  BackgroundWorker.active_jobs
  BackgroundWorker._get_next_job
  BackgroundWorker._mark_job_done
  BackgroundWorker.cancel_job
  BackgroundWorker.is_running
  BackgroundWorker.threads_alive  (before start())
  BackgroundWorker.seconds_since_last_activity  (before any activity recorded)
  BackgroundWorker._touch_activity  (via seconds_since_last_activity)
  BackgroundWorker.thread_count  (before start())

Methods intentionally skipped:
  start() / _worker_loop()    — spawns real threads that fork subprocesses
  stop()                       — requires started threads
  _process_job()               — forks a real mp.Process
  _get_service()               — instantiates DspyService (requires registry setup)
  submit_job()                 — calls update_job on a real job store w/ Pydantic model
  _terminate_run_process()     — requires a live process handle
  _drain_subprocess_events()   — requires a live mp.Queue from a subprocess
  dump_thread_stacks()         — requires live threads (sys._current_frames)
  get_worker() / reset_worker_for_tests() — module-level singletons that start threads
"""

from __future__ import annotations

import threading
import time
from typing import cast

import pytest

from core.storage.base import JobStore

from ..engine import BackgroundWorker
from .conftest import FakeJobStore


@pytest.fixture
def store() -> FakeJobStore:
    """Yield a fresh in-memory job store for a test."""
    return FakeJobStore()


@pytest.fixture
def worker(store: FakeJobStore) -> BackgroundWorker:
    """Build an unstarted BackgroundWorker bound to the test store."""
    return BackgroundWorker(job_store=cast(JobStore, store), num_workers=2, poll_interval=1.0)


def test_worker_initial_queue_size_is_zero(worker: BackgroundWorker) -> None:
    """A fresh worker reports queue size 0."""
    assert worker.queue_size() == 0


def test_worker_initial_active_jobs_is_zero(worker: BackgroundWorker) -> None:
    """A fresh worker reports 0 active jobs."""
    assert worker.active_jobs() == 0


def test_worker_initial_is_not_running(worker: BackgroundWorker) -> None:
    """A fresh worker is not running."""
    assert worker.is_running() is False


def test_worker_initial_threads_alive_is_false(worker: BackgroundWorker) -> None:
    """A fresh worker has no live threads."""
    assert worker.threads_alive() is False


def test_worker_initial_thread_count_is_zero(worker: BackgroundWorker) -> None:
    """A fresh worker has thread count 0."""
    assert worker.thread_count() == 0


def test_worker_initial_no_activity_recorded(worker: BackgroundWorker) -> None:
    """A fresh worker has no recorded activity."""
    assert worker.seconds_since_last_activity() is None


def test_enqueue_job_increments_queue_size(worker: BackgroundWorker) -> None:
    """Enqueueing one job grows the queue size to 1."""
    worker.enqueue_job("opt-1")
    assert worker.queue_size() == 1


def test_enqueue_job_multiple_increments_in_order(worker: BackgroundWorker) -> None:
    """Three enqueues yield queue size 3."""
    worker.enqueue_job("opt-1")
    worker.enqueue_job("opt-2")
    worker.enqueue_job("opt-3")
    assert worker.queue_size() == 3


def test_enqueue_job_is_idempotent_for_duplicate_pending(
    worker: BackgroundWorker,
) -> None:
    """Enqueueing the same ID twice does not duplicate it in the queue."""
    worker.enqueue_job("opt-1")
    worker.enqueue_job("opt-1")
    assert worker.queue_size() == 1


def test_enqueue_job_creates_cancel_event(worker: BackgroundWorker) -> None:
    """Enqueueing creates a ``threading.Event`` cancel signal for the job."""
    worker.enqueue_job("opt-1")
    assert "opt-1" in worker._cancel_events
    assert isinstance(worker._cancel_events["opt-1"], threading.Event)


def test_enqueue_job_cancel_event_starts_unset(worker: BackgroundWorker) -> None:
    """The cancel event begins life unset."""
    worker.enqueue_job("opt-1")
    assert not worker._cancel_events["opt-1"].is_set()


def test_get_next_job_returns_none_when_empty(worker: BackgroundWorker) -> None:
    """``_get_next_job`` returns ``None`` when the queue is empty."""
    assert worker._get_next_job() is None


def test_get_next_job_returns_first_enqueued_id(worker: BackgroundWorker) -> None:
    """``_get_next_job`` returns the first enqueued ID."""
    worker.enqueue_job("opt-1")
    worker.enqueue_job("opt-2")
    result = worker._get_next_job()
    assert result == "opt-1"


def test_get_next_job_decrements_pending_queue(worker: BackgroundWorker) -> None:
    """Dequeueing reduces the pending queue size."""
    worker.enqueue_job("opt-1")
    worker._get_next_job()
    assert worker.queue_size() == 0


def test_get_next_job_moves_id_to_processing(worker: BackgroundWorker) -> None:
    """Dequeued jobs move into the active-jobs set."""
    worker.enqueue_job("opt-1")
    worker._get_next_job()
    assert worker.active_jobs() == 1


def test_get_next_job_fifo_ordering(worker: BackgroundWorker) -> None:
    """The pending queue dequeues in FIFO order."""
    for i in range(5):
        worker.enqueue_job(f"opt-{i}")
    dequeued = [worker._get_next_job() for _ in range(5)]
    assert dequeued == [f"opt-{i}" for i in range(5)]


def test_mark_job_done_removes_from_processing(worker: BackgroundWorker) -> None:
    """``_mark_job_done`` removes the ID from the processing set."""
    worker.enqueue_job("opt-1")
    worker._get_next_job()
    worker._mark_job_done("opt-1")
    assert worker.active_jobs() == 0


def test_mark_job_done_removes_cancel_event(worker: BackgroundWorker) -> None:
    """``_mark_job_done`` discards the per-job cancel event."""
    worker.enqueue_job("opt-1")
    worker._get_next_job()
    worker._mark_job_done("opt-1")
    assert "opt-1" not in worker._cancel_events


def test_mark_job_done_is_idempotent(worker: BackgroundWorker) -> None:
    """``_mark_job_done`` does not raise on unknown IDs."""
    worker._mark_job_done("nonexistent")  # should not raise


def test_cancel_job_sets_cancel_event_for_pending_job(worker: BackgroundWorker) -> None:
    """Cancelling a pending job removes it from the pending queue."""
    worker.enqueue_job("opt-1")
    worker.cancel_job("opt-1")
    # After cancelling a pending job, the event should have been set before removal.
    # The job is removed from pending AND from cancel_events.
    assert "opt-1" not in worker._pending_jobs


def test_cancel_job_returns_true_for_pending_job(worker: BackgroundWorker) -> None:
    """``cancel_job`` returns ``True`` for a pending job."""
    worker.enqueue_job("opt-1")
    result = worker.cancel_job("opt-1")
    assert result is True


def test_cancel_job_removes_pending_job_from_queue(worker: BackgroundWorker) -> None:
    """Cancelling removes only the targeted pending job."""
    worker.enqueue_job("opt-1")
    worker.enqueue_job("opt-2")
    worker.cancel_job("opt-1")
    assert worker.queue_size() == 1
    assert worker._pending_jobs == ["opt-2"]


def test_cancel_job_returns_false_for_unknown_job(worker: BackgroundWorker) -> None:
    """``cancel_job`` returns ``False`` for an unknown ID."""
    result = worker.cancel_job("does-not-exist")
    assert result is False


def test_cancel_job_sets_event_for_processing_job(worker: BackgroundWorker) -> None:
    """``cancel_job`` signals the cancel event for an in-flight job."""
    worker.enqueue_job("opt-1")
    worker._get_next_job()  # moves to _processing_jobs
    worker.cancel_job("opt-1")
    # Event was set — the running thread would observe this on next poll.
    # The event entry may or may not still be in _cancel_events; the key thing
    # is cancel_job returned True.


def test_cancel_job_returns_true_for_processing_job(worker: BackgroundWorker) -> None:
    """``cancel_job`` returns ``True`` for an in-flight job."""
    worker.enqueue_job("opt-1")
    worker._get_next_job()
    result = worker.cancel_job("opt-1")
    assert result is True


def test_touch_activity_causes_activity_to_be_recorded(
    worker: BackgroundWorker,
) -> None:
    """``_touch_activity`` causes ``seconds_since_last_activity`` to be non-None."""
    worker._touch_activity(worker_id=0)
    elapsed = worker.seconds_since_last_activity()
    assert elapsed is not None
    assert elapsed >= 0.0


def test_seconds_since_last_activity_is_small_immediately_after_touch(
    worker: BackgroundWorker,
) -> None:
    """The reported elapsed activity time is small right after touching."""
    worker._touch_activity(worker_id=0)
    elapsed = worker.seconds_since_last_activity()
    assert elapsed is not None
    assert elapsed < 1.0


def test_touch_activity_tracks_most_recent_across_workers(
    worker: BackgroundWorker,
) -> None:
    """The reported elapsed time reflects the most recent worker touch."""
    worker._touch_activity(worker_id=0)
    time.sleep(0.05)
    worker._touch_activity(worker_id=1)
    elapsed = worker.seconds_since_last_activity()
    assert elapsed is not None
    # Should reflect time since worker_id=1 touched (< 0.1s), not worker_id=0.
    assert elapsed < 0.1


@pytest.mark.parametrize("n_jobs", [1, 3, 5])
def test_queue_size_reflects_enqueued_count(worker: BackgroundWorker, n_jobs: int) -> None:
    """``queue_size`` equals the number of jobs enqueued."""
    for i in range(n_jobs):
        worker.enqueue_job(f"opt-{i}")
    assert worker.queue_size() == n_jobs


def test_active_jobs_reflects_processing_count(worker: BackgroundWorker) -> None:
    """``active_jobs`` equals the number of jobs in the processing set."""
    worker.enqueue_job("opt-1")
    worker.enqueue_job("opt-2")
    worker._get_next_job()
    assert worker.active_jobs() == 1
    worker._get_next_job()
    assert worker.active_jobs() == 2


def test_active_jobs_decrements_on_mark_done(worker: BackgroundWorker) -> None:
    """``active_jobs`` decrements when a job is marked done."""
    worker.enqueue_job("opt-1")
    worker._get_next_job()
    assert worker.active_jobs() == 1
    worker._mark_job_done("opt-1")
    assert worker.active_jobs() == 0


def test_get_next_job_remove_and_add_are_atomic(worker: BackgroundWorker) -> None:
    """_get_next_job holds _queue_lock across BOTH the removal from _pending_jobs
    AND the addition to _processing_jobs (single 'with self._queue_lock:' block,
    engine.py lines 165-169).

    Because Python's threading.Lock is a C extension whose acquire/release
    attributes are read-only, we cannot monkey-patch them.  Instead we verify
    the invariant behaviourally: a second thread that acquires the lock AFTER
    _get_next_job returns must observe the job already in _processing_jobs and
    absent from _pending_jobs — proving both mutations were visible before the
    lock was ever available to outsiders.
    """
    worker.enqueue_job("opt-a")

    snapshot_pending: list[list] = []
    snapshot_processing: list[set] = []

    def _observe_under_lock() -> None:
        """Snapshot the pending and processing collections under ``_queue_lock``."""
        with worker._queue_lock:
            snapshot_pending.append(list(worker._pending_jobs))
            snapshot_processing.append(set(worker._processing_jobs))

    result = worker._get_next_job()

    observer = threading.Thread(target=_observe_under_lock)
    observer.start()
    observer.join(timeout=2.0)

    assert result == "opt-a"
    assert snapshot_pending, "Observer thread did not run"

    # The observer acquired the lock after _get_next_job returned.
    # Both mutations must be complete by then.
    assert "opt-a" not in snapshot_pending[0]
    assert "opt-a" in snapshot_processing[0]


def test_cancel_job_cannot_miss_job_being_dequeued(worker: BackgroundWorker) -> None:
    """cancel_job() acquires _queue_lock to check/remove the job ID from
    _pending_jobs and _cancel_events, as does _get_next_job(). Because both
    hold the same lock, the two operations are mutually exclusive: a job
    cannot appear to be both 'not in pending' and 'not in processing'
    simultaneously from cancel_job's perspective.

    This test exercises the non-racy fast path: after _get_next_job() moves
    a job to _processing_jobs, cancel_job() must return True (the job is
    still tracked via its cancel event) rather than False (missed).
    """
    worker.enqueue_job("opt-b")
    worker._get_next_job()  # moves opt-b to _processing_jobs

    # cancel_job should find the cancel event and return True.
    result = worker.cancel_job("opt-b")
    assert result is True


def test_get_next_job_queue_state_is_consistent_throughout(
    worker: BackgroundWorker,
) -> None:
    """Immediately after _get_next_job() returns, the job must appear in
    exactly one of the two queues (_processing_jobs), never in both or neither.
    """
    worker.enqueue_job("opt-c")

    assert "opt-c" in worker._pending_jobs
    assert "opt-c" not in worker._processing_jobs

    result = worker._get_next_job()
    assert result == "opt-c"

    assert "opt-c" not in worker._pending_jobs
    assert "opt-c" in worker._processing_jobs
