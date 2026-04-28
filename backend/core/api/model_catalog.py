"""Dynamic model catalog powered by LiteLLM's ``model_cost`` registry.

LiteLLM ships ``model_prices_and_context_window.json`` — ~2600 models with
metadata (provider, mode, context window, ``supports_reasoning``, etc.).
We filter to chat-mode models, de-duplicate dated variants, and mark which
providers have active API keys via ``litellm.get_valid_models()``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import litellm
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CatalogModel(BaseModel):
    """A single model entry exposed to the frontend."""

    value: str = Field(..., description="Canonical LiteLLM model ID (e.g. 'gpt-4o-mini').")
    label: str = Field(..., description="Human-friendly display name.")
    provider: str = Field(..., description="Provider slug for grouping (e.g. 'openai').")
    supports_thinking: bool = Field(default=False, description="Model supports reasoning_effort.")
    supports_vision: bool = Field(
        default=False,
        description="Model accepts image inputs (required when the dataset has a dspy.Image column).",
    )
    available: bool = Field(default=False, description="True if backend has an API key for this model.")
    max_input_tokens: int | None = Field(default=None, description="Context window size.")


class CatalogProvider(BaseModel):
    """A provider section in the catalog."""

    slug: str
    label: str
    env_var: str | None = None
    default_base_url: str | None = None
    has_env_key: bool = False


class ModelCatalogResponse(BaseModel):
    """Response for GET /models."""

    providers: list[CatalogProvider]
    models: list[CatalogModel]


_PROVIDER_META: dict[str, tuple[str, str | None, str | None]] = {
    "openai": ("OpenAI", "OPENAI_API_KEY", "https://api.openai.com/v1"),
    "anthropic": ("Anthropic", "ANTHROPIC_API_KEY", "https://api.anthropic.com"),
    "gemini": ("Google Gemini", "GEMINI_API_KEY", None),
    "groq": ("Groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1"),
    "deepseek": ("DeepSeek", "DEEPSEEK_API_KEY", "https://api.deepseek.com"),
    "xai": ("xAI (Grok)", "XAI_API_KEY", "https://api.x.ai/v1"),
    "together_ai": ("Together AI", "TOGETHERAI_API_KEY", "https://api.together.xyz/v1"),
    "openrouter": ("OpenRouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
    "cerebras": ("Cerebras", "CEREBRAS_API_KEY", None),
    "fireworks_ai": ("Fireworks AI", "FIREWORKS_AI_API_KEY", None),
    "cohere_chat": ("Cohere", "COHERE_API_KEY", None),
    "mistral": ("Mistral", "MISTRAL_API_KEY", None),
    "moonshot": ("Moonshot (Kimi)", "MOONSHOT_API_KEY", None),
    "volcengine": ("Volcengine", "VOLCENGINE_API_KEY", None),
    "novita": ("Novita AI", "NOVITA_API_KEY", None),
    "ollama": ("Ollama (self-hosted)", None, "http://localhost:11434"),
}

_DATE_SUFFIX_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")

# ``None`` means skip the live probe and fall back to LiteLLM's API-key
# heuristic — used for providers with bespoke auth (Anthropic), non-OpenAI
# shapes (Gemini, Ollama), or no public /models endpoint we can rely on
# (Cohere, Volcengine).
_PROVIDER_MODELS_URL: dict[str, str | None] = {
    "openai": "https://api.openai.com/v1/models",
    "anthropic": None,
    "gemini": None,
    "groq": "https://api.groq.com/openai/v1/models",
    "deepseek": "https://api.deepseek.com/v1/models",
    "xai": "https://api.x.ai/v1/models",
    "together_ai": "https://api.together.xyz/v1/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
    "cerebras": "https://api.cerebras.ai/v1/models",
    "fireworks_ai": "https://api.fireworks.ai/inference/v1/models",
    "cohere_chat": None,
    "mistral": "https://api.mistral.ai/v1/models",
    "moonshot": "https://api.moonshot.cn/v1/models",
    "volcengine": None,
    "novita": "https://api.novita.ai/v3/openai/models",
    "ollama": None,
}


def _make_label(model_id: str) -> str:
    """Strip the provider prefix from a model ID for display.

    Args:
        model_id: A LiteLLM model ID, optionally prefixed with ``provider/``.

    Returns:
        The bare model name with any leading ``provider/`` removed.
    """
    name = model_id.split("/", 1)[-1] if "/" in model_id else model_id
    return name


def _probe_deployed_models(provider_slug: str) -> set[str] | None:
    """Query a provider's OpenAI-compatible ``/models`` endpoint.

    Args:
        provider_slug: LiteLLM provider key (e.g. ``"openai"``, ``"fireworks_ai"``).

    Returns:
        The set of model IDs the provider currently has deployed, or ``None``
        when no live check is configured for the provider, the API key is
        missing, the request fails, or the response shape is unexpected. The
        caller should then fall back to the LiteLLM ``valid_set`` heuristic.
    """
    url = _PROVIDER_MODELS_URL.get(provider_slug)
    if not url:
        return None
    env_var = _PROVIDER_META[provider_slug][1]
    if not env_var:
        return None
    api_key = os.getenv(env_var)
    if not api_key:
        return None

    # Fireworks (and some other providers) reject the default
    # ``Python-urllib/3.x`` UA with 403 — set an explicit one.
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "skynet-catalog/0.1",
    }
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=4) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(body)
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("model-list probe for %s failed: %s", provider_slug, exc)
        return None

    raw = data.get("data") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return None

    ids: set[str] = set()
    for item in raw:
        if isinstance(item, dict):
            val = item.get("id") or item.get("name")
            if isinstance(val, str) and val:
                ids.add(val)
        elif isinstance(item, str):
            ids.add(item)
    return ids


def _probe_all_providers() -> dict[str, set[str] | None]:
    """Probe every configured provider in parallel, capped at 8 workers.

    Returns:
        A mapping of provider slug to the set of deployed model IDs reported
        by the provider, or ``None`` when the live probe was skipped or
        failed for that provider.
    """
    results: dict[str, set[str] | None] = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_probe_deployed_models, slug): slug for slug in _PROVIDER_META
        }
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()
    return results


def get_catalog() -> ModelCatalogResponse:
    """Build a model catalog from LiteLLM's bundled model registry.

    Filters to ``mode == "chat"`` models, de-duplicates dated variants, and
    marks each model ``available`` by either the provider's live ``/models``
    probe (when reachable) or LiteLLM's API-key heuristic. Models that fail
    a successful live probe are dropped from the catalog.

    Returns:
        A :class:`ModelCatalogResponse` containing the active providers and
        the sorted list of available chat models.
    """

    cost: dict[str, dict] = litellm.model_cost
    try:
        valid_set: set[str] = set(litellm.get_valid_models())
    except Exception as exc:
        logger.warning("litellm.get_valid_models() failed: %s; marking none as available", exc)
        valid_set = set()

    deployed_by_provider = _probe_all_providers()

    seen_providers: dict[str, CatalogProvider] = {}
    models: list[CatalogModel] = []
    base_names_seen: set[str] = set()

    for model_id, meta in cost.items():
        if meta.get("mode") != "chat":
            continue

        provider_slug: str = meta.get("litellm_provider", "unknown")

        if provider_slug not in _PROVIDER_META:
            continue

        base_name = _DATE_SUFFIX_RE.sub("", model_id)
        if base_name != model_id and base_name in cost:
            continue

        if base_name in base_names_seen:
            continue
        base_names_seen.add(base_name)

        # dspy.LM rejects un-prefixed IDs — always emit ``provider/model``.
        prefixed_id = model_id if "/" in model_id else f"{provider_slug}/{model_id}"

        # Probe responses use the provider's native ID shape (e.g.
        # ``accounts/fireworks/models/...``), not the ``fireworks_ai/...``
        # catalog prefix — match against the un-prefixed form.
        canonical_id = (
            model_id.split("/", 1)[1]
            if model_id.startswith(f"{provider_slug}/")
            else model_id
        )
        deployed = deployed_by_provider.get(provider_slug)
        if deployed is not None:
            available = canonical_id in deployed or model_id in deployed
            if not available:
                continue
        else:
            available = model_id in valid_set or prefixed_id in valid_set

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

        models.append(
            CatalogModel(
                value=prefixed_id,
                label=_make_label(model_id),
                provider=provider_slug,
                supports_thinking=bool(meta.get("supports_reasoning")),
                supports_vision=bool(meta.get("supports_vision")),
                available=available,
                max_input_tokens=meta.get("max_input_tokens"),
            )
        )

    models = [m for m in models if m.available]

    models.sort(key=lambda m: (m.provider, m.value))

    available_providers = {m.provider for m in models}
    providers = sorted(
        (p for p in seen_providers.values() if p.slug in available_providers or not p.env_var),
        key=lambda p: (not p.has_env_key, p.slug),
    )

    return ModelCatalogResponse(providers=providers, models=models)


_cached_response: ModelCatalogResponse | None = None


def get_catalog_cached() -> ModelCatalogResponse:
    """Return the catalog, computing it once and caching forever.

    Returns:
        The cached ``ModelCatalogResponse``, built lazily on first call.
    """
    global _cached_response
    if _cached_response is None:
        _cached_response = get_catalog()
        logger.info(
            "Model catalog built: %d providers, %d models",
            len(_cached_response.providers),
            len(_cached_response.models),
        )
    return _cached_response
