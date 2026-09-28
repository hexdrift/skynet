"""A text-protocol chat adapter that keeps the ReAct tool roster where a prompt cache can reuse it.

Stock ``dspy.ChatAdapter`` renders the ``tools`` roster inside the *current*
user message. On a loop's first call that is the first user message; on every
later call the loop's steps are replayed as history and the roster is rendered
again after them. The prompt therefore diverges from the previous call right
after the task inputs, so a provider prefix cache never covers the roster or
anything behind it. With ten tools roughly 70% of every loop prompt is billed
as fresh input, and the share grows with the roster.

This adapter renders the roster once, in the conversation's first user message,
and leaves only the short output-format reminder trailing. Each loop call then
extends the previous one, so the roster and all earlier steps are cache hits.
The roster text, the instructions and the reply protocol are unchanged; only the
roster's position moves.
"""

from __future__ import annotations

from typing import Any

import dspy
from dspy.signatures.signature import Signature


class StableRosterChatAdapter(dspy.ChatAdapter):
    """``dspy.ChatAdapter`` with the tool roster pinned to the first user message."""

    def format_conversation_history(
        self,
        signature: type[Signature],
        history_field_name: str,
        inputs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Format the history with the tool roster moved into its first message.

        Native function calling strips the roster before formatting, so this is
        a no-op there; it only reshapes the text tool protocol.

        Args:
            signature: The signature being formatted, without its history field.
            history_field_name: Name of the history input.
            inputs: The call inputs; the roster is removed from them when moved.

        Returns:
            The history as chat messages.
        """
        tools_field = self._get_tool_call_input_field_name(signature)
        history = inputs.get(history_field_name)
        turns = list(getattr(history, "messages", None) or [])
        if tools_field and tools_field in inputs and turns and tools_field not in turns[0]:
            turns[0] = {**turns[0], tools_field: inputs.pop(tools_field)}
            inputs[history_field_name] = dspy.History(messages=turns)
        return super().format_conversation_history(signature, history_field_name, inputs)


# DSPy's ``StreamListener`` picks its field delimiters by the active adapter's
# class *name* and rejects any name it does not know, so a subclass that keeps
# the chat wire format has to keep the chat adapter's name to stay streamable.
StableRosterChatAdapter.__name__ = "ChatAdapter"

__all__ = ["StableRosterChatAdapter"]
