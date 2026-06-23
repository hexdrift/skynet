"""Tests for the version-agnostic ReAct reply streamer.

``ReactReplyStream`` bridges the two ways a ReAct program surfaces its reply:
ReActV2 (DSPy 3.3+) carries it as a ``submit`` tool-call argument on the inner
``react`` predictor's ``tool_calls`` field, while classic ReAct (DSPy 3.2.x)
streams it straight off a separate ``extract`` predictor. These tests exercise
both branches regardless of which DSPy line is installed, by toggling the
presence of an ``extract`` attribute on a stand-in program.
"""

from __future__ import annotations

import dspy

from core.service_gateway.agents.code import ReactReplyStream
from core.service_gateway.react_compat import REACT_CLASS, react_uses_submit


class _Sig(dspy.Signature):
    """Reply to the user."""

    user_message: str = dspy.InputField()
    reply: str = dspy.OutputField()


def _noop(x: str) -> str:
    """Echo the argument.

    Args:
        x: Arbitrary string.

    Returns:
        The argument unchanged.
    """
    return x


def _response(field: str, chunk: str, *, last: bool = False) -> dspy.streaming.StreamResponse:
    """Build a ``StreamResponse`` for a given field and chunk.

    Args:
        field: The ``signature_field_name`` the chunk belongs to.
        chunk: The streamed text fragment.
        last: Whether this is the field's terminal chunk.

    Returns:
        A populated ``dspy.streaming.StreamResponse``.
    """
    return dspy.streaming.StreamResponse(
        predict_name="react",
        signature_field_name=field,
        chunk=chunk,
        is_last_chunk=last,
    )


class _SubmitProgram:
    """A stand-in ReActV2 program: an inner ``react`` predictor and no ``extract``."""

    def __init__(self, react: dspy.Predict) -> None:
        """Store the inner predictor that drives the loop.

        Args:
            react: A real predictor so reasoning-listener binding succeeds.
        """
        self.react = react


def test_native_program_matches_capability_probe() -> None:
    """The streamer's submit/extract choice tracks ``react_uses_submit``."""
    program = REACT_CLASS(_Sig, tools=[_noop], max_iters=3)
    stream = ReactReplyStream(program, "reply")

    assert stream._uses_submit is react_uses_submit(program)
    listeners = stream.listeners()
    assert len(listeners) == 2
    assert dspy.streamify(program, stream_listeners=listeners, async_streaming=True) is not None


def test_extract_program_streams_reply_field_directly() -> None:
    """Classic ReAct: the reply field's chunks pass through verbatim."""
    program = REACT_CLASS(_Sig, tools=[_noop], max_iters=3)
    if react_uses_submit(program):
        program.extract = program.react  # force the classic branch on a 3.3 install

    stream = ReactReplyStream(program, "reply")

    assert stream._uses_submit is False
    assert stream.reply_delta(_response("reply", "Hel")) == "Hel"
    assert stream.reply_delta(_response("reply", "lo", last=True)) == "lo"
    assert stream.reply_delta(_response("next_thought", "ignored")) is None


def test_submit_program_decodes_partial_tool_call_json() -> None:
    """ReActV2: partial ``submit`` JSON yields the growing reply argument."""
    base = REACT_CLASS(_Sig, tools=[_noop], max_iters=3)
    stream = ReactReplyStream(_SubmitProgram(base.react), "reply")

    assert stream._uses_submit is True
    assert stream.reply_delta(_response("reply", "anything")) is None  # not the tool_calls field
    first = stream.reply_delta(_response("tool_calls", '{"tool_calls":[{"name":"submit","args":{"reply":"Hi'))
    second = stream.reply_delta(_response("tool_calls", ' there"}}]}', last=True))
    assert (first or "") + (second or "") == "Hi there"
