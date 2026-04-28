"""Unit tests for the model catalog DTOs and ``get_catalog`` helper."""

from __future__ import annotations

import litellm
import pytest

from .. import model_catalog as mc
from ..model_catalog import (  # type: ignore[attr-defined]
    CatalogModel,
    CatalogProvider,
    ModelCatalogResponse,
    _make_label,
    get_catalog,
)


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("gpt-4o-mini", "gpt-4o-mini"),
        ("openai/gpt-4o-mini", "gpt-4o-mini"),
        ("together_ai/mistral-7b-instruct-v0.1", "mistral-7b-instruct-v0.1"),
        ("anthropic/claude-3-5-haiku-20241022", "claude-3-5-haiku-20241022"),
    ],
    ids=["no_prefix", "openai_prefix", "together_ai_prefix", "anthropic_prefix"],
)
def test_make_label_strips_provider_prefix(model_id: str, expected: str) -> None:
    """``_make_label`` strips known provider prefixes from a model id."""
    assert _make_label(model_id) == expected


def test_make_label_leaves_id_without_slash_untouched() -> None:
    """An id with no provider prefix is returned unchanged."""
    assert _make_label("gpt-4o") == "gpt-4o"


def test_catalog_model_defaults() -> None:
    """Optional fields default to ``False`` / ``None`` on ``CatalogModel``."""
    m = CatalogModel(value="openai/gpt-4o", label="gpt-4o", provider="openai")
    assert m.supports_thinking is False
    assert m.supports_vision is False
    assert m.available is False
    assert m.max_input_tokens is None


def test_catalog_model_stores_all_fields() -> None:
    """Explicitly-supplied fields are preserved on ``CatalogModel``."""
    m = CatalogModel(
        value="openai/gpt-4o",
        label="gpt-4o",
        provider="openai",
        supports_thinking=True,
        available=True,
        max_input_tokens=128000,
    )
    assert m.supports_thinking is True
    assert m.available is True
    assert m.max_input_tokens == 128000


def test_catalog_provider_has_env_key_defaults_false() -> None:
    """``has_env_key`` defaults to ``False`` on ``CatalogProvider``."""
    p = CatalogProvider(slug="openai", label="OpenAI")
    assert p.has_env_key is False


def test_catalog_provider_stores_env_var_and_url() -> None:
    """Provider env vars and base URLs round-trip through ``CatalogProvider``."""
    p = CatalogProvider(
        slug="openai",
        label="OpenAI",
        env_var="OPENAI_API_KEY",
        default_base_url="https://api.openai.com/v1",
        has_env_key=True,
    )
    assert p.env_var == "OPENAI_API_KEY"
    assert p.default_base_url == "https://api.openai.com/v1"
    assert p.has_env_key is True


def test_model_catalog_response_empty_lists() -> None:
    """An empty response carries empty ``providers`` and ``models`` lists."""
    resp = ModelCatalogResponse(providers=[], models=[])
    assert resp.providers == []
    assert resp.models == []


def test_model_catalog_response_preserves_order() -> None:
    """Model insertion order is preserved on the response."""
    models = [
        CatalogModel(value="openai/gpt-4o-mini", label="gpt-4o-mini", provider="openai", available=True),
        CatalogModel(
            value="anthropic/claude-3-5-haiku-20241022",
            label="claude-3-5-haiku-20241022",
            provider="anthropic",
            available=True,
        ),
    ]
    resp = ModelCatalogResponse(providers=[], models=models)
    assert resp.models[0].value == "openai/gpt-4o-mini"
    assert resp.models[1].provider == "anthropic"


def test_get_catalog_returns_correct_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_catalog`` returns a structured response of providers and models.

    Monkeypatches ``litellm.get_valid_models`` to avoid API keys and to make
    results deterministic. Asserts only structural invariants -- specific
    models change as LiteLLM updates its registry.
    """
    fake_cost: dict = dict(litellm.model_cost)
    fake_cost["fakeprovider-model-a"] = {
        "mode": "chat",
        "litellm_provider": "openai",
        "supports_reasoning": False,
        "max_input_tokens": 4096,
        "input_cost_per_token": 0,
        "output_cost_per_token": 0,
    }

    monkeypatch.setattr(litellm, "model_cost", fake_cost)
    monkeypatch.setattr(litellm, "get_valid_models", lambda: ["fakeprovider-model-a"])
    monkeypatch.setattr(mc, "_probe_all_providers", dict)

    result = get_catalog()

    assert isinstance(result, ModelCatalogResponse)
    assert isinstance(result.providers, list)
    assert isinstance(result.models, list)
    # The injected model should be available and visible
    values = [m.value for m in result.models]
    assert any("fakeprovider-model-a" in v for v in values)


def test_get_catalog_only_returns_available_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Models that aren't reported by ``get_valid_models`` are filtered out."""
    fake_cost: dict = {
        "only-in-registry": {
            "mode": "chat",
            "litellm_provider": "openai",
            "supports_reasoning": False,
            "max_input_tokens": 4096,
            "input_cost_per_token": 0,
            "output_cost_per_token": 0,
        }
    }
    monkeypatch.setattr(litellm, "model_cost", fake_cost)
    monkeypatch.setattr(litellm, "get_valid_models", list)
    monkeypatch.setattr(mc, "_probe_all_providers", dict)

    result = get_catalog()

    assert result.models == []


def test_get_catalog_deduplicates_dated_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dated variants are dropped when the base model id is also present.

    A dated variant (``gpt-4o-2024-08-06``) is excluded when the base name
    (``gpt-4o``) exists in the cost table.
    """
    fake_cost: dict = {
        "gpt-4o": {
            "mode": "chat",
            "litellm_provider": "openai",
            "supports_reasoning": False,
            "max_input_tokens": 128000,
            "input_cost_per_token": 0,
            "output_cost_per_token": 0,
        },
        "gpt-4o-2024-08-06": {
            "mode": "chat",
            "litellm_provider": "openai",
            "supports_reasoning": False,
            "max_input_tokens": 128000,
            "input_cost_per_token": 0,
            "output_cost_per_token": 0,
        },
    }
    monkeypatch.setattr(litellm, "model_cost", fake_cost)
    monkeypatch.setattr(litellm, "get_valid_models", lambda: ["gpt-4o", "gpt-4o-2024-08-06"])
    monkeypatch.setattr(mc, "_probe_all_providers", dict)

    result = get_catalog()

    values = [m.value for m in result.models]
    # Dated variant must not appear
    assert not any("2024-08-06" in v for v in values)
    # Base must appear
    assert any(v.endswith("gpt-4o") for v in values)


def test_get_catalog_filters_out_non_chat_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only chat-mode entries are relevant for DSPy LMs; others are filtered."""
    fake_cost: dict = {
        "text-embedding-ada-002": {
            "mode": "embedding",
            "litellm_provider": "openai",
            "max_input_tokens": 8192,
            "input_cost_per_token": 0,
            "output_cost_per_token": 0,
        },
    }
    monkeypatch.setattr(litellm, "model_cost", fake_cost)
    monkeypatch.setattr(litellm, "get_valid_models", lambda: ["text-embedding-ada-002"])
    monkeypatch.setattr(mc, "_probe_all_providers", dict)

    result = get_catalog()

    assert result.models == []


def test_get_catalog_propagates_supports_vision_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """``supports_vision`` is propagated from the cost table to the catalog."""
    fake_cost: dict = {
        "vision-model": {
            "mode": "chat",
            "litellm_provider": "openai",
            "supports_reasoning": False,
            "supports_vision": True,
            "max_input_tokens": 128000,
            "input_cost_per_token": 0,
            "output_cost_per_token": 0,
        },
        "text-only-model": {
            "mode": "chat",
            "litellm_provider": "openai",
            "supports_reasoning": False,
            "max_input_tokens": 8192,
            "input_cost_per_token": 0,
            "output_cost_per_token": 0,
        },
    }
    monkeypatch.setattr(litellm, "model_cost", fake_cost)
    monkeypatch.setattr(litellm, "get_valid_models", lambda: ["vision-model", "text-only-model"])
    monkeypatch.setattr(mc, "_probe_all_providers", dict)

    result = get_catalog()

    by_value = {m.value: m for m in result.models}
    assert by_value["openai/vision-model"].supports_vision is True
    assert by_value["openai/text-only-model"].supports_vision is False


def test_get_catalog_handles_valid_models_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failure inside ``get_valid_models`` is swallowed into an empty list.

    If ``get_valid_models`` raises, the catalog returns an empty models list
    rather than propagating the exception.
    """
    fake_cost: dict = {
        "gpt-4o": {
            "mode": "chat",
            "litellm_provider": "openai",
            "supports_reasoning": False,
            "max_input_tokens": 128000,
            "input_cost_per_token": 0,
            "output_cost_per_token": 0,
        },
    }
    monkeypatch.setattr(litellm, "model_cost", fake_cost)
    monkeypatch.setattr(litellm, "get_valid_models", lambda: (_ for _ in ()).throw(RuntimeError("API error")))
    monkeypatch.setattr(mc, "_probe_all_providers", dict)

    # Should not raise
    result = get_catalog()
    assert isinstance(result, ModelCatalogResponse)
    # model is not in valid_set so it's unavailable → filtered out
    assert result.models == []
