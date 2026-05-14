"""Background worker for DSPy optimization jobs.

Threaded worker that claims pending jobs from a shared job store and processes
them with configurable concurrency. Multi-pod safety is delegated to the store:
:meth:`JobStore.claim_next_job` performs an atomic claim (Postgres uses
``SELECT ... FOR UPDATE SKIP LOCKED``) so two pods running side by side cannot
race on the same row.
"""

from __future__ import annotations

import contextlib
import json
import logging
import multiprocessing as mp
import os
import queue
import socket
import sys
import threading
import time
import traceback
from datetime import UTC, datetime
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
from ..service_gateway.embedding_pipeline import embed_finished_job
from ..storage import JobStore
from .constants import EVENT_ERROR, EVENT_LOG, EVENT_PROGRESS, EVENT_RESULT
from .subprocess_runner import run_service_in_subprocess, set_fork_service

logger = logging.getLogger(__name__)


class CancellationError(Exception):
    """Raised inside a job thread when the job is cancelled by the user."""


def _raise_if_cancelled(cancel_event: threading.Event | None, optimization_id: str) -> None:
    """Raise ``CancellationError`` when the caller's cancel flag is set; ``None`` is treated as not cancelled.

    Args:
        cancel_event: The cooperative cancel flag (``None`` skips the check).
        optimization_id: ID embedded in the raised error message.

    Raises:
        CancellationError: When ``cancel_event`` is set.
    """
    if cancel_event and cancel_event.is_set():
        raise CancellationError(f"Optimization {optimization_id} cancelled by user")


class BackgroundWorker:
    """Multi-threaded worker that polls a job store and runs optimization jobs.

    Each worker thread calls ``_worker_loop``, which polls ``_pending_jobs`` and
    dispatches work to ``_process_job``.  Jobs run inside a child process created
    with the configured multiprocessing start method (fork or spawn); events
    (progress, logs, result, error) are streamed back through a ``mp.Queue``
    and persisted by ``_drain_subprocess_events``.  Cancellation is cooperative:
    each job has a ``threading.Event``; ``_raise_if_cancelled`` polls it between
    subprocess join timeouts so the child can be terminated promptly on request.
    """

    def __init__(
        self,
        job_store: JobStore,
        num_workers: int = 2,
        poll_interval: float = 2.0,
        service: DspyService | None = None,
        pod_name: str | None = None,
        lease_seconds: float = 60.0,
    ) -> None:
        """Initialize the worker with a job store and concurrency settings.

        Args:
            job_store: Backend used to load and persist job state.
            num_workers: Number of worker threads to spawn on ``start``.
            poll_interval: Seconds the loop sleeps between empty-queue checks.
            service: Optional pre-built ``DspyService``; one is built lazily otherwise.
            pod_name: Identifier written to ``jobs.claimed_by`` so claim
                ownership survives a process restart and is observable across
                the fleet. Defaults to ``$POD_NAME`` (set via the Kubernetes
                downward API in the Helm chart) or, failing that, the
                hostname.
            lease_seconds: Initial lease window granted by ``claim_next_job``.
                The worker loop renews it via ``_touch_activity`` on every
                cancel-poll tick; should comfortably exceed
                ``cancel_poll_interval × 3``.
        """
        self._job_store = job_store
        self._num_workers = num_workers
        self._poll_interval = poll_interval
        self._running = False
        self._threads: list[threading.Thread] = []
        self._service: DspyService | None = service
        self._pod_name = pod_name or os.environ.get("POD_NAME") or socket.gethostname()
        self._lease_seconds = max(float(lease_seconds), 5.0)

        # In-memory queue is retained as a backwards-compat seam: tests and
        # any legacy single-pod callers can still call ``enqueue_job`` directly
        # and the worker loop will drain that list before falling back to the
        # shared ``claim_next_job`` queue.
        self._pending_jobs: list[str] = []
        self._processing_jobs: set[str] = set()
        self._claimed_jobs: set[str] = set()
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

        self._last_activity: dict[int, float] = {}
        self._activity_lock = threading.Lock()
        # Per-thread current job for lease heartbeats.
        self._thread_current_job: dict[int, str] = {}

    @staticmethod
    def _resolve_mp_context() -> mp.context.BaseContext:
        """Resolve multiprocessing start method from JOB_RUN_START_METHOD, falling back to system default.

        Returns:
            A multiprocessing context honoring the configured start method.
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
        """Get or lazily build the shared DspyService instance.

        Returns:
            The shared ``DspyService`` used by all worker threads.
        """
        if self._service is None:
            self._service = DspyService(ServiceRegistry())
        return self._service

    def enqueue_job(self, optimization_id: str) -> None:
        """Register a cancel event for ``optimization_id`` and pre-stage it locally.

        With the DB-backed claim queue, the canonical hand-off is the row's
        ``status='pending'`` flag, which any pod can claim on its next poll
        tick. The local in-memory queue is kept only so tests and legacy
        single-pod callers continue to work — the worker loop drains it
        before falling back to ``claim_next_job``.

        Args:
            optimization_id: ID of the job to register.
        """
        with self._queue_lock:
            self._cancel_events.setdefault(optimization_id, threading.Event())
            if (
                optimization_id not in self._pending_jobs
                and optimization_id not in self._processing_jobs
            ):
                self._pending_jobs.append(optimization_id)
                logger.info("Optimization %s enqueued (local hint)", optimization_id)

    def submit_job(self, optimization_id: str, payload: RunRequest | GridSearchRequest) -> None:
        """Persist payload to the job store; rely on DB claim for pickup.

        Writes the payload onto the existing ``pending`` row and registers a
        cancel event; the next worker tick (on this pod or a peer) picks the
        job up via :meth:`JobStore.claim_next_job`. Latency-to-pickup is
        bounded by the worker poll interval.

        Args:
            optimization_id: ID of the job being submitted.
            payload: Pydantic model whose ``model_dump`` is stored on the job.
        """
        self._job_store.update_job(
            optimization_id,
            payload=payload.model_dump(mode="json", by_alias=True),
        )
        with self._queue_lock:
            self._cancel_events[optimization_id] = threading.Event()
        logger.info("Optimization %s submitted (awaiting claim)", optimization_id)

    def _claim_job_from_store(self) -> str | None:
        """Try to claim a pending job from the shared store.

        Returns:
            The claimed optimization ID, or ``None`` when no work is available.
        """
        try:
            record = self._job_store.claim_next_job(self._pod_name, self._lease_seconds)
        except AttributeError:
            # Older JobStore implementation without claim support — fall back
            # to legacy in-memory only behaviour.
            return None
        except Exception:
            logger.exception("claim_next_job raised; backing off")
            return None
        if record is None:
            return None
        optimization_id = record.get("optimization_id") if isinstance(record, dict) else None
        if not optimization_id:
            return None
        with self._queue_lock:
            self._cancel_events.setdefault(optimization_id, threading.Event())
            self._processing_jobs.add(optimization_id)
            self._claimed_jobs.add(optimization_id)
        return optimization_id

    def _get_next_job(self) -> str | None:
        """Return the next claimable job (in-memory hint first, then DB claim).

        Returns:
            The optimization ID to process next, or ``None`` when idle.
        """
        with self._queue_lock:
            if self._pending_jobs:
                optimization_id = self._pending_jobs.pop(0)
                self._processing_jobs.add(optimization_id)
                return optimization_id
        # Fall back to the multi-pod safe claim path.
        return self._claim_job_from_store()

    def _mark_job_done(self, optimization_id: str) -> None:
        """Release the claim and clean up per-job worker state.

        Args:
            optimization_id: ID of the job that just finished.
        """
        was_claimed = False
        with self._queue_lock:
            self._processing_jobs.discard(optimization_id)
            self._cancel_events.pop(optimization_id, None)
            if optimization_id in self._claimed_jobs:
                self._claimed_jobs.discard(optimization_id)
                was_claimed = True
        if was_claimed:
            try:
                self._job_store.release_job(optimization_id, self._pod_name)
            except AttributeError:
                pass
            except Exception:
                logger.exception("release_job failed for %s", optimization_id)

    def _worker_loop(self, worker_id: int) -> None:
        """Poll for jobs and process them until stopped.

        Args:
            worker_id: Index identifying this thread for logging.
        """
        logger.info("Worker %d started (pod=%s)", worker_id, self._pod_name)

        # Top-level guard: a fatal exception inside the loop must not let
        # the worker thread die silently — health checks would still report
        # the thread alive while no jobs got picked up.
        try:
            idle_cycles = 0
            self._touch_activity(worker_id)
            while self._running:
                optimization_id = self._get_next_job()

                if optimization_id is None:
                    time.sleep(self._poll_interval)
                    idle_cycles += 1
                    # Heartbeat every ~5 min so observability dashboards
                    # can distinguish "idle but alive" from "stuck".
                    if idle_cycles % 150 == 0:
                        logger.info("Worker %d heartbeat, idle cycles: %d", worker_id, idle_cycles)
                        self._touch_activity(worker_id)
                    continue

                idle_cycles = 0
                with self._activity_lock:
                    self._thread_current_job[worker_id] = optimization_id
                self._touch_activity(worker_id)
                try:
                    self._process_job(optimization_id, worker_id)
                except Exception:  # isolation boundary: one bad job must not kill the worker thread
                    logger.exception("Worker %d failed processing job %s", worker_id, optimization_id)
                finally:
                    with self._activity_lock:
                        self._thread_current_job.pop(worker_id, None)
                    self._mark_job_done(optimization_id)
        except Exception:
            logger.exception("Worker %d died unexpectedly", worker_id)

        logger.info("Worker %d stopped", worker_id)

    def _process_job(self, optimization_id: str, worker_id: int) -> None:
        """Run one optimization job to completion, handling all error and cancel paths.

        Loads the payload from the job store, validates it, spawns a child process
        via ``run_service_in_subprocess``, and drains the event queue until the child
        exits.  The ``BaseException`` handler at the bottom covers cancellation,
        shutdown signals (``SystemExit``/``KeyboardInterrupt``), and ordinary errors —
        each path writes the correct terminal status and fires a notification.
        Shutdown signals are re-raised after cleanup so the process can exit;
        every other exception is translated into a ``failed``/``cancelled``
        terminal status instead of propagating.

        Args:
            optimization_id: ID of the job to process.
            worker_id: Index of the calling worker thread (for activity tracking).

        Raises:
            SystemExit: Propagated after status is written, to allow shutdown.
            KeyboardInterrupt: Propagated after status is written.
        """
        logger.info("Processing job %s", optimization_id)

        overview: dict[str, Any] = {}  # pre-init so BaseException handler has a defined value even if early error

        with self._queue_lock:
            cancel_event = self._cancel_events.get(optimization_id)

        try:
            _raise_if_cancelled(cancel_event, optimization_id)  # before loading payload

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
            if not isinstance(overview, dict):
                overview = {}
            optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)

            if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
                grid_payload = GridSearchRequest.model_validate(payload_dict)
            else:
                run_payload = RunRequest.model_validate(payload_dict)

            self._job_store.update_job(
                optimization_id,
                status="validating",
                message="Validating payload",
            )

            service = self._get_service()
            if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH and hasattr(service, "validate_grid_search_payload"):
                service.validate_grid_search_payload(grid_payload)
            elif optimization_type == OPTIMIZATION_TYPE_RUN:
                service.validate_payload(run_payload)

            _raise_if_cancelled(cancel_event, optimization_id)  # before starting the optimization

            self._job_store.update_job(
                optimization_id,
                status="running",
                message="Running optimization",
                started_at=datetime.now(UTC).isoformat(),
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
                run_process = self._mp_ctx.Process(  # type: ignore[attr-defined]
                    target=run_service_in_subprocess,
                    args=(payload_dict, optimization_id, event_queue, self._mp_start_method),
                    name=f"dspy-run-{optimization_id[:8]}",
                    daemon=True,
                )
                assert run_process is not None
                run_process.start()

                while run_process.is_alive():
                    _raise_if_cancelled(cancel_event, optimization_id)
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
                _raise_if_cancelled(cancel_event, optimization_id)

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
                        # Cancel endpoint raced us past the last _raise_if_cancelled() and
                        # already wrote "cancelled" to the DB. Treat it as a cancellation.
                        raise CancellationError()
                    self._job_store.update_job(
                        optimization_id,
                        status=final_status,
                        message=final_message,
                        completed_at=datetime.now(UTC).isoformat(),
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
                        self._schedule_embedding_indexing(optimization_id)
                except KeyError:
                    logger.info(
                        "Optimization %s was deleted during execution (likely cancelled), skipping result",
                        optimization_id,
                    )
            # cleanup-and-reraise: ensure the subprocess is killed on ANY exit
            # path (including shutdown signals) before the exception propagates.
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

        # BaseException catches SystemExit/KeyboardInterrupt during graceful shutdown
        # so we still record a terminal status for the in-flight job before propagating.
        except BaseException as exc:
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
                now = datetime.now(UTC).isoformat()
                try:
                    self._job_store.update_job(
                        optimization_id, status=final_status, message=error_message, completed_at=now
                    )
                except Exception:  # isolation boundary: a DB hiccup must not prevent the notification below
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
        """Start the background worker threads and begin polling.

        Idempotent: a second call while ``_running`` is true is a no-op.
        """
        if self._running:
            return

        self._running = True
        for i in range(self._num_workers):
            # Non-daemon: the SIGTERM handler joins these threads explicitly so
            # in-flight subprocesses get a chance to terminate cleanly.
            thread = threading.Thread(
                target=self._worker_loop,
                args=(i,),
                name=f"dspy-worker-{i}",
            )
            thread.start()
            self._threads.append(thread)

        logger.info("Started %d background workers", self._num_workers)

    def stop(self, timeout: float = 30.0) -> None:
        """Signal all workers to stop and wait for them to finish.

        Clears the pending queue, sets the cancel event for every tracked job so
        in-flight subprocesses terminate promptly, and joins each worker thread
        with a share of the total ``timeout``.

        Args:
            timeout: Total seconds shared across all worker thread joins.
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
        """Return True if the worker has been started.

        Returns:
            ``True`` while ``start`` has been called and ``stop`` has not.
        """
        return self._running

    def _touch_activity(self, worker_id: int) -> None:
        """Record liveness and renew the lease on this worker's current job.

        Renewing the lease here keeps the lease window short (so a dead pod
        is reclaimed quickly) without us having to schedule a separate
        heartbeat thread — the same call sites that prove this thread is
        alive also prove that its claim is still valid.

        Args:
            worker_id: Index of the worker thread reporting liveness.
        """
        with self._activity_lock:
            self._last_activity[worker_id] = time.monotonic()
            current_job = self._thread_current_job.get(worker_id)
        if current_job is not None and current_job in self._claimed_jobs:
            try:
                still_owned = self._job_store.extend_lease(
                    current_job, self._pod_name, self._lease_seconds
                )
            except AttributeError:
                still_owned = True
            except Exception:
                logger.exception("extend_lease failed for %s", current_job)
                still_owned = True
            if not still_owned:
                # Another pod stole the lease (we hung past the window). Cancel
                # ourselves so we abandon the run instead of double-processing.
                logger.warning(
                    "Lease for %s was stolen from %s — cancelling local run",
                    current_job,
                    self._pod_name,
                )
                with self._queue_lock:
                    event = self._cancel_events.get(current_job)
                if event is not None:
                    event.set()

    def _schedule_embedding_indexing(self, optimization_id: str) -> None:
        """Fire-and-forget embed the finished job for the explore-map index.

        Runs on a daemon thread so a slow LLM call or a missing pgvector
        extension can never block the worker's hot path. Failures are
        swallowed — the job itself is already marked success; the index
        is best-effort and the startup backfill heals any gaps.

        Args:
            optimization_id: ID of the just-finished job to index.
        """
        threading.Thread(
            target=self._embed_finished_job_best_effort,
            args=(optimization_id,),
            name=f"embed-{optimization_id[:8]}",
            daemon=True,
        ).start()

    def _embed_finished_job_best_effort(self, optimization_id: str) -> None:
        """Embed a finished job, swallowing failures so they never reach the worker.

        A missing pgvector extension or LLM credentials issue only surfaces
        on the indexing thread, never on the worker hot path.

        Args:
            optimization_id: ID of the finished job to embed.
        """
        try:
            embed_finished_job(optimization_id, job_store=self._job_store)
        except Exception as exc:  # isolation boundary: best-effort indexing must never impact job status
            logger.debug("Embedding indexing for %s failed: %s", optimization_id, exc)

    def _terminate_run_process(self, run_process: mp.process.BaseProcess, optimization_id: str) -> None:
        """Terminate a still-running job subprocess, escalating to SIGKILL after a 3-second grace period.

        Sends SIGTERM, waits up to 3 s, then calls ``kill()`` if the process is
        still alive and the platform supports it.  A final 2-second join follows
        before logging the outcome.  Never raises regardless of process state.

        Args:
            run_process: The job subprocess to terminate.
            optimization_id: ID embedded in the resulting log lines.
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
            optimization_id: ID of the running job (for log routing).
            event_queue: The shared multiprocessing queue to drain.

        Returns:
            ``(result_dict, error_dict)`` — either may be ``None`` if the
            corresponding event was not present.
        """
        result_payload: dict[str, Any] | None = None
        error_payload: dict[str, Any] | None = None
        while True:
            try:
                event = event_queue.get_nowait()
            except queue.Empty:
                break
            except Exception:  # isolation boundary: a broken queue must not crash the job-processing loop
                logger.exception("Optimization %s: event queue read failed; stopping drain", optimization_id)
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
                        timestamp = datetime.fromisoformat(timestamp_raw)
                    except ValueError:
                        timestamp = None
                pair_index_raw = event.get("pair_index")
                pair_index = int(pair_index_raw) if isinstance(pair_index_raw, int) else None
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

    def seconds_since_last_activity(self) -> float | None:
        """Return seconds since the most recent worker activity, or ``None`` if none recorded yet.

        Returns:
            Seconds since any worker last touched its activity timestamp.
        """
        with self._activity_lock:
            if not self._last_activity:
                return None
            latest = max(self._last_activity.values())
        return time.monotonic() - latest

    def dump_thread_stacks(self) -> str:
        """Return formatted stack traces of all worker threads, suitable for logging when diagnosing stuck workers.

        Returns:
            A multi-line string with the current frame of each worker thread.
        """
        frames = sys._current_frames()
        lines = []
        for thread in self._threads:
            frame = frames.get(thread.ident) if thread.ident is not None else None
            if frame:
                lines.append(f"--- {thread.name} (alive={thread.is_alive()}) ---")
                lines.extend(traceback.format_stack(frame))
            else:
                lines.append(f"--- {thread.name} (no frame, alive={thread.is_alive()}) ---")
        return "\n".join(lines)

    def threads_alive(self) -> bool:
        """Return True if the worker has at least one registered thread and every one is alive.

        Returns:
            ``True`` only when every spawned worker thread is still running.
        """
        if not self._threads:
            return False
        return all(t.is_alive() for t in self._threads)

    def cancel_job(self, optimization_id: str) -> bool:
        """Signal a job to stop. Returns True if the job was found (pending or currently running).

        Args:
            optimization_id: ID of the job to cancel.

        Returns:
            ``True`` if a pending or running job was found, ``False`` otherwise.
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
            Length of the pending queue at the moment the lock is held.
        """
        with self._queue_lock:
            return len(self._pending_jobs)

    def active_jobs(self) -> int:
        """Return the number of jobs currently being processed.

        Returns:
            Size of the processing set at the moment the lock is held.
        """
        with self._queue_lock:
            return len(self._processing_jobs)

    def thread_count(self) -> int:
        """Return the number of registered worker threads (alive or finished).

        Returns:
            Length of the internal thread list.
        """
        return len(self._threads)


_worker: BackgroundWorker | None = None
_worker_lock = threading.Lock()


def get_worker(
    job_store: JobStore,
    service: DspyService | None = None,
    pending_optimization_ids: list | None = None,
) -> BackgroundWorker:
    """Return the module-level singleton ``BackgroundWorker``, creating it if needed.

    If the current singleton is missing or its threads have died a new worker is
    constructed from ``settings.worker_threads`` / ``settings.worker_poll_interval``
    and started. With the DB-backed claim queue, ``pending_optimization_ids``
    is no longer required — pending rows are picked up automatically by the
    next claim — but the parameter is preserved (and used as a local hint) so
    callers don't have to coordinate the upgrade.

    Args:
        job_store: Backend used by the worker to persist job state.
        service: Optional pre-built ``DspyService`` shared with the worker.
        pending_optimization_ids: Optional local hint for jobs already known
            to be pending (eg. recovered on the same pod's restart).

    Returns:
        The module-level worker singleton.
    """
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
    """Stop and clear the module-level worker singleton (test-only helper).

    Calls ``stop`` on the existing singleton (swallowing any shutdown error so
    the next test is not blocked) and then resets the module-level reference to
    ``None`` so the next ``get_worker`` call constructs a fresh instance.

    Args:
        timeout: Seconds shared across worker thread joins during shutdown.
    """
    global _worker
    with _worker_lock:
        if _worker is not None:
            try:
                _worker.stop(timeout=timeout)
            except Exception:  # isolation boundary: a failing shutdown must not block subsequent tests
                logger.exception("Failed to stop global worker during test reset")
        _worker = None
