from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
import signal  # [WORKER-FIX] for SIGTERM graceful shutdown
import threading
from typing import Any, Iterable, List, Optional
from uuid import uuid4
import logging

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import ValidationError
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..constants import (
    JOB_TYPE_GRID_SEARCH,
    JOB_TYPE_RUN,
    PAYLOAD_OVERVIEW_COLUMN_MAPPING,
    PAYLOAD_OVERVIEW_COMPILE_KWARGS,
    PAYLOAD_OVERVIEW_DATASET_ROWS,
    PAYLOAD_OVERVIEW_GENERATION_MODELS,
    PAYLOAD_OVERVIEW_JOB_TYPE,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODEL_SETTINGS,
    PAYLOAD_OVERVIEW_MODULE_KWARGS,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZER_KWARGS,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
    PAYLOAD_OVERVIEW_PROMPT_MODEL,
    PAYLOAD_OVERVIEW_REFLECTION_MODEL,
    PAYLOAD_OVERVIEW_REFLECTION_MODELS,
    PAYLOAD_OVERVIEW_SEED,
    PAYLOAD_OVERVIEW_SHUFFLE,
    PAYLOAD_OVERVIEW_SPLIT_FRACTIONS,
    PAYLOAD_OVERVIEW_TASK_MODEL,
    PAYLOAD_OVERVIEW_TOTAL_PAIRS,
    PAYLOAD_OVERVIEW_USERNAME,
)
from ..storage import get_job_store
from ..models import (
    HEALTH_STATUS_OK,
    GridSearchRequest,
    GridSearchResponse,
    HealthResponse,
    JobCancelResponse,
    JobDeleteResponse,
    JobLogEntry,
    JobPayloadResponse,
    JobStatus,
    JobStatusResponse,
    JobSummaryResponse,
    JobSubmissionResponse,
    PaginatedJobsResponse,
    ProgramArtifactResponse,
    QueueStatusResponse,
    RunRequest,
    RunResponse,
)
from ..registry import RegistryError, ServiceRegistry
from ..service_gateway import DspyService, ServiceError
from ..worker import BackgroundWorker, get_worker
from .converters import (
    compute_elapsed,
    extract_estimated_remaining,
    overview_to_base_fields,
    parse_overview,
    parse_timestamp,
    status_to_job_status,
)

logger = logging.getLogger(__name__)

# Terminal job states that cannot be cancelled or restarted
_TERMINAL_STATUSES = {JobStatus.success, JobStatus.failed, JobStatus.cancelled}


def create_app(
    registry: ServiceRegistry | None = None,
    *,
    service: DspyService | None = None,
    service_kwargs: dict | None = None,
) -> FastAPI:
    """Create a FastAPI app wired up with the supplied registry.

    Args:
        registry: Registry instance containing user-registered assets.
        service: Optional preconstructed ``DspyService``.
        service_kwargs: Keyword arguments forwarded to ``DspyService`` when
            ``service_gateway`` is not supplied.

    Returns:
        FastAPI: Configured application instance.
    """

    registry = registry or ServiceRegistry()
    service = service or DspyService(
        registry,
        **(service_kwargs or {}),
    )

    job_store = get_job_store()

    worker: Optional[BackgroundWorker] = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage application lifecycle - start/stop worker."""
        nonlocal worker
        job_store.recover_orphaned_jobs()  # [WORKER-FIX] mark crashed jobs from previous run as failed
        pending_ids = job_store.recover_pending_jobs()
        worker = get_worker(job_store, service=service, pending_job_ids=pending_ids)
        if pending_ids:
            logger.info("Re-queued %d pending jobs from previous run", len(pending_ids))
        logger.info("Background worker started")

        # [WORKER-FIX] register SIGTERM handler for graceful shutdown on OpenShift
        # only when running on the main interpreter thread.
        can_register_signal = threading.current_thread() is threading.main_thread()
        original_handler = signal.getsignal(signal.SIGTERM) if can_register_signal else None

        def _graceful_shutdown(signum, frame):
            logger.info("SIGTERM received, stopping worker gracefully")
            if worker:
                worker.stop()
            if callable(original_handler) and original_handler not in (signal.SIG_DFL, signal.SIG_IGN):
                original_handler(signum, frame)

        if can_register_signal:
            signal.signal(signal.SIGTERM, _graceful_shutdown)

        try:
            yield
        finally:
            if can_register_signal and original_handler is not None:
                signal.signal(signal.SIGTERM, original_handler)
            if worker:
                worker.stop()
                logger.info("Background worker stopped")

    app = FastAPI(title="DSPy as a Service", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Consistent error response format ----
    # All error responses use {"error": "<type>", "detail": "..."}
    # so API consumers can write a single error handler.

    _STATUS_TO_ERROR_TYPE = {
        400: "validation_error",
        404: "not_found",
        409: "conflict",
        422: "invalid_request",
        500: "internal_error",
        503: "service_unavailable",
    }

    @app.exception_handler(HTTPException)
    async def _http_error_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        error_type = _STATUS_TO_ERROR_TYPE.get(exc.status_code, "error")
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": error_type, "detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Transform Pydantic validation errors into a consistent response payload.

        Args:
            request: Incoming HTTP request that triggered the validation error.
            exc: Pydantic ``RequestValidationError`` raised by FastAPI.

        Returns:
            JSONResponse: Structured error response consumed by API clients.
        """

        def _format_field(loc: Iterable[Any]) -> str:
            """Join validation error location parts into a dotted field path.

            Args:
                loc: Location tuple from Pydantic validation error.

            Returns:
                str: Dotted field path like "dataset[0].question".
            """
            parts: list[str] = []
            for entry in loc:
                if entry in {"body", "__root__"}:
                    continue
                if isinstance(entry, int):
                    if parts:
                        parts[-1] = f"{parts[-1]}[{entry}]"
                    else:
                        parts.append(f"[{entry}]")
                else:
                    parts.append(str(entry))
            return ".".join(parts) if parts else "body"

        issues = []
        for error in exc.errors():
            issues.append(
                {
                    "field": _format_field(error.get("loc", [])),
                    "message": error.get("msg", "Invalid value"),
                    "type": error.get("type", "validation_error"),
                }
            )
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_request",
                "detail": issues,
            },
        )

    # [WORKER-FIX] max seconds of no worker activity before health check flags it
    WORKER_STALE_THRESHOLD = float(os.getenv("WORKER_STALE_THRESHOLD", "600"))

    @app.get("/health", response_model=HealthResponse)
    def healthcheck() -> HealthResponse:
        """Expose a snapshot of registered assets and worker health.

        Returns:
            HealthResponse: Status payload used for readiness checks.

        Raises:
            HTTPException: 503 if worker threads are not alive or stuck.
        """
        # [WORKER-FIX] return 503 if workers died so OpenShift probe detects it
        if worker is None or not worker.threads_alive():
            logger.error("Health check failed: worker threads are not alive")
            raise HTTPException(status_code=503, detail="Worker threads are not running")

        # [WORKER-FIX] detect threads that are alive but stuck (no activity for too long)
        stale_seconds = worker.seconds_since_last_activity()
        if stale_seconds is not None and stale_seconds > WORKER_STALE_THRESHOLD:
            stack_dump = worker.dump_thread_stacks()
            logger.error(
                "Health check failed: workers stuck for %.0fs. Thread stacks:\n%s",
                stale_seconds, stack_dump,
            )
            raise HTTPException(
                status_code=503,
                detail=f"Worker threads stuck for {stale_seconds:.0f}s",
            )

        snapshot = registry.snapshot()
        logger.debug("Health check requested; registered assets: %s", snapshot)
        return HealthResponse(status=HEALTH_STATUS_OK, registered_assets=snapshot)

    @app.post("/run", response_model=JobSubmissionResponse, status_code=201)
    def submit_job(payload: RunRequest) -> JobSubmissionResponse:
        """Validate and queue a DSPy optimization request.

        Args:
            payload: Parsed request containing dataset and optimizer settings.

        Returns:
            JobSubmissionResponse: Job identifier and scheduling metadata.

        Raises:
            HTTPException: If validation fails.
        """

        try:
            service.validate_payload(payload)
        except (ServiceError, RegistryError) as exc:
            logger.warning("Payload validation failed: %s", exc)
            return JSONResponse(
                status_code=400,
                content={"error": "validation_error", "detail": str(exc)},
            )

        job_id = str(uuid4())

        job_store.create_job(job_id)
        job_store.set_payload_overview(
            job_id,
            {
                PAYLOAD_OVERVIEW_JOB_TYPE: JOB_TYPE_RUN,
                PAYLOAD_OVERVIEW_USERNAME: payload.username,
                PAYLOAD_OVERVIEW_MODULE_NAME: payload.module_name,
                PAYLOAD_OVERVIEW_MODULE_KWARGS: dict(payload.module_kwargs),
                PAYLOAD_OVERVIEW_OPTIMIZER_NAME: payload.optimizer_name,
                PAYLOAD_OVERVIEW_MODEL_NAME: payload.model_settings.normalized_identifier(),
                PAYLOAD_OVERVIEW_MODEL_SETTINGS: payload.model_settings.model_dump(),
                PAYLOAD_OVERVIEW_REFLECTION_MODEL: (
                    payload.reflection_model_settings.normalized_identifier()
                    if payload.reflection_model_settings else None
                ),
                PAYLOAD_OVERVIEW_PROMPT_MODEL: (
                    payload.prompt_model_settings.normalized_identifier()
                    if payload.prompt_model_settings else None
                ),
                PAYLOAD_OVERVIEW_TASK_MODEL: (
                    payload.task_model_settings.normalized_identifier()
                    if payload.task_model_settings else None
                ),
                PAYLOAD_OVERVIEW_COLUMN_MAPPING: payload.column_mapping.model_dump(),
                PAYLOAD_OVERVIEW_DATASET_ROWS: len(payload.dataset),
                PAYLOAD_OVERVIEW_SPLIT_FRACTIONS: payload.split_fractions.model_dump(),
                PAYLOAD_OVERVIEW_SHUFFLE: payload.shuffle,
                PAYLOAD_OVERVIEW_SEED: payload.seed,
                PAYLOAD_OVERVIEW_OPTIMIZER_KWARGS: dict(payload.optimizer_kwargs),
                PAYLOAD_OVERVIEW_COMPILE_KWARGS: dict(payload.compile_kwargs),
            },
        )

        current_worker = get_worker(job_store, service=service)
        current_worker.submit_job(job_id, payload)

        logger.info(
            "Enqueued job %s for module=%s optimizer=%s",
            job_id,
            payload.module_name,
            payload.optimizer_name,
        )

        return JobSubmissionResponse(
            job_id=job_id,
            job_type=JOB_TYPE_RUN,
            status=JobStatus.pending,
            created_at=datetime.now(timezone.utc),
            username=payload.username,
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
        )

    @app.post("/grid-search", response_model=JobSubmissionResponse, status_code=201)
    def submit_grid_search(payload: GridSearchRequest) -> JobSubmissionResponse:
        """Submit a grid search over (generation, reflection) model pairs."""
        if hasattr(service, "validate_grid_search_payload"):
            try:
                service.validate_grid_search_payload(payload)
            except (ServiceError, RegistryError) as exc:
                logger.warning("Grid search validation failed: %s", exc)
                return JSONResponse(
                    status_code=400,
                    content={"error": "validation_error", "detail": str(exc)},
                )

        job_id = str(uuid4())
        total_pairs = len(payload.generation_models) * len(payload.reflection_models)

        job_store.create_job(job_id)
        job_store.set_payload_overview(
            job_id,
            {
                PAYLOAD_OVERVIEW_JOB_TYPE: JOB_TYPE_GRID_SEARCH,
                PAYLOAD_OVERVIEW_USERNAME: payload.username,
                PAYLOAD_OVERVIEW_MODULE_NAME: payload.module_name,
                PAYLOAD_OVERVIEW_MODULE_KWARGS: dict(payload.module_kwargs),
                PAYLOAD_OVERVIEW_OPTIMIZER_NAME: payload.optimizer_name,
                PAYLOAD_OVERVIEW_COLUMN_MAPPING: payload.column_mapping.model_dump(),
                PAYLOAD_OVERVIEW_DATASET_ROWS: len(payload.dataset),
                PAYLOAD_OVERVIEW_SPLIT_FRACTIONS: payload.split_fractions.model_dump(),
                PAYLOAD_OVERVIEW_SHUFFLE: payload.shuffle,
                PAYLOAD_OVERVIEW_SEED: payload.seed,
                PAYLOAD_OVERVIEW_OPTIMIZER_KWARGS: dict(payload.optimizer_kwargs),
                PAYLOAD_OVERVIEW_COMPILE_KWARGS: dict(payload.compile_kwargs),
                PAYLOAD_OVERVIEW_TOTAL_PAIRS: total_pairs,
                PAYLOAD_OVERVIEW_GENERATION_MODELS: [m.model_dump() for m in payload.generation_models],
                PAYLOAD_OVERVIEW_REFLECTION_MODELS: [m.model_dump() for m in payload.reflection_models],
            },
        )

        current_worker = get_worker(job_store, service=service)
        current_worker.submit_job(job_id, payload)

        logger.info(
            "Enqueued grid search %s: %d pairs, module=%s optimizer=%s",
            job_id, total_pairs, payload.module_name, payload.optimizer_name,
        )

        return JobSubmissionResponse(
            job_id=job_id,
            job_type=JOB_TYPE_GRID_SEARCH,
            status=JobStatus.pending,
            created_at=datetime.now(timezone.utc),
            username=payload.username,
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
        )

    def _build_summary(job_data: dict) -> JobSummaryResponse:
        """Build a JobSummaryResponse from a raw job store dict."""
        created_at = parse_timestamp(job_data.get("created_at")) or datetime.now(timezone.utc)
        started_at = parse_timestamp(job_data.get("started_at"))
        completed_at = parse_timestamp(job_data.get("completed_at"))
        overview = parse_overview(job_data)
        job_status = status_to_job_status(job_data.get("status", "pending"))
        job_type = overview.get(PAYLOAD_OVERVIEW_JOB_TYPE, JOB_TYPE_RUN)

        # Only show estimated_remaining for active jobs
        est_remaining = None
        if job_status not in _TERMINAL_STATUSES:
            est_remaining = extract_estimated_remaining(job_data)

        # Extract result metrics
        result_data = job_data.get("result")
        latest_metrics = job_data.get("latest_metrics", {})
        baseline = None
        optimized = None
        completed_pairs = None
        failed_pairs = None
        best_pair_label = None

        if isinstance(result_data, dict):
            if job_type == JOB_TYPE_GRID_SEARCH:
                best_pair = result_data.get("best_pair")
                if isinstance(best_pair, dict):
                    baseline = best_pair.get("baseline_test_metric")
                    optimized = best_pair.get("optimized_test_metric")
                    gen = best_pair.get("generation_model", "")
                    ref = best_pair.get("reflection_model", "")
                    best_pair_label = f"{gen} + {ref}"
                completed_pairs = result_data.get("completed_pairs")
                failed_pairs = result_data.get("failed_pairs")
            else:
                baseline = result_data.get("baseline_test_metric")
                optimized = result_data.get("optimized_test_metric")

        # For grid search, pull live counters from latest_metrics if result not yet available
        if job_type == JOB_TYPE_GRID_SEARCH:
            if completed_pairs is None:
                live_completed = latest_metrics.get("completed_so_far")
                completed_pairs = live_completed if isinstance(live_completed, int) else 0
            if failed_pairs is None:
                live_failed = latest_metrics.get("failed_so_far")
                failed_pairs = live_failed if isinstance(live_failed, int) else 0

        # Compute metric improvement
        metric_improvement = None
        if baseline is not None and optimized is not None:
            metric_improvement = round(optimized - baseline, 6)

        elapsed_str, elapsed_secs = compute_elapsed(created_at, started_at, completed_at)

        return JobSummaryResponse(
            job_id=job_data["job_id"],
            status=job_status,
            message=job_data.get("message"),
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            elapsed=elapsed_str,
            elapsed_seconds=elapsed_secs,
            estimated_remaining=est_remaining,
            **overview_to_base_fields(overview),
            split_fractions=overview.get(PAYLOAD_OVERVIEW_SPLIT_FRACTIONS),
            shuffle=overview.get(PAYLOAD_OVERVIEW_SHUFFLE),
            seed=overview.get(PAYLOAD_OVERVIEW_SEED),
            optimizer_kwargs=overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_KWARGS, {}),
            compile_kwargs=overview.get(PAYLOAD_OVERVIEW_COMPILE_KWARGS, {}),
            latest_metrics=latest_metrics,
            progress_count=job_data.get("progress_count", 0),
            log_count=job_data.get("log_count", 0),
            baseline_test_metric=baseline,
            optimized_test_metric=optimized,
            metric_improvement=metric_improvement,
            completed_pairs=completed_pairs,
            failed_pairs=failed_pairs,
            best_pair_label=best_pair_label,
        )

    _VALID_STATUSES = {s.value for s in JobStatus}
    _VALID_JOB_TYPES = {JOB_TYPE_RUN, JOB_TYPE_GRID_SEARCH}

    @app.get("/jobs", response_model=PaginatedJobsResponse)
    def list_jobs(
        status: Optional[str] = Query(default=None, description="Filter by job status"),
        username: Optional[str] = Query(default=None, description="Filter by username"),
        job_type: Optional[str] = Query(default=None, description="Filter by job type (run or grid_search)"),
        limit: int = Query(default=50, ge=1, le=500, description="Max results"),
        offset: int = Query(default=0, ge=0, description="Skip N results"),
    ) -> PaginatedJobsResponse:
        """List all jobs with optional filtering and pagination.

        Args:
            status: Optional status filter.
            username: Optional username filter.
            job_type: Optional job type filter ('run' or 'grid_search').
            limit: Maximum number of jobs to return.
            offset: Number of jobs to skip.

        Returns:
            PaginatedJobsResponse: Paginated jobs ordered by creation time (newest first).
        """
        if status is not None and status not in _VALID_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status filter '{status}'. Valid values: {sorted(_VALID_STATUSES)}",
            )
        if job_type is not None and job_type not in _VALID_JOB_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid job_type filter '{job_type}'. Valid values: {sorted(_VALID_JOB_TYPES)}",
            )
        total = job_store.count_jobs(status=status, username=username, job_type=job_type)
        rows = job_store.list_jobs(status=status, username=username, job_type=job_type, limit=limit, offset=offset)
        items = [_build_summary(job_data) for job_data in rows]
        return PaginatedJobsResponse(items=items, total=total, limit=limit, offset=offset)

    @app.get("/jobs/{job_id}", response_model=JobStatusResponse)
    def get_job(job_id: str) -> JobStatusResponse:
        """Return the status of a queued or running job.

        Args:
            job_id: Identifier returned during submission.

        Returns:
            JobStatusResponse: Current job metadata and latest metrics.

        Raises:
            HTTPException: If the job is not found.
        """

        try:
            job_data = job_store.get_job(job_id)
        except KeyError:
            logger.warning("Job status requested for unknown job_id=%s", job_id)
            raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'.")

        status = status_to_job_status(job_data.get("status", "pending"))

        progress_events = job_store.get_progress_events(job_id)
        logs = job_store.get_logs(job_id)

        overview = parse_overview(job_data)
        job_type = overview.get(PAYLOAD_OVERVIEW_JOB_TYPE, JOB_TYPE_RUN)

        result = None
        grid_result = None
        result_data = job_data.get("result")
        if result_data and isinstance(result_data, dict):
            try:
                if job_type == JOB_TYPE_GRID_SEARCH:
                    # Always include per-pair results so users can see what
                    # went wrong without a separate /grid-result call.
                    grid_result = GridSearchResponse.model_validate(result_data)
                elif status == JobStatus.success:
                    result = RunResponse.model_validate(result_data)
            except ValidationError:
                logger.warning("Job %s has corrupted result data", job_id)

        created_at = parse_timestamp(job_data.get("created_at")) or datetime.now(timezone.utc)
        started_at = parse_timestamp(job_data.get("started_at"))
        completed_at = parse_timestamp(job_data.get("completed_at"))

        # Only show estimated_remaining for active jobs
        est_remaining = None
        if status not in _TERMINAL_STATUSES:
            est_remaining = extract_estimated_remaining(job_data)

        # Pair counters for grid search jobs
        latest_metrics = job_data.get("latest_metrics", {})
        completed_pairs = None
        failed_pairs = None
        if job_type == JOB_TYPE_GRID_SEARCH:
            if grid_result:
                completed_pairs = grid_result.completed_pairs
                failed_pairs = grid_result.failed_pairs
            else:
                live_completed = latest_metrics.get("completed_so_far")
                completed_pairs = live_completed if isinstance(live_completed, int) else 0
                live_failed = latest_metrics.get("failed_so_far")
                failed_pairs = live_failed if isinstance(live_failed, int) else 0

        elapsed_str, elapsed_secs = compute_elapsed(created_at, started_at, completed_at)

        logger.debug("Returning status for job_id=%s state=%s", job_id, status)
        return JobStatusResponse(
            job_id=job_id,
            status=status,
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            elapsed=elapsed_str,
            elapsed_seconds=elapsed_secs,
            estimated_remaining=est_remaining,
            **overview_to_base_fields(overview),
            message=job_data.get("message"),
            latest_metrics=latest_metrics,
            completed_pairs=completed_pairs,
            failed_pairs=failed_pairs,
            progress_events=progress_events,
            logs=[JobLogEntry(**log) for log in logs],
            result=result,
            grid_result=grid_result,
        )

    @app.get("/jobs/{job_id}/summary", response_model=JobSummaryResponse)
    def get_job_summary(job_id: str) -> JobSummaryResponse:
        """Return a coarse summary of job progress and metadata.

        Args:
            job_id: Identifier for the job returned during submission.

        Returns:
            JobSummaryResponse: Aggregated job metadata and timing information.
        """

        try:
            job_data = job_store.get_job(job_id)
        except KeyError:
            logger.warning("Job summary requested for unknown job_id=%s", job_id)
            raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'.")

        job_data["progress_count"] = job_store.get_progress_count(job_id)
        job_data["log_count"] = job_store.get_log_count(job_id)
        return _build_summary(job_data)

    @app.get("/jobs/{job_id}/logs", response_model=List[JobLogEntry])
    def get_job_logs(
        job_id: str,
        limit: Optional[int] = Query(default=None, ge=1, le=5000, description="Max log entries to return"),
        offset: int = Query(default=0, ge=0, description="Skip N log entries"),
        level: Optional[str] = Query(default=None, description="Filter by log level (e.g. ERROR, WARNING, INFO)"),
    ) -> List[JobLogEntry]:
        """Return the chronological run log for the job.

        Args:
            job_id: Identifier for the job returned during submission.
            limit: Maximum number of log entries to return.
            offset: Number of log entries to skip.
            level: Filter by log level (case-insensitive).

        Returns:
            List[JobLogEntry]: Ordered log entries captured during execution.
        """

        if not job_store.job_exists(job_id):
            logger.warning("Job logs requested for unknown job_id=%s", job_id)
            raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'.")

        normalized_level = level.upper() if level else None
        log_entries = job_store.get_logs(
            job_id, limit=limit, offset=offset, level=normalized_level,
        )
        return [JobLogEntry(**entry) for entry in log_entries]

    @app.get("/jobs/{job_id}/payload", response_model=JobPayloadResponse)
    def get_job_payload(job_id: str) -> JobPayloadResponse:
        """Return the original request payload submitted for this job.

        Args:
            job_id: Identifier for the job returned during submission.

        Returns:
            JobPayloadResponse: The stored request payload.
        """
        try:
            job_data = job_store.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'.")

        payload = job_data.get("payload")
        if not payload or not isinstance(payload, dict):
            raise HTTPException(
                status_code=404,
                detail="Payload not available for this job.",
            )

        overview = parse_overview(job_data)
        job_type = overview.get(PAYLOAD_OVERVIEW_JOB_TYPE, JOB_TYPE_RUN)
        return JobPayloadResponse(job_id=job_id, job_type=job_type, payload=payload)

    @app.get("/jobs/{job_id}/artifact", response_model=ProgramArtifactResponse)
    def get_job_artifact(job_id: str) -> ProgramArtifactResponse:
        """Return the serialized artifact once the job succeeds.

        Args:
            job_id: Identifier for the job returned during submission.

        Returns:
            ProgramArtifactResponse: Serialized program artifact payload.
        """

        try:
            job_data = job_store.get_job(job_id)
        except KeyError:
            logger.warning("Artifact requested for unknown job_id=%s", job_id)
            raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'.")

        overview = parse_overview(job_data)
        job_type = overview.get(PAYLOAD_OVERVIEW_JOB_TYPE, JOB_TYPE_RUN)

        if job_type == JOB_TYPE_GRID_SEARCH:
            raise HTTPException(
                status_code=404,
                detail="Grid search jobs produce per-pair artifacts. Use GET /jobs/{job_id}/grid-result instead.",
            )

        status = status_to_job_status(job_data.get("status", "pending"))

        if status in {JobStatus.pending, JobStatus.validating, JobStatus.running}:
            raise HTTPException(status_code=409, detail="Job has not finished yet.")

        if status == JobStatus.failed:
            error_msg = job_data.get("message") or "unknown error"
            raise HTTPException(
                status_code=409,
                detail=f"Job failed and did not produce an artifact. Error: {error_msg}",
            )

        if status == JobStatus.cancelled:
            raise HTTPException(
                status_code=409,
                detail="Job was cancelled and did not produce an artifact.",
            )

        if status == JobStatus.success:
            result_data = job_data.get("result")
            if result_data and isinstance(result_data, dict):
                try:
                    result = RunResponse.model_validate(result_data)
                except ValidationError:
                    logger.warning("Job %s has corrupted result data", job_id)
                    raise HTTPException(status_code=500, detail="Job result data is corrupted.")
                return ProgramArtifactResponse(
                    program_artifact=result.program_artifact,
                )

        raise HTTPException(status_code=409, detail="Job did not produce an artifact.")

    @app.get("/jobs/{job_id}/grid-result", response_model=GridSearchResponse)
    def get_grid_search_result(job_id: str) -> GridSearchResponse:
        """Return the full grid search result once the job completes."""
        try:
            job_data = job_store.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'.")

        overview = parse_overview(job_data)
        if overview.get(PAYLOAD_OVERVIEW_JOB_TYPE) != JOB_TYPE_GRID_SEARCH:
            raise HTTPException(status_code=404, detail="Job is not a grid search.")

        status = status_to_job_status(job_data.get("status", "pending"))
        if status not in _TERMINAL_STATUSES:
            raise HTTPException(status_code=409, detail="Job has not finished yet.")

        result_data = job_data.get("result")
        if not result_data or not isinstance(result_data, dict):
            if status == JobStatus.failed:
                error_msg = job_data.get("message") or "unknown error"
                raise HTTPException(
                    status_code=409,
                    detail=f"Grid search failed and produced no result. Error: {error_msg}",
                )
            if status == JobStatus.cancelled:
                raise HTTPException(
                    status_code=409,
                    detail="Grid search was cancelled and produced no result.",
                )
            raise HTTPException(status_code=404, detail="No grid search result available.")

        try:
            return GridSearchResponse.model_validate(result_data)
        except ValidationError:
            raise HTTPException(status_code=500, detail="Grid search result data is corrupted.")

    @app.post("/jobs/{job_id}/cancel", response_model=JobCancelResponse, status_code=200)
    def cancel_job(job_id: str) -> JobCancelResponse:
        """Cancel a pending or running job.

        Args:
            job_id: Identifier for the job to cancel.

        Returns:
            dict: Confirmation with job_id and new status.

        Raises:
            HTTPException: If the job is not found or already in a terminal state.
        """
        try:
            job_data = job_store.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'.")

        status = status_to_job_status(job_data.get("status", "pending"))
        if status in _TERMINAL_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=f"Job is already in terminal state '{status.value}'.",
            )

        if worker:
            worker.cancel_job(job_id)

        now = datetime.now(timezone.utc).isoformat()
        job_store.update_job(job_id, status="cancelled", message="Cancelled by user", completed_at=now)
        logger.info("Job %s (%s) cancelled", job_id, status.value)
        return JobCancelResponse(job_id=job_id, status="cancelled")

    @app.delete("/jobs/{job_id}", response_model=JobDeleteResponse, status_code=200)
    def delete_job(job_id: str) -> JobDeleteResponse:
        """Delete a completed, failed, or cancelled job and all its data.

        Args:
            job_id: Identifier for the job to delete.

        Returns:
            dict: Confirmation with deleted job_id.

        Raises:
            HTTPException: If the job is not found or still active.
        """
        try:
            job_data = job_store.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'.")

        status = status_to_job_status(job_data.get("status", "pending"))
        if status not in _TERMINAL_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete job in '{status.value}' state. Cancel it first.",
            )

        job_store.delete_job(job_id)
        logger.info("Job %s deleted", job_id)
        return JobDeleteResponse(job_id=job_id, deleted=True)

    @app.get("/queue", response_model=QueueStatusResponse)
    def get_queue_status() -> QueueStatusResponse:
        """Return current queue and worker status.

        Returns:
            QueueStatusResponse: Queue depth and worker health snapshot.
        """
        if worker is None:
            return QueueStatusResponse(
                pending_jobs=0,
                active_jobs=0,
                worker_threads=0,
                workers_alive=False,
            )

        return QueueStatusResponse(
            pending_jobs=worker.queue_size(),
            active_jobs=worker.active_jobs(),
            worker_threads=worker.thread_count(),
            workers_alive=worker.threads_alive(),
        )

    return app
