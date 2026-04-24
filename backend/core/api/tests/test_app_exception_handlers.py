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

# Re-create the handler logic from create_app() without pulling in Postgres /
# worker / static files. The _STATUS_TO_ERROR_TYPE map below is copied from
# the production module so handler semantics stay in sync.

_STATUS_TO_ERROR_TYPE = {
    400: "validation_error",
    404: "not_found",
    409: "conflict",
    422: "invalid_request",
    500: "internal_error",
    503: "service_unavailable",
}


def _build_test_app() -> FastAPI:
    """Build a tiny FastAPI app with only the exception handlers attached.

    No routers, no static mounts, no database. Probe endpoints are
    registered inline so tests can trigger each handler path.
    """
    app = FastAPI()

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
            content={"error": "invalid_request", "detail": issues},
        )

    @app.exception_handler(Exception)
    async def _generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "detail": "An internal server error occurred. Please contact support.",
            },
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
    """HTTPException maps each known status code to its canonical error_type string."""
    resp = exc_client.get(f"/raise-http/{status_code}")

    assert resp.status_code == status_code
    body = resp.json()
    assert body["error"] == expected_error_type


def test_http_exception_includes_detail(exc_client: TestClient) -> None:
    """HTTPException response body includes the original ``detail`` string."""
    resp = exc_client.get("/raise-http/404")

    body = resp.json()
    assert "detail" in body
    assert body["detail"] == "simulated 404"


def test_http_exception_unknown_status_code_uses_generic_error_type(exc_client: TestClient) -> None:
    """Unmapped status codes fall back to the generic ``error`` type string."""
    resp = exc_client.get("/raise-http/418")

    assert resp.status_code == 418
    body = resp.json()
    assert body["error"] == "error"


def test_app_error_returns_correct_status_and_envelope(exc_client: TestClient) -> None:
    """AppError is serialized to its status_code, lowercased error_code, and message."""
    resp = exc_client.get("/raise-app-error")

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "domain_error"
    assert body["detail"] == "domain broke"


def test_validation_error_returns_422_with_issues_list(exc_client: TestClient) -> None:
    """RequestValidationError returns 422 with an ``invalid_request`` envelope and a list of issues."""
    resp = exc_client.post("/body-validation", json={"value": "not-an-int"})

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "invalid_request"
    assert isinstance(body["detail"], list)
    assert len(body["detail"]) > 0


def test_validation_error_issue_has_field_message_type(exc_client: TestClient) -> None:
    """Each issue in the validation error detail contains ``field``, ``message``, and ``type``."""
    resp = exc_client.post("/body-validation", json={"value": "not-an-int"})

    issue = resp.json()["detail"][0]
    assert "field" in issue
    assert "message" in issue
    assert "type" in issue


def test_validation_error_on_missing_body_field(exc_client: TestClient) -> None:
    """Missing required body field yields 422 with at least one issue in detail."""
    resp = exc_client.post("/body-validation", json={})

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "invalid_request"
    assert len(body["detail"]) > 0


def test_unhandled_exception_returns_500_with_safe_message(exc_client: TestClient) -> None:
    """Unhandled exceptions return 500 with a generic safe message and ``internal_error`` type."""
    resp = exc_client.get("/raise-unhandled")

    assert resp.status_code == 500
    body = resp.json()
    assert body["error"] == "internal_error"
    assert "internal server error" in body["detail"].lower()
    assert "boom" not in body["detail"]


def test_error_response_does_not_expose_stack_trace(exc_client: TestClient) -> None:
    """Error bodies must never include Python tracebacks or exception messages."""
    resp = exc_client.get("/raise-unhandled")

    body = resp.text
    assert "Traceback" not in body
    assert "RuntimeError" not in body


def test_http_error_handler_preserves_www_authenticate_header(exc_client: TestClient) -> None:
    """WWW-Authenticate header on HTTPException is passed through to the JSON error response."""
    resp = exc_client.get(
        "/raise-http-with-headers/401",
        params={"header_name": "WWW-Authenticate", "header_value": "Bearer"},
    )

    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


def test_http_error_handler_preserves_location_header_on_307(exc_client: TestClient) -> None:
    """Location header on a 307 HTTPException is forwarded to the client."""
    resp = exc_client.get(
        "/raise-http-with-headers/307",
        params={"header_name": "Location", "header_value": "/x"},
        follow_redirects=False,
    )

    assert resp.status_code == 307
    assert resp.headers.get("location") == "/x"


def test_http_error_handler_no_headers_for_bare_exception(exc_client: TestClient) -> None:
    """HTTPException without custom headers does not leak any extra headers into the response."""
    resp = exc_client.get("/raise-http/404")

    assert resp.status_code == 404
    for key in ("www-authenticate", "location", "x-custom"):
        assert key not in resp.headers
