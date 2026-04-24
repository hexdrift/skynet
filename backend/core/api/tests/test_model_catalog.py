from __future__ import annotations

import pytest

from ..model_catalog import CatalogModel, CatalogProvider, ModelCatalogResponse, _make_label, get_catalog  # type: ignore[attr-defined]

@pytest.mark.parametrize(
    "model_id,expected",
    [
        ("gpt-4o-mini", "gpt-4o-mini"),
        ("openai/gpt-4o-mini", "gpt-4o-mini"),
        ("together_ai/mistral-7b-instruct-v0.1", "mistral-7b-instruct-v0.1"),
        ("anthropic/claude-3-5-haiku-20241022", "claude-3-5-haiku-20241022"),
    ],
    ids=["no_prefix", "openai_prefix", "together_ai_prefix", "anthropic_prefix"],
)
def test_make_label_strips_provider_prefix(model_id: str, expected: str) -> None:
    assert _make_label(model_id) == expected

def test_make_label_leaves_id_without_slash_untouched() -> None:
    """_make_label returns the id unchanged when there is no provider prefix."""
    assert _make_label("gpt-4o") == "gpt-4o"

def test_catalog_model_defaults() -> None:
    """CatalogModel has supports_thinking=False, available=False, and max_input_tokens=None by default."""
    m = CatalogModel(value="openai/gpt-4o", label="gpt-4o", provider="openai")
    assert m.supports_thinking is False
    assert m.available is False
    assert m.max_input_tokens is None

def test_catalog_model_stores_all_fields() -> None:
    """CatalogModel stores all provided fields including optional thinking/token fields."""
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
    """CatalogProvider.has_env_key defaults to False when not supplied."""
    p = CatalogProvider(slug="openai", label="OpenAI")
    assert p.has_env_key is False

def test_catalog_provider_stores_env_var_and_url() -> None:
    """CatalogProvider stores env_var, default_base_url, and has_env_key when provided."""
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
    """ModelCatalogResponse accepts empty providers and models lists."""
    resp = ModelCatalogResponse(providers=[], models=[])
    assert resp.providers == []
    assert resp.models == []

def test_model_catalog_response_preserves_order() -> None:
    """ModelCatalogResponse preserves the insertion order of the models list."""
    models = [
        CatalogModel(value="openai/gpt-4o-mini", label="gpt-4o-mini", provider="openai", available=True),
        CatalogModel(value="anthropic/claude-3-5-haiku-20241022", label="claude-3-5-haiku-20241022", provider="anthropic", available=True),
    ]
    resp = ModelCatalogResponse(providers=[], models=models)
    assert resp.models[0].value == "openai/gpt-4o-mini"
    assert resp.models[1].provider == "anthropic"

def test_get_catalog_returns_correct_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_catalog() must return a ModelCatalogResponse with typed lists.

    We monkeypatch litellm.get_valid_models to avoid requiring API keys and to
    make results deterministic. The test only asserts structural invariants, not
    specific models (which change as LiteLLM updates its registry).
    """
    import litellm
    # Inject two synthetic chat-mode entries into the cost table, then mark
    # one as valid so at least one model appears in the output.
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

    result = get_catalog()

    assert isinstance(result, ModelCatalogResponse)
    assert isinstance(result.providers, list)
    assert isinstance(result.models, list)
    # The injected model should be available and visible
    values = [m.value for m in result.models]
    assert any("fakeprovider-model-a" in v for v in values)

def test_get_catalog_only_returns_available_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Models not in valid_set must be excluded from the response."""
    import litellm

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
    monkeypatch.setattr(litellm, "get_valid_models", lambda: [])  # nothing valid

    result = get_catalog()

    assert result.models == []

def test_get_catalog_deduplicates_dated_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dated variant (gpt-4o-2024-08-06) should be excluded when the base
    name (gpt-4o) exists in the cost table."""
    import litellm

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

    result = get_catalog()

    values = [m.value for m in result.models]
    # Dated variant must not appear
    assert not any("2024-08-06" in v for v in values)
    # Base must appear
    assert any(v.endswith("gpt-4o") for v in values)

def test_get_catalog_filters_out_non_chat_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Embedding/completion models must be filtered to chat only."""
    import litellm

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

    result = get_catalog()

    assert result.models == []

def test_get_catalog_handles_valid_models_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """If get_valid_models raises, catalog should return empty models list
    (no exception propagated)."""
    import litellm
    from ..model_catalog import get_catalog

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

    # Should not raise
    result = get_catalog()
    assert isinstance(result, ModelCatalogResponse)
    # model is not in valid_set so it's unavailable → filtered out
    assert result.models == []
