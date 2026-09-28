"""Conversation-grade ReActV2 loop: cache-stable prompts and stored native history.

Stock ReActV2 under DSPy's text ``ChatAdapter`` rewrites the start of the prompt
on every loop call: the tool roster and the output-format reminder sit in the
first user message on call one and move behind the history afterwards. Provider
prompt caches match on the prefix, so nearly every input token is billed fresh.

This module keeps the message list append-only instead. Tools travel on the
provider's native ``tools=`` channel, the format reminder never sits inside a
message that later calls replay, and a whole conversation is carried as the
loop's own ``dspy.History`` so turn N+1 extends the exact prompt turn N ended on.
"""

from __future__ import annotations

import textwrap
from collections.abc import Iterable
from typing import Any

import dspy
from dspy.adapters.chat_adapter import ChatAdapter
from dspy.adapters.types.tool import ToolCallResults, ToolCalls
from dspy.adapters.utils import get_field_description_string

from ..optimization.retrying_react import PARSE_RETRY_ATTEMPTS, RetryingReActV2

SUBMIT_TOOL = "submit"
_DELIVERED = "Delivered to the user."


class AppendOnlyChatAdapter(ChatAdapter):
    """A native-tool-calling ``ChatAdapter`` whose prompts only ever grow at the end."""

    def __init__(self) -> None:
        """Enable native function calling and keep one prompt shape for every call.

        The JSON fallback is off because it re-renders the whole prompt in a
        different shape, which both misses the cache and hides the failure from
        the resampling predictor that already handles it.
        """
        super().__init__(use_native_function_calling=True, use_json_adapter_fallback=False)

    def user_message_output_requirements(self, signature: type[dspy.Signature]) -> str | None:
        """Keep the format reminder out of every replayed user message.

        Args:
            signature: The signature being rendered.

        Returns:
            Always ``None``; :meth:`format` appends the reminder on its own.
        """
        return None

    def format_system_message(self, signature: type[dspy.Signature]) -> str:
        """Render the system prompt, dropping the text protocol when nothing uses it.

        Once tool calls and reasoning ride native channels no output field is
        left, and DSPy's field-structure boilerplate would only tell the model
        to end with a text marker instead of calling a tool.

        Args:
            signature: The signature after native fields were removed.

        Returns:
            The system message text.
        """
        if signature.output_fields:
            return super().format_system_message(signature)
        visible = {
            name: field for name, field in signature.input_fields.items() if field.annotation is not dspy.History
        }
        return (
            f"{textwrap.dedent(signature.instructions).strip()}\n\n"
            "Each user turn carries these fields, each under its own `[[ ## name ## ]]` header:\n"
            f"{get_field_description_string(visible)}"
        )

    def format_assistant_message_content(
        self, signature: type[dspy.Signature], outputs: dict[str, Any], missing_field_message: str | None = None
    ) -> str:
        """Render replayed assistant text, or nothing when no output field is textual.

        Args:
            signature: The signature after native fields were removed.
            outputs: The recorded output values.
            missing_field_message: Placeholder for absent fields.

        Returns:
            The assistant text. Empty when every output rides a native channel,
            so a user turn with no recorded reply adds no stray assistant message.
        """
        if not signature.output_fields:
            return ""
        return super().format_assistant_message_content(signature, outputs, missing_field_message)

    def format(
        self, signature: type[dspy.Signature], demos: list[dict[str, Any]], inputs: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Render the messages with the format reminder as a trailing message of its own.

        Args:
            signature: The signature after native fields were removed.
            demos: Few-shot examples.
            inputs: The call's input values.

        Returns:
            The chat messages. Everything before the optional trailing reminder
            is a prefix of what the next loop call renders.
        """
        messages = super().format(signature, demos, inputs)
        if signature.output_fields:
            messages.append({"role": "user", "content": super().user_message_output_requirements(signature)})
        return messages


class ConversationReAct(RetryingReActV2):
    """``RetryingReActV2`` that always runs under :class:`AppendOnlyChatAdapter`.

    Pass the ``history`` of the previous turn's prediction back in as the
    ``history`` input to continue a conversation natively.
    """

    def __init__(
        self,
        signature,
        tools,
        max_iters: int = 20,
        *,
        parse_retries: int = PARSE_RETRY_ATTEMPTS,
        serial_tool_calls: bool = True,
    ):
        """Build the loop.

        Args:
            signature: Task signature, as for the base ReAct program.
            tools: Tool roster, as for the base ReAct program.
            max_iters: Loop budget per user turn.
            parse_retries: Extra resample attempts per inner-predict call.
            serial_tool_calls: Ask the provider for one tool call per step.
        """
        super().__init__(
            signature, tools, max_iters=max_iters, parse_retries=parse_retries, serial_tool_calls=serial_tool_calls
        )
        self._adapter = AppendOnlyChatAdapter()

    def forward(self, **input_args):
        """Run one user turn under the append-only adapter.

        Args:
            **input_args: The signature's inputs, plus an optional ``history``.

        Returns:
            The prediction; its ``history`` holds the whole conversation so far.
        """
        with dspy.context(adapter=self._adapter):
            return super().forward(**input_args)


def history_from_turns(
    turns: Iterable[tuple[str, str] | tuple[str, str, list[dict[str, Any]]]],
    *,
    input_field: str,
    output_field: str,
) -> dspy.History:
    """Rebuild native loop history from plain ``(role, text)`` conversation turns.

    An earlier assistant reply is replayed the way the loop itself records one:
    as a ``submit`` call. The inner signature has no reply field, so a plain
    assistant text would be dropped from the prompt. An assistant turn may carry
    a third element, the trace of the tool calls it made, each a
    ``{tool, status, result}`` dict (``args`` optional); those are replayed
    one call per loop step ahead of the ``submit``, as the loop records them.

    Args:
        turns: Earlier turns, oldest first, with roles ``"user"`` and ``"assistant"``.
        input_field: Signature input that carries the user's text.
        output_field: Signature output that carries the assistant's reply.

    Returns:
        History to pass as the ``history`` input of the next turn.
    """
    messages: list[dict[str, Any]] = []
    pending: dict[str, Any] = {}
    for index, turn in enumerate(turns):
        role, text = turn[0], turn[1]
        if role == "user":
            if pending:
                messages.append(pending)
            pending = {input_field: text}
            continue
        trace = turn[2] if len(turn) > 2 else []
        for step, call in enumerate(trace):
            messages.append({**pending, "tool_calls": _replayed_call(
                f"turn_{index}_{step}", call["tool"], call.get("args") or {},
                call.get("result") or "", call.get("status") == "error",
            )})  # fmt: skip
            pending = {}
        submit = _replayed_call(f"turn_{index}", SUBMIT_TOOL, {output_field: text}, _DELIVERED, False)
        messages.append({**pending, "tool_calls": submit})
        pending = {}
    if pending:
        messages.append(pending)
    return dspy.History(messages=messages)


def _replayed_call(call_id: str, name: str, args: dict[str, Any], result: str, is_error: bool) -> ToolCalls:
    """Build one settled tool call for a replayed history event.

    Args:
        call_id: Tool call id; results are matched to calls by it.
        name: Tool name.
        args: Arguments the call was made with.
        result: The result text the tool returned.
        is_error: Whether the call failed.

    Returns:
        The call with its result attached.
    """
    calls = ToolCalls(tool_calls=[ToolCalls.ToolCall(id=call_id, name=name, args=args)])
    results = ToolCallResults.from_tool_calls_and_values(calls, [result], [is_error])
    return calls.model_copy(update={"tool_call_results": results})


def dump_history(history: dspy.History) -> list[dict[str, Any]]:
    """Serialize loop history to JSON-safe data for storage.

    Args:
        history: The ``history`` of a finished turn's prediction.

    Returns:
        One plain dict per loop event; :func:`load_history` reverses it.
    """
    events = []
    for message in history.messages:
        event = {}
        for name, value in message.items():
            if isinstance(value, dspy.Reasoning):
                value = value.content
            elif isinstance(value, ToolCalls):
                # ToolCalls' own serializer drops the call ids that tie results to calls.
                calls = [{"id": call.id, "name": call.name, "args": call.args} for call in value.tool_calls]
                value = {**value.model_dump(mode="json"), "tool_calls": calls}
            event[name] = value
        events.append(event)
    return events


def load_history(events: list[dict[str, Any]]) -> dspy.History:
    """Rebuild loop history from :func:`dump_history` output.

    Args:
        events: The stored events.

    Returns:
        History that renders to the same messages as the original.
    """
    return dspy.History(messages=[dict(event) for event in events])


__all__ = [
    "AppendOnlyChatAdapter",
    "ConversationReAct",
    "dump_history",
    "history_from_turns",
    "load_history",
]
