from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# noinspection PyProtectedMember
from ..routers import _helpers as _h  # noqa: SLF001
from ..routers import submissions as _sub_mod
from ..routers.submissions import create_submissions_router
from .mocks import fake_background_worker
from ...constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_GENERATION_MODELS,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
    PAYLOAD_OVERVIEW_REFLECTION_MODELS,
    PAYLOAD_OVERVIEW_TOTAL_PAIRS,
    PAYLOAD_OVERVIEW_USERNAME,
)
from ..model_catalog import CatalogModel, ModelCatalogResponse
from ...registry import RegistryError
from ...service_gateway import ServiceError

class _FakeJobStore:
    """Minimal job store for submissions tests.

    create_job / set_payload_overview are the only write paths; count_jobs
    drives quota enforcement.
    """

    def __init__(self, *, job_count: int = 0) -> None:
        self._count = job_count
        self._jobs: dict[str, dict] = {}

    def count_jobs(self, *, username: str | None = None, **_: Any) -> int:
        return self._count

    def create_job(self, optimization_id: str) -> None:
        self._jobs[optimization_id] = {}

    def set_payload_overview(self, optimization_id: str, overview: dict) -> None:
        self._jobs.setdefault(optimization_id, {})["overview"] = dict(overview)

    def created_ids(self) -> list[str]:
        return list(self._jobs.keys())

class _FakeService:
    """Service that always passes validation unless told to raise."""

    def __init__(self, *, raise_on_validate: Exception | None = None) -> None:
        self._exc = raise_on_validate

    def validate_payload(self, payload: Any) -> None:
        if self._exc:
            raise self._exc

    def validate_grid_search_payload(self, payload: Any) -> None:
        if self._exc:
            raise self._exc

def _run_payload() -> dict:
    return {
        "name": "test-run",
        "username": "alice",
        "module_name": "predict",
        "module_kwargs": {},
        "signature_code": "class Sig(dspy.Signature): q: str = dspy.InputField(); a: str = dspy.OutputField()",
        "metric_code": "def metric(example, pred, trace=None): return 1.0",
        "optimizer_name": "gepa",
        "optimizer_kwargs": {},
        "compile_kwargs": {},
        "dataset": [{"question": "Q?", "answer": "A"}],
        "column_mapping": {"inputs": {"q": "question"}, "outputs": {"a": "answer"}},
        "split_fractions": {"train": 0.7, "val": 0.15, "test": 0.15},
        "shuffle": True,
        "seed": 42,
        "dataset_filename": "test.csv",
        "model_settings": {"name": "gpt-4o-mini"},
    }

def _grid_payload() -> dict:
    return {
        "name": "test-grid",
        "username": "alice",
        "module_name": "predict",
        "module_kwargs": {},
        "signature_code": "class Sig(dspy.Signature): q: str = dspy.InputField(); a: str = dspy.OutputField()",
        "metric_code": "def metric(example, pred, trace=None): return 1.0",
        "optimizer_name": "gepa",
        "optimizer_kwargs": {},
        "compile_kwargs": {},
        "dataset": [{"question": "Q?", "answer": "A"}],
        "column_mapping": {"inputs": {"q": "question"}, "outputs": {"a": "answer"}},
        "split_fractions": {"train": 0.7, "val": 0.15, "test": 0.15},
        "shuffle": True,
        "seed": None,
        "dataset_filename": "grid.csv",
        "generation_models": [{"name": "gpt-4o-mini"}],
        "reflection_models": [{"name": "gpt-4o"}],
    }

def _make_client(
    service: Any,
    store: _FakeJobStore,
    *,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """Build a TestClient wired to a submissions router with a fake worker."""
    worker = fake_background_worker()

    monkeypatch.setattr(_sub_mod, "get_worker", lambda *a, **kw: worker)
    monkeypatch.setattr(_sub_mod, "notify_job_started", lambda **_: None)

    app = FastAPI()
    app.include_router(create_submissions_router(service=service, job_store=store))
    return TestClient(app, raise_server_exceptions=False)

def test_submit_run_returns_201_with_optimization_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /run returns 201 with an optimization_id and status=pending."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)

    resp = client.post("/run", json=_run_payload())

    assert resp.status_code == 201
    body = resp.json()
    assert "optimization_id" in body
    assert body["status"] == "pending"
    assert body["optimization_type"] == "run"

def test_submit_run_creates_job_in_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /run creates exactly one job in the store whose id matches the response."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)

    resp = client.post("/run", json=_run_payload())

    assert resp.status_code == 201
    created = store.created_ids()
    assert len(created) == 1
    assert created[0] == resp.json()["optimization_id"]

def test_submit_run_echoes_name_and_username(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /run echoes back the submitted name and username in the response body."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _run_payload()
    payload["name"] = "my-run"
    payload["username"] = "bob"

    resp = client.post("/run", json=payload)

    body = resp.json()
    assert body["name"] == "my-run"
    assert body["username"] == "bob"

def test_submit_run_returns_400_on_service_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /run returns 400 when the service raises a ServiceError during validation."""
    svc = _FakeService(raise_on_validate=ServiceError("bad module"))
    store = _FakeJobStore()
    client = _make_client(svc, store, monkeypatch=monkeypatch)

    resp = client.post("/run", json=_run_payload())

    assert resp.status_code == 400

def test_submit_run_returns_400_on_registry_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /run returns 400 when the service raises a RegistryError during validation."""
    svc = _FakeService(raise_on_validate=RegistryError("not registered"))
    store = _FakeJobStore()
    client = _make_client(svc, store, monkeypatch=monkeypatch)

    resp = client.post("/run", json=_run_payload())

    assert resp.status_code == 400

def test_submit_run_returns_409_when_user_at_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /run returns 409 when the user has reached their job quota."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 5)
    store = _FakeJobStore(job_count=5)
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)

    resp = client.post("/run", json=_run_payload())

    assert resp.status_code == 409

def test_submit_run_returns_422_on_missing_required_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /run returns 422 when a required field (username) is absent from the body."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _run_payload()
    del payload["username"]

    resp = client.post("/run", json=payload)

    assert resp.status_code == 422

def test_submit_run_returns_422_on_invalid_split_fractions(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /run returns 422 when split_fractions do not sum to 1.0."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _run_payload()
    payload["split_fractions"] = {"train": 0.5, "val": 0.5, "test": 0.5}

    resp = client.post("/run", json=payload)

    assert resp.status_code == 422

def test_submit_run_returns_422_on_empty_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /run returns 422 when the dataset list is empty."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _run_payload()
    payload["dataset"] = []

    resp = client.post("/run", json=payload)

    assert resp.status_code == 422

def test_submit_grid_search_returns_201(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /grid-search returns 201 with optimization_type=grid_search and status=pending."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)

    resp = client.post("/grid-search", json=_grid_payload())

    assert resp.status_code == 201
    body = resp.json()
    assert body["optimization_type"] == "grid_search"
    assert body["status"] == "pending"

def test_submit_grid_search_seed_assigned_when_null(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /grid-search auto-assigns a non-null seed in the overview when seed=None."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _grid_payload()
    payload["seed"] = None

    resp = client.post("/grid-search", json=payload)

    assert resp.status_code == 201
    opt_id = resp.json()["optimization_id"]
    stored = store._jobs[opt_id]["overview"]
    assert stored.get("seed") is not None

def test_submit_grid_search_returns_400_on_service_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /grid-search returns 400 when the service raises a ServiceError during validation."""
    svc = _FakeService(raise_on_validate=ServiceError("bad optimizer"))
    store = _FakeJobStore()
    client = _make_client(svc, store, monkeypatch=monkeypatch)

    resp = client.post("/grid-search", json=_grid_payload())

    assert resp.status_code == 400

def test_submit_grid_search_returns_422_on_empty_generation_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /grid-search returns 422 when generation_models is an empty list."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _grid_payload()
    payload["generation_models"] = []

    resp = client.post("/grid-search", json=payload)

    assert resp.status_code == 422

def test_submit_run_overview_contains_expected_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """The payload overview stored for a /run job must include all protocol keys."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)

    resp = client.post("/run", json=_run_payload())

    assert resp.status_code == 201
    opt_id = resp.json()["optimization_id"]
    overview = store._jobs[opt_id]["overview"]

    assert overview[PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE] == OPTIMIZATION_TYPE_RUN
    assert overview[PAYLOAD_OVERVIEW_USERNAME] == "alice"
    assert overview[PAYLOAD_OVERVIEW_MODULE_NAME] == "predict"
    assert overview[PAYLOAD_OVERVIEW_OPTIMIZER_NAME] == "gepa"
    assert PAYLOAD_OVERVIEW_MODEL_NAME in overview

def test_submit_grid_search_overview_contains_total_pairs(monkeypatch: pytest.MonkeyPatch) -> None:
    """total_pairs in the grid-search overview must equal len(gen) * len(ref)."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _grid_payload()
    # 2 generation models × 1 reflection model = 2 pairs
    payload["generation_models"] = [{"name": "gpt-4o-mini"}, {"name": "gpt-4o"}]
    payload["reflection_models"] = [{"name": "gpt-4o"}]

    resp = client.post("/grid-search", json=payload)

    assert resp.status_code == 201
    opt_id = resp.json()["optimization_id"]
    overview = store._jobs[opt_id]["overview"]

    assert overview[PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE] == OPTIMIZATION_TYPE_GRID_SEARCH
    assert overview[PAYLOAD_OVERVIEW_TOTAL_PAIRS] == 2

def test_submit_grid_search_skips_validation_when_service_lacks_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /grid-search still accepts the job when the service lacks validate_grid_search_payload.
    route must still accept and enqueue the job (hasattr guard skips validation).
    """

    class _ServiceWithoutGridValidation:
        def validate_payload(self, payload: Any) -> None:
            pass
        # NOTE: no validate_grid_search_payload

    store = _FakeJobStore()
    client = _make_client(_ServiceWithoutGridValidation(), store, monkeypatch=monkeypatch)

    resp = client.post("/grid-search", json=_grid_payload())

    assert resp.status_code == 201
    assert resp.json()["optimization_type"] == "grid_search"


def _fake_catalog(*values: str) -> ModelCatalogResponse:
    """Build a ``ModelCatalogResponse`` containing one available model per value.

    Args:
        *values: LiteLLM-style model identifiers to expose as available.

    Returns:
        A catalog response with no providers and one ``CatalogModel`` per value.
    """
    return ModelCatalogResponse(
        providers=[],
        models=[
            CatalogModel(value=v, label=v, provider="openai", available=True) for v in values
        ],
    )


def test_submit_grid_search_use_all_generation_models_expands_from_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /grid-search with use_all_available_generation_models=True replaces generation_models from the catalog."""
    monkeypatch.setattr(
        _sub_mod,
        "get_catalog_cached",
        lambda: _fake_catalog("openai/gpt-4o-mini", "openai/gpt-4o", "anthropic/claude-3-5-sonnet"),
    )
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _grid_payload()
    payload.pop("generation_models")
    payload["use_all_available_generation_models"] = True

    resp = client.post("/grid-search", json=payload)

    assert resp.status_code == 201
    opt_id = resp.json()["optimization_id"]
    overview = store._jobs[opt_id]["overview"]
    gen_names = [m["name"] for m in overview[PAYLOAD_OVERVIEW_GENERATION_MODELS]]
    assert gen_names == ["openai/gpt-4o-mini", "openai/gpt-4o", "anthropic/claude-3-5-sonnet"]
    assert overview[PAYLOAD_OVERVIEW_TOTAL_PAIRS] == 3


def test_submit_grid_search_use_all_generation_models_overrides_client_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """use_all_available_generation_models=True discards any generation_models the client supplied."""
    monkeypatch.setattr(
        _sub_mod,
        "get_catalog_cached",
        lambda: _fake_catalog("openai/gpt-4o-mini"),
    )
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _grid_payload()
    payload["generation_models"] = [{"name": "bogus-legacy-model"}]
    payload["use_all_available_generation_models"] = True

    resp = client.post("/grid-search", json=payload)

    assert resp.status_code == 201
    opt_id = resp.json()["optimization_id"]
    overview = store._jobs[opt_id]["overview"]
    gen_names = [m["name"] for m in overview[PAYLOAD_OVERVIEW_GENERATION_MODELS]]
    assert gen_names == ["openai/gpt-4o-mini"]


def test_submit_grid_search_use_all_reflection_models_expands_from_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /grid-search with use_all_available_reflection_models=True replaces reflection_models from the catalog."""
    monkeypatch.setattr(
        _sub_mod,
        "get_catalog_cached",
        lambda: _fake_catalog("openai/gpt-4o-mini", "openai/gpt-4o"),
    )
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _grid_payload()
    payload.pop("reflection_models")
    payload["use_all_available_reflection_models"] = True

    resp = client.post("/grid-search", json=payload)

    assert resp.status_code == 201
    opt_id = resp.json()["optimization_id"]
    overview = store._jobs[opt_id]["overview"]
    ref_names = [m["name"] for m in overview[PAYLOAD_OVERVIEW_REFLECTION_MODELS]]
    assert ref_names == ["openai/gpt-4o-mini", "openai/gpt-4o"]
    assert overview[PAYLOAD_OVERVIEW_TOTAL_PAIRS] == len(payload["generation_models"]) * 2


def test_submit_grid_search_use_all_both_sides_multiplies_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both flags set expand both lists to the catalog; total_pairs is count × count."""
    monkeypatch.setattr(
        _sub_mod,
        "get_catalog_cached",
        lambda: _fake_catalog("openai/gpt-4o-mini", "openai/gpt-4o", "anthropic/claude-3-5-sonnet"),
    )
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _grid_payload()
    payload.pop("generation_models")
    payload.pop("reflection_models")
    payload["use_all_available_generation_models"] = True
    payload["use_all_available_reflection_models"] = True

    resp = client.post("/grid-search", json=payload)

    assert resp.status_code == 201
    overview = store._jobs[resp.json()["optimization_id"]]["overview"]
    assert len(overview[PAYLOAD_OVERVIEW_GENERATION_MODELS]) == 3
    assert len(overview[PAYLOAD_OVERVIEW_REFLECTION_MODELS]) == 3
    assert overview[PAYLOAD_OVERVIEW_TOTAL_PAIRS] == 9


def test_submit_grid_search_use_all_generation_models_returns_400_when_catalog_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /grid-search with use_all_available_generation_models=True returns 400 when no models are available."""
    monkeypatch.setattr(_sub_mod, "get_catalog_cached", lambda: _fake_catalog())
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _grid_payload()
    payload.pop("generation_models")
    payload["use_all_available_generation_models"] = True

    resp = client.post("/grid-search", json=payload)

    assert resp.status_code == 400
    assert "אין מודלים זמינים בקטלוג" in resp.json()["detail"]


def test_submit_grid_search_use_all_reflection_models_returns_400_when_catalog_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /grid-search with use_all_available_reflection_models=True returns 400 when no models are available."""
    monkeypatch.setattr(_sub_mod, "get_catalog_cached", lambda: _fake_catalog())
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _grid_payload()
    payload.pop("reflection_models")
    payload["use_all_available_reflection_models"] = True

    resp = client.post("/grid-search", json=payload)

    assert resp.status_code == 400
    assert "אין מודלים זמינים בקטלוג" in resp.json()["detail"]
