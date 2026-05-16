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
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import litellm
from pydantic import BaseModel, Field

from ..config import settings

logger = logging.getLogger(__name__)


class CatalogModel(BaseModel):
    """A single model entry exposed to the frontend."""

    value: str = Field(..., description="Canonical LiteLLM model ID (e.g. 'gpt-4o-mini').")
    label: str = Field(..., description="Human-friendly display name.")
    provider: str = Field(..., description="Provider slug for grouping (e.g. 'openai').")
    data_center: str | None = Field(
        default=None,
        description=(
            "Data-center label this model resolves through when the provider "
            "exposes more than one endpoint (e.g. an on-prem gateway). "
            "``None`` for single-endpoint providers."
        ),
    )
    supports_thinking: bool = Field(default=False, description="Model supports reasoning_effort.")
    supports_vision: bool = Field(
        default=False,
        description="Model accepts image inputs (required when the dataset has a dspy.Image column).",
    )
    available: bool = Field(default=False, description="True if backend has an API key for this model.")
    max_input_tokens: int | None = Field(default=None, description="Context window size.")


class CatalogProvider(BaseModel):
    """A provider section in the catalog.

    A provider with a single endpoint emits one entry with
    ``data_center=None``. A provider that fans out across several endpoints
    (e.g. a public API plus an on-prem OpenAI-compatible gateway) emits one
    entry per data center, each with a distinct ``default_base_url`` and a
    populated ``data_center`` label.
    """

    slug: str
    label: str
    data_center: str | None = None
    env_var: str | None = None
    default_base_url: str | None = None
    has_env_key: bool = False


class ModelCatalogResponse(BaseModel):
    """Response for GET /models."""

    providers: list[CatalogProvider]
    models: list[CatalogModel]


class _DataCenter(BaseModel):
    """One reachable endpoint for a provider.

    ``label`` is ``None`` for a provider's sole/native endpoint (renders as
    just the provider name) and a short human string for additional centers
    such as an on-prem gateway. ``models_url`` is the OpenAI-compatible
    ``/models`` probe target, or ``None`` to fall back to LiteLLM's API-key
    heuristic.
    """

    label: str | None = None
    base_url: str | None = None
    models_url: str | None = None
    env_var: str | None = None


# Each provider declares one or more data centers. Historically every
# provider had exactly one endpoint; that maps to a single ``_DataCenter``
# with ``label=None`` so existing single-DC behaviour (and the
# ``data_center=None`` wire shape) is preserved. The on-prem gateway is
# appended at runtime by ``_provider_data_centers`` when configured.
#
# A ``models_url`` of ``None`` skips the live probe and falls back to
# LiteLLM's API-key heuristic — used for providers with bespoke auth
# (Anthropic), non-OpenAI shapes (Gemini, Ollama), or no public /models
# endpoint we can rely on (Cohere, Volcengine).
_PROVIDER_META: dict[str, tuple[str, list[_DataCenter]]] = {
    "openai": (
        "OpenAI",
        [
            _DataCenter(
                base_url="https://api.openai.com/v1",
                models_url="https://api.openai.com/v1/models",
                env_var="OPENAI_API_KEY",
            )
        ],
    ),
    "anthropic": (
        "Anthropic",
        [_DataCenter(base_url="https://api.anthropic.com", env_var="ANTHROPIC_API_KEY")],
    ),
    "gemini": ("Google Gemini", [_DataCenter(env_var="GEMINI_API_KEY")]),
    "groq": (
        "Groq",
        [
            _DataCenter(
                base_url="https://api.groq.com/openai/v1",
                models_url="https://api.groq.com/openai/v1/models",
                env_var="GROQ_API_KEY",
            )
        ],
    ),
    "deepseek": (
        "DeepSeek",
        [
            _DataCenter(
                base_url="https://api.deepseek.com",
                models_url="https://api.deepseek.com/v1/models",
                env_var="DEEPSEEK_API_KEY",
            )
        ],
    ),
    "xai": (
        "xAI (Grok)",
        [
            _DataCenter(
                base_url="https://api.x.ai/v1",
                models_url="https://api.x.ai/v1/models",
                env_var="XAI_API_KEY",
            )
        ],
    ),
    "together_ai": (
        "Together AI",
        [
            _DataCenter(
                base_url="https://api.together.xyz/v1",
                models_url="https://api.together.xyz/v1/models",
                env_var="TOGETHERAI_API_KEY",
            )
        ],
    ),
    "openrouter": (
        "OpenRouter",
        [
            _DataCenter(
                base_url="https://openrouter.ai/api/v1",
                models_url="https://openrouter.ai/api/v1/models",
                env_var="OPENROUTER_API_KEY",
            )
        ],
    ),
    "cerebras": (
        "Cerebras",
        [
            _DataCenter(
                models_url="https://api.cerebras.ai/v1/models",
                env_var="CEREBRAS_API_KEY",
            )
        ],
    ),
    "fireworks_ai": (
        "Fireworks AI",
        [
            _DataCenter(
                models_url="https://api.fireworks.ai/inference/v1/models",
                env_var="FIREWORKS_AI_API_KEY",
            )
        ],
    ),
    "cohere_chat": ("Cohere", [_DataCenter(env_var="COHERE_API_KEY")]),
    "mistral": (
        "Mistral",
        [
            _DataCenter(
                models_url="https://api.mistral.ai/v1/models",
                env_var="MISTRAL_API_KEY",
            )
        ],
    ),
    "moonshot": (
        "Moonshot (Kimi)",
        [
            _DataCenter(
                models_url="https://api.moonshot.cn/v1/models",
                env_var="MOONSHOT_API_KEY",
            )
        ],
    ),
    "volcengine": ("Volcengine", [_DataCenter(env_var="VOLCENGINE_API_KEY")]),
    "novita": (
        "Novita AI",
        [
            _DataCenter(
                models_url="https://api.novita.ai/v3/openai/models",
                env_var="NOVITA_API_KEY",
            )
        ],
    ),
    "ollama": ("Ollama (self-hosted)", [_DataCenter(base_url="http://localhost:11434")]),
}

_ON_PREM_DC_LABEL = "On-prem gateway"

_DATE_SUFFIX_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def _on_prem_base_url() -> str | None:
    """Return the configured internal OpenAI-compatible gateway URL, if any.

    Prefers ``code_agent_base_url`` (the submit-wizard agent gateway) and
    falls back to ``embeddings_base_url`` since on-prem deployments commonly
    point both at the same internal gateway family.

    Returns:
        The configured internal base URL, or ``None`` when neither
        ``CODE_AGENT_BASE_URL`` nor ``EMBEDDINGS_BASE_URL`` is set.
    """
    return (
        settings.code_agent_base_url.strip()
        or settings.embeddings_base_url.strip()
        or None
    )


def _provider_data_centers(provider_slug: str) -> list[_DataCenter]:
    """Return the data centers for ``provider_slug`` including the on-prem one.

    The configured on-prem gateway is OpenAI-compatible, so it is surfaced as
    an extra data center on the ``openai`` provider (its native ``/models``
    shape matches). All other providers return their static endpoint list
    unchanged.

    Args:
        provider_slug: LiteLLM provider key (e.g. ``"openai"``).

    Returns:
        The provider's data centers, with the on-prem gateway appended when
        configured and applicable to this provider.
    """
    centers = list(_PROVIDER_META[provider_slug][1])
    if provider_slug == "openai":
        on_prem = _on_prem_base_url()
        if on_prem:
            centers.append(
                _DataCenter(
                    label=_ON_PREM_DC_LABEL,
                    base_url=on_prem,
                    models_url=f"{on_prem.rstrip('/')}/models",
                    env_var="OPENAI_API_KEY",
                )
            )
    return centers


def _make_label(model_id: str) -> str:
    """Strip the provider prefix from a model ID for display.

    Args:
        model_id: A LiteLLM model ID, optionally prefixed with ``provider/``.

    Returns:
        The bare model name with any leading ``provider/`` removed.
    """
    name = model_id.split("/", 1)[-1] if "/" in model_id else model_id
    return name


def _probe_deployed_models(provider_slug: str, data_center: _DataCenter) -> set[str] | None:
    """Query a single data center's OpenAI-compatible ``/models`` endpoint.

    Args:
        provider_slug: LiteLLM provider key (e.g. ``"openai"``, ``"fireworks_ai"``).
        data_center: The specific endpoint to probe (its own ``models_url``
            and ``env_var``).

    Returns:
        The set of model IDs the data center currently has deployed, or
        ``None`` when no live check is configured for it, the API key is
        missing, the request fails, or the response shape is unexpected. The
        caller should then fall back to the LiteLLM ``valid_set`` heuristic.
    """
    url = data_center.models_url
    if not url:
        return None
    env_var = data_center.env_var
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


def _probe_all_providers() -> dict[tuple[str, str | None], set[str] | None]:
    """Probe every configured data center in parallel, capped at 8 workers.

    Each ``(provider, data center)`` pair is probed independently since they
    are distinct endpoints that may serve different model sets (e.g. an
    on-prem gateway exposes only locally-deployed models).

    Returns:
        A mapping of ``(provider_slug, data_center_label)`` to the set of
        deployed model IDs reported by that endpoint, or ``None`` when the
        live probe was skipped or failed for it.
    """
    results: dict[tuple[str, str | None], set[str] | None] = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {}
        for slug in _PROVIDER_META:
            for dc in _provider_data_centers(slug):
                futures[executor.submit(_probe_deployed_models, slug, dc)] = (slug, dc.label)
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
    except (OSError, RuntimeError, KeyError, ValueError, AttributeError, TypeError) as exc:
        # LiteLLM probes provider env vars + endpoints; the failure surface is
        # network-shaped (OSError, RuntimeError) or shape-shaped (Key/Value/
        # Attribute/Type). Catching the union avoids hiding real bugs while
        # still letting the catalog degrade gracefully when one provider
        # misbehaves.
        logger.warning("litellm.get_valid_models() failed: %s; marking none as available", exc)
        valid_set = set()

    deployed_by_dc = _probe_all_providers()

    seen_providers: dict[tuple[str, str | None], CatalogProvider] = {}
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

        provider_label = _PROVIDER_META[provider_slug][0]
        for dc in _provider_data_centers(provider_slug):
            deployed = deployed_by_dc.get((provider_slug, dc.label))
            if deployed is not None:
                available = canonical_id in deployed or model_id in deployed
                if not available:
                    continue
            else:
                available = model_id in valid_set or prefixed_id in valid_set

            provider_key = (provider_slug, dc.label)
            if provider_key not in seen_providers:
                has_key = bool(dc.env_var and os.getenv(dc.env_var))
                seen_providers[provider_key] = CatalogProvider(
                    slug=provider_slug,
                    label=provider_label,
                    data_center=dc.label,
                    env_var=dc.env_var,
                    default_base_url=dc.base_url,
                    has_env_key=has_key,
                )

            models.append(
                CatalogModel(
                    value=prefixed_id,
                    label=_make_label(model_id),
                    provider=provider_slug,
                    data_center=dc.label,
                    supports_thinking=bool(meta.get("supports_reasoning")),
                    supports_vision=bool(meta.get("supports_vision")),
                    available=available,
                    max_input_tokens=meta.get("max_input_tokens"),
                )
            )

    models = [m for m in models if m.available]

    models.sort(key=lambda m: (m.provider, m.data_center or "", m.value))

    available_dcs = {(m.provider, m.data_center) for m in models}
    providers = sorted(
        (
            p
            for p in seen_providers.values()
            if (p.slug, p.data_center) in available_dcs or not p.env_var
        ),
        key=lambda p: (not p.has_env_key, p.slug, p.data_center or ""),
    )

    return ModelCatalogResponse(providers=providers, models=models)


_cached_response: ModelCatalogResponse | None = None
_cached_at_monotonic: float = 0.0
_cache_lock = Lock()


def get_catalog_cached() -> ModelCatalogResponse:
    """Return the catalog, refreshing it after ``model_catalog_ttl_seconds``.

    A TTL of ``0`` disables caching (every call rebuilds). The lock makes
    concurrent first-call requests share a single rebuild instead of all
    racing into the same probe.

    Returns:
        The cached ``ModelCatalogResponse``, rebuilt when stale.
    """
    global _cached_response, _cached_at_monotonic
    ttl = float(settings.model_catalog_ttl_seconds)
    now = time.monotonic()
    if ttl > 0.0 and _cached_response is not None and (now - _cached_at_monotonic) < ttl:
        return _cached_response

    with _cache_lock:
        # Re-check under the lock so we don't rebuild twice when callers
        # race in during the first miss.
        now = time.monotonic()
        if ttl > 0.0 and _cached_response is not None and (now - _cached_at_monotonic) < ttl:
            return _cached_response
        _cached_response = get_catalog()
        _cached_at_monotonic = now
        logger.info(
            "Model catalog built: %d providers, %d models",
            len(_cached_response.providers),
            len(_cached_response.models),
        )
        return _cached_response
