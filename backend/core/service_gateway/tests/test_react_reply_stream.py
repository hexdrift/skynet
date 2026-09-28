"""Tests for the ReActV2 reply streamer.

``ReactReplyStream`` decodes the reply out of the ``submit`` tool-call argument
on the inner ``react`` predictor's ``tool_calls`` field, whether it arrives as
provider tool-call deltas or through DSPy's text protocol. These tests exercise
both extractors on a stand-in program.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import dspy
import litellm
import pytest

from core.service_gateway.agents import code as code_module
from core.service_gateway.agents.code import (
    NativeToolCallStreamListener,
    ReactReplyStream,
    _NativeSubmitArgExtractor,
    _SubmitArgExtractor,
)
from core.service_gateway.language_models import MeteredLM


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
    """A stand-in ReActV2 program: just the inner ``react`` predictor."""

    def __init__(self, react: dspy.Predict) -> None:
        """Store the inner predictor that drives the loop.

        Args:
            react: A real predictor so reasoning-listener binding succeeds.
        """
        self.react = react


def test_program_streams_through_two_listeners() -> None:
    """The streamer binds a reply listener and a reasoning listener to the loop predictor."""
    program = dspy.ReActV2(_Sig, tools=[_noop], max_iters=3)
    stream = ReactReplyStream(program, "reply")

    listeners = stream.listeners()
    assert len(listeners) == 2
    assert dspy.streamify(program, stream_listeners=listeners, async_streaming=True) is not None


def test_submit_program_decodes_partial_tool_call_json() -> None:
    """Partial ``submit`` JSON yields the growing reply argument."""
    base = dspy.ReActV2(_Sig, tools=[_noop], max_iters=3)
    stream = ReactReplyStream(_SubmitProgram(base.react), "reply")

    assert stream.reply_delta(_response("reply", "anything")) is None  # not the tool_calls field
    first = stream.reply_delta(_response("tool_calls", '{"tool_calls":[{"name":"submit","args":{"reply":"Hi'))
    second = stream.reply_delta(_response("tool_calls", ' there"}}]}', last=True))
    assert (first or "") + (second or "") == "Hi there"


def test_serial_submit_stream_suppresses_reply_that_races_a_tool() -> None:
    """A mixed tool turn never leaks its premature submit text to the user."""
    base = dspy.ReActV2(_Sig, tools=[_noop], max_iters=3)
    base.react._serial_tool_calls = True
    stream = ReactReplyStream(_SubmitProgram(base.react), "reply")

    first = stream.reply_delta(
        _response(
            "tool_calls",
            '{"tool_calls":[{"name":"count","args":{}},{"name":"submit","args":{"reply":"Checking',
        )
    )
    second = stream.reply_delta(_response("tool_calls", ' now."}}]}', last=True))
    final = stream.reply_delta(
        _response(
            "tool_calls",
            '{"tool_calls":[{"name":"submit","args":{"reply":"You have 3."}}]}',
            last=True,
        )
    )

    assert first is None
    assert second is None
    assert final == "You have 3."


def _lm_chunk(tool_calls: list | None = None, finish: str | None = None) -> SimpleNamespace:
    """Build a stand-in LiteLLM streaming chunk.

    Args:
        tool_calls: The ``delta.tool_calls`` list, or ``None`` for an empty delta.
        finish: The choice's ``finish_reason``, or ``None`` mid-stream.

    Returns:
        An object shaped like a LiteLLM ``ModelResponseStream`` chunk.
    """
    delta = SimpleNamespace(tool_calls=tool_calls, content=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish)])


def _tool_call(index: int, name: str | None = None, arguments: str | None = None) -> SimpleNamespace:
    """Build a stand-in streamed tool-call delta.

    Args:
        index: The tool call's stream index.
        name: The function name (present only in the call's first delta).
        arguments: The streaming ``arguments`` JSON fragment.

    Returns:
        An object shaped like one element of ``delta.tool_calls``.
    """
    return SimpleNamespace(index=index, function=SimpleNamespace(name=name, arguments=arguments))


def _drain_native(listener: NativeToolCallStreamListener, stream: ReactReplyStream, chunks: list) -> str:
    """Run raw chunks through the native listener + reply bridge, as the serve loop does.

    Args:
        listener: The native tool-call listener from ``stream.listeners()``.
        stream: The reply stream whose ``_NativeSubmitArgExtractor`` decodes the deltas.
        chunks: The sequence of stand-in LiteLLM chunks to replay.

    Returns:
        The reconstructed reply text.
    """
    out = ""
    for chunk in chunks:
        response = listener.receive(chunk)
        if response is None:
            continue
        delta = stream.reply_delta(response)
        if delta:
            out += delta
    return out


def test_submit_program_defaults_to_text_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    """With native calling inactive, ReActV2 keeps the text tool-call extractor."""
    monkeypatch.setattr(code_module, "native_tool_calling_active", lambda: False)
    base = dspy.ReActV2(_Sig, tools=[_noop], max_iters=3)
    stream = ReactReplyStream(_SubmitProgram(base.react), "reply")

    assert stream._native is False
    assert isinstance(stream._extractor, _SubmitArgExtractor)
    assert not isinstance(stream.listeners()[0], NativeToolCallStreamListener)


class _ScriptedGatewayLM(MeteredLM):
    """An on-prem gateway alias LiteLLM does not know, answering with a scripted ``submit``."""

    def __init__(self) -> None:
        """Build the LM under a model name absent from LiteLLM's catalogue."""
        super().__init__(model="openai/onprem-gateway-alias", cache=False)
        self.requests: list[dict[str, Any]] = []

    def forward(self, prompt=None, messages=None, **kwargs):
        """Record the request and submit a fixed reply as a native tool call.

        Args:
            prompt: Unused legacy prompt.
            messages: The rendered chat messages.
            **kwargs: Provider kwargs, including ``tools``.

        Returns:
            An OpenAI-shaped response carrying one ``submit`` tool call.
        """
        self.requests.append({"messages": messages, **kwargs})
        call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "submit", "arguments": json.dumps({"reply": "done"})},
        }
        message = {
            "role": "assistant",
            "content": "[[ ## next_thought ## ]]\nthinking\n\n[[ ## completed ## ]]",
            "tool_calls": [call],
        }
        return litellm.ModelResponse(
            model="onprem-gateway-alias",
            choices=[{"index": 0, "finish_reason": "tool_calls", "message": message}],
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )


async def test_code_agent_sends_native_tools_to_an_unknown_gateway_alias() -> None:
    """The code agent always rides the native tool channel, even for a model LiteLLM has never heard of."""
    lm = _ScriptedGatewayLM()
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    result = await code_module._run_agent(
        lm=lm,
        dataset_columns=["q", "a"],
        column_roles_json="{}",
        column_kinds_json="{}",
        sample_rows_json="[]",
        user_message="hi",
        chat_history_json="[]",
        prior_signature="",
        prior_metric="",
        prior_signature_validation="",
        prior_metric_validation="",
        initial_signature="",
        initial_metric="",
        reply_language="English",
        queue=queue,
    )

    assert "submit" in [tool["function"]["name"] for tool in lm.requests[0]["tools"]]
    assert result["assistant_message"] == "done"


def test_native_submit_program_decodes_provider_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Native calling: the submit call's provider ``arguments`` reconstruct the reply.

    A parallel non-submit tool call streams on index 0 and must be ignored; the
    submit call on index 1 carries the user-visible reply.
    """
    monkeypatch.setattr(code_module, "native_tool_calling_active", lambda: True)
    base = dspy.ReActV2(_Sig, tools=[_noop], max_iters=3)
    stream = ReactReplyStream(_SubmitProgram(base.react), "reply")

    assert stream._native is True
    assert isinstance(stream._extractor, _NativeSubmitArgExtractor)
    listener = stream.listeners()[0]
    assert isinstance(listener, NativeToolCallStreamListener)

    chunks = [
        _lm_chunk([_tool_call(0, name="edit_signature", arguments="")]),
        _lm_chunk([_tool_call(0, arguments='{"code":"x"}')]),
        _lm_chunk([_tool_call(1, name="submit", arguments="")]),
        _lm_chunk([_tool_call(1, arguments='{"reply":"Hi')]),
        _lm_chunk([_tool_call(1, arguments=' there"}')]),
        _lm_chunk(finish="tool_calls"),
    ]
    assert _drain_native(listener, stream, chunks) == "Hi there"


def test_native_listener_buffers_args_arriving_before_submit_name() -> None:
    """Args streamed before the ``submit`` name is seen are buffered, then flushed."""
    listener = NativeToolCallStreamListener(predict=None, allow_reuse=True)
    extractor = _NativeSubmitArgExtractor("reply")

    chunks = [
        _lm_chunk([_tool_call(0, arguments='{"reply":"par')]),
        _lm_chunk([_tool_call(0, name="submit", arguments="tial")]),
        _lm_chunk([_tool_call(0, arguments=' done"}')]),
        _lm_chunk(finish="stop"),
    ]
    out = ""
    for chunk in chunks:
        response = listener.receive(chunk)
        if response is None:
            continue
        delta = extractor.feed(response.chunk)
        if response.is_last_chunk:
            extractor.reset()
        if delta:
            out += delta
    assert out == "partial done"


def test_native_listener_resets_between_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reused listener + extractor decode a second turn cleanly after finish_reason."""
    monkeypatch.setattr(code_module, "native_tool_calling_active", lambda: True)
    base = dspy.ReActV2(_Sig, tools=[_noop], max_iters=3)
    stream = ReactReplyStream(_SubmitProgram(base.react), "reply")
    listener = stream.listeners()[0]

    first = _drain_native(
        listener,
        stream,
        [
            _lm_chunk([_tool_call(0, name="submit", arguments='{"reply":"one"}')]),
            _lm_chunk(finish="stop"),
        ],
    )
    second = _drain_native(
        listener,
        stream,
        [
            _lm_chunk([_tool_call(0, name="submit", arguments='{"reply":"two"}')]),
            _lm_chunk(finish="stop"),
        ],
    )
    assert first == "one"
    assert second == "two"
