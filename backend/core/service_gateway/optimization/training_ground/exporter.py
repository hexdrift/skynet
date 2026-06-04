"""Generalist on-ramp: ``agent_messages`` → stage-ready replay rows (§5.3).

This module is the reference exporter described in the SPEC's §5.3: it reads
recorded assistant turns out of ``agent_messages`` (reusing the raw-row query
that backs :func:`persistence.load_trajectories`) and emits one stage-ready
**row per turn** in the canonical §5 replay schema, ready to POST to
``POST /datasets/stage-for-agent`` and then run with ``module_name="react"``.

THE CANONICAL ROW CONTRACT
==========================

One row = one recorded turn. Each row carries both the signature-I/O columns
the candidate rollout reads and the replay columns the trace-conditioned mock
matches against:

- ``user_message`` — verbatim user message that prompted the turn (signature input).
- ``wizard_state`` — ``wizard_state_before`` snapshot (signature input).
- ``chat_history`` — prior ``{role, content}`` turns in the conversation (signature input).
- ``assistant_message`` — the recorded assistant ``content`` / output (signature output).
- ``steps`` — the raw ``agent_messages.tool_calls`` v1 list, native JSON (replay role).
- ``allowed_tools`` — the recorded ``tools_for(state)`` roster as a list (replay role).
- ``tool_schema_hashes`` — ``{tool_name: sha256(schema_json)}`` snapshot (replay role).
- ``state_before`` / ``state_after`` — the per-turn state snapshots (replay roles).

Nested values (``steps``, ``chat_history``, ``tool_schema_hashes``, the state
snapshots) travel as **native JSON** — lists and dicts, not JSON-encoded
strings — because the stage-for-agent path and the JSON/JSONL upload preserve
nested structure (§5.1). The matching column/replay mapping hints a caller
posts alongside the rows live as the module-level constants
:data:`GENERALIST_COLUMN_MAPPING` and :data:`GENERALIST_REPLAY_MAPPING`.

ROUND-TRIP INVARIANT
====================

Feeding these rows through ``run_react.build_replay_examples`` with
:data:`GENERALIST_REPLAY_MAPPING` reconstructs ``EvaluationExample`` records
whose ``replay_steps`` / ``allowed_tools`` / ``tool_schema_hashes`` equal what
``persistence.load_trajectories`` produces for the same source rows — both
paths convert the same raw ``tool_calls`` list via
``adapt_agent_tool_calls_v1_to_replay`` and normalise the same roster/hash maps.

SECRETS: rows are emitted verbatim from the recorded columns; this exporter
adds nothing and must never inject credentials or auth headers into a row.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import Engine
from sqlalchemy.engine import Row

from .persistence import _fetch_assistant_rows, load_trajectories, parse_window
from .types import EvaluationExample

# Signature-I/O column hints for ``POST /run``'s ``column_mapping``: the rows
# emitted here name their inputs ``user_message`` / ``wizard_state`` /
# ``chat_history`` and their output ``assistant_message`` (§5.1). A caller
# wires these into a ``ColumnMapping`` so the candidate rollout sees the
# generalist three-key input dict plus the recorded assistant output.
GENERALIST_COLUMN_MAPPING: dict[str, dict[str, str]] = {
    "inputs": {
        "user_message": "user_message",
        "wizard_state": "wizard_state",
        "chat_history": "chat_history",
    },
    "outputs": {"assistant_message": "assistant_message"},
}

# Replay-role column hints for ``POST /run``'s ``replay_mapping``: where the
# recorded-trajectory columns live on each row (§5.1). Mirrors the
# ``ReplayMapping`` field names so a caller can construct one directly.
GENERALIST_REPLAY_MAPPING: dict[str, str] = {
    "steps": "steps",
    "allowed_tools": "allowed_tools",
    "tool_schema_hashes": "tool_schema_hashes",
    "state_before": "state_before",
    "state_after": "state_after",
    "chat_history": "chat_history",
}


class TrajectoryLoader(Protocol):
    """Loads recorded trajectories as ``EvaluationExample`` records.

    A seam (§12 seam #1) over whatever produces replay-ready examples: the
    generalist implementation reads ``agent_messages`` via the v1 adapter,
    but a future source (a different store, a file) can satisfy the same
    contract without touching the harness.
    """

    def load(
        self, source: Engine, *, window: str, limit: int | None = None
    ) -> list[EvaluationExample]:
        """Return the recorded trajectories from ``source`` within ``window``.

        Args:
            source: The backing store handle (an ``Engine`` for the generalist).
            window: Time-window expression (see :func:`persistence.parse_window`).
            limit: Optional cap on the number of trajectories returned.

        Returns:
            The loaded evaluation examples in chronological order.
        """
        ...


class AgentMessagesTrajectoryLoader:
    """``TrajectoryLoader`` backed by the v1 ``agent_messages`` adapter.

    A thin wrapper over :func:`persistence.load_trajectories` — the existing
    loader trio (``load_trajectories`` → ``_fetch_assistant_rows`` →
    ``_row_to_example``) stays the single source of truth; this class only
    adapts its signature to the :class:`TrajectoryLoader` protocol so callers
    can depend on the seam rather than the concrete function.
    """

    def load(
        self, source: Engine, *, window: str, limit: int | None = None
    ) -> list[EvaluationExample]:
        """Delegate to :func:`persistence.load_trajectories` verbatim.

        Args:
            source: SQLAlchemy engine bound to the Skynet database.
            window: Time-window expression (see :func:`persistence.parse_window`).
            limit: Optional cap on the number of trajectories returned.

        Returns:
            The loaded evaluation examples in chronological order.
        """
        return load_trajectories(source, window=window, limit=limit)


def export_agent_messages_to_rows(
    engine: Engine, *, window: str, limit: int | None = None
) -> list[dict[str, Any]]:
    """Export recorded ``agent_messages`` turns as stage-ready replay rows.

    Reads the same raw assistant rows that back
    :func:`persistence.load_trajectories` (via :func:`_fetch_assistant_rows`)
    and emits one canonical-schema row per turn — see the module docstring for
    the column contract. Nested values are emitted as native JSON. The
    returned list is postable to ``POST /datasets/stage-for-agent`` and runs
    with ``column_mapping``/``replay_mapping`` built from
    :data:`GENERALIST_COLUMN_MAPPING` / :data:`GENERALIST_REPLAY_MAPPING`.

    Args:
        engine: SQLAlchemy engine bound to the Skynet database.
        window: Time-window expression (see :func:`persistence.parse_window`).
        limit: Optional cap on the number of source rows read.

    Returns:
        One stage-ready row dict per recorded turn, in chronological order;
        an empty list when the window holds no annotated turns.
    """
    threshold = datetime.now(UTC) - parse_window(window)
    rows = _fetch_assistant_rows(engine, since=threshold, limit=limit)
    return [_row_to_export_row(row) for row in rows]


def _row_to_export_row(row: Row) -> dict[str, Any]:
    """Map one raw assistant row to a canonical stage-ready export row.

    Normalises the replay columns so the round-trip through
    ``build_replay_examples`` reproduces ``load_trajectories`` output: the raw
    ``tool_calls`` list is emitted unchanged as ``steps`` (the v1 shape both
    paths feed to ``adapt_agent_tool_calls_v1_to_replay``), and an
    ``allowed_tools`` JSONB object is reduced to its keys (a list) so both
    paths build the same frozenset.

    Args:
        row: Result row from :func:`_fetch_assistant_rows`.

    Returns:
        A canonical-schema export row with native-JSON nested values.
    """
    allowed_tools_raw = row.allowed_tools or []
    if isinstance(allowed_tools_raw, dict):
        allowed_tools_raw = list(allowed_tools_raw.keys())
    schema_hashes = row.tool_schema_hashes or {}
    state_before = dict(row.wizard_state_before or {})
    state_after = dict(row.wizard_state_after or {})
    return {
        "user_message": (row.user_message or "").strip(),
        "wizard_state": state_before,
        "chat_history": list(row.chat_history or []),
        "assistant_message": row.content or "",
        "steps": list(row.tool_calls or []),
        "allowed_tools": [str(name) for name in allowed_tools_raw],
        "tool_schema_hashes": {str(k): str(v) for k, v in schema_hashes.items()},
        "state_before": state_before,
        "state_after": state_after,
    }


__all__ = [
    "GENERALIST_COLUMN_MAPPING",
    "GENERALIST_REPLAY_MAPPING",
    "AgentMessagesTrajectoryLoader",
    "TrajectoryLoader",
    "export_agent_messages_to_rows",
]
