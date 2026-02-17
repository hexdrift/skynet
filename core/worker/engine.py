"""Background worker for DSPy optimization jobs.

Simple threaded worker that polls the job store for pending jobs
and processes them sequentially or with configurable concurrency.
"""

import logging
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..storage import RemoteDBJobStore
from .log_handler import JobLogHandler
from ..models import RunRequest
from ..registry import ServiceRegistry
from ..service_gateway import DspyService

logger = logging.getLogger(__name__)


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
        job_store: RemoteDBJobStore,
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
        self._lock = threading.Lock()

        self._pending_jobs: list[str] = []
        self._processing_jobs: set[str] = set()
        self._queue_lock = threading.Lock()

        # [WORKER-FIX] track last activity time to detect stuck (alive but hanging) threads
        self._last_activity: Dict[int, float] = {}
        self._activity_lock = threading.Lock()

        # Reference count for jobs that need the dspy logger at INFO level.
        # The level is raised on the first job and restored on the last.
        self._dspy_info_refs: int = 0
        self._dspy_saved_level: int = 0

    def _get_service(self) -> DspyService:
        """Get or create the DspyService instance.

        Returns:
            DspyService: Shared service instance for this worker.
        """
        if self._service is None:
            self._service = DspyService(ServiceRegistry())
        return self._service

    def submit_job(self, job_id: str, payload: RunRequest) -> None:
        """Submit a job for background processing.

        Args:
            job_id: Unique job identifier.
            payload: The optimization request payload.
        """
        self._job_store.update_job(
            job_id,
            payload=payload.model_dump(mode="json"),
        )

        with self._queue_lock:
            if job_id not in self._pending_jobs and job_id not in self._processing_jobs:
                self._pending_jobs.append(job_id)
                logger.info("Job %s added to queue", job_id)

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
                    self._process_job(job_id)
                except Exception as exc:
                    logger.exception("Worker %d failed processing job %s: %s", worker_id, job_id, exc)
                finally:
                    self._mark_job_done(job_id)
        except Exception:  # [WORKER-FIX] log fatal thread errors instead of dying silently
            logger.exception("Worker %d died unexpectedly", worker_id)

        logger.info("Worker %d stopped", worker_id)

    def _process_job(self, job_id: str) -> None:
        """Process a single optimization job.

        Args:
            job_id: The job identifier to process.

        Raises:
            ValueError: If job has no payload.
        """
        logger.info("Processing job %s", job_id)

        try:
            job_data = self._job_store.get_job(job_id)
            payload_dict = job_data.get("payload")

            if not payload_dict:
                raise ValueError(f"Job {job_id} has no payload")

            payload = RunRequest.model_validate(payload_dict)

            self._job_store.update_job(
                job_id,
                status="validating",
                message="Validating payload",
            )

            service = self._get_service()
            service.validate_payload(payload)

            self._job_store.update_job(
                job_id,
                status="running",
                message="Running optimization",
                started_at=datetime.now(timezone.utc).isoformat(),
            )

            def progress_callback(message: str, metrics: Dict[str, Any]) -> None:
                # [WORKER-FIX] touch activity on every progress event to prove the thread is making progress
                current_thread = threading.current_thread()
                for i, t in enumerate(self._threads):
                    if t is current_thread:
                        self._touch_activity(i)
                        break
                logger.debug("Job %s progress: %s %s", job_id, message, metrics)
                try:  # [WORKER-FIX] protect worker thread from DB errors in progress callback
                    self._job_store.record_progress(job_id, message, metrics)
                except Exception:
                    logger.exception("Job %s: failed to record progress", job_id)

            log_handler = JobLogHandler(job_id, self._job_store)
            log_handler.setLevel(logging.INFO)
            log_handler.setFormatter(logging.Formatter("%(message)s"))
            tracked_loggers = [logging.getLogger("dspy")]

            with self._lock:
                self._dspy_info_refs += 1
                if self._dspy_info_refs == 1:
                    dspy_logger = logging.getLogger("dspy")
                    self._dspy_saved_level = dspy_logger.level
                    if dspy_logger.level == 0 or dspy_logger.level > logging.INFO:
                        dspy_logger.setLevel(logging.INFO)

            for tracked in tracked_loggers:
                tracked.addHandler(log_handler)

            try:
                result = service.run(
                    payload,
                    artifact_id=job_id,
                    progress_callback=progress_callback,
                )

                current = self._job_store.get_job(job_id)
                if current.get("status") == "cancelled":
                    logger.info("Job %s was cancelled during execution, skipping result", job_id)
                else:
                    result_dict = result.model_dump(mode="json")
                    self._job_store.update_job(
                        job_id,
                        status="success",
                        message="Optimization completed successfully",
                        completed_at=datetime.now(timezone.utc).isoformat(),
                        result=result_dict,
                    )
                    logger.info("Job %s completed successfully", job_id)

            finally:
                for tracked in tracked_loggers:
                    tracked.removeHandler(log_handler)
                with self._lock:
                    self._dspy_info_refs -= 1
                    if self._dspy_info_refs == 0:
                        logging.getLogger("dspy").setLevel(self._dspy_saved_level)

        except BaseException as exc:  # [WORKER-FIX] catch BaseException to handle shutdown signals
            is_shutdown = isinstance(exc, (SystemExit, KeyboardInterrupt))
            error_message = f"Job interrupted by service shutdown: {exc}" if is_shutdown else str(exc)
            logger.exception("Job %s failed: %s", job_id, error_message)
            try:  # [WORKER-FIX] protect against DB failure during error recording
                self._job_store.update_job(
                    job_id,
                    status="failed",
                    message=error_message,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
            except Exception:
                logger.exception("Job %s: failed to write failure status to DB", job_id)
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
        """Remove a job from the pending queue if it hasn't started yet.

        Args:
            job_id: Job identifier to cancel.

        Returns:
            bool: True if the job was found and removed from the pending queue.
        """
        with self._queue_lock:
            if job_id in self._pending_jobs:
                self._pending_jobs.remove(job_id)
                return True
        return False

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
    job_store: RemoteDBJobStore,
    service: Optional[DspyService] = None,
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

    return _worker
