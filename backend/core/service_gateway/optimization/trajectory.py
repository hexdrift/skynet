"""Per-candidate event extraction from a running GEPA optimization.

GEPA persists its full state to ``<run_dir>/gepa_state.bin`` (cloudpickle) at
the start of every iteration plus once after the loop exits. This module
watches that file and converts new accepted candidates into structured
progress events the frontend can render as a genealogy tree.

Accepted candidates flow through ``state.program_candidates`` and are emitted
as :data:`PROGRESS_CANDIDATE` events. Rejected proposals are reconstructed
from ``state.full_program_trace`` — each iteration entry there carries
``selected_program_candidate`` (parent), ``subsample_scores`` (parent),
``new_subsample_scores`` (proposed), and only entries that were accepted
also carry ``new_program_idx``. Iterations with proposed scores but no
``new_program_idx`` are rejections, and we emit them as
:data:`PROGRESS_REJECTED` events.

Reflective feedback text from each metric call is captured by
:class:`MinibatchRecorder`, a metric-callable wrapper that intercepts
``dspy.Prediction`` returns carrying ``feedback`` and forwards them as
:data:`PROGRESS_MINIBATCH` events. The wrapper is composition, not
monkey-patching — callers opt in by passing the wrapped callable to the
optimizer instead of the raw metric.
"""

from __future__ import annotations

import contextlib
import logging
import os
import pickle
import tempfile
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import cloudpickle

try:
    from gepa.proposer.reflective_mutation.reflective_mutation import (
        ReflectiveMutationProposer,
    )
except ImportError:
    ReflectiveMutationProposer = None  # type: ignore[assignment,misc]

from ...constants import (
    OPTIMIZER_NAME_GEPA,
    PROGRESS_CANDIDATE,
    PROGRESS_MINIBATCH,
    PROGRESS_REJECTED,
    PROGRESS_VALSET,
    PROGRESS_VALSET_OUTPUTS,
)

logger = logging.getLogger(__name__)


GEPA_STATE_FILENAME = "gepa_state.bin"

VALSET_FIELD_CHAR_CAP = 4096


def _normalize_field_value(value: Any) -> str:
    """Render an Example field value as a JSON-safe, length-capped string.

    The trajectory drawer wants to display the example's raw inputs and
    outputs verbatim. JSON-native scalars pass through as their string
    form; anything else (images, custom objects) is stringified so the
    SSE payload stays valid JSON.

    Args:
        value: Field value pulled out of a DSPy Example.

    Returns:
        A string no longer than :data:`VALSET_FIELD_CHAR_CAP` characters.
        Over-cap values are truncated and suffixed with an ellipsis marker
        so the UI can tell the cell is incomplete.
    """
    if value is None:
        text = ""
    elif isinstance(value, (str, int, float, bool)):
        text = str(value)
    else:
        text = str(value)
    if len(text) > VALSET_FIELD_CHAR_CAP:
        return text[:VALSET_FIELD_CHAR_CAP] + "…"
    return text


def _example_field_map(example: Any, method_name: str) -> dict[str, str]:
    """Pull inputs or labels off a DSPy Example into a string-valued dict.

    Plain dicts (used in tests and as a fallback for non-DSPy rows) take
    the same path — we treat the dict as the inputs map and emit an empty
    outputs map. This keeps the helper resilient when the optimizer runs
    against fixture data that bypasses :func:`rows_to_examples`.

    Args:
        example: DSPy ``Example`` or plain dict.
        method_name: ``"inputs"`` or ``"labels"``.

    Returns:
        Field name → normalized string. Empty dict when the example
        exposes no fields of that kind.
    """
    accessor = getattr(example, method_name, None)
    if callable(accessor):
        try:
            extracted = accessor()
        except Exception:
            return {}
        items = getattr(extracted, "items", None)
        pairs = items() if callable(items) else extracted
    elif isinstance(example, dict) and method_name == "inputs":
        pairs = example.items()
    else:
        return {}
    out: dict[str, str] = {}
    for key, value in pairs:
        out[str(key)] = _normalize_field_value(value)
    return out


def serialize_valset_rows(valset: list[Any]) -> list[dict[str, Any]]:
    """Convert a validation split into the JSON shape the frontend renders.

    The id assigned to each row matches GEPA's per-example score keys
    (sequential integers as strings starting at ``"0"``). The frontend
    keys its Pareto-cell detail lookup off this id, so the order of
    ``valset`` must match the order GEPA sees during evaluation.

    Args:
        valset: List of DSPy ``Example`` instances (or dicts) in evaluation
            order — typically ``DatasetSplits.val``.

    Returns:
        List of ``{"id", "inputs", "outputs"}`` dicts, one per example.
        Returns ``[]`` when ``valset`` is empty.
    """
    rows: list[dict[str, Any]] = []
    for idx, example in enumerate(valset):
        rows.append(
            {
                "id": str(idx),
                "inputs": _example_field_map(example, "inputs"),
                "outputs": _example_field_map(example, "labels"),
            }
        )
    return rows


def emit_valset_event(
    valset: list[Any],
    progress_callback: Callable[[str, dict[str, Any]], None] | None,
) -> None:
    """Fire a single :data:`PROGRESS_VALSET` event carrying the validation rows.

    No-op when the callback is missing (non-streaming code paths) or the
    valset is empty (test runs with only a train split). Failures inside
    the callback are logged but never propagate — losing the event must
    not abort the optimization.

    Args:
        valset: Validation split examples in GEPA-ordering.
        progress_callback: Job-level progress callback, or ``None``.
    """
    if progress_callback is None:
        return
    rows = serialize_valset_rows(valset)
    if not rows:
        return
    try:
        progress_callback(PROGRESS_VALSET, {"rows": rows})
    except Exception:
        logger.exception("progress_callback raised for valset (%d rows)", len(rows))


MINIBATCH_FEEDBACK_CHAR_CAP = 4096
MINIBATCH_PREDICTION_CHAR_CAP = 1024


def _extract_feedback(result: Any) -> str:
    """Return the feedback string GEPA attaches to a ``dspy.Prediction`` result.

    GEPA's adapter sets ``feedback`` to a non-empty string only on proposal
    minibatch evaluations; full-valset evaluations return either a bare
    float or a ``Prediction`` without feedback.

    Args:
        result: The metric's return value.

    Returns:
        Feedback text, or ``""`` when the result carries none.
    """
    feedback = getattr(result, "feedback", None)
    if isinstance(feedback, str):
        return feedback
    return ""


def _extract_score(result: Any) -> float:
    """Return the numeric score from a metric result, handling Prediction wrappers.

    Args:
        result: Either a numeric or a ``dspy.Prediction`` with ``score`` attr.

    Returns:
        Float score, defaulting to ``0.0`` when conversion fails.
    """
    score = getattr(result, "score", result)
    try:
        return float(score)
    except (TypeError, ValueError):
        return 0.0


def _normalize_prediction(prediction: Any) -> str:
    """Render a prediction as a length-capped string for SSE transport.

    Args:
        prediction: The DSPy ``Prediction`` (or other object) passed to the metric.

    Returns:
        String form capped at :data:`MINIBATCH_PREDICTION_CHAR_CAP` characters.
    """
    text = str(prediction)
    if len(text) > MINIBATCH_PREDICTION_CHAR_CAP:
        return text[:MINIBATCH_PREDICTION_CHAR_CAP] + "…"
    return text


class MinibatchRecorder:
    """Metric wrapper that emits progress events for GEPA evaluation calls.

    Composition, not monkey-patching: callers pass this callable to the
    optimizer in place of the raw metric. Each invocation is forwarded
    unchanged.

    Two event streams:
      - :data:`PROGRESS_MINIBATCH` — fires when the metric returns a
        ``dspy.Prediction`` with non-empty ``feedback`` text (reflective
        minibatch evaluation).
      - :data:`PROGRESS_VALSET_OUTPUTS` — fires once per completed full
        valset sweep, carrying ``{candidate_index, predictions}``. The
        completion check is "buffer now holds an (example_id, prediction)
        entry for every valset id." Minibatch calls write to the same
        buffer (so partial subsamples can land there too), but they never
        on their own fill it — a full sweep always touches every example,
        overwriting any stale minibatch leftovers.

    Candidate-index attribution piggybacks on the order GEPA appends to
    ``state.program_candidates``: the seed is 0 and every accepted
    candidate increments the counter. With the default
    :class:`gepa.strategies.eval_policy.FullEvaluationPolicy` (the only
    one DSPy GEPA uses), every full sweep corresponds to exactly one
    newly-added candidate, so flush_count - 1 is the right index. We rely
    on no evaluation cache being configured — caching would suppress
    metric calls and break the count.

    The example-id lookup uses object identity (``id(example)``) against
    the validation split, so the recorder must be constructed from the
    same ``DatasetSplits.val`` list the optimizer will see during compile.
    """

    def __init__(
        self,
        metric: Callable[..., Any],
        valset: list[Any],
        progress_callback: Callable[[str, dict[str, Any]], None],
    ):
        """Initialise the recorder over the GEPA-bound metric and valset.

        Args:
            metric: The original metric callable GEPA would have received.
            valset: Validation split examples in evaluation order — used to
                map an ``example`` argument back to its row id.
            progress_callback: Job-level callback that receives
                ``(PROGRESS_MINIBATCH, payload)`` for each feedback-bearing call
                and ``(PROGRESS_VALSET_OUTPUTS, payload)`` after each completed
                full valset sweep.
        """
        self._metric = metric
        self._index_by_id = {id(ex): str(idx) for idx, ex in enumerate(valset)}
        self._all_valset_ids: frozenset[str] = frozenset(
            str(idx) for idx in range(len(valset))
        )
        self._progress_callback = progress_callback
        self._lock = threading.Lock()
        self._buffer: dict[str, tuple[str, float]] = {}
        self._candidate_index = 0

    def __call__(self, example: Any, prediction: Any, *args: Any, **kwargs: Any) -> Any:
        """Invoke the wrapped metric and emit minibatch / valset-sweep events.

        Args:
            example: The DSPy ``Example`` evaluated.
            prediction: The candidate program's output for ``example``.
            *args: Forwarded positional metric args (``trace``, ``pred_name``, etc.).
            **kwargs: Forwarded keyword metric args.

        Returns:
            The wrapped metric's return value, unmodified.
        """
        result = self._metric(example, prediction, *args, **kwargs)
        ex_id = self._index_by_id.get(id(example), "?")
        score = _extract_score(result)
        prediction_text = _normalize_prediction(prediction)

        feedback = _extract_feedback(result)
        if feedback:
            try:
                self._progress_callback(
                    PROGRESS_MINIBATCH,
                    {
                        "example_id": ex_id,
                        "score": score,
                        "feedback": feedback[:MINIBATCH_FEEDBACK_CHAR_CAP],
                        "prediction": prediction_text,
                    },
                )
            except Exception:
                logger.exception(
                    "progress_callback raised for minibatch (example=%s)", ex_id
                )

        if ex_id != "?" and self._all_valset_ids:
            self._record_valset_call(ex_id, prediction_text, score)

        return result

    def _record_valset_call(self, ex_id: str, prediction_text: str, score: float) -> None:
        """Add a call to the sweep buffer; flush when the full valset is covered.

        The buffer is shared between minibatch and full-eval calls — minibatch
        writes are harmless because they're a strict subset and get overwritten
        by the next full sweep. Only fires the event when every valset id has
        been recorded since the last flush.
        """
        flushed: list[dict[str, Any]] | None = None
        index_for_event = 0
        with self._lock:
            self._buffer[ex_id] = (prediction_text, score)
            if self._all_valset_ids.issubset(self._buffer.keys()):
                flushed = [
                    {
                        "example_id": eid,
                        "prediction": self._buffer[eid][0],
                        "score": self._buffer[eid][1],
                    }
                    for eid in sorted(self._all_valset_ids, key=int)
                ]
                index_for_event = self._candidate_index
                self._candidate_index += 1
                self._buffer.clear()

        if flushed is None:
            return
        try:
            self._progress_callback(
                PROGRESS_VALSET_OUTPUTS,
                {
                    "candidate_index": index_for_event,
                    "predictions": flushed,
                },
            )
        except Exception:
            logger.exception(
                "progress_callback raised for valset_outputs (candidate=%d)",
                index_for_event,
            )


def maybe_wrap_minibatch_recorder(
    metric: Callable[..., Any],
    valset: list[Any],
    optimizer_name: str,
    progress_callback: Callable[[str, dict[str, Any]], None] | None,
) -> Callable[..., Any]:
    """Return a :class:`MinibatchRecorder` for GEPA runs, or the raw metric otherwise.

    Centralises the gating logic so callers don't need to repeat the
    optimizer/callback null-checks.

    Args:
        metric: The original metric callable.
        valset: Validation split for example-id lookup.
        optimizer_name: Name of the optimizer about to be instantiated.
        progress_callback: Job-level progress callback, or ``None``.

    Returns:
        The wrapped metric when GEPA + callback are both present, otherwise
        the metric unchanged.
    """
    if progress_callback is None:
        return metric
    if optimizer_name.lower() != OPTIMIZER_NAME_GEPA:
        return metric
    return MinibatchRecorder(metric, valset, progress_callback)


@contextlib.contextmanager
def capture_proposal_prompts(optimizer_name: str) -> Iterator[None]:
    """Stash each iteration's parent + proposed prompts onto the trace entry.

    The rejected-proposal drawer wants to show "what was the exact
    proposal text?" alongside the parent it mutated. GEPA itself doesn't
    persist the rejected proposal text anywhere — once the engine's
    accept-check fails, ``proposal.candidate`` is dropped on the floor.
    We close that gap by wrapping ``ReflectiveMutationProposer.propose``
    at the class level for the lifetime of this context, capturing
    ``state.program_candidates[selected_program_candidate]`` and the
    returned ``proposal.candidate`` into the same trace entry the
    proposer just populated with ``subsample_scores`` /
    ``new_subsample_scores``. The watcher's next disk-read picks them
    up via :func:`extract_rejected_from_trace` without any new event
    plumbing.

    Class-level patch is safe because the process runs at most one GEPA
    optimization at a time (the worker is single-job) and we always
    restore the original on context exit. Non-GEPA optimizers skip the
    patch entirely.

    Args:
        optimizer_name: Name of the optimizer about to compile. The
            capture only applies to GEPA runs.

    Yields:
        ``None`` — used purely for its enter/exit hooks.
    """
    if optimizer_name.lower() != OPTIMIZER_NAME_GEPA:
        yield
        return
    if ReflectiveMutationProposer is None:
        logger.debug("GEPA reflective proposer not importable; skipping prompt capture")
        yield
        return

    original_propose = ReflectiveMutationProposer.propose

    def wrapped_propose(self: Any, state: Any) -> Any:
        """Forward to the original propose, then snapshot prompts into the trace."""
        proposal = original_propose(self, state)
        try:
            trace = getattr(state, "full_program_trace", None)
            if not isinstance(trace, list) or not trace:
                return proposal
            entry = trace[-1]
            if not isinstance(entry, dict):
                return proposal
            parent_idx = entry.get("selected_program_candidate")
            candidates = getattr(state, "program_candidates", None)
            if (
                isinstance(parent_idx, int)
                and isinstance(candidates, list)
                and 0 <= parent_idx < len(candidates)
                and isinstance(candidates[parent_idx], dict)
            ):
                entry["parent_prompt_snapshot"] = dict(candidates[parent_idx])
            proposed = getattr(proposal, "candidate", None) if proposal is not None else None
            if isinstance(proposed, dict):
                entry["proposed_prompt_snapshot"] = dict(proposed)
        except Exception:
            logger.exception("Failed to snapshot proposal prompts onto trace entry")
        return proposal

    ReflectiveMutationProposer.propose = wrapped_propose  # type: ignore[method-assign]
    try:
        yield
    finally:
        ReflectiveMutationProposer.propose = original_propose  # type: ignore[method-assign]


@dataclass(frozen=True)
class CandidateEvent:
    """Structured snapshot of one accepted GEPA candidate.

    ``id`` is the candidate's index in ``state.program_candidates`` as a
    string ("0", "1", "2", …); the seed candidate is always ``"0"``. The
    string form is the wire identity the frontend uses for keying nodes —
    integers would clash with merge-derived synthetic ids in a future
    extension.

    ``parent_id`` is ``None`` only for the seed candidate. For merge
    candidates GEPA records multiple parents; we expose the first as
    ``parent_id`` (so the tree always has a primary spine) and the rest as
    ``parents_extra`` so the frontend can render merge edges as a secondary
    visual.

    ``generation`` is the depth in the parent tree, derived (not stored by
    GEPA) — root is 0, its children are 1, and so on.

    ``iteration`` is the engine-loop iteration that accepted this
    candidate (matches ``state.full_program_trace[i]["i"]``); ``None``
    for the seed candidate which never went through the accept path.
    The frontend keys "peers at this iteration" off this value.
    """

    id: str
    parent_id: str | None
    parents_extra: tuple[str, ...]
    generation: int
    score: float
    per_example: tuple[tuple[str, float], ...]
    prompt: dict[str, str]
    discovered_at_evals: int
    iteration: int | None

    def to_metrics(self) -> dict[str, Any]:
        """Serialise to the dict shape the ``progress_callback`` contract expects.

        Returns:
            JSON-safe dict suitable for ``progress_callback(event, metrics)``.
        """
        return {
            "candidate_id": self.id,
            "parent_id": self.parent_id,
            "parents_extra": list(self.parents_extra),
            "generation": self.generation,
            "score": self.score,
            "per_example": [{"id": eid, "score": s} for eid, s in self.per_example],
            "prompt": dict(self.prompt),
            "discovered_at_evals": self.discovered_at_evals,
            "iteration": self.iteration,
        }


@dataclass(frozen=True)
class RejectedEvent:
    """Structured snapshot of one rejected GEPA proposal.

    Rejected proposals do not appear in ``state.program_candidates``; they
    are reconstructed from ``state.full_program_trace`` entries that record
    a proposal evaluation but no ``new_program_idx``. We keep them for the
    trajectory tree so users can see how many proposals failed on each
    parent and by how much.

    ``rejection_id`` is a stable synthetic identity of the form
    ``"r{iteration}"`` so the frontend can key React nodes without
    colliding with accepted candidate ids (which are pure integers as
    strings: ``"0"``, ``"1"``, …).

    ``parent_score`` is the parent's average minibatch score on that
    iteration's subsample, and ``proposal_score`` is the proposed
    candidate's average on the same subsample. The strict-improvement
    check that rejected the proposal compares the *sums*, so
    ``proposal_score <= parent_score`` always holds for entries we emit
    (sum and mean preserve ordering when the subsample size is fixed).

    ``proposal_prompt`` and ``parent_prompt`` carry the predictor → text
    maps of the rejected proposal and the parent the engine was mutating.
    They are populated by :func:`capture_proposal_prompts` (a context
    manager around the engine's reflective proposer) and stay empty for
    runs where the capture was not active (e.g. older states reloaded
    from disk without re-running the optimization).

    ``subsample_ids`` are the train-set indices GEPA evaluated on this
    iteration; pair them with ``per_example_parent`` / ``per_example_proposal``
    to render a side-by-side score grid. Lengths match ``subsample_size``.
    """

    rejection_id: str
    iteration: int
    parent_id: str
    parent_score: float
    proposal_score: float
    subsample_size: int
    proposal_prompt: dict[str, str]
    parent_prompt: dict[str, str]
    subsample_ids: tuple[str, ...]
    per_example_parent: tuple[tuple[str, float], ...]
    per_example_proposal: tuple[tuple[str, float], ...]

    def to_metrics(self) -> dict[str, Any]:
        """Serialise to the dict shape the ``progress_callback`` contract expects.

        Returns:
            JSON-safe dict suitable for ``progress_callback(event, metrics)``.
        """
        return {
            "rejection_id": self.rejection_id,
            "iteration": self.iteration,
            "parent_id": self.parent_id,
            "parent_score": self.parent_score,
            "proposal_score": self.proposal_score,
            "subsample_size": self.subsample_size,
            "proposal_prompt": dict(self.proposal_prompt),
            "parent_prompt": dict(self.parent_prompt),
            "subsample_ids": list(self.subsample_ids),
            "per_example_parent": [
                {"id": eid, "score": s} for eid, s in self.per_example_parent
            ],
            "per_example_proposal": [
                {"id": eid, "score": s} for eid, s in self.per_example_proposal
            ],
        }


def _mean(values: list[float]) -> float:
    """Return the arithmetic mean of ``values``, or ``0.0`` for an empty list.

    Args:
        values: Numeric values. May be empty.

    Returns:
        Sum divided by length, or ``0.0`` when ``values`` is empty.
    """
    if not values:
        return 0.0
    return sum(values) / len(values)


def extract_rejected_from_trace(
    state: dict[str, Any],
    last_seen_iteration: int,
) -> list[RejectedEvent]:
    """Walk ``state.full_program_trace`` and emit events for new rejections.

    A trace entry is a rejection when it has ``subsample_scores`` and
    ``new_subsample_scores`` (so the engine actually evaluated a proposal)
    but no ``new_program_idx`` (so the engine did not accept it). All
    other entries — proposals that were never built, accepted candidates
    that ended up in ``program_candidates``, or entries that are still
    mid-iteration — are skipped.

    Args:
        state: Deserialised GEPA state dict.
        last_seen_iteration: Highest ``iteration`` value already emitted in
            a previous tick. Pass ``-1`` on first call so iteration ``0``
            (if rejected) is still considered.

    Returns:
        Events for new rejections, ordered by iteration ascending. Returns
        ``[]`` when nothing new has appeared.
    """
    trace = state.get("full_program_trace") or []
    if not isinstance(trace, list):
        return []

    out: list[RejectedEvent] = []
    for idx, entry in enumerate(trace):
        if not isinstance(entry, dict):
            continue
        if idx <= last_seen_iteration:
            continue
        if "new_program_idx" in entry:
            continue
        subsample_scores = entry.get("subsample_scores")
        new_subsample_scores = entry.get("new_subsample_scores")
        if not isinstance(subsample_scores, list):
            continue
        if not isinstance(new_subsample_scores, list):
            continue
        if len(subsample_scores) == 0:
            continue
        parent_idx = entry.get("selected_program_candidate")
        if not isinstance(parent_idx, int):
            continue
        try:
            parent_floats = [float(s) for s in subsample_scores]
            proposal_floats = [float(s) for s in new_subsample_scores]
        except (TypeError, ValueError):
            continue
        subsample_ids = _coerce_subsample_ids(entry.get("subsample_ids"), len(parent_floats))
        per_example_parent = tuple(zip(subsample_ids, parent_floats, strict=False))
        per_example_proposal = tuple(zip(subsample_ids, proposal_floats, strict=False))
        out.append(
            RejectedEvent(
                rejection_id=f"r{idx}",
                iteration=idx,
                parent_id=str(parent_idx),
                parent_score=_mean(parent_floats),
                proposal_score=_mean(proposal_floats),
                subsample_size=len(parent_floats),
                proposal_prompt=_coerce_prompt(entry.get("proposed_prompt_snapshot")),
                parent_prompt=_coerce_prompt(entry.get("parent_prompt_snapshot")),
                subsample_ids=subsample_ids,
                per_example_parent=per_example_parent,
                per_example_proposal=per_example_proposal,
            )
        )
    return out


def _coerce_subsample_ids(raw: Any, expected_len: int) -> tuple[str, ...]:
    """Render trace ``subsample_ids`` as a tuple of string ids of the expected length.

    GEPA stores ``subsample_ids`` as integers (train-set indices) or in
    a few code paths as strings already. When the entry pre-dates the
    feature or is malformed we fall back to ``("0", "1", …)`` of the
    expected length so the per-example grid still aligns with the score
    arrays even if the ids are synthetic.

    Args:
        raw: Value pulled from ``entry["subsample_ids"]`` (may be missing).
        expected_len: Number of subsample scores already validated;
            authoritative length for the returned tuple.

    Returns:
        Tuple of ``expected_len`` string ids.
    """
    if isinstance(raw, list) and len(raw) == expected_len:
        return tuple(str(v) for v in raw)
    return tuple(str(i) for i in range(expected_len))


def _coerce_prompt(raw: Any) -> dict[str, str]:
    """Render a captured prompt snapshot as a JSON-safe str→str dict.

    Args:
        raw: Value pulled from ``entry["proposed_prompt_snapshot"]`` or
            ``entry["parent_prompt_snapshot"]``. Either is missing on
            trace entries written before :func:`capture_proposal_prompts`
            was active.

    Returns:
        Predictor name → instruction text, or an empty dict when the
        snapshot is absent or malformed.
    """
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def _compute_depths(parents: list[list[int | None] | None]) -> list[int]:
    """Compute per-candidate depth from the parent table.

    Walks the parent list once in index order; safe because GEPA always
    appends new candidates after their parents.

    Args:
        parents: ``state.parent_program_for_candidate`` — a list where each
            entry is a list of parent indices (or ``None`` for the seed).

    Returns:
        Depth for each candidate, in index order.
    """
    depths: list[int] = []
    for idx, parent_list in enumerate(parents):
        if not parent_list or parent_list[0] is None:
            depths.append(0)
            continue
        primary = parent_list[0]
        if not isinstance(primary, int) or primary < 0 or primary >= len(depths):
            depths.append(0)
            continue
        depths.append(depths[primary] + 1)
    return depths


def extract_candidates_from_state(
    state: dict[str, Any],
    last_seen_count: int,
) -> list[CandidateEvent]:
    """Walk a deserialised GEPAState dict and emit events for new candidates.

    Reads from the dict that ``GEPAState.save`` writes — i.e.
    ``dict(self.__dict__.items())`` — so this function is decoupled from
    the GEPA class hierarchy and survives upstream refactors as long as the
    persisted field names stay stable.

    Args:
        state: Deserialised dict from ``gepa_state.bin``.
        last_seen_count: Number of candidates already emitted previously.
            Pass ``0`` on first call.

    Returns:
        Events for candidates with index ``>= last_seen_count``, in index order.
        Returns ``[]`` (not None) when nothing new exists.
    """
    candidates = state.get("program_candidates") or []
    parents = state.get("parent_program_for_candidate") or []
    subscores = state.get("prog_candidate_val_subscores") or []
    discovery = state.get("num_metric_calls_by_discovery") or []
    iteration_by_idx = _iteration_index_from_trace(state.get("full_program_trace"))

    if last_seen_count >= len(candidates):
        return []

    depths = _compute_depths(parents)

    out: list[CandidateEvent] = []
    for idx in range(last_seen_count, len(candidates)):
        parent_list = parents[idx] if idx < len(parents) else [None]
        if not parent_list or parent_list[0] is None:
            parent_id: str | None = None
            parents_extra: tuple[str, ...] = ()
        else:
            parent_id = str(parent_list[0])
            parents_extra = tuple(
                str(p) for p in parent_list[1:] if isinstance(p, int)
            )

        per_example_dict = subscores[idx] if idx < len(subscores) else {}
        per_example = tuple(
            (str(k), float(v)) for k, v in per_example_dict.items()
        )
        score = (
            sum(v for _, v in per_example) / len(per_example)
            if per_example
            else 0.0
        )

        prompt_raw = candidates[idx]
        prompt = (
            {str(k): str(v) for k, v in prompt_raw.items()}
            if isinstance(prompt_raw, dict)
            else {}
        )

        out.append(
            CandidateEvent(
                id=str(idx),
                parent_id=parent_id,
                parents_extra=parents_extra,
                generation=depths[idx] if idx < len(depths) else 0,
                score=score,
                per_example=per_example,
                prompt=prompt,
                discovered_at_evals=(
                    int(discovery[idx]) if idx < len(discovery) else 0
                ),
                iteration=iteration_by_idx.get(idx),
            )
        )
    return out


def _iteration_index_from_trace(trace: Any) -> dict[int, int]:
    """Build a candidate-index → iteration map by scanning the trace.

    The engine sets ``entry["new_program_idx"]`` on the accepting iteration
    just before adding the candidate, so a single linear pass over the
    trace gives us the iteration each accepted candidate landed on. Used
    by the frontend to surface peers ("other candidates at this
    iteration") without needing a separate event stream.

    Args:
        trace: ``state.full_program_trace`` (or any value — non-list
            inputs return an empty map so the caller doesn't need to
            null-check).

    Returns:
        Mapping ``program_candidates`` index → iteration ``i``. Seed
        candidate ``0`` is intentionally absent (never went through the
        accept path).
    """
    if not isinstance(trace, list):
        return {}
    out: dict[int, int] = {}
    for entry in trace:
        if not isinstance(entry, dict):
            continue
        idx = entry.get("new_program_idx")
        iteration = entry.get("i")
        if isinstance(idx, int) and isinstance(iteration, int):
            out[idx] = iteration
    return out


def _load_state(state_path: str) -> dict[str, Any] | None:
    """Load and deserialise a GEPA state file.

    Tries cloudpickle first (matches GEPA's save default when ``use_cloudpickle``
    is True) and falls back to stdlib pickle. Returns ``None`` on any failure
    — the caller treats that as "try again on next tick", which handles the
    race where the file exists but GEPA is mid-write.

    Args:
        state_path: Absolute path to ``gepa_state.bin``.

    Returns:
        Deserialised dict, or ``None`` if the file is missing, truncated, or
        unreadable.
    """
    try:
        with open(state_path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    for loader in (cloudpickle.loads, pickle.loads):
        try:
            obj = loader(data)
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
        return None
    return None


class TrajectoryWatcher:
    """Polls a GEPA run directory and forwards new candidates through a callback.

    Spawns a daemon thread that watches ``<run_dir>/gepa_state.bin`` via mtime,
    deserialises it on change, and invokes the provided progress callback once
    per new candidate. Robust to partial writes: a failed deserialise just
    waits for the next tick rather than raising.

    Use as a context manager so cleanup always happens, including a final
    drain after ``__exit__`` so the last save (which GEPA emits after the
    loop) is not lost between the optimizer returning and the watcher waking.

    Thread safety: the callback is invoked from the watcher thread. Callers
    that touch shared state must protect it accordingly.
    """

    _POLL_SECONDS = 1.0

    def __init__(
        self,
        run_dir: str,
        progress_callback: Callable[[str, dict[str, Any]], None],
    ):
        """Initialise the watcher; does not start the thread.

        Args:
            run_dir: Directory GEPA writes ``gepa_state.bin`` into.
            progress_callback: Existing job-level progress callback. Each
                new candidate is forwarded as
                ``progress_callback(PROGRESS_CANDIDATE, event.to_metrics())``.
        """
        self._run_dir = run_dir
        self._progress_callback = progress_callback
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_count = 0
        self._last_rejected_iteration = -1
        self._last_mtime: float | None = None
        self._tick_lock = threading.Lock()

    def __enter__(self) -> TrajectoryWatcher:
        """Start the watcher thread on context entry.

        Returns:
            This watcher instance for use in ``with`` blocks.
        """
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Stop the watcher and run a final drain on context exit.

        Args:
            exc_type: Exception class raised inside the ``with`` block, or None.
            exc_value: Exception instance raised inside the ``with`` block, or None.
            traceback: Traceback if the block raised, else None.
        """
        self.stop()

    def start(self) -> None:
        """Spawn the daemon watcher thread. Idempotent."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="gepa-trajectory-watcher",
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the thread to stop, join, then run one final drain tick.

        The drain handles the race between GEPA's final ``state.save`` (after
        the main loop exits) and the watcher's poll cadence — without it,
        the last candidate(s) of every run would be lost.

        Args:
            timeout: Seconds to wait for the worker thread to exit.
        """
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=timeout)
        try:
            self._tick(force=True)
        except Exception:
            logger.exception("Final trajectory drain failed for %s", self._run_dir)

    def _run(self) -> None:
        """Watcher thread body. Polls until ``_stop`` is set."""
        while not self._stop.wait(self._POLL_SECONDS):
            try:
                self._tick()
            except Exception:
                logger.exception(
                    "Trajectory watcher tick failed for %s — continuing",
                    self._run_dir,
                )

    def _tick(self, *, force: bool = False) -> None:
        """One poll cycle: detect change, load, diff, forward.

        Args:
            force: When True, re-read even if mtime hasn't changed. Used by
                the final drain after ``stop()``.
        """
        with self._tick_lock:
            state_path = os.path.join(self._run_dir, GEPA_STATE_FILENAME)
            try:
                mtime = os.path.getmtime(state_path)
            except OSError:
                return
            if not force and mtime == self._last_mtime:
                return

            state = _load_state(state_path)
            if state is None:
                self._last_mtime = None
                return
            self._last_mtime = mtime

            new_events = extract_candidates_from_state(state, self._last_count)
            for event in new_events:
                try:
                    self._progress_callback(PROGRESS_CANDIDATE, event.to_metrics())
                except Exception:
                    logger.exception("progress_callback raised for candidate %s", event.id)
            self._last_count += len(new_events)

            new_rejected = extract_rejected_from_trace(state, self._last_rejected_iteration)
            for rej in new_rejected:
                try:
                    self._progress_callback(PROGRESS_REJECTED, rej.to_metrics())
                except Exception:
                    logger.exception(
                        "progress_callback raised for rejected proposal %s",
                        rej.rejection_id,
                    )
            if new_rejected:
                self._last_rejected_iteration = new_rejected[-1].iteration


@contextlib.contextmanager
def gepa_log_dir(optimizer_name: str) -> Iterator[str | None]:
    """Allocate a temporary directory for GEPA's state file, or yield ``None``.

    GEPA writes ``gepa_state.bin`` here on every iteration; the path is
    handed to ``instantiate_optimizer(log_dir=...)``. Non-GEPA optimizers
    don't use it, so no directory is created and ``None`` is yielded —
    ``instantiate_optimizer`` ignores ``log_dir`` for those.

    Args:
        optimizer_name: The optimizer's registered name.

    Yields:
        Absolute path to a fresh tempdir for GEPA, or ``None`` for other
        optimizers. The directory is removed on context exit.
    """
    if optimizer_name.lower() != OPTIMIZER_NAME_GEPA:
        yield None
        return
    with tempfile.TemporaryDirectory(prefix="gepa_trajectory_") as tmpdir:
        yield tmpdir


@contextlib.contextmanager
def trajectory_watch(
    log_dir: str | None,
    progress_callback: Callable[[str, dict[str, Any]], None] | None,
) -> Iterator[None]:
    """Run a :class:`TrajectoryWatcher` for the duration of the context.

    No-op when either ``log_dir`` or ``progress_callback`` is missing — the
    non-GEPA path skips both, and runs without a callback would have nothing
    to forward emitted events to.

    Args:
        log_dir: Directory GEPA writes ``gepa_state.bin`` into, or ``None``
            for non-GEPA optimizers.
        progress_callback: Job-level progress callback that receives
            ``(event, metrics)`` tuples, or ``None`` when the caller does
            not need progress.

    Yields:
        ``None`` — used purely for its enter/exit hooks.
    """
    if log_dir is None or progress_callback is None:
        yield
        return
    with TrajectoryWatcher(log_dir, progress_callback):
        yield
