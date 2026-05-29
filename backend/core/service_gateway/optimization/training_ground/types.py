"""Dataclasses shared by the training-ground harness.

All immutable so they can be hashed into GEPA's deduplicated batches and
shipped between processes without surprises. The bundle Pydantic model
mirrors the on-disk schema in ``training_ground_SPEC.md`` §8 verbatim so a
bundle round-trip survives a `pydantic` validate-dump cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ReplayStep:
    """One recorded tool call from a production turn.

    ``argument_hash`` is the sha256 of canonical-JSON arguments and is the
    only thing the mock matches against — keys/values can come back in any
    order, but ``json.dumps(..., sort_keys=True, separators=(',', ':'))``
    flattens both into the same string.

    Args:
        tool_name: MCP tool name (matches the names exposed by ``tools_for``).
        arguments: Original arguments dict for debugging / reflective feedback.
        argument_hash: sha256 hex digest of canonical-JSON arguments.
        status: ``done`` when the recorded tool returned cleanly, ``error``
            when the recorded tool raised.
        result: Result payload exactly as the agent runtime saw it.
        reason: Optional ``reason`` field the agent emitted alongside the call.
        started_at_ms: Recorded wall-clock start, ms since epoch, when known.
        ended_at_ms: Recorded wall-clock end, ms since epoch, when known.
    """

    tool_name: str
    arguments: dict[str, Any]
    argument_hash: str
    status: Literal["done", "error"]
    result: Any
    reason: str | None
    started_at_ms: int | None
    ended_at_ms: int | None


ReplayOutcome = Literal[
    "hit", "tool_not_allowed", "schema_drift", "no_data", "no_call"
]


@dataclass(frozen=True)
class ReplayEvent:
    """One observation from a candidate's hybrid-mock rollout.

    Either records an exact match against a recorded ``ReplayStep`` and the
    recorded result that was replayed, or records the divergence reason that
    caused the rollout to terminate.

    Args:
        outcome: Match category — see ``ReplayOutcome``.
        candidate_tool: Tool name the candidate attempted.
        candidate_arguments: Arguments the candidate attempted.
        candidate_argument_hash: sha256 of canonical-JSON candidate args.
        matched_step: The ``ReplayStep`` that was replayed, when outcome=hit.
        evidence: Short, human-readable string used for reflective feedback.
    """

    outcome: ReplayOutcome
    candidate_tool: str
    candidate_arguments: dict[str, Any]
    candidate_argument_hash: str
    matched_step: ReplayStep | None
    evidence: str


@dataclass(frozen=True)
class ReplayRollout:
    """The full observation log produced by ``TraceConditionedMCPMock``.

    Args:
        events: Per-step events in chronological order. May be shorter than
            ``len(recorded_steps)`` when the rollout terminated early.
        terminated_early: True iff the rollout was cut short by a non-hit
            event before consuming every recorded step.
        terminated_reason: Outcome that ended the rollout; ``None`` when the
            rollout consumed every recorded step or ended via submit.
        submit_called: True iff the candidate cleanly invoked ``submit``
            (``Prediction.termination_reason == "submit"``). Never set for
            forced-submit fallbacks.
        submit_payload: The arguments dict from the last clean submit, when known.
        forced_submit: True iff ReActV2 fell through to its
            ``forced_submit`` fallback because the candidate exhausted
            ``max_iters`` without calling submit. Recorded separately so
            metrics can penalise the exhaustion path without treating it as
            a clean submit.
    """

    events: tuple[ReplayEvent, ...]
    terminated_early: bool
    terminated_reason: ReplayOutcome | None
    submit_called: bool
    submit_payload: dict[str, Any] | None
    forced_submit: bool = False


@dataclass(frozen=True)
class EvaluationExample:
    """One turn-scoped training/eval example pulled from ``agent_messages``.

    Args:
        turn_id: Stable id for the assistant turn (``agent_messages.id`` as str).
        user_message: Verbatim user message that prompted this turn.
        wizard_state_before: Snapshot captured at turn start.
        wizard_state_after: Snapshot captured at turn end (after tool calls).
        allowed_tools: ``tools_for(wizard_state_before)`` at turn time.
        tool_schema_hashes: ``{tool_name: sha256(schema_json)}`` snapshot.
        replay_steps: Chronological recorded calls + results for the turn.
        chat_history: Prior ``{role, content}`` turns in the same conversation.
    """

    turn_id: str
    user_message: str
    wizard_state_before: dict[str, Any]
    wizard_state_after: dict[str, Any]
    allowed_tools: frozenset[str]
    tool_schema_hashes: dict[str, str]
    replay_steps: tuple[ReplayStep, ...]
    chat_history: tuple[dict[str, Any], ...]


@dataclass
class ScoredVector:
    """Result of one candidate rollout against one example.

    Not frozen — GEPA's batch evaluator collects these into a list inside a
    tight loop and we mutate ``trajectory`` afterwards when ``capture_traces``
    is True.

    Args:
        objective_scores: The 12 per-dimension reward components.
        scalar: ``scalar_with_hard_caps(objective_scores)`` — what GEPA's
            frontier compares.
        rollout: The hybrid-mock rollout that produced these scores.
        feedback: Human-readable evidence string consumed by the reflective
            proposer.
    """

    objective_scores: dict[str, float]
    scalar: float
    rollout: ReplayRollout
    feedback: str


class PairedBootstrapResult(BaseModel):
    """Acceptance statistics produced by ``persistence.paired_bootstrap_ci``."""

    resamples: int
    mean_delta: float
    ci95_lower: float
    ci95_upper: float


class Bundle(BaseModel):
    """On-disk bundle format mounted from the prod ConfigMap.

    Schema is the source of truth for the file the runtime loads at
    ``/etc/skynet/bundles/<model_id>/current.json``. Any field rename here
    is a breaking change — bump ``bundle_format_version`` before shipping.
    """

    bundle_format_version: int = Field(default=1)
    model_id: str
    version: str
    dspy_version: str
    gepa_version: str
    gate_logic_version: str
    tool_schema_hashes: dict[str, str]
    max_iters: int = Field(default=8, ge=1)
    program_state: dict[str, Any]
    # GEPA-mutated overlays applied on top of the live MCP tools at
    # runtime. ``program.save(save_program=False)`` discards the program's
    # tool dict, so these are persisted separately and re-applied in
    # ``registry.fresh_program_for_bundle``. Default-empty for backwards
    # compatibility with bundles produced before this field existed.
    tool_descriptions: dict[str, str] = Field(default_factory=dict)
    tool_arg_descriptions: dict[str, dict[str, str]] = Field(default_factory=dict)
    scalar_score: float
    objective_scores: dict[str, float]
    window_days: int = Field(ge=1)
    trajectories_trained_on: int = Field(ge=0)
    trajectories_held_out: int = Field(ge=0)
    paired_bootstrap: PairedBootstrapResult
    # Optional debug metadata (provenance — not enforced on load).
    optimizer_kwargs: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "Bundle",
    "EvaluationExample",
    "PairedBootstrapResult",
    "ReplayEvent",
    "ReplayOutcome",
    "ReplayRollout",
    "ReplayStep",
    "ScoredVector",
]


# Silence "unused" warning for re-exported dataclass field helper if any
# downstream module decides to wire defaults later.
_ = field
