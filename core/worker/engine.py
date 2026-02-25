"""Background worker for DSPy optimization jobs.

Simple threaded worker that polls the job store for pending jobs
and processes them sequentially or with configurable concurrency.
"""

import logging
import multiprocessing as mp
import os
import queue
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..storage import JobStore
from ..models import GridSearchRequest, RunRequest
from ..registry import ServiceRegistry
from ..service_gateway import DspyService

logger = logging.getLogger(__name__)

_EVENT_PROGRESS = "progress"
_EVENT_LOG = "log"
_EVENT_RESULT = "result"
_EVENT_ERROR = "error"

# Populated before forking so child processes can reuse the same registry-backed service.
_FORK_SERVICE: Optional[DspyService] = None


def _safe_queue_put(event_queue: Any, event: Dict[str, Any]) -> None:
    try:
        event_queue.put(event)
    except Exception:
        # Parent may have already torn down the queue during cancellation/shutdown.
        pass


class _SubprocessLogHandler(logging.Handler):
    """Forward DSPy logs from the subprocess to the parent worker."""

    def __init__(self, event_queue: Any) -> None:
        super().__init__()
        self._event_queue = event_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        _safe_queue_put(
            self._event_queue,
            {
                "type": _EVENT_LOG,
                "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": message,
            },
        )


def _run_service_in_subprocess(
    payload_dict: Dict[str, Any],
    artifact_id: str,
    event_queue: Any,
    start_method: str,
) -> None:
    """Execute a DSPy run in a child process and stream events to parent."""
    service = _FORK_SERVICE if start_method == "fork" and _FORK_SERVICE is not None else DspyService(ServiceRegistry())
    dspy_logger = logging.getLogger("dspy")
    saved_level = dspy_logger.level
    log_handler = _SubprocessLogHandler(event_queue)
    log_handler.setLevel(logging.INFO)
    log_handler.setFormatter(logging.Formatter("%(message)s"))

    if dspy_logger.level == 0 or dspy_logger.level > logging.INFO:
        dspy_logger.setLevel(logging.INFO)
    dspy_logger.addHandler(log_handler)

    try:
        is_grid_search = "generation_models" in payload_dict

        def progress_callback(message: str, metrics: Dict[str, Any]) -> None:
            _safe_queue_put(
                event_queue,
                {
                    "type": _EVENT_PROGRESS,
                    "event": message,
                    "metrics": metrics or {},
                },
            )

        if is_grid_search:
            # Grid search requires DspyService; fall back if injected service lacks it.
            if not hasattr(service, "run_grid_search"):
                service = DspyService(ServiceRegistry())
            payload = GridSearchRequest.model_validate(payload_dict)
            result = service.run_grid_search(
                payload,
                artifact_id=artifact_id,
                progress_callback=progress_callback,
            )
        else:
            payload = RunRequest.model_validate(payload_dict)
            result = service.run(
                payload,
                artifact_id=artifact_id,
                progress_callback=progress_callback,
            )
        _safe_queue_put(
            event_queue,
            {
                "type": _EVENT_RESULT,
                "result": result.model_dump(mode="json"),
            },
        )
    except BaseException as exc:
        _safe_queue_put(
            event_queue,
            {
                "type": _EVENT_ERROR,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
    finally:
        dspy_logger.removeHandler(log_handler)
        dspy_logger.setLevel(saved_level)


class CancellationError(Exception):
    """Raised inside a job thread when the job is cancelled by the user."""


class BackgroundWorker:
    """Background worker that processes optimization jobs.

    Uses threading to run jobs in the background while the API
    continues to accept requests.

    Args:
        job_store: Job store instance for tracking job state.
        num_workers: Number of concurrent worker threads.
        poll_interval: Seconds between polling for new jobs.
    """

    def __init__(
        self,
        job_store: JobStore,
        num_workers: int = 2,
        poll_interval: float = 2.0,
        service: Optional[DspyService] = None,
    ) -> None:
        self._job_store = job_store
        self._num_workers = num_workers
        self._poll_interval = poll_interval
        self._running = False
        self._threads: list[threading.Thread] = []
        self._service: Optional[DspyService] = service

        self._pending_jobs: list[str] = []
        self._processing_jobs: set[str] = set()
        self._cancel_events: Dict[str, threading.Event] = {}
        self._queue_lock = threading.Lock()
        poll_raw = os.getenv("CANCEL_POLL_INTERVAL", "1.0")
        try:
            self._cancel_poll_interval = max(float(poll_raw), 0.05)
        except ValueError:
            logger.warning("Invalid CANCEL_POLL_INTERVAL=%r; using 1.0", poll_raw)
            self._cancel_poll_interval = 1.0
        self._mp_ctx = self._resolve_mp_context()
        self._mp_start_method = self._mp_ctx.get_start_method()

        # [WORKER-FIX] track last activity time to detect stuck (alive but hanging) threads
        self._last_activity: Dict[int, float] = {}
        self._activity_lock = threading.Lock()

    @staticmethod
    def _resolve_mp_context() -> mp.context.BaseContext:
        """Resolve multiprocessing start method for per-job subprocess execution."""
        requested = os.getenv("JOB_RUN_START_METHOD", "fork").strip().lower()
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
        """Get or create the DspyService instance.

        Returns:
            DspyService: Shared service instance for this worker.
        """
        if self._service is None:
            self._service = DspyService(ServiceRegistry())
        return self._service

    def enqueue_job(self, job_id: str) -> None:
        """Add job to the pending queue and wire its cancel event.

        Used for both new job submissions and jobs recovered from DB on startup.

        Args:
            job_id: Unique job identifier.
        """
        with self._queue_lock:
            self._cancel_events[job_id] = threading.Event()
            if job_id not in self._pending_jobs and job_id not in self._processing_jobs:
                self._pending_jobs.append(job_id)
                logger.info("Job %s enqueued", job_id)

    def submit_job(self, job_id: str, payload) -> None:
        """Submit a job for background processing.

        Args:
            job_id: Unique job identifier.
            payload: The optimization request payload.
        """
        self._job_store.update_job(
            job_id,
            payload=payload.model_dump(mode="json"),
        )
        self.enqueue_job(job_id)

    def _get_next_job(self) -> Optional[str]:
        """Get the next pending job from the queue.

        Returns:
            Optional[str]: Job ID if available, None otherwise.
        """
        with self._queue_lock:
            if self._pending_jobs:
                job_id = self._pending_jobs.pop(0)
                self._processing_jobs.add(job_id)
                return job_id
        return None

    def _mark_job_done(self, job_id: str) -> None:
        """Mark a job as no longer processing.

        Args:
            job_id: The job identifier to mark as done.
        """
        with self._queue_lock:
            self._processing_jobs.discard(job_id)
            self._cancel_events.pop(job_id, None)

    def _worker_loop(self, worker_id: int) -> None:
        """Main worker loop that processes jobs.

        Args:
            worker_id: Identifier for this worker thread.
        """
        logger.info("Worker %d started", worker_id)

        try:  # [WORKER-FIX] top-level guard prevents silent thread death
            idle_cycles = 0
            self._touch_activity(worker_id)
            while self._running:
                job_id = self._get_next_job()

                if job_id is None:
                    time.sleep(self._poll_interval)
                    idle_cycles += 1
                    if idle_cycles % 150 == 0:  # [WORKER-FIX] heartbeat every ~5min for observability
                        logger.info("Worker %d heartbeat, idle cycles: %d", worker_id, idle_cycles)
                        self._touch_activity(worker_id)
                    continue

                idle_cycles = 0
                self._touch_activity(worker_id)
                try:
                    self._process_job(job_id, worker_id)
                except Exception as exc:
                    logger.exception("Worker %d failed processing job %s: %s", worker_id, job_id, exc)
                finally:
                    self._mark_job_done(job_id)
        except Exception:  # [WORKER-FIX] log fatal thread errors instead of dying silently
            logger.exception("Worker %d died unexpectedly", worker_id)

        logger.info("Worker %d stopped", worker_id)

    def _process_job(self, job_id: str, worker_id: int) -> None:
        """Process a single optimization job.

        Args:
            job_id: The job identifier to process.
            worker_id: Owning worker thread id for activity tracking.

        Raises:
            ValueError: If job has no payload.
        """
        logger.info("Processing job %s", job_id)

        with self._queue_lock:
            cancel_event = self._cancel_events.get(job_id)

        def _check_cancel() -> None:
            if cancel_event and cancel_event.is_set():
                raise CancellationError(f"Job {job_id} cancelled by user")

        try:
            _check_cancel()  # before loading payload

            job_data = self._job_store.get_job(job_id)
            payload_dict = job_data.get("payload")

            if not payload_dict:
                raise ValueError(f"Job {job_id} has no payload")

            is_grid_search = "generation_models" in payload_dict
            if is_grid_search:
                payload = GridSearchRequest.model_validate(payload_dict)
            else:
                payload = RunRequest.model_validate(payload_dict)

            self._job_store.update_job(
                job_id,
                status="validating",
                message="Validating payload",
            )

            service = self._get_service()
            if is_grid_search and hasattr(service, "validate_grid_search_payload"):
                service.validate_grid_search_payload(payload)
            elif not is_grid_search:
                service.validate_payload(payload)

            _check_cancel()  # before starting the optimization

            self._job_store.update_job(
                job_id,
                status="running",
                message="Running optimization",
                started_at=datetime.now(timezone.utc).isoformat(),
            )

            run_process: Optional[mp.process.BaseProcess] = None
            event_queue: Optional[Any] = None
            result_dict: Optional[Dict[str, Any]] = None
            subprocess_error: Optional[Dict[str, Any]] = None

            # Preserve registry-backed service in child when using fork.
            if self._mp_start_method == "fork":
                global _FORK_SERVICE
                _FORK_SERVICE = service

            try:
                event_queue = self._mp_ctx.Queue()
                run_process = self._mp_ctx.Process(
                    target=_run_service_in_subprocess,
                    args=(payload_dict, job_id, event_queue, self._mp_start_method),
                    name=f"dspy-run-{job_id[:8]}",
                    daemon=True,
                )
                run_process.start()

                while run_process.is_alive():
                    _check_cancel()
                    self._touch_activity(worker_id)
                    run_process.join(timeout=self._cancel_poll_interval)
                    drained_result, drained_error = self._drain_subprocess_events(job_id, event_queue)
                    if drained_result is not None:
                        result_dict = drained_result
                    if drained_error is not None:
                        subprocess_error = drained_error

                drained_result, drained_error = self._drain_subprocess_events(job_id, event_queue)
                if drained_result is not None:
                    result_dict = drained_result
                if drained_error is not None:
                    subprocess_error = drained_error

                if subprocess_error:
                    traceback_text = subprocess_error.get("traceback")
                    if traceback_text:
                        logger.error("Job %s subprocess traceback:\n%s", job_id, traceback_text)
                    raise RuntimeError(str(subprocess_error.get("error", "Unknown subprocess error")))

                if run_process.exitcode not in (0, None) and result_dict is None:
                    raise RuntimeError(f"Job subprocess exited with code {run_process.exitcode}")

                if result_dict is None:
                    raise RuntimeError("Job subprocess finished without a result payload")

                # Check cancel one last time: service.run() may have completed
                # during a long phase with no progress callbacks, after the
                # cancel endpoint already marked the job as cancelled.
                _check_cancel()

                try:
                    self._job_store.update_job(
                        job_id,
                        status="success",
                        message="Optimization completed successfully",
                        completed_at=datetime.now(timezone.utc).isoformat(),
                        result=result_dict,
                    )
                    logger.info("Job %s completed successfully", job_id)
                except KeyError:
                    logger.info("Job %s was deleted during execution (likely cancelled), skipping result", job_id)
            except BaseException:
                if run_process is not None and run_process.is_alive():
                    self._terminate_run_process(run_process, job_id)
                raise
            finally:
                if event_queue is not None:
                    try:
                        event_queue.close()
                    except Exception:
                        pass
                    try:
                        event_queue.join_thread()
                    except Exception:
                        pass

        except BaseException as exc:  # [WORKER-FIX] catch BaseException to handle shutdown signals
            is_shutdown = isinstance(exc, (SystemExit, KeyboardInterrupt))
            is_cancelled = isinstance(exc, CancellationError)
            if is_cancelled:
                final_status, error_message = "cancelled", "Cancelled by user"
                logger.info("Job %s cancelled", job_id)
            elif is_shutdown:
                final_status = "failed"
                error_message = f"Job interrupted by service shutdown: {exc}"
                logger.exception("Job %s failed: %s", job_id, error_message)
            else:
                final_status = "failed"
                error_message = str(exc)
                logger.exception("Job %s failed: %s", job_id, error_message)
            if is_cancelled:
                # Cancelled jobs are cleaned up entirely
                try:
                    self._job_store.delete_job(job_id)
                except KeyError:
                    pass  # already deleted (e.g., cancel endpoint beat the worker thread)
                except Exception:
                    logger.exception("Job %s: failed to delete from DB after cancel", job_id)
            else:
                # Failed jobs are retained so users can inspect the error
                now = datetime.now(timezone.utc).isoformat()
                try:
                    self._job_store.update_job(
                        job_id, status=final_status, message=error_message, completed_at=now
                    )
                except Exception:
                    logger.exception("Job %s: failed to update status to %s", job_id, final_status)
            if is_shutdown:
                raise

    def start(self) -> None:
        """Start the background worker threads."""
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
        """Stop the background worker threads.

        Args:
            timeout: Maximum seconds to wait for threads to finish.
        """
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
        """Check if the worker is running.

        Returns:
            bool: True if worker threads are active.
        """
        return self._running

    def _touch_activity(self, worker_id: int) -> None:  # [WORKER-FIX] update activity timestamp
        """Record that a worker thread is actively making progress."""
        with self._activity_lock:
            self._last_activity[worker_id] = time.monotonic()

    def _terminate_run_process(self, run_process: mp.process.BaseProcess, job_id: str) -> None:
        """Force-stop a still-running job subprocess."""
        run_process.terminate()
        run_process.join(timeout=3.0)
        if run_process.is_alive() and hasattr(run_process, "kill"):
            run_process.kill()
            run_process.join(timeout=2.0)
        if run_process.is_alive():
            logger.error("Job %s subprocess did not terminate cleanly", job_id)
        else:
            logger.info("Job %s subprocess terminated", job_id)

    def _drain_subprocess_events(
        self,
        job_id: str,
        event_queue: Any,
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Persist queued child-process events and return latest result/error payloads."""
        result_payload: Optional[Dict[str, Any]] = None
        error_payload: Optional[Dict[str, Any]] = None
        while True:
            try:
                event = event_queue.get_nowait()
            except queue.Empty:
                break
            except Exception:
                break

            event_type = event.get("type")
            if event_type == _EVENT_PROGRESS:
                try:
                    self._job_store.record_progress(
                        job_id,
                        event.get("event"),
                        event.get("metrics") or {},
                    )
                except Exception:
                    logger.exception("Job %s: failed to persist subprocess progress event", job_id)
            elif event_type == _EVENT_LOG:
                timestamp = None
                timestamp_raw = event.get("timestamp")
                if isinstance(timestamp_raw, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
                    except ValueError:
                        timestamp = None
                try:
                    self._job_store.append_log(
                        job_id,
                        level=str(event.get("level", "INFO")),
                        logger_name=str(event.get("logger", "dspy")),
                        message=str(event.get("message", "")),
                        timestamp=timestamp,
                    )
                except Exception:
                    logger.exception("Job %s: failed to persist subprocess log entry", job_id)
            elif event_type == _EVENT_RESULT:
                payload = event.get("result")
                if isinstance(payload, dict):
                    result_payload = payload
            elif event_type == _EVENT_ERROR:
                payload = {
                    "error": str(event.get("error", "Unknown subprocess error")),
                    "traceback": str(event.get("traceback", "")),
                }
                error_payload = payload

        return result_payload, error_payload

    def seconds_since_last_activity(self) -> Optional[float]:  # [WORKER-FIX] detect stuck threads
        """Return seconds since any worker was last active, or None if no activity yet."""
        with self._activity_lock:
            if not self._last_activity:
                return None
            latest = max(self._last_activity.values())
        return time.monotonic() - latest

    def dump_thread_stacks(self) -> str:  # [WORKER-FIX] capture where threads are stuck for debugging
        """Return stack traces of all worker threads for debugging."""
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
        """Check if all worker threads are still alive.

        Returns:
            bool: True if all worker threads are alive.
        """
        if not self._threads:
            return False
        return all(t.is_alive() for t in self._threads)

    def cancel_job(self, job_id: str) -> bool:
        """Signal a job to stop, removing it from the queue or interrupting it if running.

        Args:
            job_id: Job identifier to cancel.

        Returns:
            bool: True if the job was found (pending or running).
        """
        with self._queue_lock:
            event = self._cancel_events.get(job_id)
            if event:
                event.set()
            if job_id in self._pending_jobs:
                self._pending_jobs.remove(job_id)
                # Pending jobs never reach _mark_job_done; clean up event here.
                self._cancel_events.pop(job_id, None)
                return True
        return event is not None  # True if was running

    def queue_size(self) -> int:
        """Get the number of pending jobs.

        Returns:
            int: Count of jobs waiting to be processed.
        """
        with self._queue_lock:
            return len(self._pending_jobs)

    def active_jobs(self) -> int:
        """Get the number of jobs currently being processed.

        Returns:
            int: Count of jobs actively running.
        """
        with self._queue_lock:
            return len(self._processing_jobs)

    def thread_count(self) -> int:
        """Get the number of worker threads.

        Returns:
            int: Number of worker threads.
        """
        return len(self._threads)


# Global worker instance
_worker: Optional[BackgroundWorker] = None
_worker_lock = threading.Lock()


def get_worker(
    job_store: JobStore,
    service: Optional[DspyService] = None,
    pending_job_ids: Optional[list] = None,
) -> BackgroundWorker:
    """Get or create the global background worker.

    Args:
        job_store: Job store for the worker to use.
        service: Optional DspyService instance to share with the worker.

    Returns:
        BackgroundWorker: The global worker instance.
    """
    global _worker

    with _worker_lock:
        if _worker is None or not _worker.threads_alive():
            num_workers = int(os.getenv("WORKER_CONCURRENCY", "2"))
            poll_interval = float(os.getenv("WORKER_POLL_INTERVAL", "2.0"))
            _worker = BackgroundWorker(
                job_store=job_store,
                num_workers=num_workers,
                poll_interval=poll_interval,
                service=service,
            )
            _worker.start()
            for job_id in (pending_job_ids or []):
                _worker.enqueue_job(job_id)

    return _worker


def reset_worker_for_tests(timeout: float = 5.0) -> None:
    """Reset module-global worker state.

    Test-only helper to avoid leaked global worker state between tests.
    """
    global _worker
    with _worker_lock:
        if _worker is not None:
            try:
                _worker.stop(timeout=timeout)
            except Exception:
                logger.exception("Failed to stop global worker during test reset")
        _worker = None
