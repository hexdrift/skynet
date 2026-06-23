"""Version-agnostic handle on DSPy's ReAct program.

DSPy 3.3 reworked the agentic loop as ``ReActV2``: a single inner ``react``
predictor whose final answer is an argument of an internal ``submit`` tool call.
DSPy 3.2.x ships the classic ``ReAct``: the same ``react`` loop predictor plus a
separate ``extract`` predictor that emits the signature's output fields directly.

Both expose the same constructor (``signature, tools, max_iters``), an inner
``self.react`` predictor, and a ``self.tools`` dict, so the agent layer binds to
whichever class the installed DSPy provides and forks only where the two
genuinely differ — final-answer streaming (see ``react_reply_stream``).
"""

from __future__ import annotations

import dspy

REACT_CLASS: type[dspy.Module] = getattr(dspy, "ReActV2", None) or dspy.ReAct
"""The ReAct program class of the installed DSPy: ``ReActV2`` on 3.3+, else ``ReAct``."""


def react_uses_submit(program: dspy.Module) -> bool:
    """Report whether ``program`` carries its reply in a ``submit`` tool call.

    ReActV2 streams the final answer as a ``submit`` argument on the inner
    ``react`` predictor; classic ReAct streams it straight off a separate
    ``extract`` predictor. The presence of ``extract`` is the load-bearing
    distinction, so it is checked per-instance rather than inferred from the
    DSPy version.

    Args:
        program: A constructed ReAct/ReActV2 program (or subclass).

    Returns:
        ``True`` when the reply rides a ``submit`` tool call (ReActV2),
        ``False`` when a dedicated ``extract`` predictor emits it (classic).
    """
    return not hasattr(program, "extract")


__all__ = ["REACT_CLASS", "react_uses_submit"]
