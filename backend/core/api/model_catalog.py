"""Dynamic model catalog powered by LiteLLM's ``model_cost`` registry.

LiteLLM ships ``model_prices_and_context_window.json`` — ~2600 models with
metadata (provider, mode, context window, ``supports_reasoning``, etc.).
We filter to chat-mode models, de-duplicate dated variants, and mark which
providers have active API keys via ``litellm.get_valid_models()``.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional, Set

import litellm
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)



class CatalogModel(BaseModel):
    """A single model entry exposed to the frontend."""

    value: str = Field(..., description="Canonical LiteLLM model ID (e.g. 'gpt-4o-mini').")
    label: str = Field(..., description="Human-friendly display name.")
    provider: str = Field(..., description="Provider slug for grouping (e.g. 'openai').")
    supports_thinking: bool = Field(default=False, description="Model supports reasoning_effort.")
    available: bool = Field(default=False, description="True if backend has an API key for this model.")
    max_input_tokens: Optional[int] = Field(default=None, description="Context window size.")


class CatalogProvider(BaseModel):
    """A provider section in the catalog."""

    slug: str
    label: str
    env_var: Optional[str] = None
    default_base_url: Optional[str] = None
    has_env_key: bool = False


class ModelCatalogResponse(BaseModel):
    """Response for GET /models."""

    providers: List[CatalogProvider]
    models: List[CatalogModel]


# Maps LiteLLM provider slug → (display label, env var, default base URL).

_PROVIDER_META: Dict[str, tuple[str, Optional[str], Optional[str]]] = {
    "openai": ("OpenAI", "OPENAI_API_KEY", "https://api.openai.com/v1"),
    "anthropic": ("Anthropic", "ANTHROPIC_API_KEY", "https://api.anthropic.com"),
    "gemini": ("Google Gemini", "GEMINI_API_KEY", None),
    "groq": ("Groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1"),
    "deepseek": ("DeepSeek", "DEEPSEEK_API_KEY", "https://api.deepseek.com"),
    "xai": ("xAI (Grok)", "XAI_API_KEY", "https://api.x.ai/v1"),
    "together_ai": ("Together AI", "TOGETHERAI_API_KEY", "https://api.together.xyz/v1"),
    "openrouter": ("OpenRouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
    "cerebras": ("Cerebras", "CEREBRAS_API_KEY", None),
    "fireworks_ai": ("Fireworks AI", "FIREWORKS_API_KEY", None),
    "cohere_chat": ("Cohere", "COHERE_API_KEY", None),
    "mistral": ("Mistral", "MISTRAL_API_KEY", None),
    "ollama": ("Ollama (self-hosted)", None, "http://localhost:11434"),
}

# Date-suffixed variant pattern: e.g. "gpt-4o-2024-08-06", "o3-mini-2025-01-31"
_DATE_SUFFIX_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def _make_label(model_id: str) -> str:
    """Turn a LiteLLM model ID into a human-friendly label.

    Args:
        model_id: Raw LiteLLM model identifier, optionally prefixed with a provider.

    Returns:
        The model name with any provider prefix stripped.
    """

    # Strip provider prefix if present (e.g. "openai/gpt-4o" → "gpt-4o")
    name = model_id.split("/", 1)[-1] if "/" in model_id else model_id
    return name


def get_catalog() -> ModelCatalogResponse:
    """Build a model catalog from LiteLLM's bundled model registry.

    - Filters to ``mode == "chat"`` models only.
    - De-duplicates dated variants (keeps the base name).
    - Uses ``litellm.get_valid_models()`` to flag available models.
    - Reads ``supports_reasoning`` from LiteLLM metadata.

    Returns:
        ModelCatalogResponse containing providers and available models.
    """

    cost: Dict[str, dict] = litellm.model_cost
    try:
        valid_set: Set[str] = set(litellm.get_valid_models())
    except Exception:
        logger.warning("litellm.get_valid_models() failed; marking none as available")
        valid_set = set()

    seen_providers: Dict[str, CatalogProvider] = {}
    models: List[CatalogModel] = []
    base_names_seen: Set[str] = set()

    for model_id, meta in cost.items():
        if meta.get("mode") != "chat":
            continue

        provider_slug: str = meta.get("litellm_provider", "unknown")

        if provider_slug not in _PROVIDER_META:
            continue

        # De-duplicate dated variants — if "gpt-4o" exists, skip "gpt-4o-2024-08-06"
        base_name = _DATE_SUFFIX_RE.sub("", model_id)
        if base_name != model_id and base_name in cost:
            continue  # prefer the un-dated base entry

        # Skip if we already have this base name (handles duplicates)
        if base_name in base_names_seen:
            continue
        base_names_seen.add(base_name)

        if provider_slug not in seen_providers:
            label, env_var, default_url = _PROVIDER_META[provider_slug]
            has_key = bool(env_var and os.getenv(env_var))
            seen_providers[provider_slug] = CatalogProvider(
                slug=provider_slug,
                label=label,
                env_var=env_var,
                default_base_url=default_url,
                has_env_key=has_key,
            )

        # Ensure dspy.LM-compatible provider prefix (e.g. "openai/gpt-4o-mini")
        prefixed_id = model_id if "/" in model_id else f"{provider_slug}/{model_id}"

        models.append(CatalogModel(
            value=prefixed_id,
            label=_make_label(model_id),
            provider=provider_slug,
            supports_thinking=bool(meta.get("supports_reasoning")),
            available=model_id in valid_set or prefixed_id in valid_set,
            max_input_tokens=meta.get("max_input_tokens"),
        ))

    # Only return models the backend has API keys for
    models = [m for m in models if m.available]

    models.sort(key=lambda m: (m.provider, m.value))

    # Only return providers that have at least one available model or no key needed (ollama)
    available_providers = {m.provider for m in models}
    providers = sorted(
        (p for p in seen_providers.values() if p.slug in available_providers or not p.env_var),
        key=lambda p: (not p.has_env_key, p.slug),
    )

    return ModelCatalogResponse(providers=providers, models=models)


_cached_response: Optional[ModelCatalogResponse] = None


def get_catalog_cached() -> ModelCatalogResponse:
    """Return the catalog, computing it once and caching forever.

    Returns:
        ModelCatalogResponse served from the process-wide cache.
    """

    global _cached_response
    if _cached_response is None:
        _cached_response = get_catalog()
        logger.info("Model catalog built: %d providers, %d models", len(_cached_response.providers), len(_cached_response.models))
    return _cached_response
