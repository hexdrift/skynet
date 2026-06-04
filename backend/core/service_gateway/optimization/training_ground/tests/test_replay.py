"""Unit tests for the V1 ``tool_calls`` → ``ReplayStep`` adapter + arg hashing.

The mock's rollout behavior is pinned in ``test_contract_fixes.py``; this
module covers the ingestion edge of §5 — converting a persisted
``agent_messages.tool_calls`` row into ordered ``ReplayStep`` records and
the canonical argument hash that step-matching depends on.
"""

from __future__ import annotations

import pytest

from core.service_gateway.optimization.training_ground.replay import (
    ReplayTerminated,
    TraceConditionedMCPMock,
    adapt_agent_tool_calls_v1_to_replay,
    canonical_argument_hash,
)
from core.service_gateway.optimization.training_ground.types import (
    EvaluationExample,
    ReplayStep,
)


def _step(tool: str, arguments: dict) -> ReplayStep:
    """Build a done ``ReplayStep`` carrying the canonical hash of ``arguments``."""
    return ReplayStep(
        tool_name=tool,
        arguments=arguments,
        argument_hash=canonical_argument_hash(arguments),
        status="done",
        result={"value": tool},
        reason=None,
        started_at_ms=None,
        ended_at_ms=None,
    )


def _two_step_example() -> EvaluationExample:
    """Build an example whose recorded trajectory is A(args1) then B(args2)."""
    return EvaluationExample(
        turn_id="t-mm",
        user_message="",
        wizard_state_before={},
        wizard_state_after={},
        allowed_tools=frozenset({"A", "B"}),
        tool_schema_hashes={},
        replay_steps=(_step("A", {"args": 1}), _step("B", {"args": 2})),
        chat_history=(),
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


def test_exact_mode_diverges_on_wrong_args() -> None:
    """In ``exact`` mode (default) a wrong-arg call to A terminates after one step."""
    example = _two_step_example()
    mock = TraceConditionedMCPMock(example)

    with pytest.raises(ReplayTerminated):
        mock._on_candidate_call("A", {"args": "WRONG"})
    # ReActV2 keeps looping; the post-termination B call re-raises and never hits.
    with pytest.raises(ReplayTerminated):
        mock._on_candidate_call("B", {"args": "WRONG"})
    rollout = mock.rollout_so_far()

    assert [e.outcome for e in rollout.events] == ["no_data"]
    assert rollout.terminated_early
    assert rollout.terminated_reason == "no_data"


def test_tool_name_mode_hits_on_name_match_despite_wrong_args() -> None:
    """In ``tool_name`` mode wrong-arg calls to A then B both hit and advance."""
    example = _two_step_example()
    mock = TraceConditionedMCPMock(example, match_mode="tool_name")

    assert mock._on_candidate_call("A", {"args": "WRONG"}) == {"value": "A"}
    assert mock._on_candidate_call("B", {"args": "WRONG"}) == {"value": "B"}
    rollout = mock.rollout_so_far()

    assert [e.outcome for e in rollout.events] == ["hit", "hit"]
    assert not rollout.terminated_early
    # The hit events carry matched_step so the reward can score arg fidelity:
    # the candidate hash differs from the recorded step's hash.
    assert rollout.events[0].matched_step is example.replay_steps[0]
    assert rollout.events[1].matched_step is example.replay_steps[1]
    assert (
        rollout.events[0].candidate_argument_hash
        != rollout.events[0].matched_step.argument_hash
    )
