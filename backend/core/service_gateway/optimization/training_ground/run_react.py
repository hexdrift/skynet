"""Shared core for the react ``POST /run`` path (Phase B).

Bridges a generic :class:`dspy.Signature` + replay-mapped dataset onto the
training-ground GEPA harness. Three pure-ish building blocks, none of which
touch a live model on their own:

- :func:`build_replay_examples` converts ``dspy.Example`` rows into the
  harness's :class:`EvaluationExample` records, populating ``signature_inputs``
  so the adapter drives the resolved signature instead of the generalist
  three-key dict.
- :func:`resolve_react_tools` materialises the tool roster (live MCP listing or
  a dataset-carried snapshot) plus its schema-hash map.
- :func:`run_react_optimization` wires a seed ``ReActV2`` through
  ``gepa.optimize`` with the parameterised ECHO adapter and returns the
  servable program state + acceptance statistics.

Mirrors the generalist CLI in ``optimize.py`` (it reuses that module's tool
listing, candidate evaluation, and program-state helpers) so the two paths
share one rollout/scoring contract. See ``training_ground_SPEC.md`` §6/§7.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import dspy
import gepa

from core.config import Settings
from core.constants import DETAIL_BASELINE, PROGRESS_BASELINE

from ..trajectory import react_minibatch_feedback, react_valset_outputs
from .gepa_adapter import (
    TrainingGroundDspyAdapter,
    VectorRewardFn,
    _candidate_tool_arg_descriptions,
    _candidate_tool_descriptions,
    _candidate_tool_names,
    seed_candidate_from_program,
)
from .grounding import ChatTemplate, PromptScorer
from .metrics import RewardSpec
from .optimize import (
    _AUTO_BUDGETS,
    _best_candidate,
    _evaluate_candidate_on_examples,
    _list_live_tools,
    _program_state_from,
    _resolve_promotion,
)
from .persistence import paired_bootstrap_ci
from .registry import hash_tool_schema
from .replay import (
    SUBMIT_TOOL_NAME,
    adapt_agent_tool_calls_v1_to_replay,
)
from .types import EvaluationExample, PairedBootstrapResult, ReplayStep

logger = logging.getLogger(__name__)


class _JobLogGepaLogger:
    """Forward GEPA's free-text progress lines into the job log sink.

    GEPA reports per-iteration status (e.g. ``"Iteration N: Valset score for new
    program: X"``) through a ``gepa.logging.LoggerProtocol`` object. Its default
    ``StdOutLogger`` prints to stdout, which the worker's ``JobLogHandler`` never
    captures, so the score chart (``extractScoresFromLogs``) stays empty for
    react runs. Forwarding to a module logger lets those records propagate up to
    the ``core.service_gateway.optimization`` handler instead.
    """

    def __init__(self, sink: logging.Logger):
        """Store the logger the GEPA lines are forwarded to.

        Args:
            sink: Logger whose records reach the job's ``JobLogHandler``.
        """
        self._sink = sink

    def log(self, message: str) -> None:
        """Forward one GEPA progress line to the job log sink.

        Args:
            message: The free-text progress line emitted by GEPA's engine.
        """
        self._sink.info(message)


DEFAULT_MAX_ITERS = 8
"""ReActV2 loop budget for the react /run seed program. Mirrors the generalist
CLI default so a /run-produced bundle behaves like a CLI-produced one."""


def _row_value(example: dspy.Example, column: str) -> Any:
    """Read ``column`` off a ``dspy.Example`` as a plain attribute.

    ``rows_to_examples(..., extra_columns=...)`` attaches the replay role
    columns as unmarked attributes (so they stay out of ``example.inputs()``).
    Returns ``None`` when the column is absent on this row.

    Args:
        example: The DSPy example carrying the replay role columns.
        column: Source-column name to read.

    Returns:
        The stored value, or ``None`` when the example has no such attribute.
    """
    try:
        return getattr(example, column)
    except AttributeError:
        return None


def _as_mapping(value: Any) -> dict[str, Any]:
    """Coerce a cell value into a plain dict, tolerating JSON-string cells.

    Snapshot/state columns arrive either as already-parsed mappings or as
    JSON strings (CSV ingestion keeps everything as text). Anything that is
    neither parses to an empty dict so a malformed cell degrades to "no
    state" rather than raising mid-build.

    Args:
        value: Raw cell value (mapping, JSON string, or other).

    Returns:
        A dict — empty when the value is missing or not object-shaped.
    """
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _as_sequence(value: Any) -> list[Any]:
    """Coerce a cell value into a list, tolerating JSON-string cells.

    Args:
        value: Raw cell value (sequence, JSON string, or other).

    Returns:
        A list — empty when the value is missing or not array-shaped.
    """
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return list(parsed) if isinstance(parsed, (list, tuple)) else []
    return []


def _allowed_tools_from(value: Any) -> frozenset[str]:
    """Build the allowed-tool roster from a recorded column, dropping submit.

    Accepts either a list of tool names or a JSON-string of one. ``submit`` is
    excluded — ReActV2 owns that synthetic terminal, never the recorded roster.

    Args:
        value: Raw cell value for the ``allowed_tools`` replay role.

    Returns:
        A frozenset of allowed tool names (never including ``submit``).
    """
    names = {str(name).strip() for name in _as_sequence(value) if str(name).strip()}
    names.discard(SUBMIT_TOOL_NAME)
    return frozenset(names)


def _schema_hashes_from(value: Any) -> dict[str, str]:
    """Build the ``{tool_name: hash}`` snapshot from a recorded column.

    Args:
        value: Raw cell value for the ``tool_schema_hashes`` replay role.

    Returns:
        A ``{str: str}`` map; empty when the cell is missing or malformed.
    """
    mapping = _as_mapping(value)
    return {str(name): str(digest) for name, digest in mapping.items()}


def _chat_history_from(value: Any) -> tuple[dict[str, Any], ...]:
    """Build the chat-history tuple from a recorded column.

    Each entry is kept as a plain dict (``{role, content}`` and friends);
    non-mapping entries are skipped so a malformed row degrades gracefully.

    Args:
        value: Raw cell value for the ``chat_history`` replay role.

    Returns:
        A tuple of message dicts in recorded order.
    """
    return tuple(
        dict(entry) for entry in _as_sequence(value) if isinstance(entry, Mapping)
    )


def _coerce_signature_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Render structured signature inputs as JSON strings.

    Recorded rows carry structured inputs natively (e.g. ``wizard_state`` as a
    dict, ``chat_history`` as a list), but ReAct signature fields are typically
    ``str``. Encode every non-string value as JSON so the rollout receives the
    same string form the live agent produced (matching the CLI's ``json.dumps``
    on ``wizard_state``/``chat_history``) instead of dspy's Python-repr
    fallback coercion.

    Args:
        inputs: The signature input field values for one turn.

    Returns:
        The mapping with non-string values JSON-encoded.
    """
    return {
        key: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        for key, value in dict(inputs).items()
    }


def build_replay_examples(
    dspy_examples: Sequence[dspy.Example],
    replay_mapping: Any,
) -> list[EvaluationExample]:
    """Convert replay-mapped ``dspy.Example`` rows into ``EvaluationExample`` s.

    For each example the replay-role columns named by ``replay_mapping`` are
    read off the example's attributes (carried there by
    ``rows_to_examples(..., extra_columns=...)``) and assembled into the
    harness's per-turn record. The recorded ``steps`` column is converted via
    :func:`adapt_agent_tool_calls_v1_to_replay` into ordered ``ReplayStep`` s,
    and ``signature_inputs`` is set to ``dict(example.inputs())`` so the
    adapter feeds the resolved signature verbatim. ``user_message`` is left
    empty because ``signature_inputs`` supersedes it on this path.

    Args:
        dspy_examples: Examples produced by ``rows_to_examples`` with the
            replay role columns attached as extras.
        replay_mapping: A ``ReplayMapping``-shaped object naming the dataset
            columns for ``steps``/``allowed_tools``/``tool_schema_hashes`` and
            the optional ``state_before``/``state_after``/``chat_history``.

    Returns:
        One :class:`EvaluationExample` per input example, ``signature_inputs``
        populated, in input order.
    """
    examples: list[EvaluationExample] = []
    for idx, example in enumerate(dspy_examples):
        turn_id = str(_row_value(example, "turn_id") or idx)
        steps_raw = _as_sequence(_row_value(example, replay_mapping.steps))
        # Drop errored recorded calls: an error result is bad ground truth to
        # replay back to the candidate, so only keep cleanly-resolved steps.
        replay_steps: tuple[ReplayStep, ...] = tuple(
            step
            for step in adapt_agent_tool_calls_v1_to_replay(steps_raw, turn_id=turn_id)
            if step.status == "done"
        )
        allowed = _allowed_tools_from(_row_value(example, replay_mapping.allowed_tools))
        schema_hashes = _schema_hashes_from(
            _row_value(example, replay_mapping.tool_schema_hashes)
        )
        state_before = (
            _as_mapping(_row_value(example, replay_mapping.state_before))
            if replay_mapping.state_before
            else {}
        )
        state_after = (
            _as_mapping(_row_value(example, replay_mapping.state_after))
            if replay_mapping.state_after
            else {}
        )
        chat_history = (
            _chat_history_from(_row_value(example, replay_mapping.chat_history))
            if replay_mapping.chat_history
            else ()
        )
        examples.append(
            EvaluationExample(
                turn_id=turn_id,
                user_message="",
                wizard_state_before=state_before,
                wizard_state_after=state_after,
                allowed_tools=allowed,
                tool_schema_hashes=schema_hashes,
                replay_steps=replay_steps,
                chat_history=chat_history,
                signature_inputs=_coerce_signature_inputs(example.inputs()),
            )
        )
    return examples


def _dataset_snapshot_tools(dataset: Sequence[Mapping[str, Any]] | None) -> list[dspy.Tool]:
    """Rebuild a ``dspy.Tool`` roster from a dataset-carried snapshot sidecar.

    A ``dataset_snapshot`` tool source carries the tool roster on the dataset
    rather than from a live MCP. The reserved sidecar lives under a
    ``__tool_snapshot__`` key on any row (the first row that has it wins) and
    is a list of specs::

        {"name": str, "description": str, "args": {<arg>: {<schema>}}}

    Each spec becomes a no-op ``dspy.Tool`` — the roster is only used for its
    ``name``/``desc``/``args`` (seed instructions, schema-hash snapshot, and
    arg-description overlays); rollout-time calls route through the replay mock,
    never these callables.

    Args:
        dataset: Raw dataset rows; scanned for the snapshot sidecar.

    Returns:
        One ``dspy.Tool`` per snapshot spec (``submit`` excluded), in spec
        order. Empty when no sidecar is present.
    """
    specs = _find_snapshot_specs(dataset)
    tools: list[dspy.Tool] = []
    for spec in specs:
        if not isinstance(spec, Mapping):
            continue
        name = str(spec.get("name") or "").strip()
        if not name or name == SUBMIT_TOOL_NAME:
            continue
        desc = str(spec.get("description") or spec.get("desc") or "")
        args = spec.get("args") if isinstance(spec.get("args"), Mapping) else {}
        tools.append(_snapshot_tool(name=name, desc=desc, args=dict(args)))
    return tools


def _find_snapshot_specs(
    dataset: Sequence[Mapping[str, Any]] | None,
) -> list[Any]:
    """Return the tool-snapshot spec list from the dataset sidecar.

    Args:
        dataset: Raw dataset rows.

    Returns:
        The first row's ``__tool_snapshot__`` list, or an empty list when no
        row carries one.
    """
    if not dataset:
        return []
    for row in dataset:
        if not isinstance(row, Mapping):
            continue
        sidecar = row.get("__tool_snapshot__")
        if isinstance(sidecar, str):
            sidecar = _as_sequence(sidecar)
        if isinstance(sidecar, (list, tuple)) and sidecar:
            return list(sidecar)
    return []


def _snapshot_tool(*, name: str, desc: str, args: dict[str, Any]) -> dspy.Tool:
    """Construct a no-op ``dspy.Tool`` carrying a snapshot spec's schema.

    The callable is never invoked (rollouts go through the replay mock), so it
    only has to exist for ``dspy.Tool`` to introspect ``name``/``desc``/``args``.

    Args:
        name: Tool name.
        desc: Tool description.
        args: Per-arg JSON schema map.

    Returns:
        A ``dspy.Tool`` whose ``args`` mirror the snapshot spec.
    """

    def _noop(**_kwargs: Any) -> None:
        """Placeholder body — snapshot tools are never called at rollout time."""

    _noop.__name__ = name
    _noop.__doc__ = desc
    return dspy.Tool(_noop, name=name, desc=desc, args=args or None)


def resolve_react_tools(
    tool_source: Any,
    signature_cls: type,
    settings: Settings,
    *,
    dataset: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[list[dspy.Tool], dict[str, str]]:
    """Materialise the react tool roster + its schema-hash snapshot.

    Two sources, mirroring ``ToolSource.kind``:

    - ``live_mcp`` lists the live MCP roster via :func:`_list_live_tools`
      (the same helper the generalist CLI uses), optionally filtering and
      reordering by ``tool_source.tool_filter``.
    - ``dataset_snapshot`` rebuilds the roster from the dataset's reserved
      ``__tool_snapshot__`` sidecar (run path) or the source's own persisted
      ``tool_snapshot`` specs (serve path) via :func:`_dataset_snapshot_tools`.

    The schema-hash map is computed with :func:`hash_tool_schema` over whatever
    roster was resolved, so it stays 1:1 with the tools the seed program sees.

    Args:
        tool_source: A ``ToolSource``-shaped object or a persisted mapping
            (``kind`` plus optional ``mcp_url``/``mcp_auth_header``/
            ``tool_filter``/``tool_snapshot``); read field-tolerantly via
            :func:`_ts` so the run and serve paths share one resolver.
        signature_cls: The resolved signature (unused today; accepted so the
            call site stays stable as the snapshot path grows).
        settings: Runtime settings — supplies the default MCP URL.
        dataset: Raw dataset rows, required for the ``dataset_snapshot`` kind.

    Returns:
        ``(tools, schema_hashes)`` — the resolved roster and its
        ``{tool_name: sha256_hex}`` snapshot.

    Raises:
        ValueError: When ``tool_source.kind`` is unrecognised, or when a
            snapshot source carries no tools.
    """
    _ = signature_cls
    kind = _ts(tool_source, "kind")
    if kind == "live_mcp":
        mcp_url = _ts(tool_source, "mcp_url") or settings.generalist_agent_mcp_url
        tools = asyncio.run(
            _list_live_tools(mcp_url, _ts(tool_source, "mcp_auth_header"))
        )
        tools = _apply_tool_filter(tools, _ts(tool_source, "tool_filter"))
    elif kind == "dataset_snapshot":
        tools = _dataset_snapshot_tools(_snapshot_source(tool_source, dataset))
        tools = _apply_tool_filter(tools, _ts(tool_source, "tool_filter"))
        if not tools:
            raise ValueError(
                "dataset_snapshot tool source carried no tools — expected a "
                "'__tool_snapshot__' sidecar with at least one spec."
            )
    else:
        raise ValueError(f"Unknown tool_source.kind {kind!r}.")
    schema_hashes = {tool.name: hash_tool_schema(tool) for tool in tools}
    return tools, schema_hashes


def _ts(tool_source: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` off a tool source that may be an object or a mapping.

    The run path passes a ``ToolSource`` model (attribute access); the serve
    path re-sources from a persisted dict (mapping access). Reads through
    both so the same resolver serves either shape.

    Args:
        tool_source: A ``ToolSource``-shaped object or a plain mapping.
        key: Field name to read.
        default: Returned when the key is absent on either shape.

    Returns:
        The stored value, or ``default`` when absent.
    """
    if isinstance(tool_source, Mapping):
        return tool_source.get(key, default)
    return getattr(tool_source, key, default)


def _snapshot_source(
    tool_source: Any, dataset: Sequence[Mapping[str, Any]] | None
) -> Sequence[Mapping[str, Any]] | None:
    """Pick the snapshot-spec carrier for a ``dataset_snapshot`` source.

    Serve persists the snapshot specs on the source itself under
    ``tool_snapshot``; the run path carries them on the dataset's
    ``__tool_snapshot__`` sidecar. When the source carries them, wrap the
    specs in a synthetic single-row sidecar so :func:`_dataset_snapshot_tools`
    can read them without the original dataset.

    Args:
        tool_source: The ``dataset_snapshot`` tool source (object or mapping).
        dataset: Raw dataset rows for the run path.

    Returns:
        A row sequence carrying the snapshot sidecar, or ``dataset`` when the
        source has no persisted ``tool_snapshot``.
    """
    snapshot = _ts(tool_source, "tool_snapshot")
    if snapshot:
        return [{"__tool_snapshot__": snapshot}]
    return dataset


def _apply_tool_filter(
    tools: list[dspy.Tool], tool_filter: list[str] | None
) -> list[dspy.Tool]:
    """Filter and order a tool roster by ``tool_filter``.

    When ``tool_filter`` is set the result keeps only the named tools, in the
    filter's order (names absent from the roster are skipped). When ``None`` the
    roster is returned unchanged.

    Args:
        tools: The resolved tool roster.
        tool_filter: Optional ordered allow-list of tool names.

    Returns:
        The filtered, reordered roster (or the original when no filter).
    """
    if not tool_filter:
        return tools
    by_name = {tool.name: tool for tool in tools}
    return [by_name[name] for name in tool_filter if name in by_name]


def run_react_optimization(
    *,
    signature_cls: type,
    tools: list[dspy.Tool],
    schema_hashes: dict[str, str],
    reward_spec: RewardSpec,
    vector_fn: VectorRewardFn,
    grounding_weight: float,
    train: list[EvaluationExample],
    val: list[EvaluationExample],
    test: list[EvaluationExample],
    student_lm: dspy.LM,
    reflection_lm: dspy.LM,
    max_metric_calls: int = _AUTO_BUDGETS["medium"],
    template: ChatTemplate | None = None,
    scorer: PromptScorer | None = None,
    max_iters: int = DEFAULT_MAX_ITERS,
    seed: int = 0,
    match_mode: str = "exact",
    run_dir: str | None = None,
    progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Optimise a react program against replay examples and report acceptance.

    Builds a seed ``ReActV2`` over ``signature_cls`` + ``tools``, runs
    ``gepa.optimize`` with the parameterised ECHO adapter (task reward from
    ``reward_spec``/``vector_fn`` plus an optional grounding auxiliary), then
    evaluates seed and best candidate on ``test`` so the §11 paired-bootstrap
    delta is apples-to-apples (same instantiation path GEPA uses internally).

    Args:
        signature_cls: Resolved DSPy signature the program is built around.
        tools: Tool roster from :func:`resolve_react_tools`.
        schema_hashes: ``{tool_name: hash}`` snapshot carried into the overlay.
        reward_spec: Scalarizer config for the task term.
        vector_fn: Per-example reward-vector function paired with ``reward_spec``.
        grounding_weight: ECHO's λ; ``> 0`` requires ``template`` + ``scorer``.
        train: Train split (replay examples).
        val: Validation split passed to ``gepa.optimize`` as the valset.
        test: Held-out split scored for the acceptance statistics.
        student_lm: Candidate-rollout model.
        reflection_lm: Reflective-proposer model.
        max_metric_calls: GEPA metric-call budget (default medium = 2000).
        template: Chat-template renderer; required when grounding is weighted.
        scorer: Per-token echo scorer; required when grounding is weighted.
        max_iters: ReActV2 loop budget for the seed program.
        seed: RNG seed shared by GEPA + the bootstrap.
        match_mode: Replay step-matching policy (``"exact"`` default, or
            ``"tool_name"``) forwarded to the adapter's replay mocks.
        run_dir: Directory where GEPA persists its state (``gepa_state.bin``) so
            the trajectory watcher can stream the candidate tree; ``None`` keeps
            the run in-memory with no persisted state.
        progress_callback: Job-level progress callback. When provided, each
            candidate's full-valset sweep streams a ``PROGRESS_VALSET_OUTPUTS``
            event so the Pareto-cell prediction panel can render per-example
            outputs; ``None`` runs without that stream.

    Returns:
        A dict with the servable ``program_state``, baseline/optimized objective
        means and scalars, the ``paired_bootstrap`` result, an advisory
        ``promotion`` verdict (``{promotable, reasons}``), and a ``tool_overlay``
        (descriptions, arg descriptions, schema hashes, max_iters) for the bundle.
    """
    seed_program = dspy.ReActV2(signature_cls, tools=tools, max_iters=max_iters)
    seed_candidate = seed_candidate_from_program(seed_program)
    adapter = TrainingGroundDspyAdapter(
        seed_program=seed_program,
        student_lm=student_lm,
        reflection_lm=reflection_lm,
        include_task_reward=True,
        grounding_weight=grounding_weight,
        template=template,
        scorer=scorer,
        reward_spec=reward_spec,
        vector_fn=vector_fn,
        match_mode=match_mode,
    )
    # Score the seed on the held-out test set up front and surface it before the
    # GEPA loop starts, mirroring the scalar run path (core._run_program): the
    # early baseline_evaluated event lets the live score card render as soon as
    # the baseline is known instead of only after the whole loop finishes. The
    # seed scoring is independent of optimize(), so moving it earlier is a pure
    # reorder — total runtime is unchanged.
    baseline_scalars, baseline_objectives, baseline_objective_mean = (
        _evaluate_candidate_on_examples(
            adapter=adapter, candidate=seed_candidate, examples=test
        )
    )
    if progress_callback:
        progress_callback(PROGRESS_BASELINE, {DETAIL_BASELINE: _mean(baseline_scalars)})

    with (
        react_valset_outputs(adapter, val, progress_callback),
        react_minibatch_feedback(adapter, val, progress_callback),
    ):
        result = gepa.optimize(
            seed_candidate=seed_candidate,
            trainset=train,
            valset=val,
            adapter=adapter,
            frontier_type="objective",
            max_metric_calls=max_metric_calls,
            seed=seed,
            run_dir=run_dir,
            # GEPA defaults both off, which left react runs without a score chart
            # or a progress bar: logger=None prints iteration lines to stdout
            # (never reaching job_logs), and display_progress_bar=False means no
            # rollouts bar for capture_tqdm to relay as optimizer_progress.
            logger=_JobLogGepaLogger(logger),
            display_progress_bar=True,
        )
    best_candidate = _best_candidate(result)
    program_state = _program_state_from(best_candidate=best_candidate, adapter=adapter)

    optimized_scalars, optimized_objectives, optimized_objective_mean = (
        _evaluate_candidate_on_examples(
            adapter=adapter, candidate=best_candidate, examples=test
        )
    )
    bootstrap = _bootstrap_or_empty(
        baseline_scalars=baseline_scalars,
        optimized_scalars=optimized_scalars,
        seed=seed,
    )
    # Advisory only: the service path has no wizard-phase notion, so the
    # promotion verdict floors on total holdout scale (single bucket) rather
    # than per-phase. It surfaces the §11 gate without blocking serving.
    verdict = _resolve_promotion(
        bootstrap=bootstrap,
        baseline_objectives=baseline_objectives,
        candidate_objectives=optimized_objectives,
        holdout_examples=test,
        stratifier=None,
    )
    return {
        "program_state": program_state,
        "baseline_objective_scores": baseline_objective_mean,
        "optimized_objective_scores": optimized_objective_mean,
        "baseline_objective_per_example": baseline_objectives,
        "optimized_objective_per_example": optimized_objectives,
        "baseline_scalar": _mean(baseline_scalars),
        "optimized_scalar": _mean(optimized_scalars),
        "baseline_scalars_per_example": baseline_scalars,
        "optimized_scalars_per_example": optimized_scalars,
        "paired_bootstrap": bootstrap,
        "promotion": {
            "promotable": verdict.promotable,
            "reasons": list(verdict.reasons),
        },
        "tool_overlay": {
            "tool_descriptions": _candidate_tool_descriptions(best_candidate),
            "tool_arg_descriptions": _candidate_tool_arg_descriptions(best_candidate),
            "tool_names": _candidate_tool_names(best_candidate),
            "tool_schema_hashes": schema_hashes,
            "max_iters": max_iters,
        },
    }


def _bootstrap_or_empty(
    *,
    baseline_scalars: list[float],
    optimized_scalars: list[float],
    seed: int,
) -> PairedBootstrapResult:
    """Run the paired bootstrap, returning a zeroed result on an empty test set.

    ``paired_bootstrap_ci`` raises on an empty test split; a react run with no
    held-out examples should still produce a (degenerate) envelope rather than
    aborting, so the empty case collapses to a zero-delta result.

    Args:
        baseline_scalars: Per-example seed scalars on the test set.
        optimized_scalars: Per-example optimized scalars on the test set.
        seed: RNG seed for reproducibility.

    Returns:
        The paired-bootstrap result, or a zeroed one when the test set is empty.
    """
    if not baseline_scalars or not optimized_scalars:
        return PairedBootstrapResult(
            resamples=0, mean_delta=0.0, ci95_lower=0.0, ci95_upper=0.0
        )
    return paired_bootstrap_ci(
        baseline_scores=baseline_scalars,
        candidate_scores=optimized_scalars,
        seed=seed,
    )


def _mean(values: list[float]) -> float:
    """Arithmetic mean, ``0.0`` for an empty list."""
    return sum(values) / len(values) if values else 0.0


__all__ = [
    "DEFAULT_MAX_ITERS",
    "build_replay_examples",
    "resolve_react_tools",
    "run_react_optimization",
]


# Keep ``Callable`` referenced for the VectorRewardFn alias signature parity.
_ = Callable
