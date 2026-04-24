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
from collections.abc import Iterable
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from scalar_fastapi import AgentScalarConfig, DocumentDownloadType, get_scalar_api_reference

from ..exceptions import AppError
from ..i18n import t
from ..models import HEALTH_STATUS_OK, HealthResponse, QueueStatusResponse
from ..registry import ServiceRegistry
from ..service_gateway import DspyService
from ..storage import get_job_store
from ..worker import BackgroundWorker, get_worker
from .mcp_mount import mount_mcp_on_app
from .routers.analytics import create_analytics_router
from .routers.code_agent import create_code_agent_router
from .routers.code_validation import create_code_validation_router
from .routers.datasets import create_datasets_router
from .routers.generalist_agent import create_generalist_agent_router
from .routers.models import create_models_router
from .routers.optimizations import create_optimizations_router
from .routers.optimizations_meta import create_optimizations_meta_router
from .routers.dashboard import create_dashboard_router
from .routers.recommendations import create_recommendations_router
from .routers.registry import create_registry_router
from .routers.serve import create_serve_router
from .routers.submissions import create_submissions_router
from .routers.templates import create_templates_router
from .routers.wizard import create_wizard_router

logger = logging.getLogger(__name__)

_SCALAR_STATIC_DIR = Path(__file__).parent / "static" / "scalar"

# Routes that should be hidden from the *public* API reference shown by
# Scalar. These are still live and still in /openapi.json — the filter
# is applied only to the copy served at /openapi.public.json, which is
# what Scalar fetches. The cut is aimed at developers integrating with
# Skynet: submit jobs, poll, download artifacts, run inference, done.
# Hidden routes fall into three categories:
#   1. Frontend plumbing (sidebar lists, SSE streams, dataset reshuffle,
#      code formatter, analytics dashboards, template CRUD)
#   2. Redundant per-example readers whose data is already in
#      /optimizations/{id} and /optimizations/{id}/grid-result
#   3. Dashboard-only mutations (rename, pin, archive toggles, per-user
#      evaluate-examples playground)
_SCALAR_HIDDEN_PATHS = frozenset(
    {
        # Dashboard plumbing
        "/optimizations/sidebar",
        "/optimizations/counts",
        "/optimizations/bulk-delete",
        "/optimizations/{optimization_id}/name",
        "/optimizations/{optimization_id}/pin",
        "/optimizations/{optimization_id}/archive",
        "/optimizations/{optimization_id}/payload",
        "/optimizations/{optimization_id}/evaluate-examples",
        "/optimizations/{optimization_id}/dataset",
        "/optimizations/{optimization_id}/pair/{pair_index}",
        "/optimizations/{optimization_id}/pair/{pair_index}/test-results",
        # SSE streams (frontend real-time updates)
        "/optimizations/stream",
        "/optimizations/{optimization_id}/stream",
        "/optimizations/ai-generate-code",
        "/optimizations/generalist-agent",
        "/optimizations/generalist-agent/confirm",
        "/serve/{optimization_id}/stream",
        "/serve/{optimization_id}/pair/{pair_index}/stream",
        # Grid-pair-level serve (too granular for public docs)
        "/serve/{optimization_id}/pair/{pair_index}",
        "/serve/{optimization_id}/pair/{pair_index}/info",
        # Analytics (dashboard-only aggregations)
        "/analytics/summary",
        "/analytics/optimizers",
        "/analytics/models",
        "/analytics/dashboard",
        # Internal tools
        "/models/discover",
        "/format-code",
        "/templates",
        "/templates/{template_id}",
        "/wizard/update",
    }
)

# Custom CSS for Scalar that (a) hides UI chrome we don't want in an
# air-gapped deployment, (b) renders the Skynet logo next to the API
# title, and (c) retints the reference in the same warm beige/brown
# palette as the main app (see frontend/src/app/globals.css light mode).
_SCALAR_CUSTOM_CSS = """
/* Hide Generate/Connect MCP sidebar block — no-op in air-gapped mode */
.scalar-mcp-layer { display: none !important; }

/* Hide all toolbar popover buttons (Share, Deploy, Configure, Developer Tools).
   HeadlessUI IDs are dynamic, so match the stable prefix. */
[id^="headlessui-popover-button"] { display: none !important; }

/* Hide the version + OAS chips and the "Skynet" h1 from the intro */
.introduction-section .badge,
.introduction-section .section-header-label {
  display: none !important;
}

/* Sidebar: hide "Introduction" link (visible at page top anyway)
   and the auto-generated "Models" schemas section (duplicate of the
   tagged Models group — devs see schemas inline per endpoint). */
[data-sidebar-id="api-1/description/introduction"],
[data-sidebar-id="api-1/models"] {
  display: none !important;
}

/* Animate sidebar group expand/collapse — chevron rotates and
   child list slides open with height transition. */
.group\/group-button > button .size-4 {
  transition: transform 200ms cubic-bezier(0.4, 0, 0.2, 1);
}
.group\/group-button > button[aria-expanded="true"] .size-4 {
  transform: rotate(90deg);
}
.group\/group-button + ul,
.group\/group-button + div {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 250ms cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}
.group\/group-button > button[aria-expanded="true"] ~ ul,
.group\/group-button > button[aria-expanded="true"] ~ div {
  grid-template-rows: 1fr;
}
.group\/group-button + ul > *,
.group\/group-button + div > * {
  min-height: 0;
}

/* Hide "Powered by Scalar" footer and dark mode toggle in sidebar */
.t-doc__sidebar [href*="scalar.com"],
.t-doc__sidebar [href*="scalar.com"] ~ button,
.t-doc__header [href*="scalar.com"],
.t-doc__header [href*="scalar.com"] ~ button {
  display: none !important;
}

/* Remove the empty client-libraries / server-url bar above the
   description so the intro paragraph sits higher on the page. */
.introduction-section .custom-scroll {
  display: none !important;
}
.introduction-section .section-column {
  padding-top: 0 !important;
}
.introduction-section {
  padding-top: 16px !important;
  gap: 0 !important;
}

/* ── Toolbar brand button ─────────────────────────────────────────
   The brand button sits in the top-left of the toolbar. When the
   sidebar is hidden, hovering the button fades the SKYNET wordmark
   out and reveals a sidebar-toggle icon in the same spot — click to
   open. When the sidebar is open, the brand button is hidden entirely
   (the wordmark + close button move into the sidebar header instead).
   This mirrors chatgpt.com's sidebar UX. */
.api-reference-toolbar {
  position: sticky !important;
  top: 0;
  z-index: 40;
}

.skynet-toolbar-brand {
  position: absolute;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  height: 32px;
  width: 40px;
  padding: 0 8px;
  border: 0;
  background: transparent;
  color: #3D2E22;
  cursor: pointer;
  border-radius: 8px;
  transition: background-color 140ms ease;
  overflow: visible;
}
.skynet-toolbar-brand:hover { background: #f0ebe4; }
.skynet-toolbar-brand:focus-visible {
  outline: 2px solid #3D2E22;
  outline-offset: 2px;
}

.skynet-toolbar-brand .skynet-wordmark,
.skynet-toolbar-brand .skynet-toolbar-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  transition: opacity 200ms ease;
}
.skynet-toolbar-brand .skynet-toolbar-icon {
  opacity: 0;
  pointer-events: none;
}
.skynet-wordmark { color: #3D2E22; user-select: none; }
.skynet-wordmark svg { overflow: visible; }

/* Hover swap is only meaningful while the sidebar can still be opened */
html[data-skynet-sidebar="hidden"] .skynet-toolbar-brand:hover .skynet-wordmark {
  opacity: 0;
}
html[data-skynet-sidebar="hidden"] .skynet-toolbar-brand:hover .skynet-toolbar-icon {
  opacity: 1;
}

/* When the sidebar is open, the brand moves into the sidebar header */
html[data-skynet-sidebar="visible"] .skynet-toolbar-brand {
  display: none;
}

/* ── Sidebar header (only shown while sidebar is visible) ─────────── */
.skynet-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 10px 10px 16px;
  border-bottom: 1px solid #ddd6cc;
  flex-shrink: 0;
}
html[data-skynet-sidebar="hidden"] .skynet-sidebar-header {
  display: none;
}

.skynet-sidebar-home {
  display: inline-flex;
  align-items: center;
  padding: 6px 8px;
  border-radius: 8px;
  color: #3D2E22;
  text-decoration: none;
  transition: background-color 120ms ease;
}
.skynet-sidebar-home:hover { background: #ede7dd; }
.skynet-sidebar-home:focus-visible {
  outline: 2px solid #3D2E22;
  outline-offset: 2px;
}

.skynet-sidebar-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #3D2E22;
  cursor: pointer;
  border-radius: 8px;
  transition: background-color 120ms ease;
}
.skynet-sidebar-close:hover { background: #ede7dd; }
.skynet-sidebar-close:focus-visible {
  outline: 2px solid #3D2E22;
  outline-offset: 2px;
}

/* ── Animated collapsible sidebar (desktop only) ───────────────────
   Only override Scalar's grid on viewports wide enough for the
   sidebar. Below 1024px Scalar's own responsive layout takes over. */
@media (min-width: 1024px) {
  .references-layout {
    grid-template-columns: 288px minmax(0, 1fr) !important;
    transition: grid-template-columns 320ms cubic-bezier(0.4, 0, 0.2, 1);
  }
  .t-doc__sidebar {
    min-width: 0 !important;
    transition:
      transform 320ms cubic-bezier(0.4, 0, 0.2, 1),
      opacity 220ms ease;
  }
  html[data-skynet-sidebar="hidden"] .references-layout {
    grid-template-columns: 0px minmax(0, 1fr) !important;
    overflow: hidden;
  }
  html[data-skynet-sidebar="hidden"] .t-doc__sidebar {
    transform: translateX(-100%);
    opacity: 0;
    pointer-events: none;
    width: 0 !important;
    min-width: 0 !important;
    overflow: hidden;
  }
}

/* Let the content fill the full width on wide viewports */
.scalar-api-reference {
  --refs-content-max-width: none !important;
}

/* Skynet warm-beige light theme to match the main app */
.light-mode {
  --scalar-background-1: #faf8f5;
  --scalar-background-2: #f5f1ec;
  --scalar-background-3: #f0ebe4;
  --scalar-background-accent: #ede7dd;
  --scalar-background-card: #ffffff;
  --scalar-color-1: #1c1612;
  --scalar-color-2: #5c4f42;
  --scalar-color-3: #8c7a6b;
  --scalar-color-accent: #3d2e22;
  --scalar-border-color: #ddd6cc;
}
.light-mode .t-doc__sidebar {
  --scalar-sidebar-background-1: #f5f1ec;
  --scalar-sidebar-item-hover-background: #ede7dd;
  --scalar-sidebar-item-active-background: #e3dcd0;
  --scalar-sidebar-border-color: #ddd6cc;
  --scalar-sidebar-color-1: #1c1612;
  --scalar-sidebar-color-2: #8c7a6b;
  --scalar-sidebar-color-active: #3d2e22;
  --scalar-sidebar-search-background: #ffffff;
  --scalar-sidebar-search-border-color: #ddd6cc;
  --scalar-sidebar-search--color: #8c7a6b;
}

/* ── Mobile sidebar slide animation ────────────────────────────────
   Scalar's mobile menu lives inside .t-doc__header (NOT .t-doc__sidebar).
   When the hamburger is tapped, the header expands to full screen.
   We animate that expansion with a slide-in from the left. The desktop
   .t-doc__sidebar stays hidden on mobile (Tailwind's `hidden` class). */
@media (max-width: 1023px) {
  .skynet-toolbar-brand { display: none !important; }

  .t-doc__header {
    transform-origin: left top;
    transition:
      transform 320ms cubic-bezier(0.4, 0, 0.2, 1),
      opacity 200ms ease;
  }

  /* When the mobile menu is closed, the header is just the toolbar bar */
  .references-layout:not(.references-sidebar-mobile-open) .t-doc__header {
    /* no extra styles — Scalar handles the collapsed state */
  }

  /* When open, slide in from left */
  .references-sidebar-mobile-open .t-doc__header {
    animation: skynet-slide-in 320ms cubic-bezier(0.4, 0, 0.2, 1) both;
  }
}

@keyframes skynet-slide-in {
  from {
    transform: translateX(-40px);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
@media (max-width: 768px) {
  .section-container,
  .endpoint-container {
    padding-inline: 12px !important;
  }
  .api-reference-toolbar {
    padding-inline: 8px !important;
  }
}

/* ── Cross-platform viewport adaptation ──────────────────────────
   Reserve scrollbar width on Windows (classic scrollbars) to prevent
   layout shift. On macOS overlay scrollbars this is a no-op. */
.scalar-api-reference {
  scrollbar-gutter: stable;
}

/* Fluid padding for narrow desktop windows (split-screen, snapped) */
@media (max-width: 600px) {
  .section-container,
  .endpoint-container {
    padding-inline: 8px !important;
  }
  /* Prevent code blocks from overflowing */
  pre, code {
    font-size: 12px !important;
    word-break: break-all;
  }
}

/* Sensible content width on ultrawides so lines stay readable */
@media (min-width: 1800px) {
  .scalar-api-reference {
    --refs-content-max-width: 1600px !important;
  }
}
"""

_OPENAPI_TAGS = [
    {"name": "Optimizations", "description": "Submit, list, inspect, and manage DSPy optimization jobs."},
    {"name": "Inference", "description": "Run inference against an optimized program."},
    {"name": "Analytics", "description": "Aggregate stats across jobs, optimizers, and models."},
    {"name": "Models", "description": "Model catalog and provider discovery."},
    {"name": "Datasets", "description": "Profile uploaded datasets and recommend split plans."},
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
    """Assemble and return the fully-configured FastAPI application.

    Args:
        registry: Pre-built ServiceRegistry; a new one is created if omitted.
        service: Pre-built DspyService; constructed from *registry* if omitted.
        service_kwargs: Extra kwargs forwarded to the DspyService constructor
            when *service* is not supplied.

    Returns:
        A FastAPI instance with all middleware, exception handlers, and routers
        mounted and ready to serve.
    """
    registry = registry or ServiceRegistry()
    service = service or DspyService(
        registry,
        **(service_kwargs or {}),
    )

    job_store = get_job_store()

    worker: BackgroundWorker | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
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
        # Disable FastAPI's built-in Swagger UI and ReDoc — Scalar at
        # /scalar replaces both. /openapi.json stays enabled so Scalar
        # and any other consumers can still fetch the spec.
        docs_url=None,
        redoc_url=None,
        description=(
            "Backend API for **Skynet** — a DSPy-as-a-service platform for "
            "submitting, comparing, and serving optimized language-model "
            "programs. Submit optimization runs or grid searches, stream "
            "live progress and metrics, inspect per-example baselines vs. "
            "optimized predictions, and run inference against the final "
            "compiled program. All traffic stays on your local network; "
            "this interactive reference is served directly from the "
            "running backend and works fully offline."
        ),
    )

    app.mount(
        "/scalar-static",
        StaticFiles(directory=_SCALAR_STATIC_DIR),
        name="scalar-static",
    )

    @app.get("/openapi.public.json", include_in_schema=False)
    async def public_openapi() -> JSONResponse:
        """Filtered copy of /openapi.json with hidden paths and empty tags pruned."""
        base = app.openapi()
        spec = deepcopy(base)
        paths = spec.get("paths", {})
        for path in list(paths.keys()):
            if path in _SCALAR_HIDDEN_PATHS:
                del paths[path]
        used_tags: set[str] = set()
        for methods in paths.values():
            if not isinstance(methods, dict):
                continue
            for op in methods.values():
                if isinstance(op, dict):
                    for tag in op.get("tags", []):
                        used_tags.add(tag)
        if "tags" in spec:
            spec["tags"] = [t for t in spec["tags"] if t.get("name") in used_tags]
        return JSONResponse(spec)

    @app.get("/scalar", include_in_schema=False)
    async def scalar_docs() -> HTMLResponse:
        base = get_scalar_api_reference(
            openapi_url="/openapi.public.json",
            title=f"{app.title} API",
            scalar_favicon_url="/scalar-static/favicon.svg",
            scalar_js_url="/scalar-static/standalone.js",
            agent=AgentScalarConfig(disabled=True),
            telemetry=False,
            document_download_type=DocumentDownloadType.NONE,
            persist_auth=True,
            default_open_all_tags=False,
            dark_mode=False,
            custom_css=_SCALAR_CUSTOM_CSS,
        )
        # Inject the animated wordmark script. scalar-fastapi only exposes
        # custom_css, so we append our own <script> tag just before </body>.
        html = base.body.decode("utf-8")
        script_tag = '<script src="/scalar-static/wordmark.js" defer></script>'
        html = html.replace("</body>", f"{script_tag}</body>")
        return HTMLResponse(content=html)

    allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in allowed_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # All error responses share {"error": "<type>", "detail": "..."} so
    # API consumers can write a single error handler.
    _STATUS_TO_ERROR_TYPE = {
        400: "validation_error",
        404: "not_found",
        409: "conflict",
        422: "invalid_request",
        500: "internal_error",
        503: "service_unavailable",
    }

    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error_code.lower(), "detail": exc.message},
        )

    @app.exception_handler(HTTPException)
    async def _http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        error_type = _STATUS_TO_ERROR_TYPE.get(exc.status_code, "error")
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": error_type, "detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        def _format_field(loc: Iterable[Any]) -> str:
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
        """Return registered-asset inventory and worker health for liveness/readiness probes.

        503 if workers are dead or stuck longer than ``WORKER_STALE_THRESHOLD`` seconds (default 600).
        """
        # [WORKER-FIX] return 503 if workers died so OpenShift probe detects it
        if worker is None or not worker.threads_alive():
            logger.error("Health check failed: worker threads are not alive")
            raise HTTPException(status_code=503, detail=t("health.workers_dead"))

        # [WORKER-FIX] detect threads that are alive but stuck (no activity for too long)
        stale_seconds = worker.seconds_since_last_activity()
        if stale_seconds is not None and stale_seconds > WORKER_STALE_THRESHOLD:
            stack_dump = worker.dump_thread_stacks()
            logger.error(
                "Health check failed: workers stuck for %.0fs. Thread stacks:\n%s",
                stale_seconds,
                stack_dump,
            )
            raise HTTPException(
                status_code=503,
                detail=t("health.workers_stuck", seconds=f"{stale_seconds:.0f}"),
            )

        snapshot = registry.snapshot()
        logger.debug("Health check requested; registered assets: %s", snapshot)
        return HealthResponse(status=HEALTH_STATUS_OK, registered_assets=snapshot)

    @app.middleware("http")
    async def add_cache_headers(request: Request, call_next):
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
        """Return pending/active job counts and worker-thread health.

        All counts are zero before the lifespan context starts.

        Returns:
            QueueStatusResponse with current queue depth and worker state.
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

    app.include_router(create_models_router(), tags=["Models"])
    app.include_router(create_registry_router(registry=registry), tags=["Registry"])
    app.include_router(create_code_validation_router(), tags=["Code Validation"])
    app.include_router(create_code_agent_router(), tags=["Code Validation"])
    app.include_router(create_generalist_agent_router(), tags=["Optimizations"])
    app.include_router(create_datasets_router(), tags=["Datasets"])
    app.include_router(create_wizard_router(), tags=["Wizard"])
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
        create_recommendations_router(job_store=job_store),
        tags=["Recommendations"],
    )
    app.include_router(
        create_dashboard_router(job_store=job_store),
        tags=["Dashboard"],
    )
    app.include_router(
        create_optimizations_meta_router(job_store=job_store),
        tags=["Optimizations"],
    )

    # Mount FastMCP AFTER routers so from_fastapi() sees the full route
    # table. Only endpoints tagged "agent" are projected into tools; every
    # other REST route is unaffected. The sub-app handles Streamable HTTP
    # at POST /mcp. Tolerated import error so the backend still boots in
    # environments where the dep hasn't been reinstalled yet.
    try:
        mount_mcp_on_app(app)
    except ImportError as exc:
        logger.warning("FastMCP not available, skipping /mcp mount: %s", exc)

    return app
