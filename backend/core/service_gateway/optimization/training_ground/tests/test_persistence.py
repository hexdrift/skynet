"""Unit tests for the persistence layer's pure transforms + statistics.

Covers the §7 stratified splitter, the §11 paired-bootstrap CI, the §8
atomic bundle writer + ``program.save`` state extractor, and the SQL
row → ``EvaluationExample`` transform that ``load_trajectories`` builds on.
The raw window query itself is Postgres-only (``jsonb_agg`` / ``::jsonb``)
and stays integration-tested; this module pins the logic around it.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import dspy
import pytest

from core.service_gateway.optimization.training_ground import persistence
from core.service_gateway.optimization.training_ground.types import (
    Bundle,
    EvaluationExample,
    PairedBootstrapResult,
)


class _Sig(dspy.Signature):
    """Tiny signature for the program-state round-trip test."""

    user_message: str = dspy.InputField()
    assistant_message: str = dspy.OutputField()


def _example(state: dict[str, Any], *, turn_id: str = "t-1") -> EvaluationExample:
    """Build an EvaluationExample whose only meaningful field is the wizard state."""
    return EvaluationExample(
        turn_id=turn_id,
        user_message="",
        wizard_state_before=state,
        wizard_state_after={},
        allowed_tools=frozenset(),
        tool_schema_hashes={},
        replay_steps=(),
        chat_history=(),
    )


def _bundle() -> Bundle:
    """Build a minimal valid Bundle for the writer round-trip test."""
    return Bundle(
        model_id="generalist",
        version="2026-05-28",
        dspy_version="3.3.0b1",
        gepa_version="0.1.1",
        gate_logic_version="abc123",
        tool_schema_hashes={"foo": "h"},
        max_iters=8,
        program_state={"react": {}},
        scalar_score=0.7,
        objective_scores={},
        window_days=14,
        trajectories_trained_on=400,
        trajectories_held_out=300,
        paired_bootstrap=PairedBootstrapResult(
            resamples=10_000, mean_delta=0.05, ci95_lower=0.04, ci95_upper=0.06
        ),
    )


def test_parse_window_days_and_weeks() -> None:
    """``Nd`` and ``Nw`` resolve to the right timedelta; weeks are 7×days."""
    assert persistence.parse_window("14d") == timedelta(days=14)
    assert persistence.parse_window("2w") == timedelta(days=14)
    assert persistence.parse_window("30d") == timedelta(days=30)


def test_parse_window_rejects_bad_input() -> None:
    """Empty, too-short, bad-suffix, and non-positive counts all raise."""
    for bad in ("", "d", "5y", "0d", "-3d", "xd"):
        with pytest.raises(ValueError):
            persistence.parse_window(bad)


def test_phase_of_buckets() -> None:
    """Each wizard snapshot maps to its phase label in ladder order."""
    assert persistence.phase_of(_example({})) == "intake"
    assert persistence.phase_of(_example({"job_id": "j"})) == "post_submit"
    assert persistence.phase_of(_example({"submitted": True})) == "post_submit"
    assert persistence.phase_of(_example({"dataset_ready": True})) == "dataset_ready"
    assert (
        persistence.phase_of(
            _example({"dataset_ready": True, "columns_configured": True})
        )
        == "configured"
    )
    assert (
        persistence.phase_of(
            _example(
                {
                    "dataset_ready": True,
                    "signature_code": "s",
                    "metric_code": "m",
                    "model_configured": True,
                }
            )
        )
        == "ready_to_submit"
    )


def test_split_stratified_empty() -> None:
    """An empty input yields two empty splits, not a crash."""
    assert persistence.split_stratified([]) == ([], [])


def test_split_stratified_is_deterministic_per_seed() -> None:
    """The same seed must reproduce the exact train/holdout partition + order."""
    examples = [
        _example({"dataset_ready": True}, turn_id=f"ds-{i}") for i in range(10)
    ] + [_example({}, turn_id=f"in-{i}") for i in range(10)]
    train_a, hold_a = persistence.split_stratified(examples, holdout_frac=0.2, seed=7)
    train_b, hold_b = persistence.split_stratified(examples, holdout_frac=0.2, seed=7)
    assert [e.turn_id for e in train_a] == [e.turn_id for e in train_b]
    assert [e.turn_id for e in hold_a] == [e.turn_id for e in hold_b]


def test_split_stratified_holdout_fraction_per_phase() -> None:
    """A single 10-example phase at 20% holdout yields 2 held out / 8 trained."""
    examples = [_example({"dataset_ready": True}, turn_id=f"t-{i}") for i in range(10)]
    train, holdout = persistence.split_stratified(examples, holdout_frac=0.2, seed=0)
    assert len(holdout) == 2
    assert len(train) == 8


def test_split_stratified_keeps_singleton_bucket_in_train() -> None:
    """A phase with one example can't hold any out — it stays entirely in train."""
    examples = [_example({"dataset_ready": True}, turn_id="solo")]
    train, holdout = persistence.split_stratified(examples, holdout_frac=0.5)
    assert [e.turn_id for e in train] == ["solo"]
    assert holdout == []


def test_split_stratified_default_single_bucket_pools_all_phases() -> None:
    """Without a stratifier every example shares one bucket, so a lone
    off-phase example is eligible for holdout instead of pinned to train."""
    examples = [
        _example({"dataset_ready": True}, turn_id=f"ds-{i}") for i in range(9)
    ] + [_example({}, turn_id="lone-intake")]
    train, holdout = persistence.split_stratified(examples, holdout_frac=0.2, seed=0)
    assert len(holdout) == 2
    assert len(train) == 8
    ids = {e.turn_id for e in train} | {e.turn_id for e in holdout}
    assert ids == {f"ds-{i}" for i in range(9)} | {"lone-intake"}


def test_split_stratified_with_phase_of_pins_singleton_phase_to_train() -> None:
    """Passing ``phase_of`` recovers per-phase buckets: the lone intake
    example forms a singleton bucket and stays entirely in train."""
    examples = [
        _example({"dataset_ready": True}, turn_id=f"ds-{i}") for i in range(9)
    ] + [_example({}, turn_id="lone-intake")]
    train, holdout = persistence.split_stratified(
        examples, holdout_frac=0.2, seed=0, stratifier=persistence.phase_of
    )
    assert "lone-intake" in {e.turn_id for e in train}
    assert "lone-intake" not in {e.turn_id for e in holdout}
    assert len(holdout) == 2


def test_paired_bootstrap_constant_delta_collapses_ci() -> None:
    """Identical per-trajectory deltas make every resample mean equal — CI collapses."""
    res = persistence.paired_bootstrap_ci(
        [0.2, 0.2, 0.2, 0.2], [0.5, 0.5, 0.5, 0.5], resamples=1000, seed=1
    )
    assert res.mean_delta == pytest.approx(0.3)
    assert res.ci95_lower == pytest.approx(0.3)
    assert res.ci95_upper == pytest.approx(0.3)
    assert res.resamples == 1000


def test_paired_bootstrap_ci_brackets_mean_delta() -> None:
    """For varied positive deltas the CI must bracket the observed mean delta."""
    base = [0.1, 0.2, 0.3, 0.4, 0.5]
    cand = [0.5, 0.5, 0.5, 0.7, 0.9]
    res = persistence.paired_bootstrap_ci(base, cand, resamples=2000, seed=3)
    assert res.mean_delta == pytest.approx(0.32)
    assert res.ci95_lower <= res.mean_delta <= res.ci95_upper
    assert res.ci95_lower > 0.0


def test_paired_bootstrap_validates_inputs() -> None:
    """Mismatched lengths, empty input, and out-of-range confidence all raise."""
    with pytest.raises(ValueError):
        persistence.paired_bootstrap_ci([0.1], [0.1, 0.2])
    with pytest.raises(ValueError):
        persistence.paired_bootstrap_ci([], [])
    with pytest.raises(ValueError):
        persistence.paired_bootstrap_ci([0.1], [0.2], confidence=1.5)


def test_write_bundle_atomic_round_trip(tmp_path) -> None:
    """The writer creates parent dirs, round-trips, and leaves no temp files."""
    out = tmp_path / "minimax-2.7" / "current.json"
    persistence.write_bundle(bundle=_bundle(), out_path=out)
    assert out.exists()
    restored = Bundle.model_validate_json(out.read_text())
    assert restored.model_id == "generalist"
    assert [p.name for p in out.parent.iterdir()] == ["current.json"]


def test_extract_program_state_round_trips_through_load_state() -> None:
    """The saved state must be a dict a freshly-built ReActV2 can ``load_state``."""
    tool = dspy.Tool(
        func=lambda x: x,
        name="foo",
        desc="d",
        args={"x": {"type": "integer"}},
    )
    program = dspy.ReActV2(_Sig, tools=[tool], max_iters=2)
    state = persistence.extract_program_state(program)
    assert isinstance(state, dict)
    assert state
    assert "react" in state
    fresh = dspy.ReActV2(_Sig, tools=[tool], max_iters=2)
    fresh.load_state(state)


def test_row_to_example_coerces_types() -> None:
    """A populated SQL row maps to a fully-typed EvaluationExample."""
    row = SimpleNamespace(
        id=42,
        tool_calls=[
            {
                "tool": "alpha",
                "status": "done",
                "payload": {"arguments": {"k": 1}, "result": {"ok": 1}},
            }
        ],
        allowed_tools=["alpha", "beta"],
        tool_schema_hashes={"alpha": "h1"},
        chat_history=[{"role": "user", "content": "hi"}],
        user_message="  do it  ",
        wizard_state_before={"dataset_ready": True},
        wizard_state_after={"dataset_ready": True, "submitted": True},
    )
    example = persistence._row_to_example(row)
    assert example.turn_id == "42"
    assert example.allowed_tools == frozenset({"alpha", "beta"})
    assert example.tool_schema_hashes == {"alpha": "h1"}
    assert example.user_message == "do it"
    assert example.wizard_state_before == {"dataset_ready": True}
    assert len(example.replay_steps) == 1
    assert example.replay_steps[0].tool_name == "alpha"


def test_row_to_example_allowed_tools_dict_uses_keys() -> None:
    """An ``allowed_tools`` JSONB object is reduced to its keys; nulls default cleanly."""
    row = SimpleNamespace(
        id=1,
        tool_calls=None,
        allowed_tools={"alpha": "x", "beta": "y"},
        tool_schema_hashes={},
        chat_history=None,
        user_message=None,
        wizard_state_before=None,
        wizard_state_after=None,
    )
    example = persistence._row_to_example(row)
    assert example.allowed_tools == frozenset({"alpha", "beta"})
    assert example.user_message == ""
    assert example.replay_steps == ()
    assert example.wizard_state_before == {}
