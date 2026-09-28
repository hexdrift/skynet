"""Native tool-calling configuration for DSPy's ``ReActV2`` program.

``ReActV2`` runs a single inner ``react`` predictor whose final answer is an
argument of an internal ``submit`` tool call. This module owns the process-wide
switch that routes those tool calls through the provider's native function
calling API instead of DSPy's text protocol, plus the probe the reply streamer
uses to tell which of the two is in force.
"""

from __future__ import annotations

import contextlib
import logging

import dspy
from dspy.adapters.chat_adapter import ChatAdapter

from ..config import settings

logger = logging.getLogger(__name__)


def native_react_adapter() -> ChatAdapter:
    """Build the ChatAdapter that routes ReActV2 tools through native function calling.

    ``use_native_function_calling`` diverts a signature's ``list[dspy.Tool]``
    input and ``dspy.ToolCalls`` output onto the provider's ``tools=`` API, so
    turns come back as structured tool calls instead of DSPy's text protocol.
    It stays a no-op for signatures without a ToolCalls field, so only ReAct's
    inner predictor is affected. ``parallel_tool_calls`` is deliberately left
    unset: the adapter would otherwise inject it on every call, including
    ReActV2's forced-submit turn whose ``tool_choice`` pins the ``submit``
    function — a combination providers reject. Provider-default parallelism
    still applies on the normal (auto-``tool_choice``) turns.

    Returns:
        A ``ChatAdapter`` with native function calling enabled.
    """
    return ChatAdapter(use_native_function_calling=True)


def configure_native_tool_calling() -> None:
    """Install the native-function-calling adapter process-wide when enabled.

    Reads ``settings.react_native_tool_calling``; when on, sets a global
    ``ChatAdapter`` via ``dspy.configure`` so every ReAct run — optimization
    rollouts and all serve paths, including those built from the plain
    ``dspy.ReActV2`` — resolves it through the ``main_thread_config`` fallback.
    A no-op when the flag is off. Failures are swallowed so a DSPy build that
    rejects the adapter kwargs can never abort process startup.
    """
    if not settings.react_native_tool_calling:
        return
    with contextlib.suppress(Exception):
        dspy.configure(adapter=native_react_adapter())
        logger.info("ReActV2 native function calling enabled (global ChatAdapter).")


def native_tool_calling_active() -> bool:
    """Report whether the currently active DSPy adapter uses native function calling.

    Inspects the live ``dspy.settings.adapter`` rather than the config flag, so
    reply-streaming adapts to whatever adapter is actually in force at call time
    (context override or global default).

    Returns:
        ``True`` when an adapter with ``use_native_function_calling`` is active.
    """
    adapter = getattr(dspy.settings, "adapter", None)
    return bool(getattr(adapter, "use_native_function_calling", False))


__all__ = [
    "configure_native_tool_calling",
    "native_react_adapter",
    "native_tool_calling_active",
]
