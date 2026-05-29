"""Unit tests for the §6 reward scalarizer, gate ladder, and feedback string.

Pins the hard-cap behavior of ``scalar_with_hard_caps`` (the reward-hacking
defense), the monotonic ``_gate_score`` phase ladder that ``gate_progress``
is built on, and the evidence-rich ``feedback_from_low_dims`` string the
reflective proposer consumes.
"""

from __future__ import annotations

import pytest

from core.service_gateway.optimization.training_ground.metrics import (
    _HARD_CAP,
    _WEIGHTS,
    _gate_score,
    feedback_from_low_dims,
    scalar_with_hard_caps,
)
from core.service_gateway.optimization.training_ground.replay import (
    ReplayTerminated,
    TraceConditionedMCPMock,
    canonical_argument_hash,
)
from core.service_gateway.optimization.training_ground.types import (
    EvaluationExample,
    ReplayStep,
)


def _make_example(
    *,
    turn_id: str = "t-1",
    allowed_tools: frozenset[str] = frozenset(),
    replay_steps: tuple[ReplayStep, ...] = (),
) -> EvaluationExample:
    """Build a minimal EvaluationExample for metric tests."""
    return EvaluationExample(
        turn_id=turn_id,
        user_message="",
        wizard_state_before={},
        wizard_state_after={},
        allowed_tools=allowed_tools,
        tool_schema_hashes={},
        replay_steps=replay_steps,
        chat_history=(),
    )


def _make_step(tool: str, arguments: dict, *, status: str = "done") -> ReplayStep:
    """Build a ``ReplayStep`` with the canonical argument hash."""
    return ReplayStep(
        tool_name=tool,
        arguments=arguments,
        argument_hash=canonical_argument_hash(arguments),
        status=status,  # type: ignore[arg-type]
        result={"ok": True},
        reason=None,
        started_at_ms=None,
        ended_at_ms=None,
    )


def test_scalar_all_pass_is_full_weighted_mean() -> None:
    """All dims at 1.0 give the full weighted mean (weights sum to 1.0)."""
    vec = dict.fromkeys(_WEIGHTS, 1.0)
    assert scalar_with_hard_caps(vec) == pytest.approx(1.0)


def test_scalar_hard_cap_trips_on_low_critical_dim() -> None:
    """A single critical dim below the floor caps the scalar at ``_HARD_CAP``."""
    vec = dict.fromkeys(_WEIGHTS, 1.0)
    vec["gate_progress"] = 0.0
    assert scalar_with_hard_caps(vec) == pytest.approx(_HARD_CAP)


def test_scalar_low_non_critical_dim_does_not_cap() -> None:
    """A low non-critical dim only docks its weight — no hard cap."""
    vec = dict.fromkeys(_WEIGHTS, 1.0)
    vec["observation_usefulness"] = 0.0
    out = scalar_with_hard_caps(vec)
    assert out > _HARD_CAP
    assert out == pytest.approx(1.0 - _WEIGHTS["observation_usefulness"])


def test_scalar_empty_vector_is_zero() -> None:
    """Missing dims count as 0.0 and trip no cap (no critical dim is present)."""
    assert scalar_with_hard_caps({}) == pytest.approx(0.0)


def test_gate_score_empty_state_is_zero() -> None:
    """An empty wizard snapshot scores 0.0 (intake, no progress)."""
    assert _gate_score({}) == 0.0


def test_gate_score_ladder_is_monotonic() -> None:
    """Each rung of the wizard ladder scores strictly higher; full = 1.0."""
    intake = _gate_score({})
    dataset = _gate_score({"dataset_ready": True})
    configured = _gate_score({"dataset_ready": True, "columns_configured": True})
    full = _gate_score(
        {
            "dataset_ready": True,
            "columns_configured": True,
            "signature_code": "s",
            "metric_code": "m",
            "model_configured": True,
            "submitted": True,
        }
    )
    assert intake < dataset < configured < full
    assert full == pytest.approx(1.0)


def test_gate_score_model_config_name_counts_as_model_rung() -> None:
    """A ``model_config`` with a name scores the model rung without ``model_configured``."""
    assert _gate_score({"model_config": {"name": "gpt"}}) == pytest.approx(0.15)


def test_feedback_all_high_returns_sentinel() -> None:
    """When every dim is ≥ 0.99 the feedback is the all-clear sentinel."""
    vec = dict.fromkeys(_WEIGHTS, 1.0)
    example = _make_example()
    rollout = TraceConditionedMCPMock(example).rollout_so_far()
    assert "≥ 0.99" in feedback_from_low_dims(vec, rollout, example)


def test_feedback_surfaces_lowest_dims_and_missing_submit() -> None:
    """The string names the turn, the worst dims, and the missing submit."""
    vec = dict.fromkeys(_WEIGHTS, 1.0)
    vec["submit_clean"] = 0.0
    vec["gate_progress"] = 0.1
    example = _make_example(turn_id="turn-X")
    rollout = TraceConditionedMCPMock(example).rollout_so_far()
    out = feedback_from_low_dims(vec, rollout, example, max_dims=2)
    assert "turn-X" in out
    assert "submit_clean" in out
    assert "never called the submit tool" in out


def test_feedback_reports_early_termination() -> None:
    """A diverged rollout surfaces the early-termination note for the proposer."""
    step = _make_step("alpha", {"k": 1})
    example = _make_example(allowed_tools=frozenset({"alpha"}), replay_steps=(step,))
    mock = TraceConditionedMCPMock(example)
    with pytest.raises(ReplayTerminated):
        mock._on_candidate_call("ghost", {"k": 1})
    rollout = mock.rollout_so_far()
    vec = dict.fromkeys(_WEIGHTS, 1.0)
    vec["no_phantom_refusal"] = 0.0
    out = feedback_from_low_dims(vec, rollout, example)
    assert "terminated early" in out
