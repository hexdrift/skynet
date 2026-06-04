"""Tests for GEPA tool-NAME optimization with replay canonicalization.

The candidate may propose a clearer display name per tool that the agent sees
in its ReAct roster, while replay matching / reward dims / drift / persisted
state all stay keyed on the original (canonical) name. These tests pin that
contract: a renamed tool still hits its canonical recorded step, collisions
fall back to canonical, and the proposed names round-trip through the overlay.
"""

from __future__ import annotations

import json

import dspy

from core.models.artifacts import ReactOverlay
from core.service_gateway.optimization.tool_overlay import (
    _apply_tool_name_overrides,
)
from core.service_gateway.optimization.training_ground.gepa_adapter import (
    TOOL_MODULE_KEY,
    _candidate_tool_names,
    seed_candidate_from_program,
)
from core.service_gateway.optimization.training_ground.replay import (
    TraceConditionedMCPMock,
    canonical_argument_hash,
    resolve_proposed_names,
)
from core.service_gateway.optimization.training_ground.types import (
    EvaluationExample,
    ReplayStep,
)


def _make_example(
    *,
    allowed_tools: frozenset[str],
    replay_steps: tuple[ReplayStep, ...],
) -> EvaluationExample:
    """Build a minimal ``EvaluationExample`` for the replay mock."""
    return EvaluationExample(
        turn_id="t-1",
        user_message="",
        wizard_state_before={},
        wizard_state_after={},
        allowed_tools=allowed_tools,
        tool_schema_hashes={},
        replay_steps=replay_steps,
        chat_history=(),
    )


def _make_step(tool: str, arguments: dict) -> ReplayStep:
    """Build a done ``ReplayStep`` with a canonical argument hash."""
    return ReplayStep(
        tool_name=tool,
        arguments=arguments,
        argument_hash=canonical_argument_hash(arguments),
        status="done",
        result={"value": 42},
        reason=None,
        started_at_ms=None,
        ended_at_ms=None,
    )


def _canonicalizer(proposed: dict[str, str], allowed: frozenset[str]):
    """Build the proposed->canonical mapper the adapter wires into the mock."""
    resolved = resolve_proposed_names(proposed, allowed)
    canonical_by_proposed = {p: c for c, p in resolved.items()}
    return lambda n: canonical_by_proposed.get(n, n)


def test_renamed_call_hits_canonical_recorded_step() -> None:
    """A call under the proposed name canonicalizes back and hits the canonical step."""
    step = _make_step("alpha", {"k": 1})
    example = _make_example(allowed_tools=frozenset({"alpha"}), replay_steps=(step,))
    mock = TraceConditionedMCPMock(
        example,
        name_canonicalizer=_canonicalizer({"alpha": "search_records"}, example.allowed_tools),
    )

    # The agent invokes the proxy under the proposed display name.
    assert mock._on_candidate_call("search_records", {"k": 1}) == {"value": 42}
    rollout = mock.rollout_so_far()
    assert [e.outcome for e in rollout.events] == ["hit"]
    # The recorded event is keyed on the CANONICAL name so reward dims stay stable.
    assert rollout.events[0].candidate_tool == "alpha"
    assert not rollout.terminated_early


def test_identity_canonicalizer_unchanged_behavior() -> None:
    """With no rename, behavior is byte-identical to the pre-rename mock."""
    step = _make_step("alpha", {"k": 1})
    example = _make_example(allowed_tools=frozenset({"alpha"}), replay_steps=(step,))
    mock = TraceConditionedMCPMock(example)

    assert mock._on_candidate_call("alpha", {"k": 1}) == {"value": 42}
    assert mock.rollout_so_far().events[0].candidate_tool == "alpha"


def test_renamed_call_allowed_check_uses_canonical() -> None:
    """Calling the canonical name when a rename is active is NOT in the display roster.

    After a rename the agent only ever sees the proposed name; a call arriving
    under the canonical name canonicalizes to itself (it's not in the
    proposed->canonical map) and is checked against ``allowed_tools`` directly,
    which still contains the canonical — so it is allowed and hits.
    """
    step = _make_step("alpha", {"k": 1})
    example = _make_example(allowed_tools=frozenset({"alpha"}), replay_steps=(step,))
    mock = TraceConditionedMCPMock(
        example,
        name_canonicalizer=_canonicalizer({"alpha": "search_records"}, example.allowed_tools),
    )

    assert mock._on_candidate_call("alpha", {"k": 1}) == {"value": 42}
    assert mock.rollout_so_far().events[0].candidate_tool == "alpha"


def test_resolve_proposed_names_collision_keeps_canonical() -> None:
    """Two canonicals proposing the same name both keep their canonical name."""
    resolved = resolve_proposed_names(
        {"alpha": "dup", "beta": "dup"}, frozenset({"alpha", "beta"})
    )
    assert resolved == {"alpha": "alpha", "beta": "beta"}


def test_resolve_proposed_names_identity_when_none() -> None:
    """A ``None`` proposal map yields identity over the allowed tools."""
    resolved = resolve_proposed_names(None, frozenset({"alpha", "beta"}))
    assert resolved == {"alpha": "alpha", "beta": "beta"}


def test_candidate_tool_names_parses_proposed() -> None:
    """``_candidate_tool_names`` reads the proposed name, falling back to canonical."""
    blob = {
        "react": "do the thing",
        "tools": {
            "alpha": {"name": "search_records", "desc": "d", "args": {}},
            "beta": {"name": "  ", "desc": "d", "args": {}},
            "gamma": {"desc": "d", "args": {}},
        },
    }
    candidate = {TOOL_MODULE_KEY: json.dumps(blob)}
    names = _candidate_tool_names(candidate)
    assert names == {"alpha": "search_records", "beta": "beta", "gamma": "gamma"}


def test_seed_blob_carries_canonical_name() -> None:
    """The seed blob seeds ``name`` equal to the canonical key (identity proposal)."""

    def _echo(**kwargs: object) -> object:
        """Trivial tool body."""
        return kwargs

    class _Sig(dspy.Signature):
        """Tiny signature for the seed program."""

        user_message: str = dspy.InputField()
        assistant_message: str = dspy.OutputField()

    tool = dspy.Tool(_echo, name="alpha", desc="the alpha tool")
    program = dspy.ReActV2(_Sig, tools=[tool], max_iters=4)

    candidate = seed_candidate_from_program(program)
    blob = json.loads(candidate[TOOL_MODULE_KEY])
    assert blob["tools"]["alpha"]["name"] == "alpha"
    assert _candidate_tool_names(candidate)["alpha"] == "alpha"


def test_apply_tool_name_overrides_renames_in_place() -> None:
    """The serve rename helper renames cloned tools to their proposed names."""

    def _body(**kwargs: object) -> object:
        return kwargs

    tools = [
        dspy.Tool(_body, name="alpha", desc="a"),
        dspy.Tool(_body, name="beta", desc="b"),
    ]
    _apply_tool_name_overrides(tools, {"alpha": "search_records"})
    assert [t.name for t in tools] == ["search_records", "beta"]


def test_apply_tool_name_overrides_none_is_noop() -> None:
    """A ``None`` map leaves tool names untouched (pre-rename behavior)."""

    def _body(**kwargs: object) -> object:
        return kwargs

    tools = [dspy.Tool(_body, name="alpha", desc="a")]
    _apply_tool_name_overrides(tools, None)
    assert tools[0].name == "alpha"


def test_apply_tool_name_overrides_collision_keeps_canonical() -> None:
    """Two tools proposing the same display name both keep their canonical name."""

    def _body(**kwargs: object) -> object:
        return kwargs

    tools = [
        dspy.Tool(_body, name="alpha", desc="a"),
        dspy.Tool(_body, name="beta", desc="b"),
    ]
    _apply_tool_name_overrides(tools, {"alpha": "dup", "beta": "dup"})
    assert sorted(t.name for t in tools) == ["alpha", "beta"]


def test_react_overlay_roundtrips_tool_names() -> None:
    """``ReactOverlay`` serializes and reloads ``tool_names`` unchanged."""
    overlay = ReactOverlay(max_iters=8, tool_names={"alpha": "search_records"})
    reloaded = ReactOverlay.model_validate(overlay.model_dump())
    assert reloaded.tool_names == {"alpha": "search_records"}


def test_react_overlay_tool_names_defaults_none() -> None:
    """``tool_names`` defaults to ``None`` so existing artifacts are unaffected."""
    overlay = ReactOverlay(max_iters=8)
    assert overlay.tool_names is None
