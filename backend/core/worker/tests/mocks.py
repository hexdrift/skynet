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
from functools import cache
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

_FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


@cache
def _read_fixture_text(name: str) -> str:
    """Read a fixture file once and cache its text.

    Args:
        name: Fixture path relative to the fixtures root.

    Returns:
        Raw text of the fixture file.
    """
    return (_FIXTURES_ROOT / name).read_text()


def load_fixture(name: str) -> Any:
    """Load a JSON fixture by relative path.

    Args:
        name: Fixture path relative to the fixtures root.

    Returns:
        Parsed JSON value (typically a dict).
    """
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
    """Build a synthetic ``EVENT_LOG`` dict for tests.

    Args:
        msg: Log message text.
        level: Log level name.
        logger: Originating logger name.
        timestamp: ISO 8601 timestamp string.

    Returns:
        Dict matching the ``EVENT_LOG`` shape produced by the runner.
    """
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
    """Build a synthetic ``EVENT_PROGRESS`` dict for tests.

    Args:
        phase: Phase label.
        metrics: Metric snapshot, defaults to a copy of the first GEPA event.
        timestamp: ISO 8601 timestamp string.

    Returns:
        Dict matching the ``EVENT_PROGRESS`` shape produced by the runner.
    """
    if metrics is None:
        metrics = dict(_GEPA_PROGRESS[0]["metrics"])
    return {
        "type": "progress",
        "event": phase,
        "metrics": metrics,
        "timestamp": timestamp,
    }


def make_result_event(result: dict | None = None) -> dict:
    """Build a synthetic ``EVENT_RESULT`` dict for tests.

    Args:
        result: Result payload; defaults to a copy of ``REAL_RESULT``.

    Returns:
        Dict matching the ``EVENT_RESULT`` shape produced by the runner.
    """
    return {"type": "result", "result": result if result is not None else dict(REAL_RESULT)}


def make_error_event(
    error: str = "RuntimeError: model exploded",
    traceback: str = "Traceback (most recent call last):\n  ...",
) -> dict:
    """Build a synthetic ``EVENT_ERROR`` dict for tests.

    Args:
        error: Error string.
        traceback: Formatted traceback string.

    Returns:
        Dict matching the ``EVENT_ERROR`` shape produced by the runner.
    """
    return {"type": "error", "error": error, "traceback": traceback}


def fake_dspy_service(result: dict | None = None) -> MagicMock:
    """Return a MagicMock DspyService with ``run`` and ``run_grid_search`` wired.

    Args:
        result: Result dict the mock should yield via ``model_dump``.

    Returns:
        A MagicMock whose run/run_grid_search return the same fake result.
    """
    result_payload = result if result is not None else dict(REAL_RESULT)
    fake_result = MagicMock()
    fake_result.model_dump.return_value = result_payload

    svc = MagicMock()
    svc.run.return_value = fake_result
    svc.run_grid_search.return_value = fake_result
    return svc


def fake_service_registry() -> MagicMock:
    """Return a MagicMock standing in for ``ServiceRegistry``."""
    return MagicMock()


def fake_mp_queue(*events: dict) -> MagicMock:
    """Return a MagicMock queue prefilled with ``events`` for ``get_nowait`` consumption.

    Args:
        *events: Events to enqueue, in order.

    Returns:
        A MagicMock with ``get_nowait``/``close``/``join_thread`` methods wired.
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
    """Return a MagicMock process with configurable ``exitcode`` and ``is_alive``.

    Args:
        exitcode: Value placed on ``proc.exitcode``.
        is_alive: ``list[bool]`` consumed as side-effect, or single ``bool``.

    Returns:
        A MagicMock standing in for ``mp.Process``.
    """
    proc = MagicMock()
    proc.exitcode = exitcode
    if isinstance(is_alive, list):
        proc.is_alive.side_effect = is_alive
    else:
        proc.is_alive.return_value = False if is_alive is None else is_alive
    return proc


def make_mp_context(exitcode: int = 0, result_events: list | None = None) -> tuple[MagicMock, MagicMock]:
    """Build a fake mp context whose Queue is preloaded and Process is already dead.

    Args:
        exitcode: Exit code to expose on the fake process.
        result_events: Events to seed onto the fake queue.

    Returns:
        ``(ctx, proc)`` mocks suitable for assigning to a worker's ``_mp_ctx``.
    """
    result_events = result_events or []
    proc = fake_mp_process(exitcode=exitcode)
    mq = fake_mp_queue(*result_events)

    ctx = MagicMock()
    ctx.Queue.return_value = mq
    ctx.Process.return_value = proc
    ctx.get_start_method.return_value = "spawn"
    return ctx, proc
