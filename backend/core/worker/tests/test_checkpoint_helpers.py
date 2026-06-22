"""Tests for the worker's GEPA checkpoint persist/restore helpers.

Exercises ``_checkpoints_enabled``, ``_prepare_gepa_dir`` (restore-on-resume) and
``_persist_gepa_checkpoint`` (mtime-gated save) directly — the durable half of
resume, for both a single run and a grid of per-pair runs — without spinning up
the optimization subprocess.
"""

from __future__ import annotations

import json
import shutil
from types import SimpleNamespace
from typing import cast

from core.constants import OPTIMIZATION_TYPE_GRID_SEARCH, OPTIMIZATION_TYPE_RUN
from core.service_gateway.optimization.trajectory import GEPA_STATE_FILENAME, GRID_PAIR_RESULT_FILENAME
from core.storage import JobStore
from core.worker.engine import BackgroundWorker


class _CheckpointStore:
    """In-memory stand-in exposing the checkpoint/pair-result surface the helpers use."""

    def __init__(self) -> None:
        """Start with no saved checkpoints or pair results."""
        self.checkpoints: dict[int, tuple[bytes, int]] = {}
        self.pair_results: dict[int, dict] = {}

    def save_gepa_checkpoint(self, optimization_id: str, data: bytes, iteration: int, pair_index: int = -1) -> None:
        """Record one run/pair's checkpoint bytes and iteration."""
        self.checkpoints[pair_index] = (data, iteration)

    def get_gepa_checkpoint(self, optimization_id: str, pair_index: int = -1):
        """Return one run/pair's checkpoint record, or ``None``."""
        row = self.checkpoints.get(pair_index)
        if row is None:
            return None
        return SimpleNamespace(pair_index=pair_index, data=row[0], iteration=row[1], stored_bytes=len(row[0]))

    def list_gepa_checkpoints(self, optimization_id: str):
        """Return every stored checkpoint record."""
        return [self.get_gepa_checkpoint(optimization_id, idx) for idx in self.checkpoints]

    def delete_gepa_checkpoint(self, optimization_id: str, pair_index: int = -1) -> None:
        """Drop one run/pair's checkpoint."""
        self.checkpoints.pop(pair_index, None)

    def save_grid_pair_result(self, optimization_id: str, pair_index: int, result: dict) -> None:
        """Record one finished grid pair's result."""
        self.pair_results[pair_index] = result


def _worker(store: object) -> BackgroundWorker:
    """Build a worker bound to ``store`` (never started)."""
    return BackgroundWorker(job_store=cast(JobStore, store))


def test_checkpoints_enabled_for_runs_and_grids_on_capable_store() -> None:
    """Enabled for single runs AND grids on a capable store; off for an incapable one."""
    worker = _worker(_CheckpointStore())
    assert worker._checkpoints_enabled(OPTIMIZATION_TYPE_RUN) is True
    assert worker._checkpoints_enabled(OPTIMIZATION_TYPE_GRID_SEARCH) is True
    assert _worker(object())._checkpoints_enabled(OPTIMIZATION_TYPE_RUN) is False


def test_single_run_persist_is_mtime_gated_and_prepare_restores() -> None:
    """Single run: persist saves on change only; a later prepare seeds state back."""
    store = _CheckpointStore()
    worker = _worker(store)

    base = worker._prepare_gepa_dir("w1", is_grid=False)
    try:
        assert base.exists()
        assert not (base / GEPA_STATE_FILENAME).exists()

        (base / GEPA_STATE_FILENAME).write_bytes(b"STATE-1")
        tracker: dict = {}
        worker._persist_gepa_checkpoint("w1", base, tracker, is_grid=False)
        assert store.checkpoints[-1] == (b"STATE-1", 1)

        before = store.checkpoints[-1]
        worker._persist_gepa_checkpoint("w1", base, tracker, is_grid=False)
        assert store.checkpoints[-1] is before  # unchanged mtime → no re-save
    finally:
        shutil.rmtree(base, ignore_errors=True)

    base2 = worker._prepare_gepa_dir("w1", is_grid=False)
    try:
        assert (base2 / GEPA_STATE_FILENAME).read_bytes() == b"STATE-1"
    finally:
        shutil.rmtree(base2, ignore_errors=True)


def test_grid_persist_stores_finished_pairs_and_checkpoints_in_flight() -> None:
    """Grid: a pair's result.json is stored (and its checkpoint dropped); others persist state."""
    store = _CheckpointStore()
    worker = _worker(store)

    base = worker._prepare_gepa_dir("g1", is_grid=True)
    try:
        # Pair 0 finished → result.json; pair 1 still in-flight → gepa_state.bin.
        (base / "pair_0").mkdir()
        (base / "pair_0" / GRID_PAIR_RESULT_FILENAME).write_text(json.dumps({"pair_index": 0, "optimized_test_metric": 0.8}))
        (base / "pair_0" / GEPA_STATE_FILENAME).write_bytes(b"P0-STATE")
        (base / "pair_1").mkdir()
        (base / "pair_1" / GEPA_STATE_FILENAME).write_bytes(b"P1-STATE")

        tracker: dict = {}
        worker._persist_gepa_checkpoint("g1", base, tracker, is_grid=True)

        # Finished pair 0: result stored, no checkpoint kept.
        assert store.pair_results[0]["optimized_test_metric"] == 0.8
        assert 0 not in store.checkpoints
        # In-flight pair 1: checkpoint persisted under its index.
        assert store.checkpoints[1] == (b"P1-STATE", 1)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_grid_prepare_restores_in_flight_pair_checkpoints() -> None:
    """Grid resume: saved pair checkpoints are written back under their pair dirs."""
    store = _CheckpointStore()
    store.checkpoints = {0: (b"P0", 3), 2: (b"P2", 5)}
    worker = _worker(store)

    base = worker._prepare_gepa_dir("g2", is_grid=True)
    try:
        assert (base / "pair_0" / GEPA_STATE_FILENAME).read_bytes() == b"P0"
        assert (base / "pair_2" / GEPA_STATE_FILENAME).read_bytes() == b"P2"
        assert not (base / "pair_1").exists()  # pair 1 had no checkpoint (e.g. already finished)
    finally:
        shutil.rmtree(base, ignore_errors=True)
