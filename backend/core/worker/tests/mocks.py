"""Centralized mock builders for core/worker/tests/.

All fakes here carry realistic data pulled from tests/fixtures/.

Division of responsibilities:
  - conftest.py  — FakeJobStore (stateful in-memory store, pytest fixture)
  - mocks.py     — stateless builder functions for external collaborators
                   (DspyService, ServiceRegistry, mp.Queue, mp.Process)

Usage example:
    from .mocks import fake_dspy_service, fake_mp_process, REAL_RUN_PAYLOAD
"""

from __future__ import annotations

import json
import queue
from functools import lru_cache
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

_FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


@lru_cache(maxsize=None)
def _read_fixture_text(name: str) -> str:
    return (_FIXTURES_ROOT / name).read_text()


def load_fixture(name: str) -> Any:
    return json.loads(_read_fixture_text(name))

_GRID = load_fixture("jobs/success_grid.detail.json")
_GEPA = load_fixture("jobs/success_single_gepa.detail.json")

REAL_OPTIMIZATION_ID: str = _GEPA["optimization_id"]
REAL_GRID_OPTIMIZATION_ID: str = _GRID["optimization_id"]

# Real result payload from the gepa run (sans large blobs).
REAL_RESULT: dict = {
    k: v
    for k, v in _GEPA["result"].items()
    if k
    not in (
        "program_artifact",
        "baseline_test_results",
        "optimized_test_results",
        "run_log",
        "details",
        "optimization_metadata",
    )
}

# Submission payload shapes mirroring what engine._process_job receives.
REAL_RUN_PAYLOAD: dict = {
    "username": _GEPA["username"],
    "module_name": _GEPA["module_name"],
    "signature_code": "question -> answer",
    "metric_code": "def metric(example, pred, trace=None): return True",
    "optimizer_name": _GEPA["optimizer_name"],
    "dataset": [{"question": "Q1", "answer": "A1"}],
    "column_mapping": _GEPA["column_mapping"],
    "model_settings": _GEPA["model_settings"],
    "_optimization_type": "run",
}

REAL_GRID_PAYLOAD: dict = {
    "username": _GRID["username"],
    "module_name": _GRID["module_name"],
    "signature_code": "question -> answer",
    "metric_code": "def metric(example, pred, trace=None): return True",
    "optimizer_name": _GRID["optimizer_name"],
    "dataset": [{"question": "Q1", "answer": "A1"}],
    "column_mapping": _GRID["column_mapping"],
    "generation_models": _GRID["generation_models"],
    "reflection_models": _GRID["reflection_models"],
    "_optimization_type": "grid_search",
}

_GEPA_PROGRESS = _GEPA["progress_events"]
_GEPA_LOGS = _GEPA["logs"]


def make_log_event(
    msg: str = _GEPA_LOGS[0]["message"],
    level: str = "INFO",
    logger: str = "dspy.evaluate.evaluate",
    timestamp: str = _GEPA_LOGS[0]["timestamp"],
) -> dict:
    """Return a dict shaped like a real EVENT_LOG event."""
    return {
        "type": "log",
        "level": level,
        "logger": logger,
        "message": msg,
        "timestamp": timestamp,
    }


def make_progress_event(
    phase: str = _GEPA_PROGRESS[0]["event"],
    metrics: dict | None = None,
    timestamp: str = _GEPA_PROGRESS[0]["timestamp"],
) -> dict:
    """Return a dict shaped like a real EVENT_PROGRESS event."""
    if metrics is None:
        metrics = dict(_GEPA_PROGRESS[0]["metrics"])
    return {
        "type": "progress",
        "event": phase,
        "metrics": metrics,
        "timestamp": timestamp,
    }


def make_result_event(result: dict | None = None) -> dict:
    """Return a dict shaped like a real EVENT_RESULT event."""
    return {"type": "result", "result": result if result is not None else dict(REAL_RESULT)}


def make_error_event(
    error: str = "RuntimeError: model exploded",
    traceback: str = "Traceback (most recent call last):\n  ...",
) -> dict:
    """Return a dict shaped like a real EVENT_ERROR event."""
    return {"type": "error", "error": error, "traceback": traceback}



def fake_dspy_service(result: dict | None = None) -> MagicMock:
    """Return a MagicMock DspyService whose .run() returns a realistic RunResponse.

    Args:
        result: Optional override for the result dict. Defaults to REAL_RESULT.
    """
    result_payload = result if result is not None else dict(REAL_RESULT)
    fake_result = MagicMock()
    fake_result.model_dump.return_value = result_payload

    svc = MagicMock()
    svc.run.return_value = fake_result
    svc.run_grid_search.return_value = fake_result
    return svc


def fake_service_registry() -> MagicMock:
    """Return a MagicMock ServiceRegistry (no meaningful configuration needed)."""
    return MagicMock()


def fake_mp_queue(*events: dict) -> MagicMock:
    """Return a MagicMock that behaves like a multiprocessing.Queue for drain purposes.

    Backed by a real queue.Queue pre-filled with *events* so that
    get_nowait() works correctly. close() and join_thread() are no-ops.
    """
    q: queue.Queue = queue.Queue()
    for event in events:
        q.put(event)

    mock_q = MagicMock()
    mock_q.get_nowait.side_effect = q.get_nowait
    mock_q.close.return_value = None
    mock_q.join_thread.return_value = None
    return mock_q


def fake_mp_process(
    exitcode: int = 0,
    is_alive: bool | list[bool] | None = None,
) -> MagicMock:
    """Return a MagicMock multiprocessing.Process.

    Args:
        exitcode: Value of proc.exitcode after the process finishes.
        is_alive: If a list, used as side_effect for successive is_alive() calls.
                  If a single bool, returned on every call. Defaults to False
                  (process already dead).
    """
    proc = MagicMock()
    proc.exitcode = exitcode
    if isinstance(is_alive, list):
        proc.is_alive.side_effect = is_alive
    else:
        proc.is_alive.return_value = False if is_alive is None else is_alive
    return proc


def make_mp_context(exitcode: int = 0, result_events: list | None = None) -> tuple[MagicMock, MagicMock]:
    """Return (ctx_mock, proc_mock) simulating a completed subprocess.

    The process is already dead (is_alive=False), so _process_job skips the
    poll loop and goes straight to the final drain.  result_events are
    pre-loaded into the queue returned by ctx.Queue().
    """
    result_events = result_events or []
    proc = fake_mp_process(exitcode=exitcode)
    mq = fake_mp_queue(*result_events)

    ctx = MagicMock()
    ctx.Queue.return_value = mq
    ctx.Process.return_value = proc
    ctx.get_start_method.return_value = "spawn"
    return ctx, proc
