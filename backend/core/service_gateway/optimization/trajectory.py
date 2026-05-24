"""Per-candidate event extraction from a running GEPA optimization.

GEPA persists its full state to ``<run_dir>/gepa_state.bin`` (cloudpickle) at
the start of every iteration plus once after the loop exits. This module
watches that file and converts new accepted candidates into structured
progress events the frontend can render as a genealogy tree.

Only accepted candidates flow through ``gepa_state.bin`` — rejected proposals
are visible only in GEPA's text log and are captured by a separate follow-up
mechanism, not here.
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

from ...constants import OPTIMIZER_NAME_GEPA, PROGRESS_CANDIDATE

logger = logging.getLogger(__name__)


GEPA_STATE_FILENAME = "gepa_state.bin"


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
    """

    id: str
    parent_id: str | None
    parents_extra: tuple[str, ...]
    generation: int
    score: float
    per_example: tuple[tuple[str, float], ...]
    prompt: dict[str, str]
    discovered_at_evals: int

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
        }


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
            )
        )
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
