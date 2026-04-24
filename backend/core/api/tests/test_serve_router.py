from __future__ import annotations

import json
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# noinspection PyProtectedMember
from ..routers import _helpers  # noqa: SLF001
from ..routers.serve import create_serve_router
from .mocks import (
    _BaseFakeJobStore,
    make_artifact,
    make_grid_job,
    make_run_result,
)
from ...models import ProgramArtifact

# Use the shared base fake store; the serve router only needs get_job + seed_job.
_FakeJobStore = _BaseFakeJobStore

# noinspection PyProtectedMember
@pytest.fixture(autouse=True)
def _clear_program_cache() -> None:
    """Reset the module-level program cache before every test to prevent bleed."""
    _helpers.clear_program_cache()
    yield
    _helpers.clear_program_cache()

@pytest.fixture
def serve_store() -> _FakeJobStore:
    return _FakeJobStore()

@pytest.fixture
def serve_client(serve_store: _FakeJobStore) -> TestClient:
    app = FastAPI()
    app.include_router(create_serve_router(job_store=serve_store))
    return TestClient(app, raise_server_exceptions=False)

def test_serve_info_returns_404_for_unknown_id(serve_client: TestClient) -> None:
    """GET /serve/{id}/info returns 404 when the optimization id is unknown."""
    resp = serve_client.get("/serve/ghost/info")

    assert resp.status_code == 404

def test_serve_info_returns_409_for_pending_job(
    serve_client: TestClient, serve_store: _FakeJobStore
) -> None:
    """GET /serve/{id}/info returns 409 when the job is still pending."""
    serve_store.seed_job("p", status="pending")

    resp = serve_client.get("/serve/p/info")

    assert resp.status_code == 409

def test_serve_info_returns_409_for_running_job(
    serve_client: TestClient, serve_store: _FakeJobStore
) -> None:
    """GET /serve/{id}/info returns 409 when the job is running."""
    serve_store.seed_job("r", status="running")

    resp = serve_client.get("/serve/r/info")

    assert resp.status_code == 409

def test_serve_info_returns_409_for_failed_job(
    serve_client: TestClient, serve_store: _FakeJobStore
) -> None:
    """GET /serve/{id}/info returns 409 when the job has failed."""
    serve_store.seed_job("f", status="failed")

    resp = serve_client.get("/serve/f/info")

    assert resp.status_code == 409

def test_serve_info_returns_409_for_cancelled_job(
    serve_client: TestClient, serve_store: _FakeJobStore
) -> None:
    """GET /serve/{id}/info returns 409 when the job was cancelled."""
    serve_store.seed_job("c", status="cancelled")

    resp = serve_client.get("/serve/c/info")

    assert resp.status_code == 409

@pytest.mark.parametrize("non_success_status", ["pending", "validating", "running", "failed", "cancelled"])
def test_serve_info_returns_409_for_all_non_success_statuses(
    serve_client: TestClient,
    serve_store: _FakeJobStore,
    non_success_status: str,
) -> None:
    """GET /serve/{id}/info returns 409 for every non-success status."""
    serve_store.seed_job(f"j_{non_success_status}", status=non_success_status)

    resp = serve_client.get(f"/serve/j_{non_success_status}/info")

    assert resp.status_code == 409

def test_serve_program_returns_404_for_unknown_id(serve_client: TestClient) -> None:
    """POST /serve/{id} returns 404 when the optimization id is unknown."""
    resp = serve_client.post("/serve/ghost", json={"inputs": {"q": "hello"}})

    assert resp.status_code == 404

def test_serve_program_returns_409_for_pending_job(
    serve_client: TestClient, serve_store: _FakeJobStore
) -> None:
    """POST /serve/{id} returns 409 when the job has not yet completed."""
    serve_store.seed_job("p", status="pending")

    resp = serve_client.post("/serve/p", json={"inputs": {"q": "hello"}})

    assert resp.status_code == 409

def test_serve_program_returns_409_for_failed_job(
    serve_client: TestClient, serve_store: _FakeJobStore
) -> None:
    """POST /serve/{id} returns 409 when the job has failed."""
    serve_store.seed_job("f", status="failed")

    resp = serve_client.post("/serve/f", json={"inputs": {"q": "hello"}})

    assert resp.status_code == 409

class _FakePrediction:
    """Minimal prediction object that mimics dspy.Prediction."""

    answer: str = "42"

    @staticmethod
    def toDict() -> dict:
        return {"answer": "42"}

def _seed_run_job(
    store: _FakeJobStore,
    opt_id: str,
    artifact: ProgramArtifact | None = None,
    overview_extra: dict | None = None,
    status: str = "success",
) -> dict:
    """Seed a single-run job and pre-populate the program cache."""
    if artifact is None:
        artifact = make_artifact()
    result = make_run_result(artifact)
    overview = {"model_name": "openai/gpt-4o-mini", **(overview_extra or {})}
    job = store.seed_job(
        opt_id,
        status=status,
        payload_overview=overview,
        result=result.model_dump(),
    )
    # noinspection PyProtectedMember
    _helpers._program_cache[opt_id] = MagicMock(return_value=_FakePrediction())  # noqa: SLF001
    return job

_PATCH_LM = patch(
    "core.service_gateway.language_models.build_language_model",
    return_value=MagicMock(),
)
_PATCH_DSPY_CTX = patch("dspy.context", return_value=nullcontext())

def test_serve_program_happy_path(
    serve_client: TestClient, serve_store: _FakeJobStore
) -> None:
    """POST /serve/{id} returns 200 with outputs and output_fields for a success job."""
    # Arrange
    _seed_run_job(serve_store, "ok")

    # Act
    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = serve_client.post("/serve/ok", json={"inputs": {"question": "hello"}})

    # Assert
    assert resp.status_code == 200
    body = resp.json()
    assert body["optimization_id"] == "ok"
    assert "answer" in body["outputs"]
    assert body["output_fields"] == ["reasoning", "answer"]
    assert "model_used" in body

def test_serve_program_model_resolution_from_override(
    serve_client: TestClient, serve_store: _FakeJobStore
) -> None:
    """model_config_override takes precedence over stored model settings."""
    _seed_run_job(serve_store, "ov", overview_extra={"model_settings": {"name": "openai/gpt-4o"}})

    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = serve_client.post(
            "/serve/ov",
            json={
                "inputs": {"question": "hi"},
                "model_config_override": {"name": "openai/gpt-3.5-turbo"},
            },
        )

    assert resp.status_code == 200
    assert resp.json()["model_used"] == "openai/gpt-3.5-turbo"

def test_serve_program_model_resolution_from_stored_settings(
    serve_client: TestClient, serve_store: _FakeJobStore
) -> None:
    """When model_settings dict is present in overview, it is used as ModelConfig."""
    _seed_run_job(
        serve_store,
        "ms",
        overview_extra={"model_settings": {"name": "openai/gpt-4-turbo"}},
    )

    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = serve_client.post("/serve/ms", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 200
    assert resp.json()["model_used"] == "openai/gpt-4-turbo"

def test_serve_program_model_resolution_from_model_name_only(
    serve_client: TestClient, serve_store: _FakeJobStore
) -> None:
    """When only model_name is in overview (legacy), a minimal ModelConfig is used."""
    _seed_run_job(serve_store, "mn")

    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = serve_client.post("/serve/mn", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 200
    assert resp.json()["model_used"] == "openai/gpt-4o-mini"

def test_serve_program_returns_400_when_no_model_config(
    serve_client: TestClient, serve_store: _FakeJobStore
) -> None:
    """POST /serve/{id} returns 400 when the overview has neither model_name nor model_settings."""
    _seed_run_job(serve_store, "nm", overview_extra={"model_name": "", "model_settings": {}})
    # Clear override so the fallback chain reaches the 400 branch
    # (model_name key present but empty, model_settings empty dict)
    serve_store.update_job("nm", payload_overview={})

    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = serve_client.post("/serve/nm", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 400
    assert "model_config_override" in resp.json()["detail"]

def test_serve_program_returns_400_for_no_input_fields(
    serve_client: TestClient, serve_store: _FakeJobStore
) -> None:
    """POST /serve/{id} returns 400 when the artifact declares no input fields."""
    artifact = make_artifact(input_fields=[], output_fields=["answer"])
    _seed_run_job(serve_store, "nif", artifact=artifact)
    # noinspection PyProtectedMember
    # Ensure the cache reflects the artifact with empty input_fields (not a prior entry)
    _helpers._program_cache["nif"] = MagicMock(return_value=_FakePrediction())  # noqa: SLF001

    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = serve_client.post("/serve/nif", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 400
    assert "אין שדות קלט מוצהרים" in resp.json()["detail"]

def test_serve_program_returns_400_for_missing_input_fields(
    serve_client: TestClient, serve_store: _FakeJobStore
) -> None:
    """POST /serve/{id} returns 400 when required input fields are absent from the request body."""
    _seed_run_job(serve_store, "mif")

    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = serve_client.post("/serve/mif", json={"inputs": {"wrong_key": "hi"}})

    assert resp.status_code == 400
    assert "חסרים שדות קלט נדרשים" in resp.json()["detail"]

def test_serve_program_output_todict_fallback(
    serve_client: TestClient, serve_store: _FakeJobStore
) -> None:
    """POST /serve/{id} falls back to toDict() when the artifact declares no output fields."""
    artifact = make_artifact(input_fields=["question"], output_fields=[])
    _seed_run_job(serve_store, "tdf", artifact=artifact)
    # Return a prediction whose toDict has an extra key
    pred = MagicMock()
    pred.toDict.return_value = {"answer": "via todict", "score": 0.9}
    # noinspection PyProtectedMember
    _helpers._program_cache["tdf"] = MagicMock(return_value=pred)  # noqa: SLF001

    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = serve_client.post("/serve/tdf", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 200
    body = resp.json()
    assert body["outputs"]["answer"] == "via todict"
    assert body["output_fields"] == []

@pytest.fixture
def grid_store() -> _FakeJobStore:
    store = _FakeJobStore()
    job = make_grid_job("grid1", pair_index=0)
    store.seed_raw("grid1", job=job)
    # noinspection PyProtectedMember
    _helpers._program_cache["grid1_pair_0"] = MagicMock(return_value=_FakePrediction())  # noqa: SLF001
    return store

@pytest.fixture
def grid_client(grid_store: _FakeJobStore) -> TestClient:
    app = FastAPI()
    app.include_router(create_serve_router(job_store=grid_store))
    return TestClient(app, raise_server_exceptions=False)

def test_serve_pair_happy_path(
    grid_client: TestClient, grid_store: _FakeJobStore
) -> None:
    """POST /serve/{id}/pair/{index} returns 200 with outputs and model_used."""
    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = grid_client.post("/serve/grid1/pair/0", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 200
    body = resp.json()
    assert body["optimization_id"] == "grid1"
    assert "answer" in body["outputs"]
    assert "model_used" in body

def test_serve_pair_returns_404_for_unknown_job(grid_client: TestClient) -> None:
    """POST /serve/{id}/pair/{index} returns 404 when the optimization id is unknown."""
    resp = grid_client.post("/serve/ghost/pair/0", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 404

def test_serve_pair_returns_404_for_out_of_range_index(grid_client: TestClient) -> None:
    """POST /serve/{id}/pair/{index} returns 404 when the pair index is out of range."""
    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = grid_client.post("/serve/grid1/pair/99", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 404

def test_serve_pair_returns_409_for_non_success_job(
    grid_client: TestClient, grid_store: _FakeJobStore
) -> None:
    """POST /serve/{id}/pair/{index} returns 409 when the parent grid-search job is not successful."""
    grid_store.update_job("grid1", status="failed")

    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = grid_client.post("/serve/grid1/pair/0", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 409

def test_serve_pair_returns_400_for_missing_inputs(
    grid_client: TestClient,
) -> None:
    """POST /serve/{id}/pair/{index} returns 400 when required input fields are absent."""
    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = grid_client.post("/serve/grid1/pair/0", json={"inputs": {"wrong": "hi"}})

    assert resp.status_code == 400
    assert "חסרים שדות קלט נדרשים" in resp.json()["detail"]

def test_serve_pair_uses_override_model(
    grid_client: TestClient,
) -> None:
    """POST /serve/{id}/pair/{index} respects model_config_override when provided."""
    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = grid_client.post(
            "/serve/grid1/pair/0",
            json={"inputs": {"question": "hi"}, "model_config_override": {"name": "openai/gpt-3.5-turbo"}},
        )

    assert resp.status_code == 200
    assert resp.json()["model_used"] == "openai/gpt-3.5-turbo"

def test_serve_pair_info_happy_path(grid_client: TestClient) -> None:
    """GET /serve/{id}/pair/{index}/info returns 200 with input_fields, output_fields, and model_name."""
    resp = grid_client.get("/serve/grid1/pair/0/info")

    assert resp.status_code == 200
    body = resp.json()
    assert body["optimization_id"] == "grid1"
    assert body["input_fields"] == ["question"]
    assert body["output_fields"] == ["reasoning", "answer"]
    assert body["model_name"] == "openai/gpt-4o-mini"

def test_serve_pair_info_returns_404_for_unknown_id(grid_client: TestClient) -> None:
    """GET /serve/{id}/pair/{index}/info returns 404 when the optimization id is unknown."""
    resp = grid_client.get("/serve/ghost/pair/0/info")

    assert resp.status_code == 404

def test_serve_pair_info_returns_404_for_out_of_range_pair(grid_client: TestClient) -> None:
    """GET /serve/{id}/pair/{index}/info returns 404 when the pair index is out of range."""
    resp = grid_client.get("/serve/grid1/pair/99/info")

    assert resp.status_code == 404

def test_serve_pair_info_returns_409_for_non_success_job(
    grid_client: TestClient, grid_store: _FakeJobStore
) -> None:
    """GET /serve/{id}/pair/{index}/info returns 409 when the parent job is not successful."""
    grid_store.update_job("grid1", status="running")

    resp = grid_client.get("/serve/grid1/pair/0/info")

    assert resp.status_code == 409

@pytest.fixture
def stream_store(serve_store: _FakeJobStore) -> _FakeJobStore:
    """Seed a success run job and cache its program for streaming tests."""
    _seed_run_job(serve_store, "stream_job")
    return serve_store

@pytest.fixture
def stream_client(stream_store: _FakeJobStore) -> TestClient:
    app = FastAPI()
    app.include_router(create_serve_router(job_store=stream_store))
    return TestClient(app, raise_server_exceptions=False)

def test_serve_stream_returns_404_for_unknown_id(stream_client: TestClient) -> None:
    """POST /serve/{id}/stream returns 404 when the optimization id is unknown."""
    resp = stream_client.post("/serve/ghost/stream", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 404

def test_serve_stream_returns_409_for_non_success_job(
    stream_client: TestClient, stream_store: _FakeJobStore
) -> None:
    """POST /serve/{id}/stream returns 409 when the job is not in a success state."""
    stream_store.seed_job("pending_s", status="pending")

    resp = stream_client.post("/serve/pending_s/stream", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 409

def test_serve_stream_returns_400_for_missing_inputs(stream_client: TestClient) -> None:
    """POST /serve/{id}/stream returns 400 when required input fields are missing."""
    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = stream_client.post("/serve/stream_job/stream", json={"inputs": {"wrong": "x"}})

    assert resp.status_code == 400

def test_serve_stream_fallback_when_streamify_raises(stream_client: TestClient) -> None:
    """When dspy.streamify raises, handler falls back to blocking call and emits final SSE."""
    with _PATCH_LM, _PATCH_DSPY_CTX, patch("dspy.streamify", side_effect=RuntimeError("not streamable")):
        resp = stream_client.post("/serve/stream_job/stream", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    raw = resp.text
    assert "event: final" in raw
    payload = json.loads(raw.split("data: ", 1)[1].split("\n")[0])
    assert payload["streaming_fallback"] is True
    assert "answer" in payload["outputs"]

@pytest.fixture
def pair_stream_store(grid_store: _FakeJobStore) -> _FakeJobStore:
    return grid_store

@pytest.fixture
def pair_stream_client(pair_stream_store: _FakeJobStore) -> TestClient:
    app = FastAPI()
    app.include_router(create_serve_router(job_store=pair_stream_store))
    return TestClient(app, raise_server_exceptions=False)

def test_serve_pair_stream_returns_404_for_unknown_id(pair_stream_client: TestClient) -> None:
    """POST /serve/{id}/pair/{index}/stream returns 404 when the optimization id is unknown."""
    resp = pair_stream_client.post("/serve/ghost/pair/0/stream", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 404

def test_serve_pair_stream_returns_409_for_non_success_job(
    pair_stream_client: TestClient, pair_stream_store: _FakeJobStore
) -> None:
    """POST /serve/{id}/pair/{index}/stream returns 409 when the parent job is not successful."""
    pair_stream_store.update_job("grid1", status="failed")

    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = pair_stream_client.post("/serve/grid1/pair/0/stream", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 409

def test_serve_pair_stream_returns_400_for_missing_inputs(pair_stream_client: TestClient) -> None:
    """POST /serve/{id}/pair/{index}/stream returns 400 when required input fields are missing."""
    with _PATCH_LM, _PATCH_DSPY_CTX:
        resp = pair_stream_client.post("/serve/grid1/pair/0/stream", json={"inputs": {"wrong": "x"}})

    assert resp.status_code == 400

def test_serve_pair_stream_fallback_when_streamify_raises(pair_stream_client: TestClient) -> None:
    """Pair stream falls back to blocking call and emits final SSE when streamify raises."""
    with _PATCH_LM, _PATCH_DSPY_CTX, patch("dspy.streamify", side_effect=RuntimeError("not streamable")):
        resp = pair_stream_client.post("/serve/grid1/pair/0/stream", json={"inputs": {"question": "hi"}})

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    raw = resp.text
    assert "event: final" in raw
    payload = json.loads(raw.split("data: ", 1)[1].split("\n")[0])
    assert payload["streaming_fallback"] is True
