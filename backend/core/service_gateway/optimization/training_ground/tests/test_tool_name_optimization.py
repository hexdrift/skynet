"""Tests for GEPA tool-NAME optimization.

The candidate may propose a clearer display name per tool that the agent sees
in its ReAct roster, while persisted state / overlay application stay keyed on
the original (canonical) name. These tests pin that contract: the proposed
names parse out of the candidate blob, round-trip through the seed, apply to a
live tool roster, collisions fall back to canonical, and the overlay model
serializes the rename map.
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
from core.service_gateway.react_compat import REACT_CLASS


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
    program = REACT_CLASS(_Sig, tools=[tool], max_iters=4)

    candidate = seed_candidate_from_program(program)
    blob = json.loads(candidate[TOOL_MODULE_KEY])
    assert blob["tools"]["alpha"]["name"] == "alpha"
    assert _candidate_tool_names(candidate)["alpha"] == "alpha"


def test_apply_tool_name_overrides_renames_in_place() -> None:
    """The serve rename helper renames cloned tools to their proposed names."""

    def _body(**kwargs: object) -> object:
        """Trivial tool body."""
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
        """Trivial tool body."""
        return kwargs

    tools = [dspy.Tool(_body, name="alpha", desc="a")]
    _apply_tool_name_overrides(tools, None)
    assert tools[0].name == "alpha"


def test_apply_tool_name_overrides_collision_keeps_canonical() -> None:
    """Two tools proposing the same display name both keep their canonical name."""

    def _body(**kwargs: object) -> object:
        """Trivial tool body."""
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
