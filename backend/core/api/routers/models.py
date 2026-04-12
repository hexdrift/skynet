"""Routes for model catalog and live model discovery.

``GET /models`` returns the curated catalog. ``POST /models/discover`` probes
an OpenAI-compatible endpoint for its available models.
"""

from __future__ import annotations

import json as _json
import urllib.error
import urllib.request

from fastapi import APIRouter
from pydantic import BaseModel

from ..model_catalog import ModelCatalogResponse, get_catalog_cached


class DiscoverModelsRequest(BaseModel):
    """Request payload for POST /models/discover."""

    base_url: str
    api_key: str | None = None


class DiscoverModelsResponse(BaseModel):
    """Response payload for POST /models/discover."""

    models: list[str] = []
    base_url: str
    error: str | None = None


def create_models_router() -> APIRouter:
    """Build the models router.

    Returns:
        APIRouter: Router with two routes — catalog list and discovery probe.
    """
    router = APIRouter()

    @router.get(
        "/models",
        response_model=ModelCatalogResponse,
        summary="List the curated model catalog",
    )
    def list_models() -> ModelCatalogResponse:
        """Return every model the backend knows how to drive, plus whether each
        provider's API key is already configured in the server environment.

        The frontend uses this endpoint to populate the model-name dropdown on
        the submission form and to decide whether the user needs to type an
        API key manually: if the provider's key is already set on the server
        (e.g. ``OPENAI_API_KEY``), the frontend leaves the field optional.

        Response shape:
            - ``models``: list of ``{provider, name, display_name, context_window, ...}``
            - ``provider_status``: map of provider name → ``{has_key: bool}``

        Cached: 5 minutes public, 10 minutes stale-while-revalidate. The
        catalog rarely changes at runtime so the response is effectively
        static per process lifetime.

        Returns:
            ModelCatalogResponse with the curated model and provider list.
        """
        catalog = get_catalog_cached()
        return catalog

    @router.post(
        "/models/discover",
        response_model=DiscoverModelsResponse,
        summary="Probe an OpenAI-compatible endpoint for its model list",
    )
    def discover_models(payload: DiscoverModelsRequest) -> DiscoverModelsResponse:
        """Ask any OpenAI-compatible server (vLLM, Ollama, LM Studio, LiteLLM
        proxies, etc.) for the models it currently serves.

        How it works:
            1. Calls ``GET {base_url}/v1/models`` with an 8-second timeout.
            2. If that returns 404, retries ``GET {base_url}/models`` (some
               deployments skip the ``/v1`` prefix).
            3. Parses the OpenAI response shape (``{"data": [{"id": ...}]}``)
               or a plain list, extracts model IDs, deduplicates and sorts.

        Error handling: this endpoint never raises. If the probe fails (DNS,
        timeout, 401, malformed JSON, etc.), ``models`` is empty and
        ``error`` contains a human-readable reason. The frontend treats the
        result as advisory — users can still type a model name manually.

        Authentication: pass ``api_key`` in the body if the target requires
        a bearer token. The key is used only for this one outbound request
        and is not stored anywhere.

        Args:
            payload: Request body with base URL and optional bearer token.

        Returns:
            DiscoverModelsResponse with the discovered model IDs, or an error.
        """
        base = payload.base_url.rstrip("/")
        candidates = [f"{base}/v1/models", f"{base}/models"]
        headers = {"Accept": "application/json"}
        if payload.api_key:
            headers["Authorization"] = f"Bearer {payload.api_key}"

        last_error: str | None = None
        for url in candidates:
            try:
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=8) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                data = _json.loads(body)
                raw = data.get("data") if isinstance(data, dict) else data
                if not isinstance(raw, list):
                    last_error = "Unexpected response shape"
                    continue
                ids: list[str] = []
                for item in raw:
                    if isinstance(item, dict):
                        val = item.get("id") or item.get("name")
                        if isinstance(val, str) and val:
                            ids.append(val)
                    elif isinstance(item, str):
                        ids.append(item)
                return DiscoverModelsResponse(models=sorted(set(ids)), base_url=base)
            except urllib.error.HTTPError as exc:
                last_error = f"HTTP {exc.code}"
                if exc.code == 404:
                    continue
                break
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = str(exc.reason if hasattr(exc, "reason") else exc)
                break
            except (ValueError, _json.JSONDecodeError) as exc:
                last_error = f"Invalid JSON: {exc}"
                break
        return DiscoverModelsResponse(models=[], base_url=base, error=last_error or "Unable to fetch models")

    return router
