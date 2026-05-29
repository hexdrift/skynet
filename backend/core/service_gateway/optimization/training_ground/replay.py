"""Counterfactual trace-conditioned replay for GEPA evaluation.

The replay is a hybrid mock — when the candidate matches the recorded
``(tool_name, argument_hash)`` we hand back the recorded result; when it
deviates we record why and terminate the rollout so the prefix still
earns credit. The contract is documented in ``training_ground_SPEC.md``
§5 and intentionally never reaches the real MCP server.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import dspy

from .types import (
    EvaluationExample,
    ReplayEvent,
    ReplayOutcome,
    ReplayRollout,
    ReplayStep,
)

SUBMIT_TOOL_NAME = "submit"
"""ReActV2's reserved terminal tool. The mock never exposes it — ReActV2 owns
the submit-tool construction and binds it to the signature's output fields."""


def canonical_argument_hash(arguments: Mapping[str, Any] | None) -> str:
    """Return the sha256 hex digest of canonical-JSON ``arguments``.

    Canonical = ``json.dumps(sort_keys=True, separators=(',', ':'),
    ensure_ascii=False, default=str)``. ``default=str`` lets us hash dicts
    that still contain Pydantic models / UUIDs without rejecting the row.

    Args:
        arguments: Arguments dict (possibly ``None``).

    Returns:
        Lowercase hex sha256 digest of the canonical-JSON encoding.
    """
    payload = arguments or {}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def adapt_agent_tool_calls_v1_to_replay(
    tool_calls: Sequence[Mapping[str, Any]] | None,
    *,
    turn_id: str,
    max_steps: int | None = None,
) -> list[ReplayStep]:
    """Convert one persisted ``agent_messages.tool_calls`` row into ``ReplayStep`` s.

    The persisted shape (built in
    ``core/api/routers/generalist_agent.py::_wrap_with_persistence``) is::

        {
          "id": "<uuid>",
          "tool": "<mcp_tool_name>",
          "reason": "<agent reasoning>",
          "status": "running" | "done" | "error",
          "startedAt": <ms>,
          "endedAt": <ms> | None,
          "payload": {"arguments": {...}, "result": {...}}
        }

    Args:
        tool_calls: The persisted JSONB list, or ``None`` when the turn was
            text-only.
        turn_id: ``agent_messages.id`` stringified — used only for error
            messages so a malformed row can be tracked back.
        max_steps: Optional truncation cap; useful for ``--dry-run``.

    Returns:
        A list of ``ReplayStep`` records in the original recorded order.
        Tool calls still ``running`` (never resolved) and tool calls with
        the synthetic ``submit`` name are filtered out — the mock manages
        submits itself.
    """
    if not tool_calls:
        return []
    steps: list[ReplayStep] = []
    for entry in tool_calls:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("tool") or "").strip()
        if not name or name == SUBMIT_TOOL_NAME:
            continue
        status_raw = str(entry.get("status") or "").strip()
        if status_raw == "running":
            continue
        status = "done" if status_raw == "done" else "error"
        payload = entry.get("payload") if isinstance(entry.get("payload"), Mapping) else {}
        arguments_raw = payload.get("arguments") if payload else None
        arguments = dict(arguments_raw) if isinstance(arguments_raw, Mapping) else {}
        result = payload.get("result") if payload else None
        reason_raw = entry.get("reason")
        reason = str(reason_raw) if isinstance(reason_raw, str) and reason_raw else None
        started_at = entry.get("startedAt")
        ended_at = entry.get("endedAt")
        steps.append(
            ReplayStep(
                tool_name=name,
                arguments=arguments,
                argument_hash=canonical_argument_hash(arguments),
                status=status,  # type: ignore[arg-type]
                result=result,
                reason=reason,
                started_at_ms=int(started_at) if isinstance(started_at, (int, float)) else None,
                ended_at_ms=int(ended_at) if isinstance(ended_at, (int, float)) else None,
            )
        )
        if max_steps is not None and len(steps) >= max_steps:
            break
    # Keep ``turn_id`` referenced for ergonomics in caller debug strings —
    # the parameter exists for ``no_data`` evidence on the upstream side.
    _ = turn_id
    return steps


class ReplayTerminated(Exception):  # noqa: N818
    """Raised inside a fake tool call to stop the candidate's loop cleanly.

    ReActV2's outer try/except catches tool errors and turns them into a
    ``Tool error`` observation. That is exactly the behavior we want: the
    candidate stops calling that tool but the rollout's prefix scoring is
    already complete because the mock recorded the event before raising.

    This is a control-flow signal, not an error condition — the ``Error``
    suffix would mislead readers (see ruff N818 suppression above).
    """


class TraceConditionedMCPMock:
    """Replays a single turn's recorded calls against a candidate program.

    Pass ``tool_layer()`` into a fresh ``dspy.ReActV2`` instance — each
    returned ``dspy.Tool`` shares state with the mock so the rollout log
    accumulates across multiple ReAct iterations.

    Args:
        example: The training example whose recorded steps drive the mock.
    """

    def __init__(self, example: EvaluationExample) -> None:
        """Initialize replay state from the example's recorded steps.

        Args:
            example: The training example whose recorded steps drive the mock.
        """
        self._example = example
        self._pointer = 0
        self._events: list[ReplayEvent] = []
        self._terminated_reason: ReplayOutcome | None = None
        self._submit_called = False
        self._submit_payload: dict[str, Any] | None = None
        self._forced_submit = False
        self._allowed_tools: frozenset[str] = example.allowed_tools

    def rollout_so_far(self) -> ReplayRollout:
        """Snapshot the rollout state — safe to call after the candidate finishes.

        Returns:
            A ``ReplayRollout`` capturing every event the mock observed and
            whether the rollout terminated early.
        """
        return ReplayRollout(
            events=tuple(self._events),
            terminated_early=self._terminated_reason is not None,
            terminated_reason=self._terminated_reason,
            submit_called=self._submit_called,
            submit_payload=dict(self._submit_payload) if self._submit_payload else None,
            forced_submit=self._forced_submit,
        )

    def tool_layer(
        self,
        *,
        candidate_tool_descriptions: Mapping[str, str] | None = None,
        live_tools: Mapping[str, dspy.Tool] | None = None,
    ) -> list[dspy.Tool]:
        """Build the list of fake ``dspy.Tool`` objects for one candidate program.

        Tool descriptions are sourced from ``candidate_tool_descriptions``
        when present (so GEPA-mutated descriptions reach the model), and
        fall back to a generic placeholder otherwise. When ``live_tools``
        is provided, each proxy copies the corresponding live tool's
        ``args`` / ``arg_types`` so DSPy exposes the real per-arg schema
        (and downstream candidate arg-description overrides land on a
        non-empty schema instead of a ``**kwargs`` blob).

        ``submit`` is intentionally omitted — ``dspy.ReActV2`` reserves
        that name and adds its own typed submit tool (matching the
        signature's output fields). The caller observes submit via
        :meth:`record_submit` after the rollout completes.

        Args:
            candidate_tool_descriptions: GEPA-tuned descriptions, keyed by
                tool name. Missing keys get the placeholder.
            live_tools: ``{tool_name: live_dspy_tool}`` for the phased
                MCP roster. Missing entries fall back to ``**kwargs``.

        Returns:
            One ``dspy.Tool`` per name in ``allowed_tools``.
        """
        descriptions = dict(candidate_tool_descriptions or {})
        live_map: Mapping[str, dspy.Tool] = live_tools or {}
        tools: list[dspy.Tool] = []
        for name in sorted(self._allowed_tools):
            desc = descriptions.get(name) or f"Replay-mock proxy for MCP tool {name}."
            tools.append(
                _build_proxy_tool(
                    self, name=name, desc=desc, live_tool=live_map.get(name)
                )
            )
        return tools

    def record_submit(self, payload: dict[str, Any]) -> None:
        """Mark the rollout as having reached ReActV2's clean submit terminal.

        Called by the evaluator after ``program(**inputs)`` returns a
        ``Prediction`` whose ``termination_reason`` is ``"submit"`` —
        the LM's own choice to terminate the ReAct loop. Refused when the
        rollout already terminated via divergence — anything ReActV2 might
        have submitted after the prefix failed is out-of-trajectory and
        must not be scored as a successful submit. Forced-submit
        fallbacks land in :meth:`record_forced_submit` instead, so the
        reward signal can penalise iter-exhaustion without granting it
        ``submit_clean`` credit.
        """
        if self._terminated_reason is not None:
            return
        self._submit_called = True
        self._submit_payload = dict(payload)

    def record_forced_submit(self) -> None:
        """Mark the rollout as having fallen through to ReActV2's forced submit.

        ReActV2 emits ``Prediction.termination_reason == "forced_submit"``
        when the candidate exhausts ``max_iters`` without choosing to
        submit. That is a recovery path, not a clean submit, so we track
        it on a dedicated flag — the LM did not pick the terminal action
        and the synthesised payload reflects scaffolding output, not the
        candidate's reasoning. Refused when the rollout already
        terminated via divergence so the prefix-failure scoring wins.
        """
        if self._terminated_reason is not None:
            return
        self._forced_submit = True

    def _on_candidate_call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Resolve a candidate tool call against the next recorded step.

        Matching is strictly ordered — the candidate must call
        ``replay_steps[self._pointer]`` next or the rollout terminates
        with ``no_data``. Out-of-order calls and repeated calls against
        an earlier step both diverge from the recorded trajectory and
        must be scored as divergence, not as hits. Schema drift is now
        handled at example-load time (see
        ``optimize._filter_trainable_examples``), so the replay assumes
        every (tool, args) pair it sees is hash-valid against the live
        MCP surface.

        ReActV2 catches ``ReplayTerminated`` per-tool and keeps looping,
        so the candidate may issue additional calls after divergence.
        We re-raise immediately for any post-termination call to keep
        the rollout's prefix scoring intact.

        Raises:
            ReplayTerminated: on any divergence so ReActV2's loop stops
                calling that tool — the mock records the event first.
        """
        if self._terminated_reason is not None:
            raise ReplayTerminated(
                f"rollout already terminated via {self._terminated_reason!r}"
            )
        candidate_hash = canonical_argument_hash(arguments)
        if tool_name not in self._allowed_tools:
            self._record_termination(
                outcome="tool_not_allowed",
                tool=tool_name,
                arguments=arguments,
                arg_hash=candidate_hash,
                matched_step=None,
                evidence=(
                    f"Candidate called {tool_name!r}, which is not in the "
                    f"allowed tool set for this wizard phase."
                ),
            )
        if self._pointer >= len(self._example.replay_steps):
            self._record_termination(
                outcome="no_data",
                tool=tool_name,
                arguments=arguments,
                arg_hash=candidate_hash,
                matched_step=None,
                evidence=(
                    f"Candidate called {tool_name!r} after exhausting all "
                    f"{len(self._example.replay_steps)} recorded steps."
                ),
            )
        expected = self._example.replay_steps[self._pointer]
        if expected.tool_name != tool_name or expected.argument_hash != candidate_hash:
            self._record_termination(
                outcome="no_data",
                tool=tool_name,
                arguments=arguments,
                arg_hash=candidate_hash,
                matched_step=None,
                evidence=(
                    f"Candidate called {tool_name!r} arg-hash "
                    f"{candidate_hash[:12]}…, but step {self._pointer} of the "
                    f"recorded trajectory is {expected.tool_name!r} arg-hash "
                    f"{expected.argument_hash[:12]}…."
                ),
            )
        self._events.append(
            ReplayEvent(
                outcome="hit",
                candidate_tool=tool_name,
                candidate_arguments=dict(arguments),
                candidate_argument_hash=candidate_hash,
                matched_step=expected,
                evidence="hit",
            )
        )
        self._pointer += 1
        if expected.status == "error":
            return {"error": expected.result}
        return expected.result

    def _record_termination(
        self,
        *,
        outcome: ReplayOutcome,
        tool: str,
        arguments: dict[str, Any],
        arg_hash: str,
        matched_step: ReplayStep | None,
        evidence: str,
    ) -> None:
        """Append the divergence event and raise ``ReplayTerminated``."""
        self._events.append(
            ReplayEvent(
                outcome=outcome,
                candidate_tool=tool,
                candidate_arguments=dict(arguments),
                candidate_argument_hash=arg_hash,
                matched_step=matched_step,
                evidence=evidence,
            )
        )
        if self._terminated_reason is None:
            self._terminated_reason = outcome
        raise ReplayTerminated(evidence)



def _build_proxy_tool(
    mock: TraceConditionedMCPMock,
    *,
    name: str,
    desc: str,
    live_tool: dspy.Tool | None = None,
) -> dspy.Tool:
    """Construct a ``dspy.Tool`` that delegates to the mock.

    The proxy body uses ``**kwargs`` so any recorded arg shape can flow
    through. When ``live_tool`` is provided we copy its ``args`` and
    ``arg_types`` after construction so DSPy's signature formatter shows
    the real per-arg schema (description, type) to the LM, which is what
    lets the candidate's arg-description overrides actually reach the
    model. Without a live tool, we fall back to the ``**kwargs`` schema.
    """

    def _proxy(**kwargs: Any) -> Any:
        """Forward the candidate's call to the mock for this tool name."""
        return mock._on_candidate_call(name, dict(kwargs))

    _proxy.__doc__ = desc
    _proxy.__name__ = name
    tool = dspy.Tool(_proxy, name=name, desc=desc)
    if live_tool is not None:
        live_args = getattr(live_tool, "args", None)
        if isinstance(live_args, dict):
            tool.args = json.loads(json.dumps(live_args, default=str))
        live_arg_types = getattr(live_tool, "arg_types", None)
        if isinstance(live_arg_types, dict):
            tool.arg_types = dict(live_arg_types)
    return tool


def is_replay_terminated(exc: BaseException) -> bool:
    """Return True iff ``exc`` was raised by the mock to end the rollout cleanly.

    Used in tests; ReActV2's loop already swallows the exception and the
    candidate sees a ``Tool error`` observation, but downstream code that
    wraps the rollout outside ReAct (e.g. the dry-run estimator) needs to
    differentiate intentional termination from real bugs.
    """
    return isinstance(exc, ReplayTerminated)


def iter_hit_events(rollout: ReplayRollout) -> Iterable[ReplayEvent]:
    """Yield only the ``outcome='hit'`` events from a rollout."""
    return (ev for ev in rollout.events if ev.outcome == "hit")


__all__ = [
    "SUBMIT_TOOL_NAME",
    "ReplayTerminated",
    "TraceConditionedMCPMock",
    "adapt_agent_tool_calls_v1_to_replay",
    "canonical_argument_hash",
    "is_replay_terminated",
    "iter_hit_events",
]


# Keep ``inspect`` referenced — DSPy uses it via tool reflection and a future
# revision may need to inspect candidate tool signatures here directly.
_ = inspect
