"""Tests for the ``/datasets/profile`` route."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from core.exceptions import AppError
from core.i18n_en import t_en
from core.i18n_keys import I18nKey

from ..routers.datasets import create_datasets_router


@pytest.fixture
def datasets_client() -> TestClient:
    """Build a ``TestClient`` exposing the datasets router with error handlers.

    Returns:
        A ``TestClient`` over a minimal FastAPI app with ``AppError`` and
        validation handlers wired in to mirror production behaviour.
    """
    app = FastAPI()
    app.include_router(create_datasets_router())

    # Mirror the app-level AppError handler so ValidationError (400) surfaces
    # as a proper HTTP response instead of bubbling up as a 500.
    @app.exception_handler(AppError)
    async def _app_error_handler(_request, exc: AppError) -> JSONResponse:
        content = {"error": exc.error_code.lower(), "detail": exc.message}
        if exc.code:
            content["code"] = exc.code
            content["params"] = exc.params
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(_request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": "invalid_request", "detail": exc.errors()})

    return TestClient(app, raise_server_exceptions=False)


def test_profile_returns_plan_and_profile(datasets_client: TestClient) -> None:
    """Profiling a sized dataset returns a plan and shape profile."""
    payload = {
        "dataset": [
            {"q": "q1", "a": "yes"},
            {"q": "q2", "a": "no"},
            {"q": "q3", "a": "yes"},
            {"q": "q4", "a": "no"},
        ]
        * 100,
        "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
        "seed": 42,
    }

    resp = datasets_client.post("/datasets/profile", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["profile"]["row_count"] == 400
    assert body["profile"]["target"]["name"] == "a"
    assert body["plan"]["seed"] == 42
    counts = body["plan"]["counts"]
    assert counts["train"] + counts["val"] + counts["test"] == 400


def test_profile_empty_dataset_returns_400(datasets_client: TestClient) -> None:
    """An empty dataset is rejected with a 400 carrying English detail and i18n code."""
    payload = {
        "dataset": [],
        "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
    }

    resp = datasets_client.post("/datasets/profile", json=payload)

    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"] == t_en(I18nKey.DATASET_PROFILE_EMPTY)
    assert body["code"] == I18nKey.DATASET_PROFILE_EMPTY.value


def test_profile_missing_column_mapping_returns_422(datasets_client: TestClient) -> None:
    """``column_mapping`` is required; its absence is a 422."""
    resp = datasets_client.post("/datasets/profile", json={"dataset": [{"q": "x"}]})

    assert resp.status_code == 422


def test_profile_flags_too_small_warning(datasets_client: TestClient) -> None:
    """Tiny datasets surface the ``too_small`` warning code."""
    payload = {
        "dataset": [{"q": f"q{i}", "a": "yes"} for i in range(5)],
        "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
        "seed": 1,
    }

    resp = datasets_client.post("/datasets/profile", json=payload)

    assert resp.status_code == 200
    warning_codes = {w["code"] for w in resp.json()["profile"]["warnings"]}
    assert "too_small" in warning_codes


def test_profile_omitted_seed_is_still_populated(datasets_client: TestClient) -> None:
    """A missing ``seed`` is still echoed back as a populated integer."""
    payload = {
        "dataset": [{"q": f"q{i}", "a": "yes"} for i in range(50)],
        "column_mapping": {"inputs": {"question": "q"}, "outputs": {"answer": "a"}},
    }

    resp = datasets_client.post("/datasets/profile", json=payload)

    assert resp.status_code == 200
    assert isinstance(resp.json()["plan"]["seed"], int)
