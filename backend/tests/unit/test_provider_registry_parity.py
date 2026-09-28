"""Pin BYOK provider shortcuts to the canonical ``core.provider_registry``.

The registry is the source of truth for the manual picker and bundled catalog.
Arbitrary JSON-imported connections remain valid outside this convenience set.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.api.model_catalog import _BYOK_CATALOG_PROVIDERS
from core.provider_registry import (
    BYOK_CATALOG_PREFIXES,
    BYOK_TO_LITELLM_PROVIDER,
)

_FRONTEND_BYOK_TS = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "src"
    / "features"
    / "byok"
    / "lib"
    / "byok.ts"
)


def _frontend_byok_source() -> str:
    """Return the text of the frontend BYOK catalog module.

    Returns:
        The full source of ``frontend/src/features/byok/lib/byok.ts``.
    """
    return _FRONTEND_BYOK_TS.read_text(encoding="utf-8")


def test_catalog_prefixes_match_the_registry() -> None:
    """The model catalog offers exactly the registry's LiteLLM prefixes."""
    assert _BYOK_CATALOG_PROVIDERS == BYOK_CATALOG_PREFIXES


def test_frontend_bridge_matches_the_registry() -> None:
    """The frontend slug->prefix bridge equals the registry's, exactly."""
    source = _frontend_byok_source()
    body = source[source.index("BYOK_TO_LITELLM_PROVIDER") :]
    body = body[body.index("{") + 1 : body.index("}")]
    bridge = dict(re.findall(r'(\w+):\s*"([^"]+)"', body))
    assert bridge == BYOK_TO_LITELLM_PROVIDER
