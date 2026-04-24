"""Background worker for DSPy optimization jobs.

Simple threaded worker that polls the job store for pending jobs
and processes them sequentially or with configurable concurrency.
"""

import contextlib
import json
import logging
import multiprocessing as mp
import queue
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Any

from ..config import settings
from ..constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
    PAYLOAD_OVERVIEW_USERNAME,
)
from ..i18n import CANCELLATION_REASON
from ..models import GridSearchRequest, RunRequest
from ..notifications import notify_job_completed
from ..registry import ServiceRegistry
from ..service_gateway import DspyService
from ..storage import JobStore
from .subprocess_runner import (
    EVENT_ERROR,
    EVENT_LOG,
    EVENT_PROGRESS,
    EVENT_RESULT,
    run_service_in_subprocess,
    set_fork_service,
)

logger = logging.getLogger(__name__)


class CancellationError(Exception):
    """Raised inside a job thread when the job is cancelled by the user."""


class BackgroundWorker:
    """Multi-threaded worker that polls a job store and runs optimization jobs.

    Each worker thread calls ``_worker_loop``, which polls ``_pending_jobs`` and
    dispatches work to ``_process_job``.  Jobs run inside a child process created
    with the configured multiprocessing start method (fork or spawn); events
    (progress, logs, result, error) are streamed back through a ``mp.Queue``
    and persisted by ``_drain_subprocess_events``.  Cancellation is cooperative:
    each job has a ``threading.Event``; ``_check_cancel`` polls it between subprocess
    join timeouts so the child can be terminated promptly on request.
    """

    def __init__(
        self,
        job_store: JobStore,
        num_workers: int = 2,
        poll_interval: float = 2.0,
        service: DspyService | None = None,
    ) -> None:
        """Initialize the worker with a job store and concurrency settings.

        Args:
            job_store: Storage backend used to read and update job state.
            num_workers: Number of worker threads to start.
            poll_interval: Seconds between idle polls for new work.
            service: Optional pre-built DspyService; created lazily if None.
        """
        self._job_store = job_store
        self._num_workers = num_workers
        self._poll_interval = poll_interval
        self._running = False
        self._threads: list[threading.Thread] = []
        self._service: DspyService | None = service

        self._pending_jobs: list[str] = []
        self._processing_jobs: set[str] = set()
        self._cancel_events: dict[str, threading.Event] = {}
        self._queue_lock = threading.Lock()
        poll_raw = str(settings.cancel_poll_interval)
        try:
            self._cancel_poll_interval = max(float(poll_raw), 0.05)
        except ValueError:
            logger.warning("Invalid CANCEL_POLL_INTERVAL=%r; using 1.0", poll_raw)
            self._cancel_poll_interval = 1.0
        self._mp_ctx = self._resolve_mp_context()
        self._mp_start_method = self._mp_ctx.get_start_method()

        # [WORKER-FIX] track last activity time to detect stuck (alive but hanging) threads
        self._last_activity: dict[int, float] = {}
        self._activity_lock = threading.Lock()

    @staticmethod
    def _resolve_mp_context() -> mp.context.BaseContext:
        """Resolve multiprocessing start method from JOB_RUN_START_METHOD, falling back to system default.

        Returns:
            Multiprocessing context configured from settings, or the system default on invalid input.
        """
        requested = settings.job_run_start_method
        try:
            ctx = mp.get_context(requested)
        except ValueError:
            logger.warning(
                "Invalid JOB_RUN_START_METHOD=%r; using default start method.",
                requested,
            )
            ctx = mp.get_context()
        if ctx.get_start_method() != "fork":
            logger.warning(
                "Multiprocessing start method is '%s'. "
                "Custom registry callables may not be available in subprocess jobs.",
                ctx.get_start_method(),
            )
        return ctx

    def _get_service(self) -> DspyService:
        """Get or create the shared DspyService instance.

        Returns:
            The cached DspyService, constructing one from ServiceRegistry if not yet set.
        """
        if self._service is None:
            self._service = DspyService(ServiceRegistry())
        return self._service

    def enqueue_job(self, optimization_id: str) -> None:
        """Add job to the pending queue and wire its cancel event.

        Used for both new job submissions and jobs recovered from DB on startup.

        Args:
            optimization_id: Unique identifier of the job to enqueue.
        """
        with self._queue_lock:
            self._cancel_events[optimization_id] = threading.Event()
            if optimization_id not in self._pending_jobs and optimization_id not in self._processing_jobs:
                self._pending_jobs.append(optimization_id)
                logger.info("Optimization %s enqueued", optimization_id)

    def submit_job(self, optimization_id: str, payload) -> None:
        """Persist payload to the job store and enqueue the job for processing.

        Args:
            optimization_id: Unique identifier of the job.
            payload: Pydantic model whose ``model_dump`` is stored as the job payload.
        """
        self._job_store.update_job(
            optimization_id,
            payload=payload.model_dump(mode="json", by_alias=True),
        )
        self.enqueue_job(optimization_id)

    def _get_next_job(self) -> str | None:
        """Pop the next pending job and move it to the processing set.

        Returns:
            The next job's optimization_id, or None if the queue is empty.
        """
        with self._queue_lock:
            if self._pending_jobs:
                optimization_id = self._pending_jobs.pop(0)
                self._processing_jobs.add(optimization_id)
                return optimization_id
        return None

    def _mark_job_done(self, optimization_id: str) -> None:
        """Remove job from the processing set and clean up its cancel event.

        Args:
            optimization_id: Identifier of the job that has finished processing.
        """
        with self._queue_lock:
            self._processing_jobs.discard(optimization_id)
            self._cancel_events.pop(optimization_id, None)

    def _worker_loop(self, worker_id: int) -> None:
        """Poll for jobs and process them until stopped.

        Args:
            worker_id: Integer index of this worker thread, used for logging and activity tracking.
        """
        logger.info("Worker %d started", worker_id)

        try:  # [WORKER-FIX] top-level guard prevents silent thread death
            idle_cycles = 0
            self._touch_activity(worker_id)
            while self._running:
                optimization_id = self._get_next_job()

                if optimization_id is None:
                    time.sleep(self._poll_interval)
                    idle_cycles += 1
                    if idle_cycles % 150 == 0:  # [WORKER-FIX] heartbeat every ~5min for observability
                        logger.info("Worker %d heartbeat, idle cycles: %d", worker_id, idle_cycles)
                        self._touch_activity(worker_id)
                    continue

                idle_cycles = 0
                self._touch_activity(worker_id)
                try:
                    self._process_job(optimization_id, worker_id)
                except Exception as exc:
                    logger.exception("Worker %d failed processing job %s: %s", worker_id, optimization_id, exc)
                finally:
                    self._mark_job_done(optimization_id)
        except Exception:  # [WORKER-FIX] log fatal thread errors instead of dying silently
            logger.exception("Worker %d died unexpectedly", worker_id)

        logger.info("Worker %d stopped", worker_id)

    def _process_job(self, optimization_id: str, worker_id: int) -> None:
        """Run one optimization job to completion, handling all error and cancel paths.

        Loads the payload from the job store, validates it, spawns a child process
        via ``run_service_in_subprocess``, and drains the event queue until the child
        exits.  The ``BaseException`` handler at the bottom covers cancellation,
        shutdown signals (``SystemExit``/``KeyboardInterrupt``), and ordinary errors —
        each path writes the correct terminal status and fires a notification.  If a
        shutdown signal is caught it is re-raised after cleanup so the process can exit.

        Args:
            optimization_id: ID of the job to process.
            worker_id: Index of the calling worker thread (for logging).
        """
        logger.info("Processing job %s", optimization_id)

        overview: dict = {}  # pre-init so BaseException handler has a defined value even if early error

        with self._queue_lock:
            cancel_event = self._cancel_events.get(optimization_id)

        def _check_cancel() -> None:
            """Raise CancellationError if the job has been cancelled."""
            if cancel_event and cancel_event.is_set():
                raise CancellationError(f"Optimization {optimization_id} cancelled by user")

        try:
            _check_cancel()  # before loading payload

            job_data = self._job_store.get_job(optimization_id)
            payload_dict = job_data.get("payload")

            if not payload_dict:
                raise ValueError(f"Optimization {optimization_id} has no payload")

            overview = job_data.get("payload_overview", {})
            if isinstance(overview, str):
                try:
                    overview = json.loads(overview)
                except (json.JSONDecodeError, TypeError):
                    overview = {}
            optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)

            if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
                payload = GridSearchRequest.model_validate(payload_dict)
            else:
                payload = RunRequest.model_validate(payload_dict)

            self._job_store.update_job(
                optimization_id,
                status="validating",
                message="Validating payload",
            )

            service = self._get_service()
            if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH and hasattr(service, "validate_grid_search_payload"):
                service.validate_grid_search_payload(payload)
            elif optimization_type == OPTIMIZATION_TYPE_RUN:
                service.validate_payload(payload)

            _check_cancel()  # before starting the optimization

            self._job_store.update_job(
                optimization_id,
                status="running",
                message="Running optimization",
                started_at=datetime.now(timezone.utc).isoformat(),
            )

            run_process: mp.process.BaseProcess | None = None
            event_queue: Any | None = None
            result_dict: dict[str, Any] | None = None
            subprocess_error: dict[str, Any] | None = None

            # Preserve registry-backed service in child when using fork.
            if self._mp_start_method == "fork":
                set_fork_service(service)

            try:
                # Inject job type so subprocess can dispatch without duck-typing.
                # Pydantic ignores this unknown key during model_validate.
                payload_dict["_optimization_type"] = optimization_type

                event_queue = self._mp_ctx.Queue()
                run_process = self._mp_ctx.Process(
                    target=run_service_in_subprocess,
                    args=(payload_dict, optimization_id, event_queue, self._mp_start_method),
                    name=f"dspy-run-{optimization_id[:8]}",
                    daemon=True,
                )
                run_process.start()

                while run_process.is_alive():
                    _check_cancel()
                    self._touch_activity(worker_id)
                    run_process.join(timeout=self._cancel_poll_interval)
                    drained_result, drained_error = self._drain_subprocess_events(optimization_id, event_queue)
                    if drained_result is not None:
                        result_dict = drained_result
                    if drained_error is not None:
                        subprocess_error = drained_error

                drained_result, drained_error = self._drain_subprocess_events(optimization_id, event_queue)
                if drained_result is not None:
                    result_dict = drained_result
                if drained_error is not None:
                    subprocess_error = drained_error

                if subprocess_error:
                    traceback_text = subprocess_error.get("traceback")
                    if traceback_text:
                        logger.error("Optimization %s subprocess traceback:\n%s", optimization_id, traceback_text)
                        # Persist traceback so users can see it via GET /jobs/{id}/logs
                        with contextlib.suppress(Exception):
                            self._job_store.append_log(
                                optimization_id,
                                level="ERROR",
                                logger_name="dspy.subprocess",
                                message=traceback_text,
                            )
                    raise RuntimeError(str(subprocess_error.get("error", "Unknown subprocess error")))

                if run_process.exitcode not in (0, None) and result_dict is None:
                    raise RuntimeError(f"Optimization subprocess exited with code {run_process.exitcode}")

                if result_dict is None:
                    raise RuntimeError("Optimization subprocess finished without a result payload")

                # Check cancel one last time: service.run() may have completed
                # during a long phase with no progress callbacks, after the
                # cancel endpoint already marked the job as cancelled.
                _check_cancel()

                # Grid search with all pairs failed is a failure, not a success.
                final_status = "success"
                final_message = "Optimization completed successfully"
                if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH and isinstance(result_dict, dict):
                    completed = result_dict.get("completed_pairs", 0)
                    total = result_dict.get("total_pairs", 0)
                    if completed == 0 and total > 0:
                        final_status = "failed"
                        final_message = f"All {total} model pairs failed"
                        pair_results = result_dict.get("pair_results") or []
                        first_error = next(
                            (p["error"] for p in pair_results if isinstance(p, dict) and p.get("error")),
                            None,
                        )
                        if first_error:
                            final_message = f"{final_message}: {first_error}"

                try:
                    current = self._job_store.get_job(optimization_id)
                    if current.get("status") == "cancelled":
                        # Cancel endpoint raced us past the last _check_cancel() and
                        # already wrote "cancelled" to the DB. Treat it as a cancellation.
                        raise CancellationError()
                    self._job_store.update_job(
                        optimization_id,
                        status=final_status,
                        message=final_message,
                        completed_at=datetime.now(timezone.utc).isoformat(),
                        result=result_dict,
                    )
                    logger.info("Optimization %s completed with status=%s", optimization_id, final_status)
                    _username = overview.get(PAYLOAD_OVERVIEW_USERNAME, "")
                    _baseline = result_dict.get("baseline_test_metric") if isinstance(result_dict, dict) else None
                    _optimized = result_dict.get("optimized_test_metric") if isinstance(result_dict, dict) else None
                    notify_job_completed(
                        optimization_id=optimization_id,
                        username=_username,
                        status=final_status,
                        message=final_message,
                        baseline_score=_baseline,
                        optimized_score=_optimized,
                    )
                    if final_status == "success":
                        self._schedule_recommendation_indexing(optimization_id)
                except KeyError:
                    logger.info(
                        "Optimization %s was deleted during execution (likely cancelled), skipping result",
                        optimization_id,
                    )
            except BaseException:
                if run_process is not None and run_process.is_alive():
                    self._terminate_run_process(run_process, optimization_id)
                raise
            finally:
                if event_queue is not None:
                    with contextlib.suppress(Exception):
                        event_queue.close()
                    with contextlib.suppress(Exception):
                        event_queue.join_thread()

        except BaseException as exc:  # [WORKER-FIX] catch BaseException to handle shutdown signals
            is_shutdown = isinstance(exc, (SystemExit, KeyboardInterrupt))
            is_cancelled = isinstance(exc, CancellationError)
            if is_cancelled:
                final_status, error_message = "cancelled", CANCELLATION_REASON
                logger.info("Optimization %s cancelled", optimization_id)
            elif is_shutdown:
                final_status = "failed"
                error_message = f"Optimization interrupted by service shutdown: {exc}"
                logger.exception("Optimization %s failed: %s", optimization_id, error_message)
            else:
                final_status = "failed"
                error_message = str(exc)
                logger.exception("Optimization %s failed: %s", optimization_id, error_message)
            _username = overview.get(PAYLOAD_OVERVIEW_USERNAME, "") if isinstance(overview, dict) else ""
            if is_cancelled:
                # Cancel endpoint already set status to "cancelled"; no further DB action needed.
                notify_job_completed(optimization_id=optimization_id, username=_username, status="cancelled")
            else:
                # Failed jobs are retained so users can inspect the error
                now = datetime.now(timezone.utc).isoformat()
                try:
                    self._job_store.update_job(
                        optimization_id, status=final_status, message=error_message, completed_at=now
                    )
                except Exception:
                    logger.exception("Optimization %s: failed to update status to %s", optimization_id, final_status)
                notify_job_completed(
                    optimization_id=optimization_id,
                    username=_username,
                    status=final_status,
                    message=error_message,
                )
            if is_shutdown:
                raise

    def start(self) -> None:
        """Start the background worker threads and begin polling."""
        if self._running:
            return

        self._running = True
        for i in range(self._num_workers):
            thread = threading.Thread(  # [WORKER-FIX] removed daemon=True so threads survive shutdown
                target=self._worker_loop,
                args=(i,),
                name=f"dspy-worker-{i}",
            )
            thread.start()
            self._threads.append(thread)

        logger.info("Started %d background workers", self._num_workers)

    def stop(self, timeout: float = 30.0) -> None:
        """Signal all workers to stop and wait for them to finish."""
        if not self._running:
            return

        self._running = False

        # Request cooperative cancellation for pending/running jobs so workers
        # can terminate subprocess execution promptly during shutdown.
        with self._queue_lock:
            self._pending_jobs.clear()
            for event in self._cancel_events.values():
                event.set()

        if not self._threads:
            return
        per_thread_timeout = timeout / len(self._threads)
        for thread in self._threads:
            thread.join(timeout=per_thread_timeout)

        self._threads.clear()
        logger.info("Stopped background workers")

    def is_running(self) -> bool:
        """Return True if the worker has been started."""
        return self._running

    def _touch_activity(self, worker_id: int) -> None:  # [WORKER-FIX] update activity timestamp
        """Record the current time as the latest activity for this worker.

        Args:
            worker_id: Index of the worker thread recording activity.
        """
        with self._activity_lock:
            self._last_activity[worker_id] = time.monotonic()

    def _schedule_recommendation_indexing(self, optimization_id: str) -> None:
        """Fire-and-forget embed the finished job for the recommendation service.

        Runs on a daemon thread so a slow LLM call or a missing pgvector
        extension can never block the worker's hot path. Failures are
        swallowed — the job itself is already marked success; the index
        is best-effort.
        """

        def _run() -> None:
            try:
                from ..service_gateway.recommendations import embed_finished_job

                embed_finished_job(optimization_id, job_store=self._job_store)
            except Exception as exc:
                logger.debug("Recommendation indexing for %s failed: %s", optimization_id, exc)

        threading.Thread(target=_run, name=f"recs-{optimization_id[:8]}", daemon=True).start()

    def _terminate_run_process(self, run_process: mp.process.BaseProcess, optimization_id: str) -> None:
        """Terminate a still-running job subprocess, escalating to SIGKILL after a 3-second grace period.

        Sends SIGTERM, waits up to 3 s, then calls ``kill()`` if the process is
        still alive and the platform supports it.  A final 2-second join follows
        before logging the outcome.  Never raises regardless of process state.

        Args:
            run_process: The child process to terminate.
            optimization_id: Used only for log context.
        """
        run_process.terminate()
        run_process.join(timeout=3.0)
        if run_process.is_alive() and hasattr(run_process, "kill"):
            run_process.kill()
            run_process.join(timeout=2.0)
        if run_process.is_alive():
            logger.error("Optimization %s subprocess did not terminate cleanly", optimization_id)
        else:
            logger.info("Optimization %s subprocess terminated", optimization_id)

    def _drain_subprocess_events(
        self,
        optimization_id: str,
        event_queue: Any,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Drain all pending events from the subprocess queue, routing each by type.

        Handles four event types emitted by ``run_service_in_subprocess``:
        ``EVENT_PROGRESS`` → ``job_store.record_progress``; ``EVENT_LOG`` →
        ``job_store.append_log``; ``EVENT_RESULT`` → captured as the return value;
        ``EVENT_ERROR`` → captured as the error return value.  Store errors are
        swallowed so a DB hiccup cannot abort an otherwise-healthy optimization.

        Args:
            optimization_id: Job whose events are being drained.
            event_queue: Multiprocessing queue filled by the child process.

        Returns:
            A ``(result_dict, error_dict)`` tuple.  Either or both may be ``None``
            if the corresponding event was not found in the queue.
        """
        result_payload: dict[str, Any] | None = None
        error_payload: dict[str, Any] | None = None
        while True:
            try:
                event = event_queue.get_nowait()
            except queue.Empty:
                break
            except Exception:
                logger.exception(
                    "Optimization %s: event queue read failed; stopping drain", optimization_id
                )
                break

            event_type = event.get("type")
            if event_type == EVENT_PROGRESS:
                try:
                    self._job_store.record_progress(
                        optimization_id,
                        event.get("event"),
                        event.get("metrics") or {},
                    )
                except Exception:
                    logger.exception("Optimization %s: failed to persist subprocess progress event", optimization_id)
            elif event_type == EVENT_LOG:
                timestamp = None
                timestamp_raw = event.get("timestamp")
                if isinstance(timestamp_raw, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
                    except ValueError:
                        timestamp = None
                pair_index_raw = event.get("pair_index")
                pair_index = (
                    int(pair_index_raw) if isinstance(pair_index_raw, int) else None
                )
                try:
                    self._job_store.append_log(
                        optimization_id,
                        level=str(event.get("level", "INFO")),
                        logger_name=str(event.get("logger", "dspy")),
                        message=str(event.get("message", "")),
                        timestamp=timestamp,
                        pair_index=pair_index,
                    )
                except Exception:
                    logger.exception("Optimization %s: failed to persist subprocess log entry", optimization_id)
            elif event_type == EVENT_RESULT:
                payload = event.get("result")
                if isinstance(payload, dict):
                    result_payload = payload
            elif event_type == EVENT_ERROR:
                payload = {
                    "error": str(event.get("error", "Unknown subprocess error")),
                    "traceback": str(event.get("traceback", "")),
                }
                error_payload = payload

        return result_payload, error_payload

    def seconds_since_last_activity(self) -> float | None:  # [WORKER-FIX] detect stuck threads
        """Return seconds since the most recent worker activity, or None if no activity recorded yet."""
        with self._activity_lock:
            if not self._last_activity:
                return None
            latest = max(self._last_activity.values())
        return time.monotonic() - latest

    def dump_thread_stacks(self) -> str:  # [WORKER-FIX] capture where threads are stuck for debugging
        """Return formatted stack traces of all worker threads."""
        frames = sys._current_frames()
        lines = []
        for thread in self._threads:
            frame = frames.get(thread.ident)
            if frame:
                lines.append(f"--- {thread.name} (alive={thread.is_alive()}) ---")
                lines.extend(traceback.format_stack(frame))
            else:
                lines.append(f"--- {thread.name} (no frame, alive={thread.is_alive()}) ---")
        return "\n".join(lines)

    def threads_alive(self) -> bool:  # [WORKER-FIX] new method for health check liveness
        """Return True if all worker threads are still alive."""
        if not self._threads:
            return False
        return all(t.is_alive() for t in self._threads)

    def cancel_job(self, optimization_id: str) -> bool:
        """Signal a job to stop.

        Args:
            optimization_id: Identifier of the job to cancel.

        Returns:
            True if the job was found (pending or currently running), False otherwise.
        """
        with self._queue_lock:
            event = self._cancel_events.get(optimization_id)
            if event:
                event.set()
            if optimization_id in self._pending_jobs:
                self._pending_jobs.remove(optimization_id)
                # Pending jobs never reach _mark_job_done; clean up event here.
                self._cancel_events.pop(optimization_id, None)
                return True
        return event is not None  # True if was running

    def queue_size(self) -> int:
        """Return the number of jobs waiting to be processed.

        Returns:
            Count of jobs in the pending queue.
        """
        with self._queue_lock:
            return len(self._pending_jobs)

    def active_jobs(self) -> int:
        """Return the number of jobs currently being processed.

        Returns:
            Count of jobs in the processing set.
        """
        with self._queue_lock:
            return len(self._processing_jobs)

    def thread_count(self) -> int:
        """Return the number of worker threads."""
        return len(self._threads)


_worker: BackgroundWorker | None = None
_worker_lock = threading.Lock()


def get_worker(
    job_store: JobStore,
    service: DspyService | None = None,
    pending_optimization_ids: list | None = None,
) -> BackgroundWorker:
    """Return the module-level singleton BackgroundWorker, creating it if needed."""
    global _worker

    with _worker_lock:
        if _worker is None or not _worker.threads_alive():
            num_workers = settings.worker_threads
            poll_interval = settings.worker_poll_interval
            _worker = BackgroundWorker(
                job_store=job_store,
                num_workers=num_workers,
                poll_interval=poll_interval,
                service=service,
            )
            _worker.start()
            for optimization_id in pending_optimization_ids or []:
                _worker.enqueue_job(optimization_id)

    return _worker


def reset_worker_for_tests(timeout: float = 5.0) -> None:
    """Stop and clear the module-level worker singleton (test-only helper)."""
    global _worker
    with _worker_lock:
        if _worker is not None:
            try:
                _worker.stop(timeout=timeout)
            except Exception:
                logger.exception("Failed to stop global worker during test reset")
        _worker = None
