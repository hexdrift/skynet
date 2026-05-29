"""Unit tests for the V1 ``tool_calls`` → ``ReplayStep`` adapter + arg hashing.

The mock's rollout behavior is pinned in ``test_contract_fixes.py``; this
module covers the ingestion edge of §5 — converting a persisted
``agent_messages.tool_calls`` row into ordered ``ReplayStep`` records and
the canonical argument hash that step-matching depends on.
"""

from __future__ import annotations

from core.service_gateway.optimization.training_ground.replay import (
    adapt_agent_tool_calls_v1_to_replay,
    canonical_argument_hash,
)


def test_canonical_hash_is_stable_under_key_reorder() -> None:
    """Argument dicts that differ only in key order hash identically."""
    assert canonical_argument_hash({"a": 1, "b": 2}) == canonical_argument_hash(
        {"b": 2, "a": 1}
    )


def test_canonical_hash_none_equals_empty() -> None:
    """A ``None`` argument set hashes the same as an empty dict."""
    assert canonical_argument_hash(None) == canonical_argument_hash({})


def test_adapt_none_returns_empty() -> None:
    """A text-only turn (no ``tool_calls``) yields no replay steps."""
    assert adapt_agent_tool_calls_v1_to_replay(None, turn_id="t") == []


def test_adapt_filters_running_submit_and_malformed() -> None:
    """Running calls, the synthetic submit, blank names, and non-mappings drop out."""
    calls = [
        {
            "tool": "alpha",
            "status": "done",
            "payload": {"arguments": {"k": 1}, "result": "r"},
        },
        {"tool": "pending", "status": "running", "payload": {}},
        {"tool": "submit", "status": "done", "payload": {}},
        {"tool": "", "status": "done"},
        {"status": "done"},
        "not-a-mapping",
    ]
    steps = adapt_agent_tool_calls_v1_to_replay(calls, turn_id="t")
    assert [s.tool_name for s in steps] == ["alpha"]
    assert steps[0].status == "done"
    assert steps[0].result == "r"
    assert steps[0].argument_hash == canonical_argument_hash({"k": 1})


def test_adapt_marks_non_done_status_as_error() -> None:
    """Any non-``done`` resolved status is normalized to ``error``."""
    calls = [
        {
            "tool": "alpha",
            "status": "error",
            "payload": {"arguments": {}, "result": "boom"},
        }
    ]
    steps = adapt_agent_tool_calls_v1_to_replay(calls, turn_id="t")
    assert steps[0].status == "error"
    assert steps[0].result == "boom"


def test_adapt_respects_max_steps() -> None:
    """``max_steps`` truncates the recorded prefix (used by ``--dry-run``)."""
    calls = [{"tool": f"t{i}", "status": "done", "payload": {}} for i in range(5)]
    steps = adapt_agent_tool_calls_v1_to_replay(calls, turn_id="t", max_steps=2)
    assert len(steps) == 2
