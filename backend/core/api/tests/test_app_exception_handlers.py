"""Exception handler tests.

Re-creates the handler logic from ``create_app()`` without pulling in Postgres,
the background worker, or static files. The ``_STATUS_TO_ERROR_TYPE`` map and
``_problem_response`` builder below are copied from the production module so
handler semantics stay in sync; envelope follows RFC 9457 (Problem Details).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator

from ...exceptions import AppError
from ..observability import get_request_id, install_request_id_middleware

_STATUS_TO_ERROR_TYPE = {
    400: "validation_error",
    404: "not_found",
    409: "conflict",
    422: "invalid_request",
    500: "internal_error",
    503: "service_unavailable",
}


def _problem_response(
    request: Request,
    *,
    status: int,
    error_type: str,
    detail: object,
    code: str | None = None,
    params: dict[str, Any] | None = None,
    title: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build an RFC 9457 ``application/problem+json`` response (test mirror).

    Args:
        request: The incoming HTTP request used to populate ``instance``.
        status: HTTP status code to return.
        error_type: Legacy ``error`` slug retained for backward compatibility.
        detail: Stable English string (or list, for validation issues).
        code: Optional i18n key identifying the problem class.
        params: Optional substitution params attached to ``code``.
        title: Optional human-readable title; derived from ``code`` when omitted.
        headers: Optional response headers (e.g. ``WWW-Authenticate``).

    Returns:
        A :class:`JSONResponse` with media type ``application/problem+json``.
    """
    body: dict[str, Any] = {
        "type": f"https://errors.skynet.app/{code}" if code else "about:blank",
        "title": title
        or (
            code.replace("_", " ").replace(".", " ").capitalize()
            if code
            else error_type.replace("_", " ").capitalize()
        ),
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "trace_id": get_request_id(),
        "error": error_type,
    }
    if code:
        body["code"] = code
        body["params"] = params or {}
    return JSONResponse(
        status_code=status,
        content=body,
        headers=headers,
        media_type="application/problem+json",
    )


def _build_test_app() -> FastAPI:
    """Build a stripped-down FastAPI app with only the handlers under test.

    No routers, static mounts, or database connections are wired in; probe
    endpoints are registered inline so each handler path can be triggered.

    Returns:
        A FastAPI app exposing routes that raise the various exception types.
    """
    app = FastAPI()
    install_request_id_middleware(app)

    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return _problem_response(
            request,
            status=exc.status_code,
            error_type=exc.error_code.lower(),
            detail=exc.message,
            code=getattr(exc, "code", None),
            params=getattr(exc, "params", None),
        )

    @app.exception_handler(HTTPException)
    async def _http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return _problem_response(
            request,
            status=exc.status_code,
            error_type=_STATUS_TO_ERROR_TYPE.get(exc.status_code, "error"),
            detail=exc.detail,
            code=getattr(exc, "code", None),
            params=getattr(exc, "params", None),
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

        issues = [
            {
                "field": _format_field(error.get("loc", [])),
                "message": error.get("msg", "Invalid value"),
                "type": error.get("type", "validation_error"),
            }
            for error in exc.errors()
        ]
        return _problem_response(
            request,
            status=422,
            error_type="invalid_request",
            detail=issues,
            title="Invalid request",
        )

    @app.exception_handler(Exception)
    async def _generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return _problem_response(
            request,
            status=500,
            error_type="internal_error",
            detail="An internal server error occurred. Please contact support.",
            title="Internal server error",
        )

    class _Item(BaseModel):
        value: int

        @field_validator("value")
        @classmethod
        def _positive(cls, v: int) -> int:
            if v < 0:
                raise ValueError("value must be non-negative")
            return v

    @app.get("/raise-http/{code}")
    def raise_http(code: int):
        raise HTTPException(status_code=code, detail=f"simulated {code}")

    @app.get("/raise-http-with-headers/{code}")
    def raise_http_with_headers(code: int, header_name: str, header_value: str):
        raise HTTPException(status_code=code, detail=f"simulated {code}", headers={header_name: header_value})

    @app.get("/raise-app-error")
    def raise_app_error():
        raise AppError("domain broke", status_code=400, error_code="DOMAIN_ERROR")

    @app.get("/raise-unhandled")
    def raise_unhandled():
        raise RuntimeError("unexpected boom")

    @app.post("/body-validation")
    def body_validation(item: _Item):
        return {"ok": True}

    return app


@pytest.fixture(scope="module")
def exc_client() -> TestClient:
    """Provide a module-scoped client around the handler test app.

    Returns:
        A ``TestClient`` that tolerates server exceptions so 500-path tests
        can inspect responses instead of re-raising.
    """
    return TestClient(_build_test_app(), raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("status_code", "expected_error_type"),
    [
        (400, "validation_error"),
        (404, "not_found"),
        (409, "conflict"),
        (422, "invalid_request"),
        (500, "internal_error"),
        (503, "service_unavailable"),
    ],
)
def test_http_exception_returns_correct_error_type(
    exc_client: TestClient,
    status_code: int,
    expected_error_type: str,
) -> None:
    """Each known status code maps to its documented ``error`` envelope tag."""
    resp = exc_client.get(f"/raise-http/{status_code}")

    assert resp.status_code == status_code
    body = resp.json()
    assert body["error"] == expected_error_type


def test_http_exception_includes_detail(exc_client: TestClient) -> None:
    """The HTTPException ``detail`` is forwarded into the response body."""
    resp = exc_client.get("/raise-http/404")

    body = resp.json()
    assert "detail" in body
    assert body["detail"] == "simulated 404"


def test_http_exception_unknown_status_code_uses_generic_error_type(exc_client: TestClient) -> None:
    """Unmapped status codes default to the generic ``"error"`` envelope tag."""
    resp = exc_client.get("/raise-http/418")

    assert resp.status_code == 418
    body = resp.json()
    assert body["error"] == "error"


def test_app_error_returns_correct_status_and_envelope(exc_client: TestClient) -> None:
    """``AppError`` instances surface as their declared status and code."""
    resp = exc_client.get("/raise-app-error")

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "domain_error"
    assert body["detail"] == "domain broke"


def test_validation_error_returns_422_with_issues_list(exc_client: TestClient) -> None:
    """Pydantic validation failures produce a 422 with an issues list."""
    resp = exc_client.post("/body-validation", json={"value": "not-an-int"})

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "invalid_request"
    assert isinstance(body["detail"], list)
    assert len(body["detail"]) > 0


def test_validation_error_issue_has_field_message_type(exc_client: TestClient) -> None:
    """Each validation issue exposes ``field``, ``message``, and ``type``."""
    resp = exc_client.post("/body-validation", json={"value": "not-an-int"})

    issue = resp.json()["detail"][0]
    assert "field" in issue
    assert "message" in issue
    assert "type" in issue


def test_validation_error_on_missing_body_field(exc_client: TestClient) -> None:
    """Missing required body fields surface as ``invalid_request`` 422s."""
    resp = exc_client.post("/body-validation", json={})

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "invalid_request"
    assert len(body["detail"]) > 0


def test_unhandled_exception_returns_500_with_safe_message(exc_client: TestClient) -> None:
    """Unhandled exceptions return a generic 500 body without raw text."""
    resp = exc_client.get("/raise-unhandled")

    assert resp.status_code == 500
    body = resp.json()
    assert body["error"] == "internal_error"
    assert "internal server error" in body["detail"].lower()
    assert "boom" not in body["detail"]


def test_error_response_does_not_expose_stack_trace(exc_client: TestClient) -> None:
    """500 responses must not leak tracebacks or exception class names."""
    resp = exc_client.get("/raise-unhandled")

    body = resp.text
    assert "Traceback" not in body
    assert "RuntimeError" not in body


def test_http_error_handler_preserves_www_authenticate_header(exc_client: TestClient) -> None:
    """Custom auth headers attached to ``HTTPException`` survive the handler."""
    resp = exc_client.get(
        "/raise-http-with-headers/401",
        params={"header_name": "WWW-Authenticate", "header_value": "Bearer"},
    )

    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


def test_http_error_handler_preserves_location_header_on_307(exc_client: TestClient) -> None:
    """Redirect headers from ``HTTPException`` survive the handler."""
    resp = exc_client.get(
        "/raise-http-with-headers/307",
        params={"header_name": "Location", "header_value": "/x"},
        follow_redirects=False,
    )

    assert resp.status_code == 307
    assert resp.headers.get("location") == "/x"


def test_http_error_handler_no_headers_for_bare_exception(exc_client: TestClient) -> None:
    """Bare ``HTTPException`` raises do not leak unrelated response headers."""
    resp = exc_client.get("/raise-http/404")

    assert resp.status_code == 404
    for key in ("www-authenticate", "location", "x-custom"):
        assert key not in resp.headers


def test_problem_response_uses_problem_json_content_type(exc_client: TestClient) -> None:
    """Error responses advertise ``application/problem+json`` per RFC 9457."""
    resp = exc_client.get("/raise-http/404")

    assert resp.headers["content-type"].startswith("application/problem+json")


def test_problem_response_includes_rfc9457_envelope_keys(exc_client: TestClient) -> None:
    """Every error body carries the RFC 9457 ``type``/``title``/``status``/``detail``/``instance`` keys."""
    resp = exc_client.get("/raise-http/404")

    body = resp.json()
    for key in ("type", "title", "status", "detail", "instance", "trace_id", "error"):
        assert key in body, f"missing RFC 9457 envelope key: {key}"
    assert body["status"] == 404
    assert body["instance"] == "/raise-http/404"
    assert body["type"] == "about:blank"


def test_problem_response_trace_id_matches_request_id_header(exc_client: TestClient) -> None:
    """``trace_id`` echoes the request-id middleware's ``X-Request-Id`` header."""
    resp = exc_client.get("/raise-http/404")

    body = resp.json()
    assert body["trace_id"] == resp.headers.get("x-request-id")
    assert body["trace_id"]


def test_problem_response_validation_error_includes_envelope(exc_client: TestClient) -> None:
    """Validation 422s carry the full RFC 9457 envelope alongside the issues list."""
    resp = exc_client.post("/body-validation", json={"value": "not-an-int"})

    body = resp.json()
    assert body["status"] == 422
    assert body["title"] == "Invalid request"
    assert body["instance"] == "/body-validation"
    assert isinstance(body["detail"], list)


def test_problem_response_500_envelope_omits_optional_code(exc_client: TestClient) -> None:
    """Internal errors emit the envelope without ``code``/``params`` extension members."""
    resp = exc_client.get("/raise-unhandled")

    body = resp.json()
    assert body["status"] == 500
    assert body["type"] == "about:blank"
    assert "code" not in body
    assert "params" not in body
