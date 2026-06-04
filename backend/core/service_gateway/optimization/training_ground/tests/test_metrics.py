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
    GENERAL_REWARD_SPEC,
    REPLAY_MATCH_REWARD_SPEC,
    _gate_score,
    feedback_from_low_dims,
    general_vector_reward,
    replay_match_vector_reward,
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
    """When every dim is ≥ 0.99 the feedback praises the reproduced sequence.

    The top-score branch now emits an informative "preserve this behavior"
    line instead of a bare "all dims ≥ 0.99" sentinel, so the proposer gets
    actionable signal even at the maximum score.
    """
    vec = dict.fromkeys(_WEIGHTS, 1.0)
    example = _make_example()
    rollout = TraceConditionedMCPMock(example).rollout_so_far()
    assert "Preserve this tool-selection behavior" in feedback_from_low_dims(
        vec, rollout, example
    )


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


_GENERAL_DIMS = frozenset(
    {
        "tool_selection",
        "argument_fidelity",
        "trajectory_coverage",
        "in_scope_tools",
        "clean_termination",
        "no_schema_drift",
        "observation_threading",
        "engaged_when_expected",
    }
)


def test_general_vector_reward_full_coverage_non_wizard_rollout() -> None:
    """A clean, fully-matched non-wizard rollout scores every §6.1 dim in [0, 1].

    The example carries a generic (non-wizard) ``stage`` snapshot and a
    plain ``search`` tool so no generalist/wizard semantics leak in: the
    8-dim general vector is derived purely from the replay trajectory.
    """
    step_one = _make_step("search", {"query": "alpha"})
    step_two = _make_step("search", {"query": "beta"})
    example = EvaluationExample(
        turn_id="general-1",
        user_message="find it",
        wizard_state_before={"stage": "search"},
        wizard_state_after={"stage": "search"},
        allowed_tools=frozenset({"search"}),
        tool_schema_hashes={},
        replay_steps=(step_one, step_two),
        chat_history=(),
    )
    mock = TraceConditionedMCPMock(example)
    mock._on_candidate_call("search", {"query": "alpha"})
    mock._on_candidate_call("search", {"query": "beta"})
    mock.record_submit({"assistant_message": "done"})
    rollout = mock.rollout_so_far()

    vec = general_vector_reward(example, rollout)

    assert set(vec) == _GENERAL_DIMS
    assert all(0.0 <= v <= 1.0 for v in vec.values())
    assert vec["trajectory_coverage"] == pytest.approx(1.0)
    assert vec["in_scope_tools"] == pytest.approx(1.0)
    assert vec["clean_termination"] == pytest.approx(1.0)


def test_general_vector_reward_no_critical_floor_misfire_on_clean_rollout() -> None:
    """A fully-matched non-wizard rollout clears every critical floor.

    None of ``GENERAL_REWARD_SPEC``'s critical dims dip below the floor, so
    the scalar must be the uncapped weighted mean — well above ``hard_cap``.
    """
    step = _make_step("search", {"query": "alpha"})
    example = EvaluationExample(
        turn_id="general-2",
        user_message="find it",
        wizard_state_before={"stage": "search"},
        wizard_state_after={"stage": "search"},
        allowed_tools=frozenset({"search"}),
        tool_schema_hashes={},
        replay_steps=(step,),
        chat_history=(),
    )
    mock = TraceConditionedMCPMock(example)
    mock._on_candidate_call("search", {"query": "alpha"})
    mock.record_submit({"assistant_message": "done"})
    rollout = mock.rollout_so_far()

    vec = general_vector_reward(example, rollout)

    for dim in GENERAL_REWARD_SPEC.critical_set:
        assert vec[dim] >= GENERAL_REWARD_SPEC.critical_floor
    scalar = scalar_with_hard_caps(vec, GENERAL_REWARD_SPEC)
    assert scalar > GENERAL_REWARD_SPEC.hard_cap


def test_general_spec_hard_cap_trips_when_coverage_collapses() -> None:
    """A divergent rollout collapses ``trajectory_coverage`` and trips the cap.

    The candidate never matches the single recorded step (calls an
    out-of-scope tool), so coverage falls to 0.0 — below the critical
    floor — and ``scalar_with_hard_caps`` caps the scalar at ``hard_cap``.
    """
    step = _make_step("search", {"query": "alpha"})
    example = EvaluationExample(
        turn_id="general-3",
        user_message="find it",
        wizard_state_before={"stage": "search"},
        wizard_state_after={"stage": "search"},
        allowed_tools=frozenset({"search"}),
        tool_schema_hashes={},
        replay_steps=(step,),
        chat_history=(),
    )
    mock = TraceConditionedMCPMock(example)
    with pytest.raises(ReplayTerminated):
        mock._on_candidate_call("ghost", {"query": "alpha"})
    rollout = mock.rollout_so_far()

    vec = general_vector_reward(example, rollout)

    assert vec["trajectory_coverage"] == pytest.approx(0.0)
    assert scalar_with_hard_caps(vec, GENERAL_REWARD_SPEC) <= GENERAL_REWARD_SPEC.hard_cap


def test_general_spec_weights_sum_to_one() -> None:
    """The general preset's weights sum to 1.0 so an all-1.0 vector scalarizes to 1.0."""
    assert sum(GENERAL_REWARD_SPEC.weights.values()) == pytest.approx(1.0)
    full = dict.fromkeys(GENERAL_REWARD_SPEC.weights, 1.0)
    assert scalar_with_hard_caps(full, GENERAL_REWARD_SPEC) == pytest.approx(1.0)


_REPLAY_MATCH_DIMS = frozenset(
    {
        "tool_selection",
        "argument_fidelity",
        "in_scope_tools",
        "engaged_when_expected",
        "no_schema_drift",
    }
)


def _tool_name_rollout(example: EvaluationExample, *calls: tuple[str, dict]):
    """Run a sequence of candidate calls through a ``tool_name``-mode mock.

    Swallows ``ReplayTerminated`` so divergent sequences still yield a
    snapshot — the reward reads the recorded events, not the raised signal.
    """
    mock = TraceConditionedMCPMock(example, match_mode="tool_name")
    for tool, args in calls:
        try:
            mock._on_candidate_call(tool, args)
        except ReplayTerminated:
            break
    return mock.rollout_so_far()


def test_replay_match_perfect_all_dims_one() -> None:
    """A fully-reproduced sequence with exact args scores 1.0 on every dim."""
    step_one = _make_step("alpha", {"k": 1})
    step_two = _make_step("beta", {"k": 2})
    example = _make_example(
        allowed_tools=frozenset({"alpha", "beta"}),
        replay_steps=(step_one, step_two),
    )
    rollout = _tool_name_rollout(example, ("alpha", {"k": 1}), ("beta", {"k": 2}))

    vec = replay_match_vector_reward(example, rollout)

    assert set(vec) == _REPLAY_MATCH_DIMS
    assert all(v == pytest.approx(1.0) for v in vec.values())


def test_replay_match_partial_coverage() -> None:
    """Matching the first of two steps then diverging scores partial coverage."""
    step_one = _make_step("alpha", {"k": 1})
    step_two = _make_step("beta", {"k": 2})
    example = _make_example(
        allowed_tools=frozenset({"alpha", "beta"}),
        replay_steps=(step_one, step_two),
    )
    rollout = _tool_name_rollout(example, ("alpha", {"k": 1}), ("alpha", {"k": 9}))

    vec = replay_match_vector_reward(example, rollout)

    assert vec["tool_selection"] == pytest.approx(0.5)
    assert 0.0 < vec["tool_selection"] < 1.0
    assert vec["engaged_when_expected"] == pytest.approx(1.0)


def test_replay_match_zero_hits_diverged_still_engaged() -> None:
    """A wrong-tool call (zero hits, one divergence event) → coverage/fidelity 0.0.

    The candidate engaged (it recorded a divergence event), so
    ``engaged_when_expected`` stays 1.0 — only the silent never-called-a-tool
    case zeroes it (covered by ``test_replay_match_zero_hits_idle``).
    """
    step = _make_step("alpha", {"k": 1})
    example = _make_example(allowed_tools=frozenset({"alpha"}), replay_steps=(step,))
    mock = TraceConditionedMCPMock(example, match_mode="tool_name")
    with pytest.raises(ReplayTerminated):
        mock._on_candidate_call("ghost", {"k": 1})
    rollout = mock.rollout_so_far()

    vec = replay_match_vector_reward(example, rollout)

    assert vec["tool_selection"] == pytest.approx(0.0)
    assert vec["argument_fidelity"] == pytest.approx(0.0)
    assert vec["engaged_when_expected"] == pytest.approx(1.0)


def test_replay_match_zero_hits_idle() -> None:
    """Recorded steps exist but the candidate never called a tool → engaged 0.0."""
    step = _make_step("alpha", {"k": 1})
    example = _make_example(allowed_tools=frozenset({"alpha"}), replay_steps=(step,))
    rollout = TraceConditionedMCPMock(example, match_mode="tool_name").rollout_so_far()

    vec = replay_match_vector_reward(example, rollout)

    assert vec["tool_selection"] == pytest.approx(0.0)
    assert vec["argument_fidelity"] == pytest.approx(0.0)
    assert vec["engaged_when_expected"] == pytest.approx(0.0)


def test_replay_match_no_steps_engaged_one_when_idle() -> None:
    """No recorded steps and no events → engaged 1.0, coverage/fidelity 1.0."""
    example = _make_example(allowed_tools=frozenset({"alpha"}), replay_steps=())
    rollout = TraceConditionedMCPMock(example, match_mode="tool_name").rollout_so_far()

    vec = replay_match_vector_reward(example, rollout)

    assert vec["tool_selection"] == pytest.approx(1.0)
    assert vec["argument_fidelity"] == pytest.approx(1.0)
    assert vec["engaged_when_expected"] == pytest.approx(1.0)


def test_replay_match_no_steps_engaged_half_when_active() -> None:
    """No recorded steps but the candidate still called a tool → engaged 0.5."""
    example = _make_example(allowed_tools=frozenset({"alpha"}), replay_steps=())
    mock = TraceConditionedMCPMock(example, match_mode="tool_name")
    with pytest.raises(ReplayTerminated):
        mock._on_candidate_call("alpha", {"k": 1})
    rollout = mock.rollout_so_far()

    vec = replay_match_vector_reward(example, rollout)

    assert vec["engaged_when_expected"] == pytest.approx(0.5)


def test_replay_match_out_of_scope_zeros_in_scope_dim() -> None:
    """A call to a tool outside the allowed set zeroes ``in_scope_tools``."""
    step = _make_step("alpha", {"k": 1})
    example = _make_example(allowed_tools=frozenset({"alpha"}), replay_steps=(step,))
    mock = TraceConditionedMCPMock(example, match_mode="tool_name")
    with pytest.raises(ReplayTerminated):
        mock._on_candidate_call("forbidden", {"k": 1})
    rollout = mock.rollout_so_far()

    vec = replay_match_vector_reward(example, rollout)

    assert vec["in_scope_tools"] == pytest.approx(0.0)


def test_replay_match_right_tools_wrong_args() -> None:
    """Right tools in order but divergent args → coverage 1.0, fidelity < 1.0."""
    step_one = _make_step("alpha", {"k": 1})
    step_two = _make_step("beta", {"k": 2})
    example = _make_example(
        allowed_tools=frozenset({"alpha", "beta"}),
        replay_steps=(step_one, step_two),
    )
    rollout = _tool_name_rollout(example, ("alpha", {"k": 1}), ("beta", {"k": 99}))

    vec = replay_match_vector_reward(example, rollout)

    assert vec["tool_selection"] == pytest.approx(1.0)
    assert vec["argument_fidelity"] == pytest.approx(0.5)
    assert vec["argument_fidelity"] < 1.0


def test_replay_match_weights_sum_to_one() -> None:
    """The replay-match preset weights sum to 1.0 and the spec carries no cap."""
    assert sum(REPLAY_MATCH_REWARD_SPEC.weights.values()) == pytest.approx(1.0)
    assert REPLAY_MATCH_REWARD_SPEC.critical_set == frozenset()
    full = dict.fromkeys(REPLAY_MATCH_REWARD_SPEC.weights, 1.0)
    assert scalar_with_hard_caps(full, REPLAY_MATCH_REWARD_SPEC) == pytest.approx(1.0)


def test_hit_event_evidence_args_exact() -> None:
    """An exact-arg hit records evidence noting the args matched."""
    step = _make_step("alpha", {"k": 1})
    example = _make_example(allowed_tools=frozenset({"alpha"}), replay_steps=(step,))
    mock = TraceConditionedMCPMock(example, match_mode="tool_name")
    mock._on_candidate_call("alpha", {"k": 1})
    rollout = mock.rollout_so_far()

    evidence = rollout.events[0].evidence
    assert "matched 'alpha'" in evidence
    assert "args exact" in evidence


def test_hit_event_evidence_args_differ() -> None:
    """A name-match-only hit records evidence noting the args differ."""
    step = _make_step("alpha", {"k": 1})
    example = _make_example(allowed_tools=frozenset({"alpha"}), replay_steps=(step,))
    mock = TraceConditionedMCPMock(example, match_mode="tool_name")
    mock._on_candidate_call("alpha", {"k": 999})
    rollout = mock.rollout_so_far()

    evidence = rollout.events[0].evidence
    assert "matched 'alpha'" in evidence
    assert "right tool, args differ" in evidence
