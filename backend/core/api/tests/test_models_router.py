from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ..model_catalog import CatalogModel, CatalogProvider, ModelCatalogResponse
from ..routers.models import create_models_router

def _make_catalog(*model_ids: str) -> ModelCatalogResponse:
    models = [
        CatalogModel(value=mid, label=mid.split("/")[-1], provider=mid.split("/")[0] if "/" in mid else "openai")
        for mid in model_ids
    ]
    providers = [CatalogProvider(slug="openai", label="OpenAI", has_env_key=True)]
    return ModelCatalogResponse(providers=providers, models=models)

@pytest.fixture
def models_client() -> TestClient:
    app = FastAPI()
    app.include_router(create_models_router())
    return TestClient(app, raise_server_exceptions=False)

def test_list_models_returns_200_with_catalog_shape(models_client: TestClient) -> None:
    """GET /models returns 200 with a body containing ``models`` and ``providers`` lists."""
    fake_catalog = _make_catalog("openai/gpt-4o-mini", "anthropic/claude-3-5-haiku-20241022")

    with patch("core.api.routers.models.get_catalog_cached", return_value=fake_catalog):
        resp = models_client.get("/models")

    assert resp.status_code == 200
    body = resp.json()
    assert "models" in body
    assert "providers" in body
    assert len(body["models"]) == 2

def test_list_models_returns_model_fields(models_client: TestClient) -> None:
    """Each model entry in GET /models includes value, label, and provider fields."""
    fake_catalog = _make_catalog("openai/gpt-4o")

    with patch("core.api.routers.models.get_catalog_cached", return_value=fake_catalog):
        resp = models_client.get("/models")

    assert resp.status_code == 200
    model = resp.json()["models"][0]
    assert model["value"] == "openai/gpt-4o"
    assert "label" in model
    assert "provider" in model

def test_list_models_empty_catalog_returns_empty_lists(models_client: TestClient) -> None:
    """GET /models returns empty models and providers lists when the catalog has no entries."""
    fake_catalog = ModelCatalogResponse(providers=[], models=[])

    with patch("core.api.routers.models.get_catalog_cached", return_value=fake_catalog):
        resp = models_client.get("/models")

    assert resp.status_code == 200
    body = resp.json()
    assert body["models"] == []
    assert body["providers"] == []

def test_discover_models_happy_path_returns_model_list(models_client: TestClient) -> None:
    """POST /models/discover returns a list of model ids from a successful Ollama-style response."""
    fake_response_body = b'{"data": [{"id": "llama-3"}, {"id": "mistral-7b"}]}'

    class _FakeResp:
        @staticmethod
        def read():
            return fake_response_body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    with patch("urllib.request.urlopen", return_value=_FakeResp()):
        resp = models_client.post("/models/discover", json={"base_url": "http://localhost:11434"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert "llama-3" in body["models"]
    assert "mistral-7b" in body["models"]

def test_discover_models_invalid_body_returns_422(models_client: TestClient) -> None:
    """POST /models/discover without base_url returns 422."""
    # base_url is required
    resp = models_client.post("/models/discover", json={})

    assert resp.status_code == 422

def test_discover_models_url_error_returns_200_with_error(models_client: TestClient) -> None:
    """POST /models/discover returns 200 with an error field when the target URL is unreachable."""
    import urllib.error

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        resp = models_client.post("/models/discover", json={"base_url": "http://nowhere.invalid"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["models"] == []
    assert body["error"] is not None

def test_discover_models_404_fallback_exhausted_returns_error(models_client: TestClient) -> None:
    """POST /models/discover returns 200 with an error field when all fallback paths return 404."""
    import urllib.error

    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(None, 404, "Not Found", {}, None)):
        resp = models_client.post("/models/discover", json={"base_url": "http://localhost:8080"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["models"] == []
    assert body["error"] is not None
