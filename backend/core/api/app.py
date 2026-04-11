"""FastAPI application factory for Skynet.

This module now contains *only* the app-lifecycle concerns:

* DI wiring (``ServiceRegistry`` + ``DspyService`` + ``job_store``)
* Background worker lifespan + SIGTERM handling
* CORS middleware + cache headers
* Consistent JSON error response shape
* Two "infra" endpoints that reference the worker directly: ``/health``
  and ``/queue``
* Scalar API reference mounted at ``/scalar`` with air-gapped static assets

Every other route has been extracted into ``backend/core/api/routers/``
and wired up via ``app.include_router``. See ``AGENTS.md`` for the
extraction rules.
"""
from __future__ import annotations

import logging
import os
import signal  # [WORKER-FIX] for SIGTERM graceful shutdown
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Iterable, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from scalar_fastapi import AgentScalarConfig, DocumentDownloadType, get_scalar_api_reference

from ..exceptions import AppError
from ..models import HEALTH_STATUS_OK, HealthResponse, QueueStatusResponse
from ..registry import ServiceRegistry
from ..service_gateway import DspyService
from ..storage import get_job_store
from ..worker import BackgroundWorker, get_worker
from .routers.analytics import create_analytics_router
from .routers.code_validation import create_code_validation_router
from .routers.models import create_models_router
from .routers.optimizations import create_optimizations_router
from .routers.optimizations_meta import create_optimizations_meta_router
from .routers.serve import create_serve_router
from .routers.submissions import create_submissions_router
from .routers.templates import create_templates_router

logger = logging.getLogger(__name__)

_SCALAR_STATIC_DIR = Path(__file__).parent / "static" / "scalar"

_OPENAPI_TAGS = [
    {"name": "Optimizations", "description": "Submit, list, inspect, and manage DSPy optimization jobs."},
    {"name": "Inference", "description": "Run inference against an optimized program."},
    {"name": "Analytics", "description": "Aggregate stats across jobs, optimizers, and models."},
    {"name": "Models", "description": "Model catalog and provider discovery."},
    {"name": "Templates", "description": "Save and reuse job configuration templates."},
    {"name": "Code Validation", "description": "Format and validate user-supplied Python code."},
    {"name": "System", "description": "Health and queue status for readiness probes."},
]


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
        worker = get_worker(job_store, service=service, pending_optimization_ids=pending_ids)
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

    app = FastAPI(
        title="Skynet",
        lifespan=lifespan,
        openapi_tags=_OPENAPI_TAGS,
        servers=[{"url": "/", "description": "This server"}],
    )

    app.mount(
        "/scalar-static",
        StaticFiles(directory=_SCALAR_STATIC_DIR),
        name="scalar-static",
    )

    @app.get("/scalar", include_in_schema=False)
    async def scalar_docs() -> HTMLResponse:
        return get_scalar_api_reference(
            openapi_url=app.openapi_url,
            title=f"{app.title} API",
            scalar_js_url="/scalar-static/standalone.js",
            agent=AgentScalarConfig(disabled=True),
            telemetry=False,
            document_download_type=DocumentDownloadType.NONE,
            persist_auth=True,
            default_open_all_tags=False,
            dark_mode=False,
            # Hide Scalar's "Generate MCP" / "Connect MCP" sidebar block.
            # scalar-fastapi has no dedicated flag for this yet, and the
            # MCP feature has no use in an air-gapped deployment.
            custom_css=".scalar-mcp-layer { display: none !important; }",
        )

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

    @app.exception_handler(AppError)
    async def _app_error_handler(
        request: Request, exc: AppError
    ) -> JSONResponse:
        """Handle domain exceptions raised by services.

        Converts AppError instances into consistent JSON responses that match
        the existing error envelope format used throughout the API.
        """
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error_code.lower(), "detail": exc.message},
        )

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

    @app.exception_handler(Exception)
    async def _generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all handler for unhandled exceptions to prevent info disclosure.

        Logs the full exception with stack trace while returning a safe generic
        error response to the client. Prevents leaking DB credentials, file paths,
        API keys, or internal implementation details.

        Args:
            request: Incoming HTTP request that triggered the exception.
            exc: Unhandled exception instance.

        Returns:
            JSONResponse: Generic 500 error response with no sensitive details.
        """
        logger.error(
            "Unhandled exception in %s %s: %s",
            request.method,
            request.url.path,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "detail": "An internal server error occurred. Please contact support.",
            },
        )

    # [WORKER-FIX] max seconds of no worker activity before health check flags it
    WORKER_STALE_THRESHOLD = float(os.getenv("WORKER_STALE_THRESHOLD", "600"))

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["System"],
        summary="Liveness and readiness probe",
    )
    def healthcheck() -> HealthResponse:
        """Return a snapshot of registered assets and background-worker health.

        Used by OpenShift / Kubernetes liveness + readiness probes and by the
        frontend's connection indicator. Returns HTTP 200 with a snapshot of
        every asset the ``ServiceRegistry`` knows about when the worker pool
        is healthy.

        Behavior:
            - Returns 503 if no worker exists or if all worker threads have died.
            - Returns 503 if worker threads are alive but idle for longer than
              ``WORKER_STALE_THRESHOLD`` seconds (default 600), which indicates
              the pool is stuck (e.g. a thread deadlocked inside a subprocess).
            - The response body is never cached by the frontend — stale data
              would defeat the point of the probe.
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

    @app.middleware("http")
    async def add_cache_headers(request: Request, call_next):
        """Add Cache-Control headers to cacheable GET endpoints."""
        response = await call_next(request)
        path = request.url.path
        if request.method == "GET":
            if path == "/models":
                # Model catalog is static per process lifetime
                response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=600"
            elif path == "/health":
                response.headers["Cache-Control"] = "no-cache, max-age=0"
            elif path == "/queue":
                # Queue status is semi-dynamic — cache briefly
                response.headers["Cache-Control"] = "private, max-age=5"
            elif path == "/optimizations" and "status" not in str(request.url.query):
                # Job list without status filter — cache briefly
                response.headers["Cache-Control"] = "private, max-age=2, stale-while-revalidate=10"
        return response

    @app.get(
        "/queue",
        response_model=QueueStatusResponse,
        tags=["System"],
        summary="Current worker queue depth and health",
    )
    def get_queue_status() -> QueueStatusResponse:
        """Return a point-in-time snapshot of the background-job queue.

        Reports how many optimization jobs are pending (waiting to run), how
        many are actively executing, how many worker threads are configured,
        and whether those threads are alive. Used by the frontend's queue
        chip/header and by `/analytics/summary` callers who want to detect
        backlog buildup.

        If no worker has been started yet (e.g. the lifespan hook hasn't run),
        the response contains all zeros with ``workers_alive=False`` instead
        of an error — callers polling at startup get a stable shape.

        Response is cached for 5 seconds to keep this endpoint cheap under
        aggressive polling from the UI.
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

    # ── Domain routers ──
    # Every route except /health and /queue lives in a sub-module under
    # routers/. Each exposes a create_<domain>_router factory returning an
    # APIRouter wired up with the dependencies it needs. Tags are applied
    # here so the OpenAPI spec (and Scalar) groups routes consistently
    # without touching the router files themselves.
    app.include_router(create_models_router(), tags=["Models"])
    app.include_router(create_code_validation_router(), tags=["Code Validation"])
    app.include_router(
        create_submissions_router(service=service, job_store=job_store),
        tags=["Optimizations"],
    )
    app.include_router(create_analytics_router(job_store=job_store), tags=["Analytics"])
    app.include_router(
        create_optimizations_router(job_store=job_store, get_worker_ref=lambda: worker),
        tags=["Optimizations"],
    )
    app.include_router(create_serve_router(job_store=job_store), tags=["Inference"])
    app.include_router(create_templates_router(job_store=job_store), tags=["Templates"])
    app.include_router(
        create_optimizations_meta_router(job_store=job_store),
        tags=["Optimizations"],
    )

    return app
