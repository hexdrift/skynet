from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
import signal  # [WORKER-FIX] for SIGTERM graceful shutdown
import threading
from typing import Any, Iterable, List, Optional
from uuid import uuid4
import logging

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, ValidationError
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse

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
    PAYLOAD_OVERVIEW_NAME,
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
    ValidateCodeRequest,
    ValidateCodeResponse,
    JobStatus,
    JobStatusResponse,
    JobSummaryResponse,
    JobSubmissionResponse,
    ModelConfig,
    PaginatedJobsResponse,
    ProgramArtifactResponse,
    QueueStatusResponse,
    RunRequest,
    RunResponse,
    ServeInfoResponse,
    ServeRequest,
    ServeResponse,
    TemplateCreateRequest,
    TemplateResponse,
)
from ..notifications import notify_job_started, notify_job_completed
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
from .model_catalog import ModelCatalogResponse, get_catalog_cached


class DiscoverModelsRequest(BaseModel):
    """Request payload for POST /models/discover."""

    base_url: str
    api_key: Optional[str] = None


class DiscoverModelsResponse(BaseModel):
    """Response payload for POST /models/discover."""

    models: List[str] = []
    base_url: str
    error: Optional[str] = None

logger = logging.getLogger(__name__)

# Terminal job states that cannot be cancelled or restarted
_TERMINAL_STATUSES = {JobStatus.success, JobStatus.failed, JobStatus.cancelled}


def _strip_api_key(d: dict) -> dict:
    """Remove api_key from a model settings dict before persisting."""
    result = dict(d)
    extra = result.get("extra")
    if isinstance(extra, dict) and "api_key" in extra:
        result["extra"] = {k: v for k, v in extra.items() if k != "api_key"}
    return result


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

    app = FastAPI(title="Skynet", lifespan=lifespan)

    allowed_origins = os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001"
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in allowed_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
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

    @app.get("/models", response_model=ModelCatalogResponse)
    def list_models() -> ModelCatalogResponse:
        """Return the curated model catalog plus per-provider env-key status.

        The frontend uses this to populate the model-name dropdown and to
        decide whether an explicit ``api_key`` input is required (if the
        backend's env already has the key, the user can leave it blank).
        """

        return get_catalog_cached()

    @app.post("/models/discover", response_model=DiscoverModelsResponse)
    def discover_models(payload: DiscoverModelsRequest) -> DiscoverModelsResponse:
        """Fetch the live model list from a user-supplied OpenAI-compatible endpoint.

        Targets ``GET {base_url}/v1/models`` (vLLM, Ollama, LM Studio, proxies).
        Falls back to ``{base_url}/models`` if the first attempt 404s. Returns
        an empty list with a human-readable ``error`` on failure instead of
        raising — the frontend treats it as advisory.
        """

        import urllib.error
        import urllib.request
        import json as _json

        base = payload.base_url.rstrip("/")
        candidates = [f"{base}/v1/models", f"{base}/models"]
        headers = {"Accept": "application/json"}
        if payload.api_key:
            headers["Authorization"] = f"Bearer {payload.api_key}"

        last_error: Optional[str] = None
        for url in candidates:
            try:
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=8) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                data = _json.loads(body)
                raw = data.get("data") if isinstance(data, dict) else data
                if not isinstance(raw, list):
                    last_error = "Unexpected response shape"
                    continue
                ids: List[str] = []
                for item in raw:
                    if isinstance(item, dict):
                        val = item.get("id") or item.get("name")
                        if isinstance(val, str) and val:
                            ids.append(val)
                    elif isinstance(item, str):
                        ids.append(item)
                return DiscoverModelsResponse(models=sorted(set(ids)), base_url=base)
            except urllib.error.HTTPError as exc:
                last_error = f"HTTP {exc.code}"
                if exc.code == 404:
                    continue
                break
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = str(exc.reason if hasattr(exc, "reason") else exc)
                break
            except (ValueError, _json.JSONDecodeError) as exc:
                last_error = f"Invalid JSON: {exc}"
                break
        return DiscoverModelsResponse(models=[], base_url=base, error=last_error or "Unable to fetch models")

    class FormatCodeRequest(BaseModel):
        code: str

    class FormatCodeResponse(BaseModel):
        code: str
        changed: bool
        error: Optional[str] = None

    @app.post("/format-code", response_model=FormatCodeResponse)
    def format_code(payload: FormatCodeRequest) -> FormatCodeResponse:
        """Format Python code using ruff."""
        import subprocess
        import tempfile

        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(payload.code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["ruff", "format", tmp_path],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return FormatCodeResponse(code=payload.code, changed=False, error=result.stderr.strip())
            with open(tmp_path, "r") as f:
                formatted = f.read()
            import os
            os.unlink(tmp_path)
            return FormatCodeResponse(code=formatted, changed=formatted != payload.code)
        except FileNotFoundError:
            return FormatCodeResponse(code=payload.code, changed=False, error="ruff is not installed on the server")
        except subprocess.TimeoutExpired:
            return FormatCodeResponse(code=payload.code, changed=False, error="Formatting timed out")
        except Exception as exc:
            return FormatCodeResponse(code=payload.code, changed=False, error=str(exc))

    @app.post("/validate-code", response_model=ValidateCodeResponse)
    def validate_code(payload: ValidateCodeRequest) -> ValidateCodeResponse:
        """Validate signature and metric code before job submission.

        Parses signature code, checks field/mapping compatibility, parses
        metric code, and runs the metric on a sample row to verify it works.
        """
        from ..service_gateway.data import (
            extract_signature_fields,
            load_metric_from_code,
            load_signature_from_code,
        )
        import dspy

        errors: list[str] = []
        warnings: list[str] = []
        sig_fields: dict[str, list[str]] | None = None

        if not payload.signature_code and not payload.metric_code:
            errors.append("Provide signature_code and/or metric_code to validate.")

        # 1. Validate signature code (if provided)
        if payload.signature_code:
            try:
                signature_cls = load_signature_from_code(payload.signature_code)
                inputs, outputs = extract_signature_fields(signature_cls)
                sig_fields = {"inputs": inputs, "outputs": outputs}
            except ServiceError as exc:
                errors.append(str(exc))
            except Exception as exc:
                errors.append(f"Signature error: {exc}")

            # 2. Check signature fields match column mapping
            if sig_fields:
                missing_inputs = set(sig_fields["inputs"]) - set(payload.column_mapping.inputs.keys())
                missing_outputs = set(sig_fields["outputs"]) - set(payload.column_mapping.outputs.keys())
                if missing_inputs:
                    errors.append(
                        f"Signature input fields not mapped to columns: {sorted(missing_inputs)}. "
                        f"Mapped input columns: {sorted(payload.column_mapping.inputs.keys())}"
                    )
                if missing_outputs:
                    errors.append(
                        f"Signature output fields not mapped to columns: {sorted(missing_outputs)}. "
                        f"Mapped output columns: {sorted(payload.column_mapping.outputs.keys())}"
                    )
                extra_inputs = set(payload.column_mapping.inputs.keys()) - set(sig_fields["inputs"])
                extra_outputs = set(payload.column_mapping.outputs.keys()) - set(sig_fields["outputs"])
                if extra_inputs:
                    warnings.append(
                        f"Input columns not in Signature (will be ignored): {sorted(extra_inputs)}"
                    )
                if extra_outputs:
                    warnings.append(
                        f"Output columns not in Signature (will be ignored): {sorted(extra_outputs)}"
                    )

        # 3. Validate metric code (if provided)
        metric_fn = None
        metric_errors_before = len(errors)
        if payload.metric_code:
            try:
                metric_fn = load_metric_from_code(payload.metric_code)
            except ServiceError as exc:
                errors.append(str(exc))
            except Exception as exc:
                errors.append(f"Metric error: {exc}")

            # 3b. GEPA metrics must accept 5 parameters: (gold, pred, trace, pred_name, pred_trace)
            if metric_fn and payload.optimizer_name == "gepa":
                import inspect
                sig = inspect.signature(metric_fn)
                params = list(sig.parameters.values())
                if len(params) < 5:
                    param_names = [p.name for p in params]
                    errors.append(
                        f"GEPA metric must accept 5 arguments: (gold, pred, trace, pred_name, pred_trace). "
                        f"Found {len(params)}: ({', '.join(param_names)}). "
                        f"See https://dspy.ai/api/optimizers/GEPA for details."
                    )

            # 4. Run the metric on a sample (uses mapping keys, doesn't require signature)
            metric_has_errors = len(errors) > metric_errors_before
            if metric_fn and payload.sample_row and not metric_has_errors:
                try:
                    mapping = payload.column_mapping
                    ex_data: dict = {}
                    for sig_field, col_name in mapping.inputs.items():
                        ex_data[sig_field] = payload.sample_row.get(col_name, "")
                    for sig_field, col_name in mapping.outputs.items():
                        ex_data[sig_field] = payload.sample_row.get(col_name, "")
                    example = dspy.Example(**ex_data).with_inputs(*mapping.inputs.keys())
                    pred = dspy.Prediction(**ex_data)

                    result = metric_fn(example, pred, trace=None)
                    is_gepa = payload.optimizer_name == "gepa"
                    if result is None:
                        errors.append(
                            "Metric returned None. "
                            + ("GEPA requires dspy.Prediction with score and feedback fields." if is_gepa
                               else "Expected a numeric (float) or boolean return value.")
                        )
                    elif isinstance(result, dspy.Prediction) and hasattr(result, "score"):
                        if not is_gepa:
                            errors.append(
                                "Metric returns dspy.Prediction but the selected optimizer requires a numeric (float/bool) return value."
                            )
                    elif isinstance(result, (int, float, bool)):
                        if is_gepa:
                            errors.append(
                                "GEPA requires the metric to return dspy.Prediction(score=..., feedback=...), "
                                "not a numeric value."
                            )
                    else:
                        errors.append(
                            f"Metric returned {type(result).__name__}. "
                            + ("GEPA requires dspy.Prediction with score and feedback fields." if is_gepa
                               else "Expected a numeric (float) or boolean return value.")
                        )
                except Exception as exc:
                    errors.append(f"Error running metric on sample row: {exc}")

        return ValidateCodeResponse(
            valid=len(errors) == 0,
            signature_fields=sig_fields,
            errors=errors,
            warnings=warnings,
        )

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
            raise HTTPException(status_code=400, detail=str(exc))

        job_id = str(uuid4())

        job_store.create_job(job_id)
        job_store.set_payload_overview(
            job_id,
            {
                PAYLOAD_OVERVIEW_JOB_TYPE: JOB_TYPE_RUN,
                PAYLOAD_OVERVIEW_NAME: payload.name,
                PAYLOAD_OVERVIEW_USERNAME: payload.username,
                PAYLOAD_OVERVIEW_MODULE_NAME: payload.module_name,
                PAYLOAD_OVERVIEW_MODULE_KWARGS: dict(payload.module_kwargs),
                PAYLOAD_OVERVIEW_OPTIMIZER_NAME: payload.optimizer_name,
                PAYLOAD_OVERVIEW_MODEL_NAME: payload.model_settings.normalized_identifier(),
                PAYLOAD_OVERVIEW_MODEL_SETTINGS: _strip_api_key(payload.model_settings.model_dump()),
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

        notify_job_started(
            job_id=job_id,
            username=payload.username,
            job_type=JOB_TYPE_RUN,
            optimizer_name=payload.optimizer_name,
            module_name=payload.module_name,
            model_name=payload.model_settings.normalized_identifier(),
        )

        return JobSubmissionResponse(
            job_id=job_id,
            job_type=JOB_TYPE_RUN,
            status=JobStatus.pending,
            created_at=datetime.now(timezone.utc),
            name=payload.name,
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
                raise HTTPException(status_code=400, detail=str(exc))

        job_id = str(uuid4())
        total_pairs = len(payload.generation_models) * len(payload.reflection_models)

        job_store.create_job(job_id)
        job_store.set_payload_overview(
            job_id,
            {
                PAYLOAD_OVERVIEW_JOB_TYPE: JOB_TYPE_GRID_SEARCH,
                PAYLOAD_OVERVIEW_NAME: payload.name,
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

        notify_job_started(
            job_id=job_id,
            username=payload.username,
            job_type=JOB_TYPE_GRID_SEARCH,
            optimizer_name=payload.optimizer_name,
            module_name=payload.module_name,
            model_name=f"{total_pairs} זוגות",
        )

        return JobSubmissionResponse(
            job_id=job_id,
            job_type=JOB_TYPE_GRID_SEARCH,
            status=JobStatus.pending,
            created_at=datetime.now(timezone.utc),
            name=payload.name,
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

    # ── Server-Sent Events (SSE) for real-time dashboard streaming ──
    # NOTE: Must be registered BEFORE /jobs/{job_id} to avoid route shadowing.

    @app.get("/jobs/stream")
    async def stream_dashboard():
        """Stream dashboard-level updates via Server-Sent Events.

        Sends a JSON event every 3 seconds with a summary of all active jobs.
        Sends an 'idle' event and closes when no active jobs remain.
        """
        import asyncio
        import json

        async def event_generator():
            while True:
                active_rows = []
                for s in ("pending", "validating", "running"):
                    active_rows.extend(
                        job_store.list_jobs(status=s, limit=100)
                    )

                summaries = []
                for row in active_rows:
                    overview = parse_overview(row)
                    summaries.append({
                        "job_id": row["job_id"],
                        "status": row.get("status", "pending"),
                        "name": overview.get(PAYLOAD_OVERVIEW_NAME),
                        "latest_metrics": row.get("latest_metrics", {}),
                        "log_count": job_store.get_log_count(row["job_id"]),
                        "progress_count": job_store.get_progress_count(row["job_id"]),
                    })

                yield f"data: {json.dumps({'active_jobs': summaries, 'active_count': len(summaries)}, default=str)}\n\n"

                if len(summaries) == 0:
                    yield f"event: idle\ndata: {json.dumps({'active_count': 0})}\n\n"
                    return

                await asyncio.sleep(3)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

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
        job_store.update_job(job_id, status="cancelled", message="בוטל על ידי המשתמש", completed_at=now)
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

    # ── Job metadata endpoints (rename, pin, archive) ──

    class RenameRequest(BaseModel):
        name: str

    @app.patch("/jobs/{job_id}/name", status_code=200)
    def rename_job(job_id: str, req: RenameRequest) -> dict:
        """Update the display name of a job."""
        try:
            job_data = job_store.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found.")
        overview = parse_overview(job_data)
        overview[PAYLOAD_OVERVIEW_NAME] = req.name.strip()
        job_store.set_payload_overview(job_id, overview)
        return {"job_id": job_id, "name": req.name.strip()}

    @app.patch("/jobs/{job_id}/pin", status_code=200)
    def toggle_pin_job(job_id: str) -> dict:
        """Toggle the pinned state of a job."""
        try:
            job_data = job_store.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found.")
        overview = parse_overview(job_data)
        current = overview.get("pinned", False)
        overview["pinned"] = not current
        job_store.set_payload_overview(job_id, overview)
        return {"job_id": job_id, "pinned": not current}

    @app.patch("/jobs/{job_id}/archive", status_code=200)
    def toggle_archive_job(job_id: str) -> dict:
        """Toggle the archived state of a job."""
        try:
            job_data = job_store.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found.")
        overview = parse_overview(job_data)
        current = overview.get("archived", False)
        overview["archived"] = not current
        job_store.set_payload_overview(job_id, overview)
        return {"job_id": job_id, "archived": not current}

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

    # ── Server-Sent Events (SSE) for real-time job streaming ──

    @app.get("/jobs/{job_id}/stream")
    async def stream_job(job_id: str):
        """Stream job status updates via Server-Sent Events.

        Sends a JSON event every 2 seconds with the current job state.
        Stops when the job reaches a terminal status. Returns 404 for
        nonexistent jobs before opening the stream.

        Args:
            job_id: The job identifier to stream.

        Returns:
            StreamingResponse: SSE stream of job status updates.

        Raises:
            HTTPException: 404 if the job does not exist.
        """
        import asyncio
        import json

        # Check job exists before opening stream
        try:
            raw = job_store.get_job(job_id)
        except KeyError:
            raw = None
        if raw is None:
            raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'.")

        terminal = {"success", "failed", "cancelled"}

        async def event_generator():
            """Yield SSE events until job completes."""
            while True:
                raw = job_store.get_job(job_id)
                if raw is None:
                    yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
                    return

                # Build a lightweight status payload
                status = raw.get("status", "pending")
                metrics = raw.get("latest_metrics", {})
                payload = {
                    "job_id": job_id,
                    "status": status,
                    "message": raw.get("message"),
                    "latest_metrics": metrics,
                    "log_count": job_store.get_log_count(job_id),
                    "progress_count": job_store.get_progress_count(job_id),
                }

                yield f"data: {json.dumps(payload, default=str)}\n\n"

                if status in terminal:
                    yield f"event: done\ndata: {json.dumps({'status': status})}\n\n"
                    return

                await asyncio.sleep(2)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Serving: run inference on optimized programs ──

    # Cache deserialized programs to avoid repeated pickle loads
    _program_cache: dict[str, Any] = {}

    def _load_program(job_id: str) -> tuple[Any, RunResponse, dict]:
        """Load and cache an optimized program from a completed job.

        Args:
            job_id: The job identifier.

        Returns:
            Tuple of (compiled_program, run_response, payload_overview).

        Raises:
            HTTPException: If job not found, not finished, or has no artifact.
        """
        import base64
        import pickle

        try:
            job_data = job_store.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'.")

        overview = parse_overview(job_data)
        job_type = overview.get(PAYLOAD_OVERVIEW_JOB_TYPE, JOB_TYPE_RUN)

        if job_type == JOB_TYPE_GRID_SEARCH:
            raise HTTPException(
                status_code=409,
                detail="Grid search jobs are not directly servable. Use the best pair's job artifact.",
            )

        status = status_to_job_status(job_data.get("status", "pending"))
        if status != JobStatus.success:
            raise HTTPException(
                status_code=409,
                detail=f"Job is '{status.value}' — only successful jobs can be served.",
            )

        result_data = job_data.get("result")
        if not result_data or not isinstance(result_data, dict):
            raise HTTPException(status_code=409, detail="Job has no result data.")

        result = RunResponse.model_validate(result_data)
        artifact = result.program_artifact
        if not artifact or not artifact.program_pickle_base64:
            raise HTTPException(status_code=409, detail="Job has no program artifact.")

        if job_id not in _program_cache:
            program_bytes = base64.b64decode(artifact.program_pickle_base64)
            _program_cache[job_id] = pickle.loads(program_bytes)  # noqa: S301

        return _program_cache[job_id], result, overview

    @app.get("/serve/{job_id}/info", response_model=ServeInfoResponse)
    def serve_info(job_id: str) -> ServeInfoResponse:
        """Return metadata about a servable program without running inference.

        Args:
            job_id: Identifier of a successful optimization job.

        Returns:
            ServeInfoResponse: Program signature and metadata.
        """
        _, result, overview = _load_program(job_id)
        artifact = result.program_artifact

        input_fields = artifact.optimized_prompt.input_fields if artifact.optimized_prompt else []
        output_fields = artifact.optimized_prompt.output_fields if artifact.optimized_prompt else []
        instructions = artifact.optimized_prompt.instructions if artifact.optimized_prompt else None
        demo_count = len(artifact.optimized_prompt.demos) if artifact.optimized_prompt else 0

        return ServeInfoResponse(
            job_id=job_id,
            module_name=overview.get(PAYLOAD_OVERVIEW_MODULE_NAME, ""),
            optimizer_name=overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_NAME, ""),
            model_name=overview.get(PAYLOAD_OVERVIEW_MODEL_NAME, ""),
            input_fields=input_fields,
            output_fields=output_fields,
            instructions=instructions,
            demo_count=demo_count,
        )

    @app.post("/serve/{job_id}", response_model=ServeResponse)
    def serve_program(job_id: str, req: ServeRequest) -> ServeResponse:
        """Run inference on an optimized program.

        Deserializes the program artifact, configures the LM, and calls
        the program with the provided inputs.

        Args:
            job_id: Identifier of a successful optimization job.
            req: Input fields and optional model config override.

        Returns:
            ServeResponse: Program outputs.
        """
        import dspy

        from ..service_gateway.language_models import build_language_model

        program, result, overview = _load_program(job_id)
        artifact = result.program_artifact

        # Determine model config
        if req.model_config_override:
            model_config = req.model_config_override
        else:
            model_settings = overview.get(PAYLOAD_OVERVIEW_MODEL_SETTINGS, {})
            model_name = overview.get(PAYLOAD_OVERVIEW_MODEL_NAME, "")
            if model_settings:
                model_config = ModelConfig.model_validate(model_settings)
            elif model_name:
                model_config = ModelConfig(name=model_name)
            else:
                raise HTTPException(
                    status_code=400,
                    detail="No model config found for this job. Provide model_config_override.",
                )

        # Validate input fields
        input_fields = artifact.optimized_prompt.input_fields if artifact.optimized_prompt else []
        output_fields = artifact.optimized_prompt.output_fields if artifact.optimized_prompt else []

        if input_fields:
            missing = [f for f in input_fields if f not in req.inputs]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required input fields: {missing}. Expected: {input_fields}",
                )

        # Build LM and run inference
        lm = build_language_model(model_config)

        with dspy.context(lm=lm):
            prediction = program(**req.inputs)

        # Extract outputs
        outputs: dict[str, Any] = {}
        if output_fields:
            for field in output_fields:
                outputs[field] = getattr(prediction, field, None)
        else:
            # Prediction fields live in its mapping API, not dir()
            for key, val in prediction.toDict().items():
                if key not in req.inputs:
                    outputs[key] = val

        return ServeResponse(
            job_id=job_id,
            outputs=outputs,
            input_fields=input_fields,
            output_fields=output_fields,
            model_used=model_config.normalized_identifier(),
        )

    @app.post("/serve/{job_id}/stream")
    async def serve_program_stream(job_id: str, req: ServeRequest):
        """Stream inference outputs token-by-token via Server-Sent Events.

        Uses ``dspy.streamify`` to wrap the loaded program with stream listeners
        for each output field, then emits SSE events:

        - ``event: token`` — ``{"field": str, "chunk": str}`` per partial token
        - ``event: final`` — ``{"outputs": {...}, "model_used": str}`` at the end
        - ``event: error`` — ``{"error": str}`` on failure

        Args:
            job_id: Identifier of a successful optimization job.
            req: Input fields and optional model config override.

        Returns:
            StreamingResponse: SSE stream of streaming events.
        """
        import asyncio
        import json

        import dspy
        from dspy.streaming import StreamListener, StreamResponse

        from ..service_gateway.language_models import build_language_model

        program, result, overview = _load_program(job_id)
        artifact = result.program_artifact

        # Determine model config (same logic as /serve/{job_id})
        if req.model_config_override:
            model_config = req.model_config_override
        else:
            model_settings = overview.get(PAYLOAD_OVERVIEW_MODEL_SETTINGS, {})
            model_name = overview.get(PAYLOAD_OVERVIEW_MODEL_NAME, "")
            if model_settings:
                model_config = ModelConfig.model_validate(model_settings)
            elif model_name:
                model_config = ModelConfig(name=model_name)
            else:
                raise HTTPException(
                    status_code=400,
                    detail="No model config found for this job. Provide model_config_override.",
                )

        input_fields = artifact.optimized_prompt.input_fields if artifact.optimized_prompt else []
        output_fields = artifact.optimized_prompt.output_fields if artifact.optimized_prompt else []

        if input_fields:
            missing = [f for f in input_fields if f not in req.inputs]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required input fields: {missing}. Expected: {input_fields}",
                )

        lm = build_language_model(model_config)
        model_used = model_config.normalized_identifier()
        listeners = [StreamListener(signature_field_name=f) for f in output_fields]

        async def event_generator():
            def sse(event: str, payload: dict) -> str:
                return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"
            try:
                final_outputs: dict[str, Any] = {}
                try:
                    stream_program = dspy.streamify(
                        program,
                        stream_listeners=listeners,
                        async_streaming=True,
                    )
                    with dspy.context(lm=lm):
                        output_stream = stream_program(**req.inputs)
                        async for item in output_stream:
                            if isinstance(item, StreamResponse):
                                yield sse("token", {"field": item.signature_field_name, "chunk": item.chunk})
                            elif isinstance(item, dspy.Prediction):
                                if output_fields:
                                    for field in output_fields:
                                        final_outputs[field] = getattr(item, field, None)
                                else:
                                    for key, val in item.toDict().items():
                                        if key not in req.inputs:
                                            final_outputs[key] = val
                    yield sse("final", {
                        "outputs": final_outputs,
                        "input_fields": input_fields,
                        "output_fields": output_fields,
                        "model_used": model_used,
                    })
                    return
                except Exception as stream_exc:  # noqa: BLE001
                    # Fall back to non-streaming: some modules/fields aren't streamable
                    with dspy.context(lm=lm):
                        prediction = await asyncio.to_thread(lambda: program(**req.inputs))
                    if output_fields:
                        for field in output_fields:
                            final_outputs[field] = getattr(prediction, field, None)
                    else:
                        for key, val in prediction.toDict().items():
                            if key not in req.inputs:
                                final_outputs[key] = val
                    yield sse("final", {
                        "outputs": final_outputs,
                        "input_fields": input_fields,
                        "output_fields": output_fields,
                        "model_used": model_used,
                        "streaming_fallback": True,
                        "fallback_reason": str(stream_exc),
                    })
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                yield sse("error", {"error": "streaming failed"})
                logger = logging.getLogger(__name__)
                logger.exception("Serve stream failed for job %s: %s", job_id, exc)
                return
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Job Templates (reusable configurations) ──

    from ..storage.local import TemplateModel, Base as StorageBase

    # Ensure template table exists
    StorageBase.metadata.create_all(job_store.engine)

    @app.post("/templates", response_model=TemplateResponse, status_code=201)
    def create_template(req: TemplateCreateRequest) -> TemplateResponse:
        """Save a reusable job configuration template."""
        from sqlalchemy.orm import Session

        template_id = str(uuid4())
        now = datetime.now(timezone.utc)

        with Session(job_store.engine) as session:
            model = TemplateModel(
                template_id=template_id,
                name=req.name.strip(),
                description=req.description,
                username=req.username,
                config=req.config,
                created_at=now,
            )
            session.add(model)
            session.commit()

        return TemplateResponse(
            template_id=template_id,
            name=req.name.strip(),
            description=req.description,
            username=req.username,
            config=req.config,
            created_at=now,
        )

    @app.get("/templates", response_model=List[TemplateResponse])
    def list_templates(
        username: Optional[str] = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> List[TemplateResponse]:
        """List templates with optional filtering and pagination."""
        from sqlalchemy.orm import Session

        with Session(job_store.engine) as session:
            query = session.query(TemplateModel).order_by(TemplateModel.created_at.desc())
            if username:
                query = query.filter(TemplateModel.username == username)
            rows = query.offset(offset).limit(limit).all()
            return [
                TemplateResponse(
                    template_id=r.template_id,
                    name=r.name,
                    description=r.description,
                    username=r.username,
                    config=r.config,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    @app.get("/templates/{template_id}", response_model=TemplateResponse)
    def get_template(template_id: str) -> TemplateResponse:
        """Retrieve a single template."""
        from sqlalchemy.orm import Session

        with Session(job_store.engine) as session:
            row = session.query(TemplateModel).filter(
                TemplateModel.template_id == template_id
            ).first()
            if not row:
                raise HTTPException(status_code=404, detail="Template not found.")
            return TemplateResponse(
                template_id=row.template_id,
                name=row.name,
                description=row.description,
                username=row.username,
                config=row.config,
                created_at=row.created_at,
            )

    @app.delete("/templates/{template_id}", status_code=200)
    def delete_template(
        template_id: str,
        username: str = Query(..., description="Owner username for authorization"),
    ) -> dict:
        """Delete a template (only the owner can delete)."""
        from sqlalchemy.orm import Session

        with Session(job_store.engine) as session:
            row = session.query(TemplateModel).filter(
                TemplateModel.template_id == template_id
            ).first()
            if not row:
                raise HTTPException(status_code=404, detail="Template not found.")
            if row.username != username:
                raise HTTPException(status_code=403, detail="You can only delete your own templates.")
            session.delete(row)
            session.commit()
        return {"template_id": template_id, "deleted": True}

    return app
