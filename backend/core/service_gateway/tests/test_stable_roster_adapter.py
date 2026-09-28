"""Tests for :mod:`...stable_roster_adapter` and its wiring into the retrying loop.

Pins what the adapter promises: the first loop call is byte-identical to stock
DSPy, every later call extends the previous one up to the trailing reminder (so
a provider prefix cache covers the tool roster), the roster is rendered exactly
once, and stock stream listeners still accept the adapter. Also pins that the
retrying predictor only substitutes it when no adapter is configured.
"""

from __future__ import annotations

import dspy
import pytest
from dspy.adapters.types.tool import ToolCallResults, ToolCalls

from ..optimization.retrying_react import RetryingPredict, RetryingReActV2
from ..stable_roster_adapter import StableRosterChatAdapter

ROSTER_MARKER = "[[ ## tools ## ]]"


def _lookup(name: str) -> str:
    """Look a thing up.

    Args:
        name: The thing to look up.

    Returns:
        A fixed value.
    """
    return "value"


def _program() -> dspy.Module:
    """Build a one-tool ReActV2 program that needs no LM to format prompts.

    Returns:
        The constructed program.
    """
    return RetryingReActV2(dspy.Signature("question: str -> reply: str", "Be helpful."), tools=[_lookup])


def _step(index: int, *, first: bool) -> dict:
    """Build the history event ReActV2 records for one loop step.

    Args:
        index: Step number, used to make each step's content distinct.
        first: Whether this is the step that carries the task inputs.

    Returns:
        The history message for the step.
    """
    calls = ToolCalls(tool_calls=[ToolCalls.ToolCall(name="_lookup", args={"name": f"x{index}"}, id=f"call_{index}")])
    results = ToolCallResults.from_tool_calls_and_values(calls, [f"value{index}"], [False])
    event = {"next_thought": f"thought {index}", "tool_calls": calls.model_copy(update={"tool_call_results": results})}
    return {"question": "hi", **event} if first else event


def _messages(adapter: dspy.ChatAdapter, steps: int) -> list[dict]:
    """Format the prompt of the loop call that follows ``steps`` completed steps.

    Args:
        adapter: The adapter under test.
        steps: How many loop steps already sit in the history.

    Returns:
        The chat messages the adapter produces.
    """
    program = _program()
    inputs = {
        "history": dspy.History(messages=[_step(i, first=i == 0) for i in range(steps)]),
        "tools": list(program.tools.values()),
    }
    if not steps:
        inputs["question"] = "hi"
    return adapter.format(program.react.signature, [], inputs)


def test_first_call_matches_stock_layout() -> None:
    """With no history to reshape, the prompt is exactly what stock DSPy sends."""
    assert _messages(StableRosterChatAdapter(), 0) == _messages(dspy.ChatAdapter(), 0)


def test_later_calls_extend_the_previous_call() -> None:
    """Each call repeats the previous one verbatim up to the trailing reminder."""
    adapter = StableRosterChatAdapter()
    second, third = _messages(adapter, 1), _messages(adapter, 2)

    assert third[: len(second) - 1] == second[:-1]
    assert second[-1] == third[-1]


def test_roster_is_rendered_once_at_the_front() -> None:
    """The roster sits in the first user message and nowhere else."""
    messages = _messages(StableRosterChatAdapter(), 2)
    # The system message names the field in its format description, so only turns count.
    holders = [i for i, m in enumerate(messages) if m["role"] != "system" and ROSTER_MARKER in m["content"]]

    assert holders == [1]
    assert messages[1]["role"] == "user"


def test_stock_layout_moves_the_roster() -> None:
    """Stock DSPy re-renders the roster after the history, which is what breaks caching."""
    messages = _messages(dspy.ChatAdapter(), 2)

    assert ROSTER_MARKER not in messages[1]["content"]
    assert ROSTER_MARKER in messages[-1]["content"]


def test_stock_stream_listeners_accept_the_adapter() -> None:
    """DSPy's listener resolves delimiters by adapter class name, so the name must be known."""
    listener = dspy.streaming.StreamListener(signature_field_name="reply")

    assert type(StableRosterChatAdapter()).__name__ in listener.adapter_identifiers


def test_retrying_predict_substitutes_only_the_default_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unconfigured adapter becomes the stable one; a configured adapter is left alone."""
    program = _program()
    seen: list[object] = []

    def fake_super_forward(self: dspy.Predict, **kwargs: object) -> dspy.Prediction:
        """Record the adapter active during the inner predict call."""
        seen.append(dspy.settings.adapter)
        return dspy.Prediction(reply="ok")

    monkeypatch.setattr(dspy.Predict, "forward", fake_super_forward)
    assert isinstance(program.react, RetryingPredict)
    configured = dspy.ChatAdapter(use_native_function_calling=True)

    with dspy.context(adapter=None):
        program.react.forward(question="q")
    with dspy.context(adapter=configured):
        program.react.forward(question="q")

    assert isinstance(seen[0], StableRosterChatAdapter)
    assert seen[1] is configured
