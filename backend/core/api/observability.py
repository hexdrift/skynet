"""Logging and metrics setup for on-prem deployments.

Three concerns live here:

* :func:`configure_logging` switches between a human-readable formatter and
  a JSON formatter based on the ``LOG_FORMAT`` env var. JSON output is what
  shipping log aggregators (Loki, Splunk, Elastic) expect; the human format
  is what developers want during local runs. Pod identity and the per-
  request id (when known) are stamped on every record so logs collected
  from many replicas stay traceable.

* :func:`install_metrics` mounts a Prometheus-compatible ``/metrics``
  endpoint via ``prometheus-fastapi-instrumentator``. The dependency is
  imported lazily so the backend still boots in environments where the
  wheel hasn't been mirrored to the local artifactory yet.

* :func:`install_request_id_middleware` adds a tiny ASGI middleware that
  reads the inbound ``X-Request-ID`` header (or generates a UUID4),
  publishes it on a :class:`contextvars.ContextVar`, and echoes it back in
  the response. The logging filter picks the contextvar up so log lines
  emitted while serving the request — including from the worker thread
  pool when it inherits the same context — share a single id.
"""

from __future__ import annotations

import logging
import os
import socket
import uuid
from contextvars import ContextVar

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# python-json-logger ships its formatter under two different names depending
# on the wheel version available in the local artifactory. Prefer the new
# location, fall back to the old one, and degrade to text logging when neither
# import resolves so the backend still boots.
try:
    from pythonjsonlogger.json import JsonFormatter as _JsonFormatter
except ImportError:
    try:
        from pythonjsonlogger.jsonlogger import JsonFormatter as _JsonFormatter  # type: ignore[no-redef]
    except ImportError:
        _JsonFormatter = None  # type: ignore[assignment]

# prometheus-fastapi-instrumentator is optional in environments where the wheel
# hasn't been mirrored — degrade ``/metrics`` to a no-op there.
try:
    from prometheus_fastapi_instrumentator import Instrumentator as _Instrumentator
except ImportError:
    _Instrumentator = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def _resolve_pod_name() -> str:
    """Return the best-effort pod identity used to enrich log records.

    Returns:
        The Kubernetes pod name from the ``POD_NAME`` env var when present,
        otherwise the OS hostname.
    """
    return os.environ.get("POD_NAME") or socket.gethostname()


_POD_NAME = _resolve_pod_name()


def get_request_id() -> str:
    """Return the request id bound to the current context.

    Returns:
        The id set by the middleware for the current request, or the
        sentinel ``"-"`` outside of any request (e.g. on startup).
    """
    return _request_id_ctx.get()


class _ContextFilter(logging.Filter):
    """Inject pod name and current request id onto every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach ``record.pod`` and ``record.request_id`` so formatters can read them.

        Args:
            record: The log record about to be formatted.

        Returns:
            ``True`` so the record continues through the handler chain.
        """
        record.pod = _POD_NAME
        record.request_id = _request_id_ctx.get()
        return True


def _build_text_handler() -> logging.Handler:
    """Build a stream handler that writes the human-readable text format.

    Returns:
        A :class:`logging.StreamHandler` with the context filter and the
        human-readable formatter installed.
    """
    handler = logging.StreamHandler()
    handler.addFilter(_ContextFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s pod=%(pod)s rid=%(request_id)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    return handler


def _build_json_handler() -> logging.Handler:
    """Build a stream handler that writes JSON-formatted records.

    Falls back to :func:`_build_text_handler` after a single warning when
    ``python-json-logger`` is not installed.

    Returns:
        A :class:`logging.StreamHandler` whose formatter renders each record
        as a JSON object with stable ``timestamp``, ``level``, ``logger``,
        ``pod``, ``request_id`` and ``message`` keys.
    """
    if _JsonFormatter is None:
        logger.warning("python-json-logger not installed; falling back to text logs")
        return _build_text_handler()
    handler = logging.StreamHandler()
    handler.addFilter(_ContextFilter())
    handler.setFormatter(
        _JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(pod)s %(request_id)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
            rename_fields={
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger",
            },
        )
    )
    return handler


def configure_logging() -> None:
    """Configure root logging for the FastAPI backend.

    Reads two env vars:

    * ``LOG_LEVEL`` — DEBUG/INFO/WARNING/ERROR/CRITICAL (default ``INFO``).
    * ``LOG_FORMAT`` — ``json`` or ``text`` (default ``text``).

    Existing handlers (e.g. one installed by Uvicorn or pytest at import
    time) are removed so log output has a single, predictable shape.
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_format = os.environ.get("LOG_FORMAT", "text").lower()

    handler = _build_json_handler() if log_format == "json" else _build_text_handler()

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)


def install_metrics(app: FastAPI) -> None:
    """Mount a Prometheus ``/metrics`` endpoint on ``app`` when the dep is present.

    Falls back to a single warning and leaves the app untouched when
    ``prometheus-fastapi-instrumentator`` is not installed, so the backend
    keeps booting in environments where the dep wheel hasn't been mirrored.

    Args:
        app: The FastAPI application to instrument. The ``/metrics`` route
            is registered in-place.
    """
    if _Instrumentator is None:
        logger.warning("prometheus-fastapi-instrumentator not installed; /metrics disabled")
        return
    _Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Bind a stable request id to every request for log correlation."""

    def __init__(self, app: ASGIApp, header_name: str = REQUEST_ID_HEADER) -> None:
        """Wrap ``app`` so each request has a request id bound on a ContextVar.

        Args:
            app: The downstream ASGI application.
            header_name: Inbound and outbound header name carrying the id.
        """
        super().__init__(app)
        self._header_name = header_name

    async def dispatch(self, request: Request, call_next):
        """Read or mint the request id, publish it on the contextvar, propagate it.

        Args:
            request: The incoming Starlette request.
            call_next: The downstream ASGI handler.

        Returns:
            The downstream :class:`starlette.responses.Response`, with the
            request id stamped on the configured response header.
        """
        incoming = request.headers.get(self._header_name)
        request_id = incoming or uuid.uuid4().hex
        token = _request_id_ctx.set(request_id)
        try:
            response: Response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)
        response.headers[self._header_name] = request_id
        return response


def install_request_id_middleware(app: FastAPI) -> None:
    """Install :class:`RequestIDMiddleware` on ``app``.

    Args:
        app: The FastAPI application to instrument.
    """
    app.add_middleware(RequestIDMiddleware)
