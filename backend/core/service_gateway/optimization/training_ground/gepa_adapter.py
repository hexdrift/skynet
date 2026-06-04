"""GEPA adapter that wires the training-ground reward into the reflective loop.

Subclass of ``gepa.adapters.dspy_adapter.DspyAdapter`` so we inherit the
canonical ``propose_new_texts`` plumbing (instruction proposer + tool
proposer) but replace ``evaluate`` with a hybrid-mock rollout and
``make_reflective_dataset`` with concrete failure evidence.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import dspy
from dspy.primitives import Example, Prediction
from gepa import EvaluationBatch
from gepa.adapters.dspy_adapter.dspy_adapter import (
    TOOL_MODULE_PREFIX,
    DspyAdapter,
)

from .grounding import (
    ChatTemplate,
    PromptScorer,
    as_unit_interval,
    grounding_reward,
)
from .metrics import (
    GENERALIST_REWARD_SPEC,
    RewardSpec,
    feedback_from_low_dims,
    scalar_with_hard_caps,
    vector_reward,
)
from .replay import (
    SUBMIT_TOOL_NAME,
    ReplayTerminated,
    TraceConditionedMCPMock,
    resolve_proposed_names,
)
from .types import EvaluationExample, ReplayRollout

logger = logging.getLogger(__name__)


VectorRewardFn = Callable[[EvaluationExample, ReplayRollout], dict[str, float]]
"""Signature of a per-example reward-vector function (generalist or general)."""


TOOL_MODULE_KEY = f"{TOOL_MODULE_PREFIX}:react"
"""Neutral composite key holding every mutable text for the candidate program.

Domain-agnostic replacement for the legacy ``:generalist`` key. Candidate
parsing accepts either key (see :data:`_LEGACY_MODULE_KEY`) so candidates
seeded before the rename still load."""

_LEGACY_MODULE_KEY = f"{TOOL_MODULE_PREFIX}:generalist"
"""Pre-rename composite key — still parsed for back-compat with old candidates."""

GENERALIST_MODULE_KEY = _LEGACY_MODULE_KEY
"""Deprecated alias for :data:`_LEGACY_MODULE_KEY`, kept for existing importers."""

REACT_PREDICTOR_NAME = "react"
"""Inner-predictor name on ReActV2 — used by the seed candidate and reflective
dataset routing."""

_GROUNDING_DIM = "observation_grounding"
"""Objective-scores key for the ECHO grounding term. Non-critical (auxiliary),
so it is logged + frontier-visible but never trips the §11 regression gate."""


def seed_candidate_from_program(program: dspy.Module) -> dict[str, str]:
    """Build the GEPA seed candidate from a ReActV2 program.

    GEPA mutates one composite ``tool_module:react`` blob so the
    instruction proposer optimizes the inner predictor's instructions and
    the tool descriptions jointly. Mirrors ``DspyAdapter.build_program``
    expectations (see ``gepa/adapters/dspy_adapter/dspy_adapter.py:180``).

    Args:
        program: The seed ReActV2 instance with its baseline signature
            and tool descriptions wired in.

    Returns:
        ``{"tool_module:react": "<json blob>"}`` where the blob is
        ``{"react": <instructions>, "tools": {<canonical>: {"name": ...,
        "desc": ..., "args": ...}}}``. The blob is keyed by canonical name and
        seeds ``name`` equal to the canonical name so GEPA can mutate a clearer
        display name the agent sees while matching/reward stay canonical.
    """
    instructions = _extract_react_instructions(program)
    tools_payload: dict[str, dict[str, Any]] = {}
    for name, tool in _collect_tools(program).items():
        if name == SUBMIT_TOOL_NAME:
            continue
        tools_payload[name] = {
            "name": name,
            "desc": tool.desc or "",
            "args": _serialize_tool_args(tool.args),
        }
    config = {REACT_PREDICTOR_NAME: instructions, "tools": tools_payload}
    return {TOOL_MODULE_KEY: json.dumps(config, ensure_ascii=False, sort_keys=True)}


class TrainingGroundDspyAdapter(DspyAdapter):
    """GEPA adapter scoring candidates by the ECHO hybrid reward.

    Implements ECHO's objective (arXiv 2605.24517, ``training_ground_SPEC.md``
    §6) over GEPA prompt search. The per-example score is::

        task_term + grounding_weight * grounding_term

    where ``task_term`` is the 12-dimension replay reward (the ℒ_GRPO analog —
    the task-quality signal available without live RL) and ``grounding_term``
    is :func:`grounding.as_unit_interval` of the mean per-token log-likelihood
    the frozen model assigns to the replayed observations (ECHO's −ℒ_Env),
    teacher-forced in the candidate's real served context. ECHO's max-gain
    recipe is the combination at ``grounding_weight = 0.05``; the endpoints
    (task-only, grounding-only) are recovered by zeroing the weight or turning
    the task term off, so one adapter reproduces the paper's GRPO / ECHO /
    env-only comparison. Unlike ECHO (which reuses the GRPO forward pass "for
    free"), grounding here costs one echo call per example — we score a frozen
    model rather than training one.

    Args:
        seed_program: Production ReActV2 instance used as the structural
            template (signature, tool roster) — instances are deep-copied
            per evaluation so mutations don't leak.
        student_lm: The model under optimization. Candidate rollouts run
            inside ``dspy.context(lm=student_lm)`` per spec §7; its ``history``
            is the source of the 1:1 served messages grounding scores.
        reflection_lm: The model used by GEPA's reflective proposer (text
            mutation suggestions). Passed through to the parent class.
        include_task_reward: Include the 12-dimension replay (task) reward.
        grounding_weight: Coefficient on the grounding auxiliary (ECHO's λ,
            0.05 in the paper). Zero disables grounding.
        template: Chat-template renderer (``MiniMaxChatTemplate``); required
            when ``grounding_weight > 0``.
        scorer: Per-token echo scorer (``FireworksEchoScorer``); required when
            ``grounding_weight > 0``.
        feedback_dim_count: Bottom-N task dimensions surfaced per example in
            the reflective dataset. Kept small so reflection prompts stay tight.
        reward_spec: Scalarizer config (weights + hard-cap policy) for the task
            term. Defaults to :data:`GENERALIST_REWARD_SPEC` so existing call
            sites keep the generalist behavior; pair with ``vector_fn`` to score
            a different dimension set.
        vector_fn: Per-example reward-vector function. Defaults to
            :func:`vector_reward` (the 12-dimension generalist vector); must
            produce the dimensions named in ``reward_spec.weights``.
        match_mode: Replay step-matching policy forwarded to every
            :class:`TraceConditionedMCPMock`. ``"exact"`` (default) keeps the
            byte-exact ``(tool_name, argument_hash)`` contract; ``"tool_name"``
            advances on a tool-name match so unreproducible free-text args don't
            kill the rollout after the first call.

    Raises:
        ValueError: when the configured reward has no active term, or grounding
            is weighted without both a template and a scorer.
    """

    def __init__(
        self,
        *,
        seed_program: dspy.Module,
        student_lm: dspy.LM,
        reflection_lm: dspy.LM | None,
        include_task_reward: bool = True,
        grounding_weight: float = 0.0,
        template: ChatTemplate | None = None,
        scorer: PromptScorer | None = None,
        feedback_dim_count: int = 3,
        reward_spec: RewardSpec = GENERALIST_REWARD_SPEC,
        vector_fn: VectorRewardFn = vector_reward,
        match_mode: str = "exact",
    ) -> None:
        """Configure the reward terms and stash the rollout collaborators.

        Args are documented on the class docstring; this validates that the
        chosen reward has at least one active term and that grounding has its
        template and scorer when weighted.

        Raises:
            ValueError: When no reward term is active, or grounding is weighted
                without both a template and a scorer.
        """
        if grounding_weight > 0 and (template is None or scorer is None):
            msg = "grounding_weight > 0 requires both a template and a scorer."
            raise ValueError(msg)
        if not include_task_reward and grounding_weight <= 0:
            msg = "Reward must use the task term, grounding (weight > 0), or both."
            raise ValueError(msg)
        super().__init__(
            student_module=seed_program,
            metric_fn=_unused_metric_fn,
            feedback_map={},
            failure_score=0.0,
            num_threads=None,
            add_format_failure_as_feedback=False,
            reflection_lm=reflection_lm,
            custom_instruction_proposer=None,
            warn_on_score_mismatch=False,
            enable_tool_optimization=True,
            reflection_minibatch_size=None,
        )
        self._student_lm = student_lm
        self._feedback_dim_count = feedback_dim_count
        self._max_iters = getattr(seed_program, "max_iters", 8)
        self._seed_program = seed_program
        self._include_task_reward = include_task_reward
        self._grounding_weight = grounding_weight
        self._template = template
        self._scorer = scorer
        self._reward_spec = reward_spec
        self._vector_fn = vector_fn
        self._match_mode = match_mode

    def evaluate(  # type: ignore[override]
        self,
        batch: list[EvaluationExample],
        candidate: dict[str, str],
        capture_traces: bool = False,
    ) -> EvaluationBatch:
        """Score one minibatch with the configured ECHO hybrid reward.

        Each example runs the trace-conditioned rollout (capturing the real
        served messages when grounding is active) and combines the task +
        grounding terms. Mirrors ``training_ground_SPEC.md`` §7 — errors are
        caught per-example because GEPA expects a failure-scoring path, not an
        exception.
        """
        outputs: list[Prediction | None] = []
        scores: list[float] = []
        trajectories: list[dict[str, Any] | None] = []
        objective_scores: list[dict[str, float]] = []
        tool_descriptions = _candidate_tool_descriptions(candidate)
        tool_arg_descriptions = _candidate_tool_arg_descriptions(candidate)
        proposed_names = _candidate_tool_names(candidate)
        instructions = _candidate_instructions(candidate)
        total = len(batch)
        logger.info("react evaluate: scoring %d example(s)", total)
        for idx, example in enumerate(batch):
            # Resolve per-example because collision filtering is scoped to this
            # turn's allowed_tools; the canonical_by_proposed inversion is then
            # exactly the canonicalizer the mock applies to every called name.
            resolved_names = resolve_proposed_names(
                proposed_names, example.allowed_tools
            )
            canonical_by_proposed = {
                proposed: canonical for canonical, proposed in resolved_names.items()
            }
            mock = TraceConditionedMCPMock(
                example,
                name_canonicalizer=lambda n, m=canonical_by_proposed: m.get(n, n),
                match_mode=self._match_mode,
            )
            messages: list[dict[str, Any]] = []
            tools: Any = None
            instantiation_failed = False
            try:
                program = self._instantiate_candidate(
                    mock=mock,
                    instructions=instructions,
                    tool_descriptions=tool_descriptions,
                    tool_arg_descriptions=tool_arg_descriptions,
                    proposed_names=resolved_names,
                )
            except Exception:  # pragma: no cover - defensive
                logger.exception(
                    "Failed to instantiate candidate for turn %s", example.turn_id
                )
                pred = None
                instantiation_failed = True
            else:
                pred, messages, tools = self._run_rollout(program, example)
                _record_submit_from_prediction(mock=mock, program=program, pred=pred)
            rollout = mock.rollout_so_far()
            scalar, objectives, mean_ll, obs_count = self._score(
                example, rollout, messages, tools
            )
            if instantiation_failed:
                scalar = self.failure_score
            # Per-rollout heartbeat: the type-mismatch warning used to be the
            # only per-rollout signal in job_logs; this keeps rollout execution
            # observable now that the warning is silenced.
            logger.info(
                "react rollout %d/%d turn=%s score=%.3f", idx + 1, total, example.turn_id, scalar
            )
            outputs.append(pred)
            scores.append(scalar)
            objective_scores.append(objectives)
            trajectories.append(
                {
                    "example": example,
                    "rollout": rollout,
                    "objective_scores": objectives,
                    "grounding_mean_logprob": mean_ll,
                    "observation_count": obs_count,
                }
                if capture_traces
                else None
            )
        return EvaluationBatch(
            outputs=outputs,
            scores=scores,
            trajectories=trajectories if capture_traces else None,
            objective_scores=objective_scores,
        )

    def _run_rollout(
        self, program: dspy.ReActV2, example: EvaluationExample
    ) -> tuple[Prediction | None, list[dict[str, Any]], Any]:
        """Run one candidate rollout, capturing served messages iff grounding is on.

        Task-only runs skip the ``lm.history`` capture so their behavior is
        identical to a pure replay-reward evaluation.
        """
        if self._grounding_weight > 0:
            return _run_candidate_and_capture(
                program=program, example=example, lm=self._student_lm
            )
        pred = _run_candidate(program=program, example=example, lm=self._student_lm)
        return pred, [], None

    def _score(
        self,
        example: EvaluationExample,
        rollout: ReplayRollout,
        messages: list[dict[str, Any]],
        tools: Any,
    ) -> tuple[float, dict[str, float], float | None, int]:
        """Combine the active reward terms.

        Returns:
            ``(scalar, objective_scores, grounding_mean_logprob, observation_count)``
            — ``grounding_mean_logprob`` is ``None`` and the count ``0`` when
            grounding is disabled or no observation was located.
        """
        objectives: dict[str, float] = {}
        scalar = 0.0
        if self._include_task_reward:
            vec = self._vector_fn(example, rollout)
            objectives.update(vec)
            scalar += scalar_with_hard_caps(vec, self._reward_spec)
        mean_log_likelihood: float | None = None
        observation_count = 0
        if self._grounding_weight > 0:
            observation_texts = observation_texts_from_messages(messages)
            observation_count = len(observation_texts)
            if observation_texts:
                mean_log_likelihood = grounding_reward(
                    messages,
                    observation_texts,
                    template=self._template,
                    scorer=self._scorer,
                    tools=tools,
                )
            grounding_term = (
                as_unit_interval(mean_log_likelihood)
                if mean_log_likelihood is not None
                else 0.0
            )
            objectives[_GROUNDING_DIM] = grounding_term
            scalar += self._grounding_weight * grounding_term
        return scalar, objectives, mean_log_likelihood, observation_count

    def make_reflective_dataset(  # type: ignore[override]
        self,
        candidate: dict[str, str],
        eval_batch: EvaluationBatch,
        components_to_update: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Emit per-example feedback for the reflective proposer.

        Each example becomes ``{"Inputs", "Generated Outputs", "Feedback"}``
        — the shape the canonical ``ToolProposer`` and
        ``InstructionProposalSignature`` consume. The feedback mixes task-dim
        and grounding signals according to which reward terms are active.
        """
        if not eval_batch.trajectories:
            return {component: [] for component in components_to_update}
        result: dict[str, list[dict[str, Any]]] = {
            component: [] for component in components_to_update
        }
        for trajectory in eval_batch.trajectories:
            if trajectory is None:
                continue
            example: EvaluationExample = trajectory["example"]
            rollout: ReplayRollout = trajectory["rollout"]
            entry = {
                "Inputs": _reflective_inputs(example),
                "Generated Outputs": _summarize_rollout(rollout),
                "Feedback": self._feedback(
                    example=example,
                    rollout=rollout,
                    objectives=trajectory["objective_scores"],
                    mean_log_likelihood=trajectory["grounding_mean_logprob"],
                    observation_count=trajectory["observation_count"],
                ),
            }
            for component in components_to_update:
                result[component].append(entry)
        return result

    def _feedback(
        self,
        *,
        example: EvaluationExample,
        rollout: ReplayRollout,
        objectives: dict[str, float],
        mean_log_likelihood: float | None,
        observation_count: int,
    ) -> str:
        """Assemble reflective feedback from whichever reward terms are active."""
        parts: list[str] = []
        if self._include_task_reward:
            task_dims = {k: v for k, v in objectives.items() if k != _GROUNDING_DIM}
            parts.append(
                feedback_from_low_dims(
                    task_dims, rollout, example, max_dims=self._feedback_dim_count
                )
            )
        if self._grounding_weight > 0:
            parts.append(
                _grounding_feedback(
                    mean_log_likelihood=mean_log_likelihood,
                    observation_count=observation_count,
                    rollout=rollout,
                    example=example,
                )
            )
        return "\n\n".join(parts)


def _candidate_blob_key(candidate: dict[str, str]) -> str:
    """Return the composite-blob key present on ``candidate``.

    Prefers the neutral ``tool_module:react`` key but falls back to the legacy
    ``tool_module:generalist`` key so candidates seeded before the rename still
    parse. Defaults to the neutral key when neither is present (an empty blob).
    """
    if TOOL_MODULE_KEY in candidate:
        return TOOL_MODULE_KEY
    if _LEGACY_MODULE_KEY in candidate:
        return _LEGACY_MODULE_KEY
    return TOOL_MODULE_KEY


def _parse_candidate_blob(candidate: dict[str, str]) -> dict[str, Any]:
    """Parse the composite ``tool_module:*`` JSON blob, swallowing errors.

    The reflective proposer can occasionally return a malformed blob — when
    that happens we want the candidate to fall back to the seed's text
    silently and have the rollout failure-score, not raise out of
    ``evaluate`` before the per-example try block catches it.
    """
    key = _candidate_blob_key(candidate)
    raw = candidate.get(key)
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "Candidate %s blob is not valid JSON — falling back to seed overrides",
            key,
        )
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _candidate_instructions(candidate: dict[str, str]) -> dict[str, str]:
    """Pull predictor instructions out of the candidate dict.

    The candidate is expected to contain a single ``tool_module:react``
    JSON blob (or the legacy ``:generalist`` key) whose top-level string keys
    are predictor instructions. Non-prefix keys are accepted as overrides.
    """
    parsed = _parse_candidate_blob(candidate)
    instructions: dict[str, str] = {
        key: value for key, value in parsed.items() if isinstance(value, str)
    }
    for key, value in candidate.items():
        if key.startswith(TOOL_MODULE_PREFIX) or not isinstance(value, str):
            continue
        instructions[key] = value
    return instructions


def _candidate_tool_descriptions(candidate: dict[str, str]) -> dict[str, str]:
    """Pull tool descriptions (no arg-level edits) out of the candidate."""
    parsed = _parse_candidate_blob(candidate)
    tools = parsed.get("tools") or {}
    descriptions: dict[str, str] = {}
    if not isinstance(tools, dict):
        return descriptions
    for name, payload in tools.items():
        if not isinstance(payload, dict):
            continue
        desc = payload.get("desc")
        if isinstance(desc, str) and desc:
            descriptions[name] = desc
    return descriptions


def _candidate_tool_names(candidate: dict[str, str]) -> dict[str, str]:
    """Extract the GEPA-proposed display name per canonical tool.

    Each ``tools[<canonical>]`` payload may carry a ``name`` GEPA mutated to a
    clearer label the agent sees. Entries whose proposed name is missing/blank
    fall back to the canonical key, so the result is always identity when no
    rename was proposed (the seed sets ``name == canonical``).

    Returns:
        ``{canonical_name: proposed_name}`` — never empty unless the blob has no
        tools; identity for any tool whose proposed name is absent or blank.
    """
    parsed = _parse_candidate_blob(candidate)
    tools = parsed.get("tools") or {}
    names: dict[str, str] = {}
    if not isinstance(tools, dict):
        return names
    for canonical, payload in tools.items():
        if not isinstance(payload, dict):
            names[canonical] = canonical
            continue
        proposed = payload.get("name")
        if isinstance(proposed, str) and proposed.strip():
            names[canonical] = proposed.strip()
        else:
            names[canonical] = canonical
    return names


def _candidate_tool_arg_descriptions(
    candidate: dict[str, str],
) -> dict[str, dict[str, str]]:
    """Extract arg-level description overrides keyed by tool then arg."""
    parsed = _parse_candidate_blob(candidate)
    tools = parsed.get("tools") or {}
    out: dict[str, dict[str, str]] = {}
    if not isinstance(tools, dict):
        return out
    for name, payload in tools.items():
        if not isinstance(payload, dict):
            continue
        args = payload.get("args") or {}
        if not isinstance(args, dict):
            continue
        arg_descs: dict[str, str] = {}
        for arg_name, arg_schema in args.items():
            if not isinstance(arg_schema, dict):
                continue
            desc = arg_schema.get("description")
            if isinstance(desc, str) and desc:
                arg_descs[arg_name] = desc
        if arg_descs:
            out[name] = arg_descs
    return out


def _extract_react_instructions(program: dspy.Module) -> str:
    """Return the inner ``react`` predictor's instruction text."""
    for name, predictor in program.named_predictors():
        if name == REACT_PREDICTOR_NAME:
            return getattr(predictor.signature, "instructions", "") or ""
    return getattr(program.signature, "instructions", "") or ""  # type: ignore[attr-defined]


def _collect_tools(program: dspy.Module) -> dict[str, dspy.Tool]:
    """Return the program's ``Tool`` map (excluding the synthetic submit)."""
    candidate = getattr(program, "tools", None)
    if not isinstance(candidate, dict):
        return {}
    return {
        name: tool
        for name, tool in candidate.items()
        if isinstance(tool, dspy.Tool)
    }


def _serialize_tool_args(args: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Round-trip the tool arg schema through JSON-safe primitives."""
    if not isinstance(args, dict):
        return {}
    payload: dict[str, dict[str, Any]] = {}
    for arg_name, schema in args.items():
        if isinstance(schema, dict):
            payload[arg_name] = dict(schema)
        else:
            payload[arg_name] = {"description": str(schema)}
    return payload


class TrainingGroundDspyAdapterInstance(TrainingGroundDspyAdapter):
    """Public alias kept for readability in optimize.py."""


def _grounding_feedback(
    *,
    mean_log_likelihood: float | None,
    observation_count: int,
    rollout: ReplayRollout,
    example: EvaluationExample,
) -> str:
    """Render grounding feedback for GEPA's reflective LM.

    ECHO's signal is a mean log-likelihood (closer to 0 = the model found the
    recorded observations less surprising in the candidate's context). The
    feedback names the score and the tools whose results were scored so the
    proposer can sharpen the instructions / tool descriptions that prime them.
    """
    if mean_log_likelihood is None:
        if not example.replay_steps:
            return (
                f"Turn {example.turn_id}: no recorded tool results, so there is no "
                "observation-grounding signal for this turn."
            )
        return (
            f"Turn {example.turn_id}: the candidate elicited none of the "
            f"{len(example.replay_steps)} recorded observations (it diverged before "
            "any matched), so grounding could not be scored. Match the recorded tool "
            "calls so the model is exposed to the environment responses."
        )
    hit_tools = sorted(
        {event.candidate_tool for event in rollout.events if event.outcome == "hit"}
    )
    lines = [
        f"Turn {example.turn_id}: grounding mean log-likelihood = "
        f"{mean_log_likelihood:.3f} over {observation_count} observation(s) "
        "(closer to 0 is better — the model assigns higher probability to the "
        "recorded tool results when your prompt + tool descriptions prepare it "
        "for them).",
        f"Observations scored came from: {', '.join(hit_tools) or 'n/a'}.",
        "Sharpen the instructions and tool descriptions so the model anticipates "
        "the shape and content of these results.",
    ]
    if rollout.terminated_early and rollout.terminated_reason:
        lines.append(
            f"Rollout terminated early via {rollout.terminated_reason!r}; only the "
            "observations before that point were scored."
        )
    return "\n".join(lines)


def _instantiate_program_shell(
    seed_program: dspy.Module,
    *,
    mock: TraceConditionedMCPMock,
    max_iters: int,
    proposed_names: dict[str, str] | None = None,
) -> dspy.ReActV2:
    """Construct a fresh ``ReActV2`` whose tool layer routes through the mock.

    Uses the seed signature so the input/output field shape stays identical.
    The seed program's live tool map is threaded into ``mock.tool_layer``
    so each proxy carries the corresponding live tool's per-arg schema —
    that is what makes the candidate's arg-description overrides
    actually visible to the LM during the rollout.

    Tool descriptions are placeholders here — the caller overlays them
    with the candidate's payload before calling the program. ``proposed_names``
    (canonical->proposed) renames the agent-facing roster; the mock
    canonicalizes the names back so matching/reward stay canonical.
    """
    signature = getattr(seed_program, "signature", None)
    if signature is None:
        raise ValueError("Seed program missing signature")
    live_tools = _collect_tools(seed_program)
    return dspy.ReActV2(
        signature,
        tools=mock.tool_layer(live_tools=live_tools, proposed_names=proposed_names),
        max_iters=max_iters,
    )


def _apply_candidate_to_program(
    program: dspy.ReActV2,
    *,
    instructions: dict[str, str],
    tool_descriptions: dict[str, str],
    tool_arg_descriptions: dict[str, dict[str, str]] | None = None,
    proposed_names: dict[str, str] | None = None,
) -> None:
    """Overlay candidate text onto a fresh program in place.

    The candidate's ``desc`` / ``args`` overrides are keyed by canonical tool
    name, but ``program.tools`` is keyed by the agent-facing (possibly renamed)
    display name. ``proposed_names`` (canonical->proposed) bridges the two so a
    renamed tool still receives its description/arg overlays; absent it the
    canonical name is used directly (identity).
    """
    display_of = proposed_names or {}
    for name, predictor in program.named_predictors():
        if name in instructions:
            predictor.signature = predictor.signature.with_instructions(
                instructions[name]
            )
    for tool_name, desc in tool_descriptions.items():
        tool = program.tools.get(display_of.get(tool_name, tool_name))
        if tool is not None:
            tool.desc = desc
    if tool_arg_descriptions:
        for tool_name, arg_map in tool_arg_descriptions.items():
            tool = program.tools.get(display_of.get(tool_name, tool_name))
            if tool is None:
                continue
            for arg_name, description in arg_map.items():
                if isinstance(tool.args, dict) and arg_name in tool.args:
                    schema = tool.args[arg_name]
                    if isinstance(schema, dict):
                        schema["description"] = description


def _record_submit_from_prediction(
    *,
    mock: TraceConditionedMCPMock,
    program: dspy.ReActV2,
    pred: Prediction | None,
) -> None:
    """Mirror ReActV2's submit terminal into the mock's rollout state.

    ReActV2 owns the synthetic ``submit`` tool. When the LM cleanly
    invokes it the engine emits ``termination_reason == "submit"`` and
    the signature's output fields appear as attributes on the
    prediction, so we reconstruct ``submit_payload`` from them. When
    ReActV2 instead falls through to its iter-exhaustion fallback the
    engine emits ``"forced_submit"`` — that path is recorded via
    :meth:`TraceConditionedMCPMock.record_forced_submit` so the reward
    signal can distinguish a clean submit from an exhausted one.
    """
    if pred is None:
        return
    termination = getattr(pred, "termination_reason", None)
    if termination == "submit":
        output_fields = getattr(program.signature, "output_fields", None) or {}
        payload = {name: getattr(pred, name, None) for name in output_fields}
        mock.record_submit(payload)
    elif termination == "forced_submit":
        mock.record_forced_submit()


def _run_candidate(
    *,
    program: dspy.ReActV2,
    example: EvaluationExample,
    lm: dspy.LM,
) -> Prediction | None:
    """Execute one candidate rollout, swallowing ``ReplayTerminated``.

    The mock raises ``ReplayTerminated`` from inside a tool function so
    ReActV2's per-tool ``except Exception`` already catches it and records a
    ``Tool error`` observation — the rollout's prefix is intact. We only
    catch it here as a defensive belt for direct callers that bypass the
    ReAct loop (the dry-run estimator does).
    """
    if example.signature_inputs is not None:
        inputs = dict(example.signature_inputs)
    else:
        inputs = {
            "user_message": example.user_message,
            "wizard_state": json.dumps(example.wizard_state_before, ensure_ascii=False),
            "chat_history": json.dumps(list(example.chat_history), ensure_ascii=False),
        }
    try:
        # wizard_state/chat_history reach the program as JSON strings (the
        # branch above and run_react._coerce_signature_inputs both stringify
        # them) to mirror the live agent's wire format, even when the authored
        # signature types those fields as dict/list. DSPy's warn_on_type_mismatch
        # would then log a benign warning per predict; the substitution is
        # deliberate and harness-controlled here, so the warning carries no signal.
        with dspy.context(lm=lm, warn_on_type_mismatch=False):
            return program(**inputs)
    except ReplayTerminated:
        return None
    except Exception as exc:
        # WARNING (not DEBUG): the subprocess log forwarder floors at INFO, so a
        # DEBUG line never reaches job_logs — a crashed rollout would silently
        # failure-score and be indistinguishable from a genuine low reward.
        logger.warning("Candidate rollout raised %s for turn %s", exc, example.turn_id)
        return None


_TOOL_RESULTS_MARKER = "[[ ## tool_call_results ## ]]"
"""DSPy ChatAdapter field header that wraps each replayed observation.

With native function calling off (the production default — ``predict.py``
resolves ``settings.adapter or ChatAdapter()`` and nothing configures one),
``format_conversation_history`` renders every tool result into a ``user``
message whose content opens with this marker. The text after it is the
environment observation ECHO scores."""


def observation_texts_from_messages(messages: list[dict[str, Any]]) -> list[str]:
    """Extract the recorded observations from a captured ReActV2 message list.

    The candidate's served messages carry each replayed tool result in a
    ``user`` message prefixed by ``_TOOL_RESULTS_MARKER``. Returning the text
    after the marker (verbatim, in trajectory order) gives
    :func:`grounding.grounding_reward` spans that are guaranteed to appear in
    the chat-template-rendered prompt — no reconstruction, so the grounding
    score stays 1:1 with serving.

    Args:
        messages: ``lm.history[-1]["messages"]`` from a candidate rollout.

    Returns:
        Observation strings in trajectory order; empty when the turn elicited
        no tool results (a divergence before any recorded step matched).
    """
    texts: list[str] = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        marker = content.find(_TOOL_RESULTS_MARKER)
        if marker < 0:
            continue
        observation = content[marker + len(_TOOL_RESULTS_MARKER) :].strip("\n")
        if observation:
            texts.append(observation)
    return texts


def _run_candidate_and_capture(
    *,
    program: dspy.ReActV2,
    example: EvaluationExample,
    lm: dspy.LM,
) -> tuple[Prediction | None, list[dict[str, Any]], Any]:
    """Run one candidate rollout and capture its final served messages.

    The last LM call holds the full trajectory — every prior thought, tool
    call, and replayed observation — so its ``messages`` carry every
    observation ECHO grounds on. We identify "our" final call by the entry
    ``uuid`` rather than an absolute ``lm.history`` index, which stays correct
    even when a long run evicts old history entries from the front.

    Returns:
        ``(prediction, final_call_messages, tools_kwarg)``. Messages is empty
        and tools is ``None`` when the rollout made no LM call (e.g. it
        diverged or raised before the first turn).
    """
    last_uuid_before = lm.history[-1].get("uuid") if lm.history else None
    pred = _run_candidate(program=program, example=example, lm=lm)
    if not lm.history:
        return pred, [], None
    last = lm.history[-1]
    if last.get("uuid") == last_uuid_before:
        return pred, [], None
    messages = last.get("messages") or []
    tools = (last.get("kwargs") or {}).get("tools")
    return pred, messages, tools


def _reflective_inputs(example: EvaluationExample) -> dict[str, Any]:
    """Build the ``Inputs`` block GEPA's reflective proposer sees per example.

    When ``example.signature_inputs`` is set (the /run path) the block is
    based on the signature inputs so the proposer sees the same fields the
    candidate was fed, still augmented with the replay context
    (``allowed_tools`` + ``recorded_tool_calls``). When ``None`` the
    generalist three-key block is returned unchanged.
    """
    base = (
        dict(example.signature_inputs)
        if example.signature_inputs is not None
        else {
            "user_message": example.user_message,
            "wizard_state_before": example.wizard_state_before,
        }
    )
    base["allowed_tools"] = sorted(example.allowed_tools)
    base["recorded_tool_calls"] = [
        {"tool": step.tool_name, "arguments": step.arguments}
        for step in example.replay_steps
    ]
    return base


def _summarize_rollout(rollout: ReplayRollout) -> dict[str, Any]:
    """Compact view of what the candidate actually produced.

    Kept JSON-ish so the reflective proposer sees the tool calls as data,
    not as a model dump.
    """
    return {
        "tool_calls": [
            {
                "tool": event.candidate_tool,
                "arguments": event.candidate_arguments,
                "outcome": event.outcome,
                "evidence": event.evidence,
            }
            for event in rollout.events
        ],
        "submit_called": rollout.submit_called,
        "submit_payload": rollout.submit_payload,
        "forced_submit": rollout.forced_submit,
        "terminated_early": rollout.terminated_early,
        "terminated_reason": rollout.terminated_reason,
    }


def _unused_metric_fn(*_args: Any, **_kwargs: Any) -> float:
    """Placeholder metric required by the parent ``DspyAdapter.__init__``.

    Our ``evaluate`` override never calls it; provided so the parent's
    constructor accepts a non-``None`` callable.
    """
    return 0.0


# Bind the instance-method-side helpers onto the adapter so we don't carry a
# global cache between optimize runs. The methods are pure wrappers — keeping
# them as module-level functions is intentional (they're called once per
# example so the dict-of-tools lookup is cheap).
def _instantiate_candidate(
    self: TrainingGroundDspyAdapter,
    *,
    mock: TraceConditionedMCPMock,
    instructions: dict[str, str],
    tool_descriptions: dict[str, str],
    tool_arg_descriptions: dict[str, dict[str, str]] | None,
    proposed_names: dict[str, str] | None = None,
) -> dspy.ReActV2:
    """Build a fresh candidate program for one example."""
    program = _instantiate_program_shell(
        self._seed_program,
        mock=mock,
        max_iters=self._max_iters,
        proposed_names=proposed_names,
    )
    _apply_candidate_to_program(
        program,
        instructions=instructions,
        tool_descriptions=tool_descriptions,
        tool_arg_descriptions=tool_arg_descriptions,
        proposed_names=proposed_names,
    )
    return program


TrainingGroundDspyAdapter._instantiate_candidate = _instantiate_candidate  # type: ignore[attr-defined]


__all__ = [
    "GENERALIST_MODULE_KEY",
    "REACT_PREDICTOR_NAME",
    "TOOL_MODULE_KEY",
    "TrainingGroundDspyAdapter",
    "observation_texts_from_messages",
    "seed_candidate_from_program",
]

# ``_candidate_tool_names`` is imported by run_react/optimize (the bundle +
# overlay persist paths) alongside the other ``_candidate_*`` parsers, which are
# likewise underscore-prefixed and intentionally absent from ``__all__``.


# Reference imports kept so a downstream typing pass can resolve the symbols
# without re-importing.
_ = Example
_ = Callable
