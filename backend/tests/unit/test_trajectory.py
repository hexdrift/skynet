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

from core.service_gateway.optimization.trajectory import (
    CandidateEvent,
    _load_state,
    extract_candidates_from_state,
    gepa_log_dir,
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
        }

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
