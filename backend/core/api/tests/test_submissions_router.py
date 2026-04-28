"""Tests for the ``/run`` and ``/grid-search`` submission endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_GENERATION_MODELS,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
    PAYLOAD_OVERVIEW_REFLECTION_MODELS,
    PAYLOAD_OVERVIEW_TOTAL_PAIRS,
    PAYLOAD_OVERVIEW_USERNAME,
)
from ...registry import RegistryError
from ...service_gateway import ServiceError
from ..model_catalog import CatalogModel, ModelCatalogResponse

# noinspection PyProtectedMember
from ..routers import _helpers as _h
from ..routers import submissions as _sub_mod
from ..routers.submissions import create_submissions_router
from .mocks import fake_background_worker


class _FakeJobStore:
    """Minimal in-memory job store stub for the submissions router tests."""

    # create_job / set_payload_overview are the only write paths exercised here;
    # count_jobs feeds the quota check.

    def __init__(self, *, job_count: int = 0) -> None:
        """Initialise with a canned job count and empty job map.

        Args:
            job_count: Value returned from ``count_jobs`` (used by quota checks).
        """
        self._count = job_count
        self._jobs: dict[str, dict] = {}

    def count_jobs(self, *, username: str | None = None, **_: Any) -> int:
        """Return the canned job count regardless of filter args.

        Args:
            username: Ignored; preserved to match the real signature.
            **_: Ignored extra filters.

        Returns:
            The canned job count from construction.
        """
        return self._count

    def create_job(self, optimization_id: str) -> None:
        """Record a new job entry under ``optimization_id``.

        Args:
            optimization_id: Identifier of the new job.
        """
        self._jobs[optimization_id] = {}

    def set_payload_overview(self, optimization_id: str, overview: dict) -> None:
        """Persist an overview dict against an existing job id.

        Args:
            optimization_id: Job id to attach the overview to.
            overview: Overview payload dict (deep-copied).
        """
        self._jobs.setdefault(optimization_id, {})["overview"] = dict(overview)

    def created_ids(self) -> list[str]:
        """Return all job ids that were created via ``create_job``.

        Returns:
            List of optimization ids in insertion order.
        """
        return list(self._jobs.keys())


class _FakeService:
    """Service stub whose validate methods optionally raise a configured error."""

    def __init__(self, *, raise_on_validate: Exception | None = None) -> None:
        """Capture the exception (if any) to raise from validate methods.

        Args:
            raise_on_validate: Exception instance to raise from both validate methods.
        """
        self._exc = raise_on_validate

    def validate_payload(self, payload: Any) -> None:
        """Validate a run payload, raising the configured exception if set.

        Args:
            payload: Run payload (ignored; only the side effect matters).

        Raises:
            Exception: The configured ``raise_on_validate`` error, if any.
        """
        if self._exc:
            raise self._exc

    def validate_grid_search_payload(self, payload: Any) -> None:
        """Validate a grid-search payload, raising the configured exception if set.

        Args:
            payload: Grid-search payload (ignored; only the side effect matters).

        Raises:
            Exception: The configured ``raise_on_validate`` error, if any.
        """
        if self._exc:
            raise self._exc


def _run_payload() -> dict:
    """Build a minimal valid run payload for ``/run`` tests.

    Returns:
        A dict matching the run submission schema.
    """
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
    """Build a minimal valid grid-search payload for ``/grid-search`` tests.

    Returns:
        A dict matching the grid-search submission schema.
    """
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
    """Build a ``TestClient`` exposing the submissions router with stubbed worker.

    Args:
        service: Service stub used by the router.
        store: Fake job store wired into the router factory.
        monkeypatch: Pytest monkeypatch fixture to stub ``get_worker`` and notifier.

    Returns:
        A ``TestClient`` over a minimal FastAPI app.
    """
    worker = fake_background_worker()

    monkeypatch.setattr(_sub_mod, "get_worker", lambda *a, **kw: worker)
    monkeypatch.setattr(_sub_mod, "notify_job_started", lambda **_: None)

    app = FastAPI()
    app.include_router(create_submissions_router(service=service, job_store=store))
    return TestClient(app, raise_server_exceptions=False)


def test_submit_run_returns_201_with_optimization_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful run submission returns 201 with a fresh optimization id."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)

    resp = client.post("/run", json=_run_payload())

    assert resp.status_code == 201
    body = resp.json()
    assert "optimization_id" in body
    assert body["status"] == "pending"
    assert body["optimization_type"] == "run"


def test_submit_run_creates_job_in_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful submission creates exactly one matching job in the store."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)

    resp = client.post("/run", json=_run_payload())

    assert resp.status_code == 201
    created = store.created_ids()
    assert len(created) == 1
    assert created[0] == resp.json()["optimization_id"]


def test_submit_run_echoes_name_and_username(monkeypatch: pytest.MonkeyPatch) -> None:
    """The response body echoes ``name`` and ``username`` from the payload."""
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
    """A ``ServiceError`` from the service layer surfaces as a 400."""
    svc = _FakeService(raise_on_validate=ServiceError("bad module"))
    store = _FakeJobStore()
    client = _make_client(svc, store, monkeypatch=monkeypatch)

    resp = client.post("/run", json=_run_payload())

    assert resp.status_code == 400


def test_submit_run_returns_400_on_registry_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``RegistryError`` from the service layer surfaces as a 400."""
    svc = _FakeService(raise_on_validate=RegistryError("not registered"))
    store = _FakeJobStore()
    client = _make_client(svc, store, monkeypatch=monkeypatch)

    resp = client.post("/run", json=_run_payload())

    assert resp.status_code == 400


def test_submit_run_returns_409_when_user_at_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    """A user already at their quota is rejected with 409."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 5)
    store = _FakeJobStore(job_count=5)
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)

    resp = client.post("/run", json=_run_payload())

    assert resp.status_code == 409


def test_submit_run_returns_422_on_missing_required_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """A run payload missing ``username`` returns a 422."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _run_payload()
    del payload["username"]

    resp = client.post("/run", json=payload)

    assert resp.status_code == 422


def test_submit_run_returns_422_on_invalid_split_fractions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Split fractions that do not sum to 1.0 produce a 422."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _run_payload()
    payload["split_fractions"] = {"train": 0.5, "val": 0.5, "test": 0.5}

    resp = client.post("/run", json=payload)

    assert resp.status_code == 422


def test_submit_run_returns_422_on_empty_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty dataset is rejected at the schema layer with a 422."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _run_payload()
    payload["dataset"] = []

    resp = client.post("/run", json=payload)

    assert resp.status_code == 422


def test_submit_grid_search_returns_201(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful grid-search submission returns 201 with the right type tag."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)

    resp = client.post("/grid-search", json=_grid_payload())

    assert resp.status_code == 201
    body = resp.json()
    assert body["optimization_type"] == "grid_search"
    assert body["status"] == "pending"


def test_submit_grid_search_seed_assigned_when_null(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``null`` seed at submit time is replaced by a concrete seed in the overview."""
    # Reproducibility contract: when caller sends seed=None, the overview must persist a concrete seed.
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
    """A ``ServiceError`` during grid validation surfaces as a 400."""
    svc = _FakeService(raise_on_validate=ServiceError("bad optimizer"))
    store = _FakeJobStore()
    client = _make_client(svc, store, monkeypatch=monkeypatch)

    resp = client.post("/grid-search", json=_grid_payload())

    assert resp.status_code == 400


def test_submit_grid_search_returns_422_on_empty_generation_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty ``generation_models`` list is rejected at the schema layer with 422."""
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _grid_payload()
    payload["generation_models"] = []

    resp = client.post("/grid-search", json=payload)

    assert resp.status_code == 422


def test_submit_run_overview_contains_expected_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """The persisted run overview contains the expected canonical keys."""
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
    """The grid overview's ``total_pairs`` equals ``len(gen) * len(ref)``."""
    # Invariant: total_pairs in overview == len(gen) * len(ref).
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
    """A service without ``validate_grid_search_payload`` is tolerated and the job is enqueued."""
    # The route uses a hasattr guard so an older service implementation without
    # validate_grid_search_payload must NOT cause a 500 — the job is enqueued anyway.

    class _ServiceWithoutGridValidation:
        """Service stub that only implements ``validate_payload``."""

        def validate_payload(self, payload: Any) -> None:
            """Accept any run payload without raising."""

        # NOTE: no validate_grid_search_payload

    store = _FakeJobStore()
    client = _make_client(_ServiceWithoutGridValidation(), store, monkeypatch=monkeypatch)

    resp = client.post("/grid-search", json=_grid_payload())

    assert resp.status_code == 201
    assert resp.json()["optimization_type"] == "grid_search"


def _fake_catalog(*values: str) -> ModelCatalogResponse:
    """Build a synthetic catalog from a list of model id strings.

    Args:
        *values: Model id strings to include in the catalog.

    Returns:
        A ``ModelCatalogResponse`` containing one entry per id with provider ``openai``.
    """
    return ModelCatalogResponse(
        providers=[],
        models=[CatalogModel(value=v, label=v, provider="openai", available=True) for v in values],
    )


def test_submit_grid_search_use_all_generation_models_expands_from_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``use_all_available_generation_models`` expands to the catalog's full list."""
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
    """The ``use_all`` flag overrides any explicit client-supplied generation models."""
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
    """``use_all_available_reflection_models`` expands to the catalog's full list."""
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
    """Setting both ``use_all`` flags yields a Cartesian product over the catalog."""
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
    """An empty catalog plus the generation ``use_all`` flag returns a 400."""
    monkeypatch.setattr(_sub_mod, "get_catalog_cached", _fake_catalog)
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
    """An empty catalog plus the reflection ``use_all`` flag returns a 400."""
    monkeypatch.setattr(_sub_mod, "get_catalog_cached", _fake_catalog)
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _grid_payload()
    payload.pop("reflection_models")
    payload["use_all_available_reflection_models"] = True

    resp = client.post("/grid-search", json=payload)

    assert resp.status_code == 400
    assert "אין מודלים זמינים בקטלוג" in resp.json()["detail"]


_VISION_SIG_CODE = (
    "import dspy\n"
    "class VisionQA(dspy.Signature):\n"
    "    picture: dspy.Image = dspy.InputField()\n"
    "    question: str = dspy.InputField()\n"
    "    answer: str = dspy.OutputField()\n"
)


def _vision_catalog(*, vision_models: list[str], text_only_models: list[str] | None = None) -> ModelCatalogResponse:
    """Build a catalog with explicit vision-capable and text-only entries.

    Args:
        vision_models: Model id strings flagged ``supports_vision=True``.
        text_only_models: Model id strings flagged ``supports_vision=False``.

    Returns:
        A ``ModelCatalogResponse`` mixing the two groups.
    """
    models: list[CatalogModel] = [
        CatalogModel(value=v, label=v, provider="openai", available=True, supports_vision=True)
        for v in vision_models
    ]
    models.extend(
        CatalogModel(value=v, label=v, provider="openai", available=True, supports_vision=False)
        for v in text_only_models or []
    )
    return ModelCatalogResponse(providers=[], models=models)


def test_submit_run_rejects_image_signature_with_non_vision_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """A run with an image signature using a non-vision model is rejected with 400."""
    monkeypatch.setattr(
        _sub_mod,
        "get_catalog_cached",
        lambda: _vision_catalog(vision_models=[], text_only_models=["gpt-4o-mini"]),
    )
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _run_payload()
    payload["signature_code"] = _VISION_SIG_CODE
    payload["column_mapping"] = {
        "inputs": {"picture": "img", "question": "q"},
        "outputs": {"answer": "a"},
    }
    payload["dataset"] = [{"img": "https://example.com/cat.png", "q": "what?", "a": "cat"}]
    payload["model_settings"] = {"name": "gpt-4o-mini"}

    resp = client.post("/run", json=payload)

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    # Hebrew message includes the field name and the offending model identifier.
    assert "picture" in detail
    assert "gpt-4o-mini" in detail


def test_submit_run_accepts_image_signature_with_vision_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """A run with an image signature using a vision-capable model is accepted."""
    monkeypatch.setattr(
        _sub_mod,
        "get_catalog_cached",
        lambda: _vision_catalog(vision_models=["gpt-4o"]),
    )
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _run_payload()
    payload["signature_code"] = _VISION_SIG_CODE
    payload["column_mapping"] = {
        "inputs": {"picture": "img", "question": "q"},
        "outputs": {"answer": "a"},
    }
    payload["dataset"] = [{"img": "https://example.com/cat.png", "q": "what?", "a": "cat"}]
    payload["model_settings"] = {"name": "gpt-4o"}

    resp = client.post("/run", json=payload)

    assert resp.status_code == 201


def test_submit_run_text_signature_skips_vision_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pure text signature does not trigger the vision-capable model check."""
    # Empty catalog — would reject every model if the vision gate ran. It must not.
    monkeypatch.setattr(_sub_mod, "get_catalog_cached", lambda: _vision_catalog(vision_models=[]))
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)

    resp = client.post("/run", json=_run_payload())

    assert resp.status_code == 201


def test_submit_grid_search_rejects_image_signature_with_any_non_vision_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A grid search rejects image signatures if any selected model lacks vision support."""
    monkeypatch.setattr(
        _sub_mod,
        "get_catalog_cached",
        lambda: _vision_catalog(vision_models=["gpt-4o"], text_only_models=["text-only-model"]),
    )
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _grid_payload()
    payload["signature_code"] = _VISION_SIG_CODE
    payload["column_mapping"] = {
        "inputs": {"picture": "img", "question": "q"},
        "outputs": {"answer": "a"},
    }
    payload["dataset"] = [{"img": "https://example.com/cat.png", "q": "what?", "a": "cat"}]
    payload["generation_models"] = [{"name": "gpt-4o"}, {"name": "text-only-model"}]
    payload["reflection_models"] = [{"name": "gpt-4o"}]

    resp = client.post("/grid-search", json=payload)

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "text-only-model" in detail
    assert "gpt-4o" not in detail.split("text-only-model")[0] or "text-only-model" in detail


def test_submit_grid_search_accepts_image_signature_when_all_models_support_vision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A grid search accepts image signatures when every selected model supports vision."""
    monkeypatch.setattr(
        _sub_mod,
        "get_catalog_cached",
        lambda: _vision_catalog(vision_models=["gpt-4o", "gpt-4o-mini"]),
    )
    store = _FakeJobStore()
    client = _make_client(_FakeService(), store, monkeypatch=monkeypatch)
    payload = _grid_payload()
    payload["signature_code"] = _VISION_SIG_CODE
    payload["column_mapping"] = {
        "inputs": {"picture": "img", "question": "q"},
        "outputs": {"answer": "a"},
    }
    payload["dataset"] = [{"img": "https://example.com/cat.png", "q": "what?", "a": "cat"}]
    payload["generation_models"] = [{"name": "gpt-4o"}, {"name": "gpt-4o-mini"}]
    payload["reflection_models"] = [{"name": "gpt-4o"}]

    resp = client.post("/grid-search", json=payload)

    assert resp.status_code == 201
