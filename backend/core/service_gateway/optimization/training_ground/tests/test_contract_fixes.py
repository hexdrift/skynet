"""Regression tests for behaviors fixed in the Codex-review pass.

Each test pins down one contract clarified during the review so a future
refactor can't quietly regress it. Reference: ``training_ground_SPEC.md``
§5 (replay outcomes), §6 (gate_progress), §8 (drift detection), §11
(promotion gate).
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import dspy
import pytest

from core.service_gateway.optimization.training_ground import optimize
from core.service_gateway.optimization.training_ground.batch_sampler import (
    PedagogicalBatchSampler,
)
from core.service_gateway.optimization.training_ground.gepa_adapter import (
    _record_submit_from_prediction,
    _summarize_rollout,
)
from core.service_gateway.optimization.training_ground.metrics import (
    _no_forced_submit,
    vector_reward,
)
from core.service_gateway.optimization.training_ground.registry import (
    ToolSchemaDriftError,
    _apply_bundle_tool_overrides,
    _assert_tool_set_matches,
    fresh_program_for_bundle,
    hash_tool_schema,
)
from core.service_gateway.optimization.training_ground.replay import (
    ReplayTerminated,
    TraceConditionedMCPMock,
    canonical_argument_hash,
)
from core.service_gateway.optimization.training_ground.types import (
    Bundle,
    EvaluationExample,
    PairedBootstrapResult,
    ReplayStep,
)


class _RoundThreeSig(dspy.Signature):
    """Tiny signature for round-3 registry tests."""

    user_message: str = dspy.InputField()
    assistant_message: str = dspy.OutputField()


def _make_example(
    *,
    turn_id: str = "t-1",
    wizard_state_before: dict | None = None,
    wizard_state_after: dict | None = None,
    allowed_tools: frozenset[str] = frozenset(),
    tool_schema_hashes: dict[str, str] | None = None,
    replay_steps: tuple[ReplayStep, ...] = (),
) -> EvaluationExample:
    """Build an ``EvaluationExample`` with sensible defaults for these tests."""
    return EvaluationExample(
        turn_id=turn_id,
        user_message="",
        wizard_state_before=wizard_state_before or {},
        wizard_state_after=wizard_state_after or {},
        allowed_tools=allowed_tools,
        tool_schema_hashes=tool_schema_hashes or {},
        replay_steps=replay_steps,
        chat_history=(),
    )


def _make_step(tool: str, arguments: dict, *, status: str = "done", result=None) -> ReplayStep:
    """Build a ``ReplayStep`` with the canonical argument hash."""
    return ReplayStep(
        tool_name=tool,
        arguments=arguments,
        argument_hash=canonical_argument_hash(arguments),
        status=status,  # type: ignore[arg-type]
        result=result if result is not None else {"ok": True},
        reason=None,
        started_at_ms=None,
        ended_at_ms=None,
    )


def _tool(name: str, *, desc: str = "x", args: dict | None = None) -> SimpleNamespace:
    """A duck-typed stand-in for ``dspy.Tool`` — only the fields read by the registry."""
    return SimpleNamespace(name=name, desc=desc, args=args or {})


# ---------- §6: gate_progress is clamped to [0, 1], no +0.5 shift ----------


def test_gate_progress_zero_when_state_unchanged() -> None:
    """A stall must score 0 so it trips the <0.5 critical floor."""
    example = _make_example(
        wizard_state_before={"dataset_ready": True},
        wizard_state_after={"dataset_ready": True},
    )
    rollout = TraceConditionedMCPMock(example).rollout_so_far()
    vec = vector_reward(example, rollout)
    assert vec["gate_progress"] == pytest.approx(0.0)


def test_gate_progress_zero_when_state_regresses() -> None:
    """A regression must clamp to 0, not produce a negative score."""
    example = _make_example(
        wizard_state_before={"dataset_ready": True, "columns_configured": True},
        wizard_state_after={"dataset_ready": True},
    )
    rollout = TraceConditionedMCPMock(example).rollout_so_far()
    vec = vector_reward(example, rollout)
    assert vec["gate_progress"] == pytest.approx(0.0)


def test_gate_progress_positive_when_state_advances() -> None:
    """A real advance must produce a positive score in [0, 1]."""
    example = _make_example(
        wizard_state_before={},
        wizard_state_after={"dataset_ready": True},
    )
    rollout = TraceConditionedMCPMock(example).rollout_so_far()
    vec = vector_reward(example, rollout)
    assert 0.0 < vec["gate_progress"] <= 1.0


# ---------- §5: TraceConditionedMCPMock uses ordered pointer matching ----------


def test_replay_terminates_on_out_of_order_call() -> None:
    """Calling step[1]'s tool before step[0] must terminate with no_data, not hit."""
    step0 = _make_step("alpha", {"k": 1})
    step1 = _make_step("beta", {"k": 2})
    example = _make_example(
        allowed_tools=frozenset({"alpha", "beta"}),
        replay_steps=(step0, step1),
    )
    mock = TraceConditionedMCPMock(example)
    with pytest.raises(ReplayTerminated):
        mock._on_candidate_call("beta", {"k": 2})
    rollout = mock.rollout_so_far()
    assert rollout.terminated_early is True
    assert rollout.terminated_reason == "no_data"
    assert rollout.events[0].outcome == "no_data"


def test_replay_hit_advances_pointer() -> None:
    """An exact match must return the recorded result and advance the pointer."""
    step0 = _make_step("alpha", {"k": 1}, result={"value": 42})
    step1 = _make_step("beta", {"k": 2}, result={"value": 99})
    example = _make_example(
        allowed_tools=frozenset({"alpha", "beta"}),
        replay_steps=(step0, step1),
    )
    mock = TraceConditionedMCPMock(example)
    assert mock._on_candidate_call("alpha", {"k": 1}) == {"value": 42}
    assert mock._on_candidate_call("beta", {"k": 2}) == {"value": 99}
    rollout = mock.rollout_so_far()
    assert rollout.terminated_early is False
    assert [e.outcome for e in rollout.events] == ["hit", "hit"]


def test_replay_terminates_when_pointer_exhausted() -> None:
    """A call after the last recorded step must terminate with no_data."""
    step0 = _make_step("alpha", {"k": 1}, result={"value": 1})
    example = _make_example(
        allowed_tools=frozenset({"alpha"}),
        replay_steps=(step0,),
    )
    mock = TraceConditionedMCPMock(example)
    mock._on_candidate_call("alpha", {"k": 1})
    with pytest.raises(ReplayTerminated):
        mock._on_candidate_call("alpha", {"k": 1})
    assert mock.rollout_so_far().terminated_reason == "no_data"


def test_replay_terminates_on_unallowed_tool() -> None:
    """A call against a tool outside allowed_tools must mark tool_not_allowed."""
    example = _make_example(
        allowed_tools=frozenset({"alpha"}),
        replay_steps=(_make_step("alpha", {"k": 1}),),
    )
    mock = TraceConditionedMCPMock(example)
    with pytest.raises(ReplayTerminated):
        mock._on_candidate_call("gamma", {"k": 1})
    assert mock.rollout_so_far().terminated_reason == "tool_not_allowed"


# ---------- §8: hash_tool_schema is strict canonical JSON ----------


def test_hash_tool_schema_is_stable_under_key_reorder() -> None:
    """Two tools with the same logical schema must hash to the same digest."""
    tool_a = _tool("alpha", desc="d", args={"x": {"type": "int"}, "y": {"type": "str"}})
    tool_b = _tool("alpha", desc="d", args={"y": {"type": "str"}, "x": {"type": "int"}})
    assert hash_tool_schema(tool_a) == hash_tool_schema(tool_b)


def test_hash_tool_schema_changes_on_desc_edit() -> None:
    """A prompt-only desc edit must invalidate the hash (bundle drift signal)."""
    tool_v1 = _tool("alpha", desc="original", args={})
    tool_v2 = _tool("alpha", desc="reworded", args={})
    assert hash_tool_schema(tool_v1) != hash_tool_schema(tool_v2)


def test_hash_tool_schema_rejects_nan() -> None:
    """NaN/Inf must raise rather than silently hash as the Python repr."""
    tool = _tool("alpha", desc="d", args={"x": {"default": math.nan}})
    with pytest.raises(ValueError):
        hash_tool_schema(tool)


# ---------- §8: _assert_tool_set_matches is intersection-only ----------


def test_assert_tool_set_matches_allows_bundle_only_tools() -> None:
    """Bundle tool missing from live (phased out) must NOT raise."""
    bundle_hashes = {
        "alpha": hash_tool_schema(_tool("alpha")),
        "phased_out": hash_tool_schema(_tool("phased_out")),
    }
    live = [_tool("alpha")]
    _assert_tool_set_matches(bundle_hashes, live)


def test_assert_tool_set_matches_allows_live_only_tools() -> None:
    """Live tool missing from bundle (added after training) must NOT raise."""
    bundle_hashes = {"alpha": hash_tool_schema(_tool("alpha"))}
    live = [_tool("alpha"), _tool("newcomer")]
    _assert_tool_set_matches(bundle_hashes, live)


def test_assert_tool_set_matches_raises_on_intersection_drift() -> None:
    """A tool present in both with a different hash IS drift and must raise."""
    bundle_hashes = {"alpha": hash_tool_schema(_tool("alpha", desc="v1"))}
    live = [_tool("alpha", desc="v2")]
    with pytest.raises(ToolSchemaDriftError):
        _assert_tool_set_matches(bundle_hashes, live)


# ---------- optimize._filter_trainable_examples drops drift & missing ----------


def test_filter_drops_examples_with_unknown_tools() -> None:
    """Examples calling tools the live MCP no longer exposes must be filtered."""
    live_hashes = {"alpha": "h-alpha"}
    keep = _make_example(
        allowed_tools=frozenset({"alpha"}),
        tool_schema_hashes={"alpha": "h-alpha"},
    )
    drop = _make_example(
        turn_id="t-2",
        allowed_tools=frozenset({"alpha", "ghost"}),
        tool_schema_hashes={"alpha": "h-alpha", "ghost": "h-ghost"},
    )
    out = optimize._filter_trainable_examples(
        [keep, drop], live_hashes=live_hashes
    )
    assert [e.turn_id for e in out] == ["t-1"]


def test_filter_drops_examples_with_schema_drift() -> None:
    """Examples whose recorded hash for a live tool drifted must be filtered."""
    live_hashes = {"alpha": "h-new"}
    keep = _make_example(
        allowed_tools=frozenset({"alpha"}),
        tool_schema_hashes={"alpha": "h-new"},
    )
    drift = _make_example(
        turn_id="t-2",
        allowed_tools=frozenset({"alpha"}),
        tool_schema_hashes={"alpha": "h-old"},
    )
    out = optimize._filter_trainable_examples(
        [keep, drift], live_hashes=live_hashes
    )
    assert [e.turn_id for e in out] == ["t-1"]


# ---------- §11: per-phase ≥30 floor in _resolve_promotion ----------


def _ok_bootstrap() -> PairedBootstrapResult:
    """A bootstrap result that clears the §11 CI lower bound."""
    return PairedBootstrapResult(
        resamples=10_000, mean_delta=0.1, ci95_lower=0.05, ci95_upper=0.15
    )


def _phase_example(phase_state: dict) -> EvaluationExample:
    """Make an example whose wizard_state_before sits in the requested phase."""
    return _make_example(wizard_state_before=phase_state)


def test_promotion_blocks_when_phase_under_floor() -> None:
    """If any populated phase has <30 examples, the bundle must be blocked."""
    # 200 ready_to_submit examples + 5 intake examples = 205 total, phase floor trips.
    ready = [
        _phase_example(
            {
                "dataset_ready": True,
                "signature_code": "x",
                "metric_code": "y",
                "model_configured": True,
            }
        )
        for _ in range(200)
    ]
    intake = [_phase_example({}) for _ in range(5)]
    verdict = optimize._resolve_promotion(
        bootstrap=_ok_bootstrap(),
        baseline_objectives=[],
        candidate_objectives=[],
        holdout_examples=ready + intake,
    )
    assert verdict.promotable is False
    assert any("intake" in r for r in verdict.reasons)


def test_promotion_blocks_when_total_under_floor() -> None:
    """If total holdout is <200, the bundle must be blocked even if phases pass."""
    examples = [_phase_example({"dataset_ready": True}) for _ in range(50)]
    verdict = optimize._resolve_promotion(
        bootstrap=_ok_bootstrap(),
        baseline_objectives=[],
        candidate_objectives=[],
        holdout_examples=examples,
    )
    assert verdict.promotable is False
    assert any("held-out scale: 50" in r for r in verdict.reasons)


def test_promotion_passes_when_all_thresholds_met() -> None:
    """A holdout with ≥200 total AND ≥30 per phase AND clean stats must promote."""
    ready = [
        _phase_example(
            {
                "dataset_ready": True,
                "signature_code": "x",
                "metric_code": "y",
                "model_configured": True,
            }
        )
        for _ in range(220)
    ]
    verdict = optimize._resolve_promotion(
        bootstrap=_ok_bootstrap(),
        baseline_objectives=[],
        candidate_objectives=[],
        holdout_examples=ready,
    )
    assert verdict.promotable is True
    assert verdict.reasons == ()


# ---------- §9: --force diverts to inspection-only filename ----------


def test_inspection_only_path_inserts_suffix(tmp_path) -> None:
    """The forced-write path must sit beside --out, not overwrite it."""
    target = tmp_path / "2026-05-28.json"
    inspected = optimize._inspection_only_path(target)
    assert inspected.name == "2026-05-28.inspection-only.json"
    assert inspected.parent == target.parent
    assert inspected != target


# ---------- Batch sampler: best_score is all-time, not windowed ----------


def test_batch_sampler_uses_alltime_best_score() -> None:
    """Once an id has seen a high score, the deficit term stays anchored to it.

    Even if recent observations drop, weight = base + (1 - best) * gain must
    reflect the historical ceiling — otherwise the sampler keeps over-sampling
    already-mastered ids whose windowed buffer rotated out the win.
    """
    sampler = PedagogicalBatchSampler(batch_size=2, seed=0)
    # Hand-craft a trace where id "A" once scored 1.0 then fell back.
    trace = [
        {"subsample_ids": ["A"], "subsample_scores": [1.0]},
        # Push the high score out of the recent window (size 6).
        *(
            {"subsample_ids": ["A"], "subsample_scores": [0.1]}
            for _ in range(6)
        ),
    ]
    state = SimpleNamespace(full_program_trace=trace)
    history = sampler._build_score_history(state)
    # Windowed buffer no longer contains 1.0 …
    assert max(history["A"]) == pytest.approx(0.1)
    # … but the all-time tracker did.
    assert sampler._best_score["A"] == pytest.approx(1.0)
    # Weight uses the all-time best so the deficit term is (1 - 1.0) = 0.
    weight = sampler._weight_for("A", history)
    assert weight == pytest.approx(0.05)


# ---------- Round 2: sticky termination after divergence ----------


def test_replay_sticky_termination_blocks_post_divergence_hits() -> None:
    """After divergence, subsequent calls must re-raise immediately.

    ReActV2 catches ``ReplayTerminated`` per-tool and lets the candidate
    keep looping — without a sticky guard the next call could match the
    recorded step at the (unchanged) pointer and append a stray hit on
    top of the already-terminated rollout.
    """
    expected = _make_step("foo", {"x": 1})
    example = _make_example(
        allowed_tools=frozenset({"foo"}),
        replay_steps=(expected,),
    )
    mock = TraceConditionedMCPMock(example)
    with pytest.raises(ReplayTerminated):
        # ``ghost`` is not in allowed_tools -> tool_not_allowed divergence.
        mock._on_candidate_call("ghost", {"x": 1})
    # Same recorded args at the (untouched) pointer, but the rollout already
    # terminated — must re-raise immediately without appending a hit.
    with pytest.raises(ReplayTerminated):
        mock._on_candidate_call("foo", {"x": 1})
    rollout = mock.rollout_so_far()
    assert rollout.terminated_early is True
    assert rollout.terminated_reason == "tool_not_allowed"
    # Exactly one event recorded — the divergence. No phantom hit afterwards.
    assert len(rollout.events) == 1
    assert rollout.events[0].outcome == "tool_not_allowed"


def test_replay_record_submit_is_sticky_after_termination() -> None:
    """``record_submit`` is a no-op when the rollout already terminated.

    A submit emitted by ReActV2 after a tool-error observation must not
    flip ``submit_called`` to True — the rollout's prefix already failed
    and scoring should reflect that.
    """
    example = _make_example(allowed_tools=frozenset({"foo"}), replay_steps=())
    mock = TraceConditionedMCPMock(example)
    with pytest.raises(ReplayTerminated):
        mock._on_candidate_call("foo", {"x": 1})  # no recorded steps -> no_data
    mock.record_submit({"assistant_message": "hi"})
    rollout = mock.rollout_so_far()
    assert rollout.submit_called is False
    assert rollout.submit_payload is None


# ---------- Round 2: filter rejects unknown tools in tool_schema_hashes ----------


def test_filter_drops_examples_with_hash_for_missing_live_tool() -> None:
    """``tool_schema_hashes`` keys must be a subset of the live roster.

    A recorded hash for a tool that no longer exists live is unverifiable
    — the example may have been conditioned on a tool surface we can't
    reconstruct, so the filter must drop it rather than silently keep it.
    """
    live_hashes = {"foo": "h_foo"}
    example = _make_example(
        allowed_tools=frozenset({"foo"}),
        # Hash references a tool that's not in live_hashes anymore.
        tool_schema_hashes={"foo": "h_foo", "ghost": "h_ghost"},
    )
    kept = optimize._filter_trainable_examples([example], live_hashes=live_hashes)
    assert kept == []


# ---------- Round 2: mock no longer exposes a synthetic submit tool ----------


def test_replay_tool_layer_omits_submit() -> None:
    """ReActV2 reserves the name ``submit``; the mock must not collide.

    Passing a tool named ``submit`` to ``dspy.ReActV2`` raises
    ``ValueError`` at construction time, blowing up every rollout. The
    mock's ``tool_layer`` must return only the allowed MCP tools and
    leave submit to ReActV2's built-in.
    """
    example = _make_example(allowed_tools=frozenset({"foo", "bar"}))
    mock = TraceConditionedMCPMock(example)
    tools = mock.tool_layer()
    names = {tool.name for tool in tools}
    assert names == {"foo", "bar"}
    assert "submit" not in names


# ---------- Round 2: bundle round-trips tool_descriptions / tool_arg_descriptions ----------


def test_bundle_round_trips_tool_descriptions_and_arg_descriptions() -> None:
    """The Bundle schema must persist GEPA-mutated tool wording.

    ``program.save(save_program=False)`` discards the program's tools,
    so the optimized overlays live on the bundle directly and the
    runtime re-applies them in ``registry.fresh_program_for_bundle``.
    """
    bundle = Bundle(
        model_id="generalist",
        version="2026-05-28",
        dspy_version="3.3.0b1",
        gepa_version="0.1.1",
        gate_logic_version="abc123",
        tool_schema_hashes={"foo": "h_foo"},
        max_iters=8,
        program_state={"react": {"signature": {}}},
        tool_descriptions={"foo": "do the foo"},
        tool_arg_descriptions={"foo": {"x": "the x value"}},
        scalar_score=0.7,
        objective_scores={},
        window_days=30,
        trajectories_trained_on=400,
        trajectories_held_out=400,
        paired_bootstrap=PairedBootstrapResult(
            resamples=10_000,
            mean_delta=0.05,
            ci95_lower=0.04,
            ci95_upper=0.06,
        ),
    )
    blob = bundle.model_dump_json()
    restored = Bundle.model_validate_json(blob)
    assert restored.tool_descriptions == {"foo": "do the foo"}
    assert restored.tool_arg_descriptions == {"foo": {"x": "the x value"}}


def test_apply_bundle_tool_overrides_mutates_live_tool_desc_and_arg_desc() -> None:
    """Runtime overlay must mutate ``desc`` and per-arg ``description`` in place."""
    live_tool = _tool(
        "foo",
        desc="stale wording",
        args={"x": {"type": "integer", "description": "stale arg desc"}},
    )
    _apply_bundle_tool_overrides(
        [live_tool],
        tool_descriptions={"foo": "optimized wording"},
        tool_arg_descriptions={"foo": {"x": "optimized arg desc"}},
    )
    assert live_tool.desc == "optimized wording"
    assert live_tool.args["x"]["description"] == "optimized arg desc"


def test_apply_bundle_tool_overrides_skips_unknown_tools_and_args() -> None:
    """Live-only tools / args have no overlay; missing keys are silently skipped."""
    live_tool = _tool("foo", desc="live desc", args={"x": {"description": "live x"}})
    _apply_bundle_tool_overrides(
        [live_tool],
        # Bundle remembers a tool that is no longer exposed live.
        tool_descriptions={"ghost": "should be ignored"},
        # Bundle remembers an arg the live tool no longer has.
        tool_arg_descriptions={"foo": {"removed_arg": "n/a"}},
    )
    assert live_tool.desc == "live desc"
    assert live_tool.args == {"x": {"description": "live x"}}


# ---------- Round 2: mock proxy tools mirror live args for arg-desc overlays ----------


def test_mock_tool_layer_copies_live_args_when_available() -> None:
    """Proxies must carry the live tool's args so DSPy exposes per-arg schemas."""
    example = _make_example(allowed_tools=frozenset({"foo"}))
    mock = TraceConditionedMCPMock(example)
    live_foo = _tool(
        "foo",
        desc="live foo",
        args={"x": {"type": "integer", "description": "x value"}},
    )
    tools = mock.tool_layer(live_tools={"foo": live_foo})
    (proxy,) = tools
    assert proxy.name == "foo"
    assert proxy.args == {"x": {"type": "integer", "description": "x value"}}


def test_mock_tool_layer_falls_back_to_empty_args_without_live_tool() -> None:
    """No live tool means no args overlay — DSPy gets the ``**kwargs`` proxy.

    The default path stays a no-op so unit tests / dry-run code that
    don't have access to a live MCP roster still build a working
    rollout.
    """
    example = _make_example(allowed_tools=frozenset({"foo"}))
    mock = TraceConditionedMCPMock(example)
    tools = mock.tool_layer()  # no live_tools mapping
    (proxy,) = tools
    assert proxy.name == "foo"
    # No live args copied — dspy.Tool's introspection on **kwargs leaves
    # the schema empty (or a single kwargs entry), but the important
    # invariant is the proxy still works and didn't crash on construction.
    assert hasattr(proxy, "args")


# ---------- Round 3: clean submit vs forced_submit dispatch ----------


def test_record_forced_submit_does_not_set_submit_called() -> None:
    """Forced-submit fallbacks must not borrow ``submit_clean`` credit."""
    example = _make_example()
    mock = TraceConditionedMCPMock(example)
    mock.record_forced_submit()
    rollout = mock.rollout_so_far()
    assert rollout.forced_submit is True
    assert rollout.submit_called is False
    assert rollout.submit_payload is None


def test_record_submit_keeps_forced_flag_false() -> None:
    """Clean submit must leave ``forced_submit`` False — the two are disjoint."""
    example = _make_example()
    mock = TraceConditionedMCPMock(example)
    mock.record_submit({"assistant_message": "hi"})
    rollout = mock.rollout_so_far()
    assert rollout.submit_called is True
    assert rollout.forced_submit is False
    assert rollout.submit_payload == {"assistant_message": "hi"}


def test_no_forced_submit_metric_penalises_forced_path() -> None:
    """``forced_submit=True`` must score 0.0 even if rollout did not terminate."""
    example = _make_example()
    mock = TraceConditionedMCPMock(example)
    mock.record_forced_submit()
    rollout = mock.rollout_so_far()
    assert _no_forced_submit(rollout) == 0.0


def test_no_forced_submit_metric_rewards_clean_submit() -> None:
    """Clean submit must score 1.0 — regression-pin for the round-3 dispatch."""
    example = _make_example()
    mock = TraceConditionedMCPMock(example)
    mock.record_submit({"assistant_message": "hi"})
    rollout = mock.rollout_so_far()
    assert _no_forced_submit(rollout) == 1.0


def test_record_submit_from_prediction_dispatches_on_termination_reason() -> None:
    """``"submit"`` → record_submit, ``"forced_submit"`` → record_forced_submit."""
    example = _make_example()
    mock_clean = TraceConditionedMCPMock(example)
    mock_forced = TraceConditionedMCPMock(example)
    program = SimpleNamespace(
        signature=SimpleNamespace(output_fields={"assistant_message": object()})
    )

    clean_pred = SimpleNamespace(
        termination_reason="submit", assistant_message="done"
    )
    _record_submit_from_prediction(mock=mock_clean, program=program, pred=clean_pred)
    rollout_clean = mock_clean.rollout_so_far()
    assert rollout_clean.submit_called is True
    assert rollout_clean.forced_submit is False
    assert rollout_clean.submit_payload == {"assistant_message": "done"}

    forced_pred = SimpleNamespace(
        termination_reason="forced_submit", assistant_message="scaffold"
    )
    _record_submit_from_prediction(mock=mock_forced, program=program, pred=forced_pred)
    rollout_forced = mock_forced.rollout_so_far()
    assert rollout_forced.submit_called is False
    assert rollout_forced.forced_submit is True
    assert rollout_forced.submit_payload is None


def test_record_submit_from_prediction_ignores_other_terminations() -> None:
    """Unknown ``termination_reason`` must leave both submit flags False."""
    example = _make_example()
    mock = TraceConditionedMCPMock(example)
    program = SimpleNamespace(
        signature=SimpleNamespace(output_fields={"assistant_message": object()})
    )
    pred = SimpleNamespace(termination_reason="max_iters", assistant_message="x")
    _record_submit_from_prediction(mock=mock, program=program, pred=pred)
    rollout = mock.rollout_so_far()
    assert rollout.submit_called is False
    assert rollout.forced_submit is False


def test_summarize_rollout_exposes_forced_submit() -> None:
    """Reflective summary must surface ``forced_submit`` for the proposer.

    The reflective proposer reads ``_summarize_rollout`` as the
    "Generated Outputs" payload. Without ``forced_submit`` in the
    summary, iter-exhaustion paths and "ran fine but never submitted"
    paths look identical to the LM, so the proposer cannot generate
    feedback specific to the exhaustion failure mode.
    """
    example = _make_example()
    mock = TraceConditionedMCPMock(example)
    mock.record_forced_submit()
    rollout = mock.rollout_so_far()
    summary = _summarize_rollout(rollout)
    assert summary["forced_submit"] is True
    assert summary["submit_called"] is False


# ---------- Round 3: bundle overrides do not poison reusable mcp_tools ----------


def _round_three_bundle(
    *,
    tool_schema_hashes: dict[str, str],
    program_state: dict,
    tool_descriptions: dict[str, str] | None = None,
    tool_arg_descriptions: dict[str, dict[str, str]] | None = None,
) -> Bundle:
    """Build a minimal valid ``Bundle`` for the registry isolation tests."""
    return Bundle(
        model_id="generalist",
        version="2026-05-28",
        dspy_version=dspy.__version__,
        gepa_version="0.1.1",
        gate_logic_version="abc",
        tool_schema_hashes=tool_schema_hashes,
        max_iters=2,
        program_state=program_state,
        tool_descriptions=tool_descriptions or {},
        tool_arg_descriptions=tool_arg_descriptions or {},
        scalar_score=0.7,
        objective_scores={},
        window_days=30,
        trajectories_trained_on=400,
        trajectories_held_out=400,
        paired_bootstrap=PairedBootstrapResult(
            resamples=10_000,
            mean_delta=0.05,
            ci95_lower=0.04,
            ci95_upper=0.06,
        ),
    )


def test_fresh_program_for_bundle_does_not_mutate_caller_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runtime must deep-copy live tools before applying overlays.

    ``_apply_bundle_tool_overrides`` mutates ``tool.desc`` and the
    nested ``args[arg]['description']`` in place, and ``hash_tool_schema``
    covers ``desc``. If the runtime mutated the caller's list directly,
    reusing the same ``mcp_tools`` across two calls would flip the live
    hash and trigger ``ToolSchemaDriftError`` on the second call — a
    self-poisoning regression. The fix in ``fresh_program_for_bundle``
    deep-clones each tool before mutation.
    """
    # Pin the bundle's installed-version check to whatever dspy/gepa we have.
    monkeypatch.setattr(
        "core.service_gateway.optimization.training_ground.registry._installed_version",
        lambda name: {"dspy": dspy.__version__, "gepa": "0.1.1"}.get(name),  # noqa: PLW0108
    )
    seed_tool = dspy.Tool(
        func=lambda x: x,
        name="foo",
        desc="seed desc",
        args={"x": {"type": "integer", "description": "seed x desc"}},
    )
    seed_program = dspy.ReActV2(_RoundThreeSig, tools=[seed_tool], max_iters=2)
    program_state = seed_program.dump_state()
    bundle = _round_three_bundle(
        tool_schema_hashes={"foo": hash_tool_schema(seed_tool)},
        program_state=program_state,
        tool_descriptions={"foo": "overlay desc"},
        tool_arg_descriptions={"foo": {"x": "overlay x desc"}},
    )
    mcp_tools = [seed_tool]
    fresh_program_for_bundle(bundle, mcp_tools, seed_signature=_RoundThreeSig)
    assert seed_tool.desc == "seed desc"
    assert seed_tool.args["x"]["description"] == "seed x desc"

    # Second call must still pass the drift check — the live tool is pristine.
    fresh_program_for_bundle(bundle, mcp_tools, seed_signature=_RoundThreeSig)
    assert seed_tool.desc == "seed desc"


def test_fresh_program_for_bundle_applies_overlays_to_program_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The deep-clone path must still hand the overlays to ``ReActV2``.

    Mutating clones would be pointless if the program then ran against
    the un-overridden originals. Verify the constructed program holds
    tools with the overlay applied while the caller's seed_tool stays
    untouched (paired invariant with the test above).
    """
    monkeypatch.setattr(
        "core.service_gateway.optimization.training_ground.registry._installed_version",
        lambda name: {"dspy": dspy.__version__, "gepa": "0.1.1"}.get(name),  # noqa: PLW0108
    )
    seed_tool = dspy.Tool(
        func=lambda x: x,
        name="foo",
        desc="seed desc",
        args={"x": {"type": "integer", "description": "seed x desc"}},
    )
    seed_program = dspy.ReActV2(_RoundThreeSig, tools=[seed_tool], max_iters=2)
    bundle = _round_three_bundle(
        tool_schema_hashes={"foo": hash_tool_schema(seed_tool)},
        program_state=seed_program.dump_state(),
        tool_descriptions={"foo": "overlay desc"},
        tool_arg_descriptions={"foo": {"x": "overlay x desc"}},
    )
    program = fresh_program_for_bundle(
        bundle, [seed_tool], seed_signature=_RoundThreeSig
    )
    program_tool = program.tools["foo"]
    assert program_tool.desc == "overlay desc"
    assert program_tool.args["x"]["description"] == "overlay x desc"
    # Caller's tool still pristine.
    assert seed_tool.desc == "seed desc"
    assert seed_tool.args["x"]["description"] == "seed x desc"
