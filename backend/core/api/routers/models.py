"""Routes for model catalog and live model discovery.

``GET /models`` returns the curated catalog. ``POST /models/discover`` probes
an OpenAI-compatible endpoint for its available models.
"""
from __future__ import annotations

import json as _json
import urllib.error
import urllib.request
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..model_catalog import ModelCatalogResponse, get_catalog_cached


class DiscoverModelsRequest(BaseModel):
    """Request payload for POST /models/discover."""

    base_url: str
    api_key: Optional[str] = None


class DiscoverModelsResponse(BaseModel):
    """Response payload for POST /models/discover."""

    models: List[str] = []
    base_url: str
    error: Optional[str] = None


def create_models_router() -> APIRouter:
    """Build the models router.

    Returns:
        APIRouter: Router with two routes — catalog list and discovery probe.
    """
    router = APIRouter()

    @router.get("/models", response_model=ModelCatalogResponse)
    def list_models() -> ModelCatalogResponse:
        """Return the curated model catalog plus per-provider env-key status.

        The frontend uses this to populate the model-name dropdown and to
        decide whether an explicit ``api_key`` input is required (if the
        backend's env already has the key, the user can leave it blank).

        Cached for 5 minutes — model catalog rarely changes at runtime.
        """
        catalog = get_catalog_cached()
        return catalog

    @router.post("/models/discover", response_model=DiscoverModelsResponse)
    def discover_models(payload: DiscoverModelsRequest) -> DiscoverModelsResponse:
        """Fetch the live model list from a user-supplied OpenAI-compatible endpoint.

        Targets ``GET {base_url}/v1/models`` (vLLM, Ollama, LM Studio, proxies).
        Falls back to ``{base_url}/models`` if the first attempt 404s. Returns
        an empty list with a human-readable ``error`` on failure instead of
        raising — the frontend treats it as advisory.
        """
        base = payload.base_url.rstrip("/")
        candidates = [f"{base}/v1/models", f"{base}/models"]
        headers = {"Accept": "application/json"}
        if payload.api_key:
            headers["Authorization"] = f"Bearer {payload.api_key}"

        last_error: Optional[str] = None
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
                ids: List[str] = []
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
