"""Unit tests for the generalist ``agent_messages`` exporter (§5.3).

Drives synthetic raw assistant rows through :func:`export_agent_messages_to_rows`
and asserts the canonical row schema (right columns, native-JSON nested
values), the round-trip invariant against ``persistence.load_trajectories``,
and the empty-source case. ``_fetch_assistant_rows`` is monkeypatched so the
tests never touch Postgres — the SQL window stays integration-tested while the
exporter's pure transform is pinned here.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from core.models.common import ColumnMapping
from core.models.submissions import ReplayMapping
from core.service_gateway.optimization.data import rows_to_examples
from core.service_gateway.optimization.training_ground import exporter, persistence
from core.service_gateway.optimization.training_ground.run_react import (
    build_replay_examples,
)


def _raw_row(
    *,
    row_id: int = 7,
    tool_calls: list[dict[str, Any]] | None = None,
    allowed_tools: Any = None,
    schema_hashes: dict[str, str] | None = None,
    content: str = "I'll do that.",
    user_message: str = "  please run it  ",
) -> SimpleNamespace:
    """Build a synthetic raw assistant row matching ``_fetch_assistant_rows``."""
    return SimpleNamespace(
        id=row_id,
        conversation_id="conv-1",
        content=content,
        tool_calls=tool_calls
        if tool_calls is not None
        else [
            {
                "tool": "alpha",
                "reason": "first",
                "status": "done",
                "startedAt": 100,
                "endedAt": 200,
                "payload": {"arguments": {"k": 1}, "result": {"ok": 1}},
            }
        ],
        model="gpt-x",
        wizard_state_before={"dataset_ready": True},
        wizard_state_after={"dataset_ready": True, "submitted": True},
        allowed_tools=allowed_tools if allowed_tools is not None else ["alpha", "beta"],
        tool_schema_hashes=schema_hashes if schema_hashes is not None else {"alpha": "h1"},
        chat_history=[{"role": "user", "content": "hi"}],
        user_message=user_message,
    )


def _patch_rows(monkeypatch, rows: list[SimpleNamespace]) -> None:
    """Stub ``_fetch_assistant_rows`` on both call sites to return ``rows``.

    The exporter imports the helper into its own namespace and
    ``persistence.load_trajectories`` calls its module-local copy, so both
    bindings are patched to the same synthetic rows for the round-trip test.
    """
    fetch = lambda *a, **k: list(rows)  # noqa: E731
    monkeypatch.setattr(persistence, "_fetch_assistant_rows", fetch)
    monkeypatch.setattr(exporter, "_fetch_assistant_rows", fetch)


def test_export_row_has_canonical_columns_and_native_json(monkeypatch) -> None:
    """One raw row exports to a row with the §5 columns and native-JSON nesting."""
    _patch_rows(monkeypatch, [_raw_row()])
    rows = exporter.export_agent_messages_to_rows(object(), window="14d")
    assert len(rows) == 1
    row = rows[0]
    assert set(row) == {
        "user_message",
        "wizard_state",
        "chat_history",
        "assistant_message",
        "steps",
        "allowed_tools",
        "tool_schema_hashes",
        "state_before",
        "state_after",
    }
    assert row["user_message"] == "please run it"
    assert row["assistant_message"] == "I'll do that."
    assert isinstance(row["steps"], list)
    assert isinstance(row["steps"][0], dict)
    assert isinstance(row["chat_history"], list)
    assert isinstance(row["tool_schema_hashes"], dict)
    assert row["wizard_state"] == {"dataset_ready": True}
    assert row["allowed_tools"] == ["alpha", "beta"]


def test_export_allowed_tools_dict_reduced_to_keys(monkeypatch) -> None:
    """An ``allowed_tools`` JSONB object exports as its key list (round-trip-safe)."""
    _patch_rows(monkeypatch, [_raw_row(allowed_tools={"alpha": "x", "beta": "y"})])
    rows = exporter.export_agent_messages_to_rows(object(), window="14d")
    assert sorted(rows[0]["allowed_tools"]) == ["alpha", "beta"]


def test_export_empty_source_yields_empty_list(monkeypatch) -> None:
    """No annotated turns in the window → an empty row list, not a crash."""
    _patch_rows(monkeypatch, [])
    assert exporter.export_agent_messages_to_rows(object(), window="14d") == []


def test_round_trip_matches_load_trajectories(monkeypatch) -> None:
    """Exported rows rebuilt via ``build_replay_examples`` equal ``load_trajectories``.

    Same source rows, two paths: the exporter → stage rows → DSPy examples →
    ``build_replay_examples`` must reconstruct ``replay_steps`` /
    ``allowed_tools`` / ``tool_schema_hashes`` identical to what
    ``load_trajectories`` produces from those rows directly.
    """
    raw_rows = [
        _raw_row(
            row_id=1,
            tool_calls=[
                {
                    "tool": "alpha",
                    "status": "done",
                    "payload": {"arguments": {"k": 1}, "result": {"ok": True}},
                },
                {
                    "tool": "beta",
                    "status": "error",
                    "payload": {"arguments": {"q": "x"}, "result": {"err": "boom"}},
                },
            ],
        ),
        _raw_row(row_id=2, tool_calls=[]),
    ]
    _patch_rows(monkeypatch, raw_rows)

    loaded = persistence.load_trajectories(object(), window="14d")
    export_rows = exporter.export_agent_messages_to_rows(object(), window="14d")

    column_mapping = ColumnMapping(**exporter.GENERALIST_COLUMN_MAPPING)
    replay_mapping = ReplayMapping(**exporter.GENERALIST_REPLAY_MAPPING)
    extra_columns = set(exporter.GENERALIST_REPLAY_MAPPING.values())
    dspy_examples = rows_to_examples(
        export_rows, column_mapping, extra_columns=extra_columns
    )
    # ``build_replay_examples`` keys ``turn_id`` off the row index, so align the
    # comparison positionally — both paths preserve chronological row order.
    rebuilt = build_replay_examples(dspy_examples, replay_mapping)

    assert len(rebuilt) == len(loaded)
    for rebuilt_ex, loaded_ex in zip(rebuilt, loaded, strict=True):
        # ``build_replay_examples`` drops errored recorded steps (bad ground
        # truth to replay) while the CLI ``load_trajectories`` path keeps them,
        # so the round-trip is over the done-status steps only.
        loaded_done_steps = tuple(
            step for step in loaded_ex.replay_steps if step.status == "done"
        )
        assert rebuilt_ex.replay_steps == loaded_done_steps
        assert rebuilt_ex.allowed_tools == loaded_ex.allowed_tools
        assert rebuilt_ex.tool_schema_hashes == loaded_ex.tool_schema_hashes
