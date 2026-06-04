"""Tests for ``core.service_gateway.optimization.validators``."""

from __future__ import annotations

import pytest

from core.exceptions import ServiceError
from core.models import ColumnMapping, ReplayMapping
from core.service_gateway.optimization.validators import (
    require_mapping_columns_in_dataset,
    require_mapping_matches_signature,
    require_replay_mapping_valid,
)


def _mapping(inputs: dict[str, str], outputs: dict[str, str]) -> ColumnMapping:
    """Build a ``ColumnMapping`` directly from input/output dicts."""
    return ColumnMapping(inputs=inputs, outputs=outputs)


def test_require_mapping_matches_signature_ok() -> None:
    """A complete mapping passes signature validation without raising."""
    m = _mapping({"question": "q"}, {"answer": "a"})
    require_mapping_matches_signature(m, ["question"], ["answer"])


def test_require_mapping_matches_signature_missing_input() -> None:
    """A missing required signature input raises with the offending name listed."""
    m = _mapping({"question": "q"}, {"answer": "a"})
    with pytest.raises(ServiceError, match="Missing inputs: \\['context'\\]"):
        require_mapping_matches_signature(m, ["question", "context"], ["answer"])


def test_require_mapping_matches_signature_missing_output() -> None:
    """A missing required signature output raises with the offending name listed."""
    m = _mapping({"question": "q"}, {"answer": "a"})
    with pytest.raises(ServiceError, match="missing outputs: \\['confidence'\\]"):
        require_mapping_matches_signature(m, ["question"], ["answer", "confidence"])


def test_require_mapping_matches_signature_reports_both() -> None:
    """When inputs and outputs are both incomplete, the error names both."""
    m = _mapping({"q": "q"}, {"a": "a"})
    with pytest.raises(ServiceError) as exc:
        require_mapping_matches_signature(m, ["q", "x"], ["a", "y"])
    assert "Missing inputs: ['x']" in str(exc.value)
    assert "missing outputs: ['y']" in str(exc.value)


def test_require_mapping_columns_in_dataset_ok() -> None:
    """A mapping whose columns all exist in the dataset passes validation."""
    m = _mapping({"question": "q"}, {"answer": "a"})
    require_mapping_columns_in_dataset(m, [{"q": "hi", "a": "hello", "extra": 1}])


def test_require_mapping_columns_in_dataset_missing() -> None:
    """A mapping referencing a column missing from every row raises."""
    m = _mapping({"question": "q"}, {"answer": "a"})
    with pytest.raises(ServiceError, match="columns not found in dataset: \\['a'\\]"):
        require_mapping_columns_in_dataset(m, [{"q": "hi"}])


def test_require_mapping_columns_in_dataset_merges_row_keys() -> None:
    """Different rows can contribute different columns to the available set."""
    m = _mapping({"question": "q"}, {"answer": "a"})
    require_mapping_columns_in_dataset(m, [{"q": "hi"}, {"a": "hello"}])


def test_require_mapping_columns_in_dataset_lists_available() -> None:
    """The error message lists the columns that ARE available, sorted."""
    m = _mapping({"question": "missing_col"}, {"answer": "also_missing"})
    with pytest.raises(ServiceError) as exc:
        require_mapping_columns_in_dataset(m, [{"q": "hi", "a": "hello"}])
    assert "Available columns: ['a', 'q']" in str(exc.value)


def _replay(**overrides) -> ReplayMapping:
    """Build a ``ReplayMapping`` with all required roles plus optional overrides."""
    base: dict = {
        "steps": "steps",
        "allowed_tools": "tools",
        "tool_schema_hashes": "hashes",
        "state_before": "before",
        "state_after": "after",
    }
    base.update(overrides)
    return ReplayMapping(**base)


def test_require_replay_mapping_valid_ok() -> None:
    """A replay mapping whose required roles all exist in the dataset passes."""
    rm = _replay()
    require_replay_mapping_valid(
        rm, [{"steps": "[]", "tools": "[]", "hashes": "{}", "before": "{}", "after": "{}", "extra": 1}]
    )


def test_require_replay_mapping_valid_missing_required_role() -> None:
    """A required role naming a column missing from every row raises."""
    rm = _replay(allowed_tools="absent_col")
    with pytest.raises(ServiceError, match="replay_mapping references columns not found"):
        require_replay_mapping_valid(rm, [{"steps": "[]", "hashes": "{}", "before": "{}", "after": "{}"}])


def test_require_replay_mapping_valid_reports_role_and_column() -> None:
    """The error names the offending role and the column it pointed at."""
    rm = _replay(steps="nope")
    with pytest.raises(ServiceError) as exc:
        require_replay_mapping_valid(rm, [{"tools": "[]", "hashes": "{}", "before": "{}", "after": "{}"}])
    assert "steps='nope'" in str(exc.value)


def test_require_replay_mapping_valid_state_role_checked() -> None:
    """A required state-snapshot role naming a missing column raises."""
    rm = _replay(state_before="ghost_col")
    with pytest.raises(ServiceError, match="state_before='ghost_col'"):
        require_replay_mapping_valid(rm, [{"steps": "[]", "tools": "[]", "hashes": "{}", "after": "{}"}])


def test_require_replay_mapping_valid_optional_chat_history_unset_ignored() -> None:
    """The still-optional chat_history role is ignored when unset."""
    rm = _replay()
    require_replay_mapping_valid(
        rm, [{"steps": "[]", "tools": "[]", "hashes": "{}", "before": "{}", "after": "{}"}]
    )


def test_require_replay_mapping_valid_skips_when_no_dataset() -> None:
    """Validation is skipped entirely when the dataset is staged (None/empty)."""
    rm = _replay(steps="anything")
    require_replay_mapping_valid(rm, None)
    require_replay_mapping_valid(rm, [])


def test_require_replay_mapping_valid_merges_row_keys() -> None:
    """Different rows can contribute different columns to the available set."""
    rm = _replay()
    require_replay_mapping_valid(
        rm, [{"steps": "[]"}, {"tools": "[]"}, {"hashes": "{}"}, {"before": "{}"}, {"after": "{}"}]
    )
