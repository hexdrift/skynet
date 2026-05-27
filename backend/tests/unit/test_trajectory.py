"""B-L2: GEPA state → CandidateEvent extraction contract.

The trajectory feature surfaces accepted GEPA candidates as progress events.
These tests pin the dict-shape that ``extract_candidates_from_state`` reads
from ``gepa_state.bin`` and the JSON-safe metrics dict it forwards to the
progress callback. Drift in either direction silently breaks the frontend
genealogy tree, so the tests live in the unit suite.
"""

from __future__ import annotations

import dataclasses
import os
import pickle
import tempfile

import cloudpickle
import pytest

import dspy
from gepa.proposer.base import CandidateProposal
from gepa.proposer.reflective_mutation.reflective_mutation import (
    ReflectiveMutationProposer,
)

from core.constants import PROGRESS_MINIBATCH, PROGRESS_VALSET, PROGRESS_VALSET_OUTPUTS
from core.service_gateway.optimization.trajectory import (
    MINIBATCH_FEEDBACK_CHAR_CAP,
    MINIBATCH_PREDICTION_CHAR_CAP,
    VALSET_FIELD_CHAR_CAP,
    CandidateEvent,
    MinibatchRecorder,
    RejectedEvent,
    _load_state,
    capture_proposal_prompts,
    emit_valset_event,
    extract_candidates_from_state,
    extract_rejected_from_trace,
    gepa_log_dir,
    maybe_wrap_minibatch_recorder,
    serialize_valset_rows,
    trajectory_watch,
)


def _minimal_state() -> dict:
    """Return a state dict mirroring two iterations of GEPA acceptance.

    Returns:
        State dict with a seed candidate plus one accepted child.
    """
    return {
        "program_candidates": [
            {"qa.predict": "Answer the question."},
            {"qa.predict": "Answer the question step by step."},
        ],
        "parent_program_for_candidate": [[None], [0]],
        "prog_candidate_val_subscores": [
            {"ex1": 0.5, "ex2": 0.75},
            {"ex1": 0.6, "ex2": 1.0},
        ],
        "num_metric_calls_by_discovery": [0, 4],
    }


class TestExtractCandidates:
    """Lock the shape and ordering of CandidateEvents emitted from a state dict."""

    def test_seed_candidate_has_no_parent(self) -> None:
        """Index-0 candidate yields ``parent_id=None`` and generation 0."""
        events = extract_candidates_from_state(_minimal_state(), last_seen_count=0)
        assert events[0].id == "0"
        assert events[0].parent_id is None
        assert events[0].generation == 0

    def test_child_candidate_carries_parent_string(self) -> None:
        """Index-1 candidate exposes ``parent_id="0"`` and generation 1."""
        events = extract_candidates_from_state(_minimal_state(), last_seen_count=0)
        assert events[1].id == "1"
        assert events[1].parent_id == "0"
        assert events[1].generation == 1

    def test_score_is_mean_of_per_example(self) -> None:
        """``score`` averages the per-example subscores."""
        events = extract_candidates_from_state(_minimal_state(), last_seen_count=0)
        assert events[1].score == 0.8

    def test_last_seen_count_filters_emitted_events(self) -> None:
        """Only candidates with index ``>= last_seen_count`` are returned."""
        events = extract_candidates_from_state(_minimal_state(), last_seen_count=1)
        assert len(events) == 1
        assert events[0].id == "1"

    def test_no_new_candidates_returns_empty_list(self) -> None:
        """When the watcher has seen everything, the next call yields ``[]``."""
        assert extract_candidates_from_state(_minimal_state(), last_seen_count=2) == []

    def test_metrics_dict_is_json_safe(self) -> None:
        """``to_metrics()`` returns plain dicts/lists, no tuples or dataclasses."""
        events = extract_candidates_from_state(_minimal_state(), last_seen_count=0)
        metrics = events[1].to_metrics()
        assert metrics == {
            "candidate_id": "1",
            "parent_id": "0",
            "parents_extra": [],
            "generation": 1,
            "score": 0.8,
            "per_example": [{"id": "ex1", "score": 0.6}, {"id": "ex2", "score": 1.0}],
            "prompt": {"qa.predict": "Answer the question step by step."},
            "discovered_at_evals": 4,
            "iteration": None,
        }

    def test_iteration_is_populated_from_trace(self) -> None:
        """Accepted candidates surface the iteration that accepted them."""
        state = _minimal_state()
        state["full_program_trace"] = [
            {"i": 0, "new_program_idx": 1, "selected_program_candidate": 0},
        ]
        events = extract_candidates_from_state(state, last_seen_count=0)
        assert events[0].iteration is None
        assert events[1].iteration == 0

    def test_merge_candidate_exposes_extra_parents(self) -> None:
        """Multi-parent rows surface the first as primary, the rest in ``parents_extra``."""
        state = _minimal_state()
        state["program_candidates"].append({"qa.predict": "Merged answer."})
        state["parent_program_for_candidate"].append([0, 1])
        state["prog_candidate_val_subscores"].append({"ex1": 1.0, "ex2": 1.0})
        state["num_metric_calls_by_discovery"].append(8)

        events = extract_candidates_from_state(state, last_seen_count=2)
        assert events[0].parent_id == "0"
        assert events[0].parents_extra == ("1",)
        assert events[0].to_metrics()["parents_extra"] == ["1"]


def _trace_with_one_acceptance_one_rejection() -> list[dict]:
    """Return a ``full_program_trace`` with iter-0 accepted and iter-1 rejected.

    Returns:
        Trace list mirroring two GEPA iterations: the first proposal was
        accepted (carries ``new_program_idx``), the second was discarded.
    """
    return [
        {
            "selected_program_candidate": 0,
            "subsample_ids": [0, 1, 2],
            "subsample_scores": [0.0, 1.0, 0.5],
            "new_subsample_scores": [1.0, 1.0, 1.0],
            "new_program_idx": 1,
        },
        {
            "selected_program_candidate": 1,
            "subsample_ids": [3, 4, 5],
            "subsample_scores": [1.0, 1.0, 1.0],
            "new_subsample_scores": [0.0, 1.0, 1.0],
        },
    ]


class TestExtractRejected:
    """Lock the shape and ordering of RejectedEvents reconstructed from full_program_trace."""

    def test_skips_iterations_with_new_program_idx(self) -> None:
        """Accepted iterations (``new_program_idx`` set) must not produce rejections."""
        state = {"full_program_trace": _trace_with_one_acceptance_one_rejection()}
        events = extract_rejected_from_trace(state, last_seen_iteration=-1)
        assert len(events) == 1
        assert events[0].iteration == 1

    def test_rejection_carries_parent_and_scores(self) -> None:
        """A rejected iteration emits the parent id and mean scores."""
        state = {"full_program_trace": _trace_with_one_acceptance_one_rejection()}
        event = extract_rejected_from_trace(state, last_seen_iteration=-1)[0]
        assert event.rejection_id == "r1"
        assert event.parent_id == "1"
        assert event.parent_score == pytest.approx(1.0)
        assert event.proposal_score == pytest.approx((0.0 + 1.0 + 1.0) / 3)
        assert event.subsample_size == 3

    def test_last_seen_iteration_filters_out_old_rejections(self) -> None:
        """Re-polls after ``last_seen_iteration=N`` skip iterations ``<=N``."""
        state = {"full_program_trace": _trace_with_one_acceptance_one_rejection()}
        assert extract_rejected_from_trace(state, last_seen_iteration=1) == []

    def test_missing_subsample_scores_is_skipped(self) -> None:
        """Entries without ``new_subsample_scores`` (e.g. setup-only) are skipped."""
        state = {
            "full_program_trace": [
                {
                    "selected_program_candidate": 0,
                    "subsample_ids": [0],
                    "subsample_scores": [0.5],
                }
            ]
        }
        assert extract_rejected_from_trace(state, last_seen_iteration=-1) == []

    def test_metrics_dict_is_json_safe(self) -> None:
        """``to_metrics()`` returns plain numerics and strings only."""
        state = {"full_program_trace": _trace_with_one_acceptance_one_rejection()}
        metrics = extract_rejected_from_trace(state, last_seen_iteration=-1)[0].to_metrics()
        assert metrics == {
            "rejection_id": "r1",
            "iteration": 1,
            "parent_id": "1",
            "parent_score": 1.0,
            "proposal_score": pytest.approx((0.0 + 1.0 + 1.0) / 3),
            "subsample_size": 3,
            "proposal_prompt": {},
            "parent_prompt": {},
            "subsample_ids": ["3", "4", "5"],
            "per_example_parent": [
                {"id": "3", "score": 1.0},
                {"id": "4", "score": 1.0},
                {"id": "5", "score": 1.0},
            ],
            "per_example_proposal": [
                {"id": "3", "score": 0.0},
                {"id": "4", "score": 1.0},
                {"id": "5", "score": 1.0},
            ],
        }

    def test_prompts_are_surfaced_when_snapshots_are_present(self) -> None:
        """``capture_proposal_prompts`` writes snapshots that the extractor reads."""
        trace = _trace_with_one_acceptance_one_rejection()
        trace[1]["parent_prompt_snapshot"] = {"qa": "Answer the question."}
        trace[1]["proposed_prompt_snapshot"] = {"qa": "Answer step by step."}
        event = extract_rejected_from_trace({"full_program_trace": trace}, last_seen_iteration=-1)[0]
        assert event.parent_prompt == {"qa": "Answer the question."}
        assert event.proposal_prompt == {"qa": "Answer step by step."}

    def test_missing_trace_returns_empty_list(self) -> None:
        """A state without ``full_program_trace`` yields ``[]``."""
        assert extract_rejected_from_trace({}, last_seen_iteration=-1) == []


class TestRejectedEvent:
    """Lock immutability invariants on the dataclass."""

    def test_is_frozen(self) -> None:
        """``RejectedEvent`` is immutable like ``CandidateEvent``."""
        event = RejectedEvent(
            rejection_id="r0",
            iteration=0,
            parent_id="0",
            parent_score=0.0,
            proposal_score=0.0,
            subsample_size=1,
            proposal_prompt={},
            parent_prompt={},
            subsample_ids=(),
            per_example_parent=(),
            per_example_proposal=(),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.iteration = 99  # type: ignore[misc]


class TestCandidateEvent:
    """Lock the dataclass invariants the consumer relies on."""

    def test_is_frozen(self) -> None:
        """``CandidateEvent`` is immutable so producers can't mutate after dispatch."""
        event = CandidateEvent(
            id="0",
            parent_id=None,
            parents_extra=(),
            generation=0,
            score=0.0,
            per_example=(),
            prompt={},
            discovered_at_evals=0,
            iteration=None,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.id = "999"  # type: ignore[misc]


class TestLoadState:
    """Both cloudpickle and stdlib pickle payloads round-trip; partials return None."""

    def test_loads_cloudpickle_payload(self) -> None:
        """Files written via ``cloudpickle.dump`` are decoded into the state dict."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gepa_state.bin")
            with open(path, "wb") as fh:
                cloudpickle.dump(_minimal_state(), fh)
            loaded = _load_state(path)
            assert isinstance(loaded, dict)
            assert loaded["program_candidates"] == _minimal_state()["program_candidates"]

    def test_loads_stdlib_pickle_payload(self) -> None:
        """Stdlib pickle is the fallback when cloudpickle.loads fails."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gepa_state.bin")
            with open(path, "wb") as fh:
                pickle.dump(_minimal_state(), fh)
            loaded = _load_state(path)
            assert isinstance(loaded, dict)

    def test_truncated_file_returns_none(self) -> None:
        """Mid-write race produces a non-deserialisable file → ``None`` (no raise)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gepa_state.bin")
            with open(path, "wb") as fh:
                fh.write(b"not-a-pickle")
            assert _load_state(path) is None

    def test_missing_file_returns_none(self) -> None:
        """Pre-first-iteration polls don't raise when the file is absent."""
        assert _load_state("/tmp/__definitely_missing_gepa_state__.bin") is None


class TestGepaLogDir:
    """The optimizer-gated tempdir context yields ``None`` for non-GEPA optimizers."""

    def test_returns_path_for_gepa(self) -> None:
        """GEPA gets a real temporary directory that exists during the block."""
        with gepa_log_dir("gepa") as log_dir:
            assert log_dir is not None
            assert os.path.isdir(log_dir)

    def test_returns_none_for_other_optimizers(self) -> None:
        """No tempdir is allocated for optimizers that don't use ``log_dir``."""
        with gepa_log_dir("bootstrap_fewshot") as log_dir:
            assert log_dir is None

    def test_directory_is_cleaned_up_on_exit(self) -> None:
        """The tempdir is removed when the context exits."""
        with gepa_log_dir("gepa") as log_dir:
            assert log_dir is not None
            captured = log_dir
        assert not os.path.exists(captured)


class TestTrajectoryWatchNoop:
    """When either input is missing, ``trajectory_watch`` is a pure no-op."""

    def test_skips_when_log_dir_none(self) -> None:
        """Non-GEPA optimizers pass ``None`` log_dir; the watcher must not start."""
        events: list[tuple] = []
        callback = lambda event, metrics: events.append((event, metrics))
        with trajectory_watch(None, callback):
            pass
        assert events == []

    def test_skips_when_callback_none(self) -> None:
        """Runs without a progress callback have nothing to forward to."""
        with tempfile.TemporaryDirectory() as tmp:
            with trajectory_watch(tmp, None):
                pass


class TestSerializeValsetRows:
    """Lock the JSON shape the Pareto-cell drawer reads from the SSE stream."""

    def test_dspy_examples_round_trip_to_string_maps(self) -> None:
        """Each Example becomes ``{"id": str(idx), "inputs": {...}, "outputs": {...}}``."""
        valset = [
            dspy.Example(question="2+2", answer="4").with_inputs("question"),
            dspy.Example(question="3+3", answer="6").with_inputs("question"),
        ]
        rows = serialize_valset_rows(valset)
        assert rows == [
            {"id": "0", "inputs": {"question": "2+2"}, "outputs": {"answer": "4"}},
            {"id": "1", "inputs": {"question": "3+3"}, "outputs": {"answer": "6"}},
        ]

    def test_ids_match_gepa_subscore_keys(self) -> None:
        """Ids are sequential integer strings starting at ``"0"`` so the frontend
        can join them against per-example score keys."""
        rows = serialize_valset_rows(
            [dspy.Example(q="a", a="x").with_inputs("q") for _ in range(3)]
        )
        assert [r["id"] for r in rows] == ["0", "1", "2"]

    def test_plain_dict_fallback_uses_dict_as_inputs(self) -> None:
        """Non-DSPy rows (test fixtures) treat the dict as inputs with empty outputs."""
        rows = serialize_valset_rows([{"question": "2+2", "context": "math"}])
        assert rows == [
            {
                "id": "0",
                "inputs": {"question": "2+2", "context": "math"},
                "outputs": {},
            }
        ]

    def test_oversized_field_is_truncated_with_marker(self) -> None:
        """Field values longer than the cap end with ``"…"`` so the UI can flag them."""
        big = "x" * (VALSET_FIELD_CHAR_CAP + 50)
        ex = dspy.Example(blob=big, label="y").with_inputs("blob")
        rows = serialize_valset_rows([ex])
        rendered = rows[0]["inputs"]["blob"]
        assert len(rendered) == VALSET_FIELD_CHAR_CAP + 1
        assert rendered.endswith("…")

    def test_empty_valset_returns_empty_list(self) -> None:
        """Runs without a validation split yield ``[]``, not ``None``."""
        assert serialize_valset_rows([]) == []


class TestEmitValsetEvent:
    """The fire-and-forget emitter must respect the SSE contract."""

    def test_emits_progress_valset_with_rows_payload(self) -> None:
        """Single ``PROGRESS_VALSET`` event carries a ``rows`` list."""
        events: list[tuple[str, dict]] = []
        emit_valset_event(
            [dspy.Example(q="a", a="x").with_inputs("q")],
            lambda event, metrics: events.append((event, metrics)),
        )
        assert len(events) == 1
        assert events[0][0] == PROGRESS_VALSET
        assert events[0][1] == {
            "rows": [{"id": "0", "inputs": {"q": "a"}, "outputs": {"a": "x"}}]
        }

    def test_noop_when_callback_missing(self) -> None:
        """Non-streaming code paths pass ``None`` and must get no exception."""
        emit_valset_event([dspy.Example(q="a").with_inputs("q")], None)

    def test_noop_when_valset_empty(self) -> None:
        """Empty splits don't emit an event (frontend treats absence as 'no rows')."""
        events: list[tuple[str, dict]] = []
        emit_valset_event([], lambda event, metrics: events.append((event, metrics)))
        assert events == []

    def test_callback_exception_is_swallowed(self) -> None:
        """A raising callback must not abort the optimization."""
        def raising(event: str, metrics: dict) -> None:
            raise RuntimeError("downstream broke")

        emit_valset_event(
            [dspy.Example(q="a").with_inputs("q")],
            raising,
        )


class TestMinibatchRecorder:
    """Composition wrapper that turns metric calls with feedback into SSE events."""

    def test_passes_through_numeric_metric_without_emitting_minibatch(self) -> None:
        """Bare-float returns mean a non-feedback eval; no minibatch event fires."""
        events: list[tuple[str, dict]] = []
        ex = dspy.Example(q="a").with_inputs("q")
        recorder = MinibatchRecorder(
            lambda *_, **__: 0.75,
            [ex],
            lambda event, metrics: events.append((event, metrics)),
        )
        result = recorder(ex, dspy.Prediction(answer="x"))
        assert result == 0.75
        assert not any(e == PROGRESS_MINIBATCH for e, _ in events)

    def test_emits_when_metric_returns_prediction_with_feedback(self) -> None:
        """Prediction-shaped returns with ``feedback`` text fire one event each."""
        events: list[tuple[str, dict]] = []
        ex = dspy.Example(q="a").with_inputs("q")
        recorder = MinibatchRecorder(
            lambda *_, **__: dspy.Prediction(score=0.4, feedback="needs more context"),
            [ex],
            lambda event, metrics: events.append((event, metrics)),
        )
        recorder(ex, dspy.Prediction(answer="x"))
        minibatch_events = [m for e, m in events if e == PROGRESS_MINIBATCH]
        assert len(minibatch_events) == 1
        metrics = minibatch_events[0]
        assert metrics["example_id"] == "0"
        assert metrics["score"] == 0.4
        assert metrics["feedback"] == "needs more context"
        assert "prediction" in metrics

    def test_returns_underlying_metric_value_unchanged(self) -> None:
        """Wrapper is transparent — the optimizer sees exactly what the metric returned."""
        ex = dspy.Example(q="a").with_inputs("q")
        pred_obj = dspy.Prediction(score=0.9, feedback="nice")
        recorder = MinibatchRecorder(
            lambda *_, **__: pred_obj,
            [ex],
            lambda *_: None,
        )
        assert recorder(ex, dspy.Prediction(answer="x")) is pred_obj

    def test_example_id_falls_back_when_identity_unknown(self) -> None:
        """Unknown example identities surface as ``"?"`` rather than raising."""
        events: list[tuple[str, dict]] = []
        ex_registered = dspy.Example(q="a").with_inputs("q")
        ex_unknown = dspy.Example(q="b").with_inputs("q")
        recorder = MinibatchRecorder(
            lambda *_, **__: dspy.Prediction(score=0.0, feedback="missed"),
            [ex_registered],
            lambda event, metrics: events.append((event, metrics)),
        )
        recorder(ex_unknown, dspy.Prediction(answer="?"))
        assert events[0][1]["example_id"] == "?"

    def test_feedback_is_truncated_to_cap(self) -> None:
        """Oversized feedback is capped so SSE payloads stay bounded."""
        events: list[tuple[str, dict]] = []
        ex = dspy.Example(q="a").with_inputs("q")
        big = "x" * (MINIBATCH_FEEDBACK_CHAR_CAP + 50)
        recorder = MinibatchRecorder(
            lambda *_, **__: dspy.Prediction(score=0.0, feedback=big),
            [ex],
            lambda event, metrics: events.append((event, metrics)),
        )
        recorder(ex, dspy.Prediction(answer="x"))
        assert len(events[0][1]["feedback"]) == MINIBATCH_FEEDBACK_CHAR_CAP

    def test_prediction_repr_is_truncated_to_cap(self) -> None:
        """Long predictions are length-capped before being placed on the wire."""
        events: list[tuple[str, dict]] = []
        ex = dspy.Example(q="a").with_inputs("q")
        recorder = MinibatchRecorder(
            lambda *_, **__: dspy.Prediction(score=0.0, feedback="short"),
            [ex],
            lambda event, metrics: events.append((event, metrics)),
        )
        recorder(ex, dspy.Prediction(answer="y" * (MINIBATCH_PREDICTION_CHAR_CAP + 200)))
        assert len(events[0][1]["prediction"]) == MINIBATCH_PREDICTION_CHAR_CAP + 1
        assert events[0][1]["prediction"].endswith("…")

    def test_callback_exception_does_not_break_metric_call(self) -> None:
        """A raising progress callback never aborts the optimizer's metric call."""
        ex = dspy.Example(q="a").with_inputs("q")
        def raising(event: str, metrics: dict) -> None:
            raise RuntimeError("downstream broke")

        recorder = MinibatchRecorder(
            lambda *_, **__: dspy.Prediction(score=1.0, feedback="ok"),
            [ex],
            raising,
        )
        result = recorder(ex, dspy.Prediction(answer="x"))
        assert getattr(result, "score") == 1.0

    def test_forwards_extra_args_and_kwargs_to_metric(self) -> None:
        """GEPA passes ``trace``/``pred_name``/``pred_trace`` — they must reach the metric."""
        seen: dict[str, Any] = {}
        ex = dspy.Example(q="a").with_inputs("q")

        def metric(example: Any, prediction: Any, *args: Any, **kwargs: Any) -> float:
            seen["args"] = args
            seen["kwargs"] = kwargs
            return 0.5

        recorder = MinibatchRecorder(metric, [ex], lambda *_: None)
        recorder(ex, dspy.Prediction(answer="x"), "trace-obj", pred_name="qa")
        assert seen["args"] == ("trace-obj",)
        assert seen["kwargs"] == {"pred_name": "qa"}

    def test_full_valset_sweep_emits_one_outputs_event_with_indices(self) -> None:
        """Once the buffer covers every valset id the recorder flushes a snapshot."""
        events: list[tuple[str, dict]] = []
        examples = [dspy.Example(q=str(i)).with_inputs("q") for i in range(3)]
        recorder = MinibatchRecorder(
            lambda ex, _pred, *_, **__: 0.5,
            examples,
            lambda event, metrics: events.append((event, metrics)),
        )
        for idx, ex in enumerate(examples):
            recorder(ex, dspy.Prediction(answer=f"a{idx}"))

        outputs_events = [m for e, m in events if e == PROGRESS_VALSET_OUTPUTS]
        assert len(outputs_events) == 1
        assert outputs_events[0]["candidate_index"] == 0
        predictions = outputs_events[0]["predictions"]
        assert [p["example_id"] for p in predictions] == ["0", "1", "2"]
        assert all(p["score"] == 0.5 for p in predictions)

    def test_consecutive_sweeps_increment_candidate_index(self) -> None:
        """Successive full passes attribute to candidate 0, 1, 2, … in order."""
        events: list[tuple[str, dict]] = []
        examples = [dspy.Example(q=str(i)).with_inputs("q") for i in range(2)]
        recorder = MinibatchRecorder(
            lambda *_, **__: 0.0,
            examples,
            lambda event, metrics: events.append((event, metrics)),
        )
        for _ in range(3):
            for idx, ex in enumerate(examples):
                recorder(ex, dspy.Prediction(answer=f"a{idx}"))

        outputs_events = [m for e, m in events if e == PROGRESS_VALSET_OUTPUTS]
        assert [m["candidate_index"] for m in outputs_events] == [0, 1, 2]

    def test_partial_minibatch_calls_do_not_emit_outputs_event(self) -> None:
        """A subset that never covers every id can't flush a sweep."""
        events: list[tuple[str, dict]] = []
        examples = [dspy.Example(q=str(i)).with_inputs("q") for i in range(3)]
        recorder = MinibatchRecorder(
            lambda *_, **__: dspy.Prediction(score=0.1, feedback="hint"),
            examples,
            lambda event, metrics: events.append((event, metrics)),
        )
        recorder(examples[0], dspy.Prediction(answer="a"))
        recorder(examples[1], dspy.Prediction(answer="b"))

        assert not any(e == PROGRESS_VALSET_OUTPUTS for e, _ in events)
        assert sum(1 for e, _ in events if e == PROGRESS_MINIBATCH) == 2


class TestMaybeWrapMinibatchRecorder:
    """The gating helper applies only when GEPA + callback are both present."""

    def test_returns_recorder_for_gepa_with_callback(self) -> None:
        """GEPA + callback yields a MinibatchRecorder wrapping the metric."""
        wrapped = maybe_wrap_minibatch_recorder(
            lambda *_, **__: 0.0,
            [dspy.Example(q="a").with_inputs("q")],
            "gepa",
            lambda *_: None,
        )
        assert isinstance(wrapped, MinibatchRecorder)

    def test_returns_raw_metric_when_callback_missing(self) -> None:
        """Without a progress callback there's nowhere to send events, so skip wrapping."""
        metric = lambda *_, **__: 0.0
        wrapped = maybe_wrap_minibatch_recorder(
            metric,
            [dspy.Example(q="a").with_inputs("q")],
            "gepa",
            None,
        )
        assert wrapped is metric

    def test_returns_raw_metric_for_non_gepa_optimizer(self) -> None:
        """Other optimizers don't produce minibatch feedback — pass-through."""
        metric = lambda *_, **__: 0.0
        wrapped = maybe_wrap_minibatch_recorder(
            metric,
            [dspy.Example(q="a").with_inputs("q")],
            "bootstrap_fewshot",
            lambda *_: None,
        )
        assert wrapped is metric


class TestCaptureProposalPrompts:
    """The propose() wrapper writes prompt snapshots onto the latest trace entry."""

    def test_noop_for_non_gepa_optimizer(self) -> None:
        """Non-GEPA optimizers don't have a reflective proposer — context is a no-op."""
        with capture_proposal_prompts("bootstrap_fewshot"):
            pass

    def test_writes_snapshots_after_proposer_returns(self) -> None:
        """A captured ``propose`` call leaves parent + proposed prompt in the trace."""

        class _FakeState:
            """Minimal stand-in for GEPAState that exposes the fields we touch."""

            def __init__(self) -> None:
                self.program_candidates = [{"qa": "Answer the question."}]
                self.full_program_trace: list[dict] = [
                    {"i": 0, "selected_program_candidate": 0}
                ]

        captured_state = _FakeState()
        proposed_text = {"qa": "Answer in detail."}

        def fake_original(self: object, state: object) -> CandidateProposal:
            """Pretend to be the original propose method, returning the proposed candidate."""
            return CandidateProposal(
                candidate=proposed_text,
                parent_program_ids=[0],
                subsample_indices=[0],
                subsample_scores_before=[0.5],
                subsample_scores_after=[0.4],
                tag="reflective_mutation",
            )

        original = ReflectiveMutationProposer.propose
        ReflectiveMutationProposer.propose = fake_original  # type: ignore[method-assign]
        try:
            with capture_proposal_prompts("gepa"):
                ReflectiveMutationProposer.propose(None, captured_state)  # type: ignore[arg-type]
        finally:
            ReflectiveMutationProposer.propose = original  # type: ignore[method-assign]

        entry = captured_state.full_program_trace[-1]
        assert entry["parent_prompt_snapshot"] == {"qa": "Answer the question."}
        assert entry["proposed_prompt_snapshot"] == {"qa": "Answer in detail."}

    def test_restores_original_propose_after_context_exits(self) -> None:
        """Wrapper must unhook itself even when the inner block raises."""
        original = ReflectiveMutationProposer.propose
        with capture_proposal_prompts("gepa"):
            assert ReflectiveMutationProposer.propose is not original
        assert ReflectiveMutationProposer.propose is original
