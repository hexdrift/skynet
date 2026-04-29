"""Contract tests for observability wiring."""

from __future__ import annotations

import importlib
import json
import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api import observability
from core.api.observability import (
    REQUEST_ID_HEADER,
    _ContextFilter,
    install_metrics,
    install_request_id_middleware,
)


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    """Snapshot and restore root-logger state so tests don't leak handlers.

    Yields:
        ``None`` after capturing the current handlers and level. On teardown
        the captured state is reinstalled on the root logger.
    """
    root = logging.getLogger()
    saved_level = root.level
    saved_handlers = list(root.handlers)
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in saved_handlers:
        root.addHandler(h)
    root.setLevel(saved_level)


def test_configure_logging_text_format_emits_pod_name(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``LOG_FORMAT=text`` produces records with ``pod=<name>`` in the output.

    Args:
        monkeypatch: pytest fixture used to set ``LOG_FORMAT`` and ``POD_NAME``.
        capsys: pytest fixture capturing stderr emitted by the stream handler.
    """
    monkeypatch.setenv("LOG_FORMAT", "text")
    monkeypatch.setenv("POD_NAME", "skynet-api-7c9d4-abcde")

    importlib.reload(observability)
    observability.configure_logging()

    logging.getLogger("test.text").info("hello")
    captured = capsys.readouterr()
    line = captured.err.strip().splitlines()[-1]
    assert "pod=skynet-api-7c9d4-abcde" in line
    assert "hello" in line


def test_configure_logging_json_format_emits_structured_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``LOG_FORMAT=json`` produces structured records with stable keys.

    Args:
        monkeypatch: pytest fixture used to set ``LOG_FORMAT`` and ``POD_NAME``.
        capsys: pytest fixture capturing the JSON line written to stderr.
    """
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("POD_NAME", "skynet-api-pod-1")

    importlib.reload(observability)
    observability.configure_logging()

    logging.getLogger("test.json").info("structured message")
    captured = capsys.readouterr()
    line = captured.err.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.json"
    assert payload["pod"] == "skynet-api-pod-1"
    assert payload["message"] == "structured message"
    assert "timestamp" in payload


def test_context_filter_attaches_pod_and_request_id() -> None:
    """``_ContextFilter`` adds ``pod`` and ``request_id`` so formatters can reference them."""
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="m",
        args=(),
        exc_info=None,
    )
    assert _ContextFilter().filter(record) is True
    # ``_ContextFilter`` injects these attributes onto every record at runtime;
    # they aren't on ``LogRecord``'s static type, so go through ``getattr``.
    pod = getattr(record, "pod", None)
    request_id = getattr(record, "request_id", None)
    assert isinstance(pod, str)
    assert pod
    # ``request_id`` defaults to the sentinel ``"-"`` outside an inbound request.
    assert isinstance(request_id, str)
    assert request_id


def test_request_id_middleware_mints_and_echoes_id() -> None:
    """When the client omits ``X-Request-ID`` the middleware mints one and echoes it back."""
    app = FastAPI()
    install_request_id_middleware(app)

    @app.get("/ping")
    async def ping() -> dict:
        """Stub route used to drive a single request through the middleware.

        Returns:
            A trivial ``{"ok": True}`` JSON body.
        """
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/ping")
    assert response.status_code == 200
    minted = response.headers.get(REQUEST_ID_HEADER)
    assert minted
    assert len(minted) >= 16


def test_request_id_middleware_propagates_inbound_id() -> None:
    """The middleware preserves a caller-supplied ``X-Request-ID`` header."""
    app = FastAPI()
    install_request_id_middleware(app)

    @app.get("/ping")
    async def ping() -> dict:
        """Stub route returning a trivial JSON payload.

        Returns:
            A trivial ``{"ok": True}`` JSON body.
        """
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/ping", headers={REQUEST_ID_HEADER: "abc-123"})
    assert response.headers[REQUEST_ID_HEADER] == "abc-123"


def test_install_metrics_exposes_metrics_endpoint() -> None:
    """``install_metrics`` registers a ``/metrics`` endpoint in Prometheus text format."""
    app = FastAPI()
    install_metrics(app)

    @app.get("/probe")
    async def probe() -> dict:
        """Stub route used to drive at least one HTTP-request counter.

        Returns:
            A trivial ``{"ok": True}`` JSON body.
        """
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/probe").status_code == 200

    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "# HELP" in body
    assert "http_request" in body
