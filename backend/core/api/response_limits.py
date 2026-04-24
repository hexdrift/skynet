"""Shared caps and helpers to keep agent-facing responses context-safe.

Agent tool results land inside the generalist's ReAct context on every
turn. An unbounded list or a 50 KB error trace silently burns the whole
window and the agent starts to hallucinate or truncate its own output.

These helpers give every agent-tagged endpoint a single place to:

* cap list-shaped responses to a sane default even if the caller omits ``limit``,
* truncate free-form text (docstrings, logs, traces) with a "…+12KB" hint so
  the agent knows there is more via a follow-up call,
* strip pickle blobs and similar oversized fields before serialising.

Constants are deliberately small. The UI layer can opt into the full
payload with ``view=full`` where it genuinely needs every byte.
"""

from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")

# List-shaped endpoints (lists of jobs, templates, models, logs).
# The agent almost never needs more than the newest slice; the UI gets
# more by explicitly passing ``limit``.
AGENT_DEFAULT_LIST = 25
AGENT_MAX_LIST = 50

# Caps on individual text fields inside responses. Generous enough that
# short, real content passes through unchanged; strict enough that a
# runaway prompt / traceback / log line can't evict the agent's plan.
AGENT_MAX_TEXT = 2000
AGENT_MAX_LOG_MESSAGE = 500
AGENT_MAX_ERROR = 500
AGENT_MAX_INSTRUCTIONS = 1500
AGENT_MAX_CODE_PREVIEW = 800


def _size_hint(dropped_chars: int) -> str:
    """Render a compact "…+12KB" / "…+340 chars" suffix for truncated strings."""
    if dropped_chars >= 1024:
        return f"… +{dropped_chars // 1024}KB truncated; call with view=full to see all"
    return f"… +{dropped_chars} chars truncated; call with view=full to see all"


def truncate_text(value: str | None, limit: int = AGENT_MAX_TEXT) -> str | None:
    """Return ``value`` unchanged when short; otherwise clip with a size hint.

    The hint tells the agent the exact number of dropped chars so it can
    decide whether to re-fetch with ``view=full`` or move on. ``None`` /
    empty inputs pass through untouched.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return value  # type: ignore[unreachable]
    if len(value) <= limit:
        return value
    dropped = len(value) - limit
    return value[:limit].rstrip() + " " + _size_hint(dropped)


def cap_list(items: list[T], limit: int = AGENT_DEFAULT_LIST) -> tuple[list[T], bool, int]:
    """Clip a list to ``limit`` items and report the full count.

    Returns ``(clipped, truncated, total)``. The caller splices ``total``
    and ``truncated`` back into the envelope so the agent can paginate.
    """
    total = len(items)
    if total <= limit:
        return items, False, total
    return items[:limit], True, total


def clamp_limit(
    requested: int | None,
    default: int = AGENT_DEFAULT_LIST,
    ceiling: int = AGENT_MAX_LIST,
) -> int:
    """Resolve a caller-provided ``limit`` to a sane value within bounds.

    ``None`` falls back to ``default``; anything above ``ceiling`` is
    silently clamped. Negative / zero values also snap to ``default`` —
    the agent is not expected to handle a pagination error from us.
    """
    if requested is None or requested <= 0:
        return default
    return min(requested, ceiling)


def strip_large_fields(
    payload: dict[str, Any], drop_keys: tuple[str, ...]
) -> dict[str, Any]:
    """Return a shallow copy of ``payload`` with oversized fields removed.

    Used to drop pickle blobs, base64 artefacts, or expanded log arrays
    from a response that the agent rarely needs. The corresponding full
    field is still reachable via a dedicated artifact endpoint.
    """
    return {k: v for k, v in payload.items() if k not in drop_keys}
