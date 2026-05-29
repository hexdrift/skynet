"""Reward signal for the training-ground harness.

Each dimension returns a value in ``[0, 1]`` so the weighted scalar is
well-behaved and the reflective proposer's feedback strings can quote
"dimension X scored 0.3" without rescaling. The dimensions and weights
are frozen by ``training_ground_SPEC.md`` §6.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Mapping
from typing import Any

from .replay import SUBMIT_TOOL_NAME, iter_hit_events
from .types import EvaluationExample, ReplayEvent, ReplayRollout

UPDATE_WIZARD_STATE_TOOL = "update_wizard_state"


_CRITICAL: frozenset[str] = frozenset(
    {
        "submit_clean",
        "no_phantom_refusal",
        "no_call_on_actionable_turn",
        "schema_parse_success",
        "no_forced_submit_exhaustion",
        "gate_progress",
        "missing_reflection_model",
        "no_repeated_dataset_upload",
        "no_hallucinated_ids",
        "tool_success_rate",
    }
)

_WEIGHTS: dict[str, float] = {
    "submit_clean": 0.18,
    "no_phantom_refusal": 0.12,
    "no_call_on_actionable_turn": 0.10,
    "schema_parse_success": 0.10,
    "no_forced_submit_exhaustion": 0.08,
    "gate_progress": 0.15,
    "tool_success_rate": 0.10,
    "one_call_compliance": 0.05,
    "missing_reflection_model": 0.05,
    "no_repeated_dataset_upload": 0.02,
    "no_hallucinated_ids": 0.03,
    "observation_usefulness": 0.02,
}

# Hard-cap kicks in when ANY of these dimensions falls below this threshold.
_CRITICAL_FLOOR = 0.5
_HARD_CAP = 0.4


def _safe_div(numerator: float, denominator: float) -> float:
    """Return 0.0 when ``denominator`` is 0; else ``numerator / denominator``."""
    return numerator / denominator if denominator else 0.0


def _gate_score(state: Mapping[str, Any]) -> float:
    """Map a wizard snapshot to a coarse progress score in ``[0, 1]``.

    The score mirrors the phase ladder in
    ``generalist.tools_for``: dataset_ready < columns_configured <
    signature+metric+model < submitted. We use it as the delta target so a
    candidate that advances the wizard scores positively even when its
    text-level reply differs from the recorded one.
    """
    if not state:
        return 0.0
    score = 0.0
    if state.get("dataset_ready") or state.get("staged_dataset_id"):
        score += 0.25
    if state.get("columns_configured"):
        score += 0.20
    if state.get("signature_code"):
        score += 0.15
    if state.get("metric_code"):
        score += 0.15
    model_config = state.get("model_config") if isinstance(state.get("model_config"), Mapping) else None
    if state.get("model_configured") or (model_config and model_config.get("name")):
        score += 0.15
    if state.get("submitted") or state.get("job_id"):
        score += 0.10
    return min(1.0, score)


def _submit_clean(rollout: ReplayRollout) -> float:
    """1.0 iff the candidate called submit cleanly and ReAct stopped without errors."""
    if not rollout.submit_called:
        return 0.0
    if rollout.terminated_early:
        return 0.0
    if rollout.submit_payload is None:
        return 0.0
    if not isinstance(rollout.submit_payload.get("assistant_message"), str):
        return 0.0
    if not rollout.submit_payload["assistant_message"].strip():
        return 0.0
    return 1.0


def _no_phantom_refusal(rollout: ReplayRollout, allowed_tools: frozenset[str]) -> float:
    """0.0 when the candidate dialed an out-of-phase tool.

    Refusal to call any tool is fine here — that is checked by
    ``_no_idle_when_tools_available``. This dimension only punishes
    candidates that hallucinated tools outside their wizard phase.
    """
    if not allowed_tools:
        return 1.0
    for event in rollout.events:
        if event.outcome == "tool_not_allowed":
            return 0.0
    return 1.0


def _no_idle_when_tools_available(
    rollout: ReplayRollout, example: EvaluationExample
) -> float:
    """Punish refusal-as-strategy when tools were exposed AND recorded.

    If the recorded turn had at least one productive tool call, an empty
    rollout (no hits, no submit) is the failure mode this guards against.
    Turns where the recorded agent answered via text only — no tools — are
    scored 1.0 so we don't penalize legitimate clarifying questions.
    """
    if not example.replay_steps:
        return 1.0
    hits = sum(1 for _ in iter_hit_events(rollout))
    if hits > 0:
        return 1.0
    if rollout.submit_called:
        return 0.3
    return 0.0


def _schema_parse_success(rollout: ReplayRollout) -> float:
    """1.0 unless the candidate hit a `schema_drift` outcome."""
    for event in rollout.events:
        if event.outcome == "schema_drift":
            return 0.0
    return 1.0


def _no_forced_submit(rollout: ReplayRollout) -> float:
    """1.0 when the candidate did not exhaust ``max_iters`` without submitting.

    ReActV2 drops out via the forced-submit path when it spins on a tool
    until ``max_iters`` is reached. ``rollout.forced_submit`` is set
    directly from ``Prediction.termination_reason == "forced_submit"`` by
    the evaluator, so the metric reads it as a primary signal — clean
    submit beats forced submit beats early divergence beats "ran fine
    but never submitted".
    """
    if rollout.submit_called:
        return 1.0
    if rollout.forced_submit:
        return 0.0
    if rollout.terminated_reason in {"no_data", "schema_drift", "tool_not_allowed"}:
        return 0.0
    if rollout.terminated_early:
        return 0.0
    return 0.5


def _replay_hit_success_rate(rollout: ReplayRollout) -> float:
    """Hit rate over all attempted candidate tool calls.

    Successful = exact ``(name, arg_hash)`` match against a recorded call.
    """
    total = len(rollout.events)
    if total == 0:
        return 0.0
    hits = sum(1 for _ in iter_hit_events(rollout))
    return _safe_div(float(hits), float(total))


def _at_most_one_update_wizard_state(rollout: ReplayRollout) -> float:
    """Enforce the "one ``update_wizard_state`` per turn" rule from the prompt."""
    count = sum(
        1
        for event in rollout.events
        if event.candidate_tool == UPDATE_WIZARD_STATE_TOOL
    )
    if count <= 1:
        return 1.0
    return max(0.0, 1.0 - 0.5 * (count - 1))


def _reflection_model_config_present(rollout: ReplayRollout) -> float:
    """1.0 unless the candidate submitted a job without ``reflection_model_config``.

    Only inspects ``submit_*`` calls — every other tool is fine.
    """
    submit_payloads = [
        event.candidate_arguments
        for event in iter_hit_events(rollout)
        if event.candidate_tool.startswith("submit_")
    ]
    if not submit_payloads:
        return 1.0
    for payload in submit_payloads:
        reflection = payload.get("reflection_model_config") or payload.get("reflection_models")
        if not reflection:
            return 0.0
        if isinstance(reflection, Mapping) and not reflection.get("name"):
            return 0.0
    return 1.0


def _no_redundant_upload(rollout: ReplayRollout) -> float:
    """Punish repeated dataset upload prompts in the same turn."""
    uploads = sum(
        1
        for event in rollout.events
        if event.candidate_tool.startswith("request_user_dataset")
    )
    if uploads <= 1:
        return 1.0
    return max(0.0, 1.0 - 0.5 * (uploads - 1))


def _ids_traceable_to_results(
    rollout: ReplayRollout, example: EvaluationExample
) -> float:
    """0.0 when the candidate's submit payload references an unseen optimization id.

    "Unseen" = not present in any recorded tool result for this example
    and not in ``wizard_state_after``. Approximation, but it catches the
    "hallucinate a job id" failure mode cheaply.
    """
    if not rollout.submit_payload:
        return 1.0
    text_blob = json.dumps(rollout.submit_payload, ensure_ascii=False, default=str)
    candidate_ids = _scan_ids(text_blob)
    if not candidate_ids:
        return 1.0
    known = _known_ids(example)
    unknown = [cid for cid in candidate_ids if cid not in known]
    if not unknown:
        return 1.0
    return max(0.0, 1.0 - 0.25 * len(unknown))


def _next_action_uses_result_fields(rollout: ReplayRollout) -> float:
    """Reward candidates that thread the previous tool result into the next call.

    Loose proxy: for each consecutive pair (hit_i, candidate_{i+1}), score
    1.0 if any value from hit_i's recorded result appears in
    candidate_{i+1}'s arguments. Averaged over all such pairs.
    """
    hits = [event for event in iter_hit_events(rollout) if event.matched_step]
    if len(hits) < 2:
        return 1.0 if hits else 0.5
    overlap_scores: list[float] = []
    for prev, nxt in itertools.pairwise(hits):
        prev_values = _flatten_values(prev.matched_step.result if prev.matched_step else None)
        nxt_values = _flatten_values(nxt.candidate_arguments)
        if not prev_values:
            overlap_scores.append(0.5)
            continue
        hit_count = sum(1 for value in nxt_values if value and value in prev_values)
        overlap_scores.append(1.0 if hit_count > 0 else 0.0)
    return sum(overlap_scores) / len(overlap_scores)


def vector_reward(
    example: EvaluationExample, rollout: ReplayRollout
) -> dict[str, float]:
    """Compute the 12-dimension reward vector for one (example, rollout) pair.

    See ``training_ground_SPEC.md`` §6 for the dimension list — order is
    preserved for reproducibility of objective_scores in the bundle.
    """
    return {
        "submit_clean": _submit_clean(rollout),
        "no_phantom_refusal": _no_phantom_refusal(rollout, example.allowed_tools),
        "no_call_on_actionable_turn": _no_idle_when_tools_available(rollout, example),
        "schema_parse_success": _schema_parse_success(rollout),
        "no_forced_submit_exhaustion": _no_forced_submit(rollout),
        "gate_progress": max(
            0.0,
            min(
                1.0,
                _gate_score(example.wizard_state_after)
                - _gate_score(example.wizard_state_before),
            ),
        ),
        "tool_success_rate": _replay_hit_success_rate(rollout),
        "one_call_compliance": _at_most_one_update_wizard_state(rollout),
        "missing_reflection_model": _reflection_model_config_present(rollout),
        "no_repeated_dataset_upload": _no_redundant_upload(rollout),
        "no_hallucinated_ids": _ids_traceable_to_results(rollout, example),
        "observation_usefulness": _next_action_uses_result_fields(rollout),
    }


def scalar_with_hard_caps(vec: Mapping[str, float]) -> float:
    """Weighted mean, hard-capped at ``_HARD_CAP`` when any critical dim < 0.5.

    Defends against reward hacking by refusal: a candidate that scores
    1.0 on easy dims by doing nothing still gets capped because
    ``no_call_on_actionable_turn`` or ``gate_progress`` collapses below
    ``_CRITICAL_FLOOR``.

    Args:
        vec: Mapping returned by ``vector_reward``.

    Returns:
        Scalar in ``[0, 1]`` suitable for GEPA's frontier comparison.
    """
    raw = sum(_WEIGHTS[k] * float(vec.get(k, 0.0)) for k in _WEIGHTS)
    raw = max(0.0, min(1.0, raw))
    triggered = any(
        float(vec.get(name, 0.0)) < _CRITICAL_FLOOR
        for name in _CRITICAL
        if name in vec
    )
    if triggered:
        return min(_HARD_CAP, raw)
    return raw


def feedback_from_low_dims(
    vec: Mapping[str, float],
    rollout: ReplayRollout,
    example: EvaluationExample,
    *,
    max_dims: int = 3,
) -> str:
    """Render a short, evidence-rich feedback string for GEPA's reflective LM.

    Surfaces the bottom ``max_dims`` dimensions and the concrete rollout
    events that explain the score. Optimized for prompt-engineering signal,
    not log readability — keep it terse.
    """
    sorted_dims = sorted(vec.items(), key=lambda kv: float(kv[1]))
    bottom = [name for name, score in sorted_dims if score < 0.99][:max_dims]
    if not bottom:
        return "All reward dimensions ≥ 0.99."
    lines = [
        f"Turn {example.turn_id}: lowest dims = " + ", ".join(
            f"{name}={float(vec[name]):.2f}" for name in bottom
        )
    ]
    last_events = list(rollout.events)[-4:]
    if last_events:
        lines.append("Recent rollout events:")
        lines.extend(f"  - {event.outcome}: {event.evidence}" for event in last_events)
    if rollout.terminated_early and rollout.terminated_reason:
        lines.append(
            f"Rollout terminated early via {rollout.terminated_reason!r}. "
            "Earlier turns of the recorded trajectory must be matched exactly."
        )
    if not rollout.submit_called:
        lines.append("Candidate never called the submit tool.")
    return "\n".join(lines)


def _flatten_values(value: Any) -> list[Any]:
    """Walk a nested JSON-like value and emit hashable leaves."""
    out: list[Any] = []
    stack: list[Any] = [value]
    seen_ids: set[int] = set()
    while stack:
        item = stack.pop()
        if id(item) in seen_ids:
            continue
        seen_ids.add(id(item))
        if isinstance(item, Mapping):
            stack.extend(item.values())
        elif isinstance(item, (list, tuple, set, frozenset)):
            stack.extend(item)
        elif isinstance(item, (str, int, float, bool)) or item is None:
            out.append(item)
    return out


_ID_PATTERN_LENGTHS: frozenset[int] = frozenset({32, 36})


def _scan_ids(blob: str) -> list[str]:
    """Heuristic ID scanner: pulls UUID-shaped tokens out of a string blob.

    Cheaper than running a full regex over every candidate payload and
    sufficient for catching ``optimization_id`` hallucinations.
    """
    tokens = [
        token.strip(' "\'')
        for token in blob.replace(",", " ").replace("{", " ").replace("}", " ").split()
    ]
    return [
        token
        for token in tokens
        if len(token) in _ID_PATTERN_LENGTHS and token.count("-") in (0, 4)
    ]


def _known_ids(example: EvaluationExample) -> frozenset[str]:
    """Collect every identifier visible to the agent at submit time."""
    parts: list[str] = []
    parts.append(json.dumps(example.wizard_state_after, ensure_ascii=False, default=str))
    for step in example.replay_steps:
        parts.append(json.dumps(step.result, ensure_ascii=False, default=str))
        parts.append(json.dumps(step.arguments, ensure_ascii=False, default=str))
    blob = " ".join(parts)
    return frozenset(_scan_ids(blob))


# Public re-exports — used by ``gepa_adapter.evaluate``.
__all__ = [
    "feedback_from_low_dims",
    "scalar_with_hard_caps",
    "vector_reward",
]


# Reference imports kept for downstream typing parity (ReplayEvent + SUBMIT name).
_ = ReplayEvent
_ = SUBMIT_TOOL_NAME
