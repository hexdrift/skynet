"""Unit tests for core.worker.subprocess_runner.

Covers (all in-process, no real subprocesses):
  safe_queue_put              — normal put and error suppression
  set_fork_service            — stores / clears module global
  SubprocessLogHandler        — emit field capture, fallback on format error, UTC timestamp
  run_service_in_subprocess   — happy path, exception path, dispatch, progress callback
"""

from __future__ import annotations

import logging
import queue
from unittest.mock import MagicMock, patch

import pytest

import core.worker.subprocess_runner as sr
from core.worker.subprocess_runner import (
    EVENT_ERROR,
    EVENT_LOG,
    EVENT_PROGRESS,
    EVENT_RESULT,
    SubprocessLogHandler,
    run_service_in_subprocess,
    safe_queue_put,
    set_fork_service,
)
from .mocks import REAL_GRID_PAYLOAD, REAL_RUN_PAYLOAD, fake_dspy_service, fake_service_registry



def _make_queue() -> queue.Queue:
    """Return a fresh empty in-process queue."""
    return queue.Queue()


def _make_record(
    msg: str = "hello",
    level: int = logging.INFO,
    logger_name: str = "dspy.test",
) -> logging.LogRecord:
    """Build a minimal LogRecord with the given message, level, and logger name."""
    return logging.LogRecord(
        name=logger_name,
        level=level,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )


def _make_handler(q: queue.Queue) -> SubprocessLogHandler:
    """Build a SubprocessLogHandler with a plain-message formatter."""
    handler = SubprocessLogHandler(event_queue=q)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler



def test_safe_queue_put_places_event_on_queue() -> None:
    """safe_queue_put() delivers the event dict to a functioning queue."""
    q = _make_queue()
    event = {"type": "test", "val": 1}

    safe_queue_put(q, event)

    assert q.get_nowait() == event


def test_safe_queue_put_suppresses_exception_from_broken_queue() -> None:
    """safe_queue_put must never propagate exceptions from a failing queue."""

    class _BrokenQueue:
        def put(self, item: object) -> None:
            raise RuntimeError("queue full")

    # Should not raise.
    safe_queue_put(_BrokenQueue(), {"type": "test"})


def test_safe_queue_put_does_not_raise_on_none_event() -> None:
    """safe_queue_put() accepts None as an event without raising."""
    q = _make_queue()

    safe_queue_put(q, None)  # type: ignore[arg-type]

    assert q.get_nowait() is None



def test_set_fork_service_stores_provided_instance() -> None:
    """set_fork_service() stores the given instance in the module-level _FORK_SERVICE."""
    fake_service = MagicMock()

    set_fork_service(fake_service)

    assert sr._FORK_SERVICE is fake_service


def test_set_fork_service_clears_when_passed_none() -> None:
    """set_fork_service(None) clears the module-level _FORK_SERVICE to None."""
    set_fork_service(MagicMock())
    set_fork_service(None)

    assert sr._FORK_SERVICE is None



def test_subprocess_log_handler_emits_log_event_type() -> None:
    """SubprocessLogHandler.emit() puts an event with type=EVENT_LOG on the queue."""
    q = _make_queue()
    handler = _make_handler(q)

    handler.emit(_make_record())

    event = q.get_nowait()
    assert event["type"] == EVENT_LOG


def test_subprocess_log_handler_emits_message() -> None:
    """SubprocessLogHandler.emit() includes the formatted message in the queued event."""
    q = _make_queue()
    handler = _make_handler(q)

    handler.emit(_make_record("my message"))

    event = q.get_nowait()
    assert event["message"] == "my message"


def test_subprocess_log_handler_emits_logger_name() -> None:
    """SubprocessLogHandler.emit() includes the logger name in the queued event."""
    q = _make_queue()
    handler = _make_handler(q)

    handler.emit(_make_record(logger_name="dspy.optimizer"))

    event = q.get_nowait()
    assert event["logger"] == "dspy.optimizer"


@pytest.mark.parametrize(
    "level_int, expected_name",
    [
        (logging.DEBUG, "DEBUG"),
        (logging.INFO, "INFO"),
        (logging.WARNING, "WARNING"),
        (logging.ERROR, "ERROR"),
        (logging.CRITICAL, "CRITICAL"),
    ],
)
def test_subprocess_log_handler_emits_level_name(
    level_int: int, expected_name: str
) -> None:
    """SubprocessLogHandler.emit() includes the string level name in the queued event."""
    q = _make_queue()
    handler = _make_handler(q)

    handler.emit(_make_record(level=level_int))

    event = q.get_nowait()
    assert event["level"] == expected_name


def test_subprocess_log_handler_emits_utc_iso_timestamp() -> None:
    """SubprocessLogHandler.emit() includes a UTC ISO-format timestamp ending in +00:00."""
    q = _make_queue()
    handler = _make_handler(q)

    handler.emit(_make_record())

    event = q.get_nowait()
    ts: str = event["timestamp"]
    assert ts.endswith("+00:00"), f"Expected UTC timestamp, got: {ts}"


def test_subprocess_log_handler_emits_multiple_records_in_order() -> None:
    """Multiple emit() calls produce events on the queue in the same order."""
    q = _make_queue()
    handler = _make_handler(q)
    messages = ["alpha", "beta", "gamma"]

    for msg in messages:
        handler.emit(_make_record(msg))

    received = [q.get_nowait()["message"] for _ in messages]
    assert received == messages



def test_subprocess_log_handler_falls_back_to_get_message_on_format_error() -> None:
    """When Formatter.format() raises, emit must fall back to record.getMessage()."""
    q = _make_queue()
    handler = SubprocessLogHandler(event_queue=q)

    class _FailFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            raise RuntimeError("formatter exploded")

    handler.setFormatter(_FailFormatter())
    handler.emit(_make_record("fallback text"))

    event = q.get_nowait()
    assert event["message"] == "fallback text"



def test_subprocess_log_handler_suppresses_broken_queue_errors() -> None:
    """emit() does not propagate exceptions raised by a failing event queue."""

    class _BrokenQueue:
        def put(self, item: object) -> None:
            raise OSError("pipe broken")

    handler = SubprocessLogHandler(event_queue=_BrokenQueue())
    handler.setFormatter(logging.Formatter("%(message)s"))

    # Should not raise.
    handler.emit(_make_record("msg"))



def _drain_queue(q: queue.Queue) -> list[dict]:
    """Return all events currently on the queue without blocking."""
    events = []
    while True:
        try:
            events.append(q.get_nowait())
        except queue.Empty:
            break
    return events


def test_run_service_in_subprocess_happy_path_emits_result_event() -> None:
    """When service.run() succeeds, an EVENT_RESULT must appear on the queue."""
    q = queue.Queue()
    svc = fake_dspy_service(result={"baseline_test_metric": 0.5, "optimized_test_metric": 0.8})

    with patch("core.worker.subprocess_runner.DspyService", return_value=svc), \
         patch("core.worker.subprocess_runner.ServiceRegistry", return_value=fake_service_registry()):
        run_service_in_subprocess(REAL_RUN_PAYLOAD, "art-1", q, "spawn")

    events = _drain_queue(q)
    result_events = [e for e in events if e.get("type") == EVENT_RESULT]
    assert len(result_events) == 1
    assert result_events[0]["result"] == {"baseline_test_metric": 0.5, "optimized_test_metric": 0.8}


def test_run_service_in_subprocess_happy_path_zero_exit() -> None:
    """run_service_in_subprocess() returns without raising on a successful service call."""
    q = queue.Queue()
    svc = fake_dspy_service()

    with patch("core.worker.subprocess_runner.DspyService", return_value=svc), \
         patch("core.worker.subprocess_runner.ServiceRegistry", return_value=fake_service_registry()):
        # Must not raise.
        run_service_in_subprocess(REAL_RUN_PAYLOAD, "art-2", q, "spawn")


def test_run_service_in_subprocess_exception_emits_error_event() -> None:
    """When service.run() raises, an EVENT_ERROR must appear on the queue."""
    q = queue.Queue()
    svc = fake_dspy_service()
    svc.run.side_effect = RuntimeError("model exploded")

    with patch("core.worker.subprocess_runner.DspyService", return_value=svc), \
         patch("core.worker.subprocess_runner.ServiceRegistry", return_value=fake_service_registry()):
        run_service_in_subprocess(REAL_RUN_PAYLOAD, "art-3", q, "spawn")

    events = _drain_queue(q)
    error_events = [e for e in events if e.get("type") == EVENT_ERROR]
    assert len(error_events) == 1
    assert "model exploded" in error_events[0]["error"]
    assert "traceback" in error_events[0]


def test_run_service_in_subprocess_exception_no_result_event() -> None:
    """When service.run() raises, no EVENT_RESULT is placed on the queue."""
    q = queue.Queue()
    svc = fake_dspy_service()
    svc.run.side_effect = ValueError("bad payload")

    with patch("core.worker.subprocess_runner.DspyService", return_value=svc), \
         patch("core.worker.subprocess_runner.ServiceRegistry", return_value=fake_service_registry()):
        run_service_in_subprocess(REAL_RUN_PAYLOAD, "art-4", q, "spawn")

    events = _drain_queue(q)
    result_events = [e for e in events if e.get("type") == EVENT_RESULT]
    assert result_events == []


def test_run_service_in_subprocess_run_type_calls_service_run() -> None:
    """_optimization_type='run' must dispatch to service.run(), not run_grid_search."""
    q = queue.Queue()
    svc = fake_dspy_service()

    with patch("core.worker.subprocess_runner.DspyService", return_value=svc), \
         patch("core.worker.subprocess_runner.ServiceRegistry", return_value=fake_service_registry()):
        run_service_in_subprocess(REAL_RUN_PAYLOAD, "art-5", q, "spawn")

    svc.run.assert_called_once()
    svc.run_grid_search.assert_not_called()


def test_run_service_in_subprocess_grid_search_type_calls_run_grid_search() -> None:
    """_optimization_type='grid_search' must dispatch to service.run_grid_search()."""
    q = queue.Queue()
    svc = fake_dspy_service()

    with patch("core.worker.subprocess_runner.DspyService", return_value=svc), \
         patch("core.worker.subprocess_runner.ServiceRegistry", return_value=fake_service_registry()):
        run_service_in_subprocess(REAL_GRID_PAYLOAD, "art-6", q, "spawn")

    svc.run_grid_search.assert_called_once()
    svc.run.assert_not_called()


def test_run_service_in_subprocess_progress_callback_emits_progress_events() -> None:
    """progress_callback invocations must land as EVENT_PROGRESS on the queue."""
    q = queue.Queue()
    svc = fake_dspy_service()

    captured_callback = {}

    def _fake_run(payload, *, artifact_id, progress_callback):
        captured_callback["cb"] = progress_callback
        progress_callback("step_a", {"score": 0.3})
        progress_callback("step_b", {"score": 0.6})
        fake_result = MagicMock()
        fake_result.model_dump.return_value = {}
        return fake_result

    svc.run.side_effect = _fake_run

    with patch("core.worker.subprocess_runner.DspyService", return_value=svc), \
         patch("core.worker.subprocess_runner.ServiceRegistry", return_value=fake_service_registry()):
        run_service_in_subprocess(REAL_RUN_PAYLOAD, "art-7", q, "spawn")

    events = _drain_queue(q)
    progress_events = [e for e in events if e.get("type") == EVENT_PROGRESS]
    assert len(progress_events) == 2
    assert progress_events[0]["event"] == "step_a"
    assert progress_events[0]["metrics"] == {"score": 0.3}
    assert progress_events[1]["event"] == "step_b"
    assert progress_events[1]["metrics"] == {"score": 0.6}


def test_run_service_in_subprocess_uses_fork_service_when_start_method_is_fork() -> None:
    """When start_method='fork' and _FORK_SERVICE is set, the fork service is used."""
    q = queue.Queue()
    fork_svc = fake_dspy_service()

    set_fork_service(fork_svc)
    try:
        with patch("core.worker.subprocess_runner.DspyService") as mock_dspy_svc, \
             patch("core.worker.subprocess_runner.ServiceRegistry"):
            run_service_in_subprocess(REAL_RUN_PAYLOAD, "art-8", q, "fork")

        # DspyService constructor must NOT have been called — fork service reused
        mock_dspy_svc.assert_not_called()
        fork_svc.run.assert_called_once()
    finally:
        set_fork_service(None)
