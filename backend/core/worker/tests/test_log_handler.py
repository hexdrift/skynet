"""Unit tests for core.worker.log_handler.

Covers:
- JobLogHandler.emit — field capture (level, logger_name, message, timestamp)
- Thread filtering — records from unregistered threads are silently dropped
- register_current_thread — makes a new thread's records pass the filter
- DB errors raised by the job store are swallowed in ``emit``
- _extract_progress_from_log — all four regex patterns
- set_current_pair_index / get_current_pair_index — thread-local round-trip
- pair_index is forwarded to append_log when set on the emitting thread
"""

from __future__ import annotations

import logging
import threading
from typing import cast

import pytest

from core.storage.base import JobStore
from core.worker.log_handler import (
    JobLogHandler,
    _extract_progress_from_log,
    get_current_pair_index,
    set_current_pair_index,
)

from .conftest import FakeJobStore


def _make_record(
    msg: str = "hello",
    level: int = logging.INFO,
    logger_name: str = "test.logger",
) -> logging.LogRecord:
    """Build a minimal ``logging.LogRecord`` for tests."""
    record = logging.LogRecord(
        name=logger_name,
        level=level,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )
    return record


def _make_handler(store: FakeJobStore, job_id: str = "job-1") -> JobLogHandler:
    """Build a JobLogHandler bound to ``store`` and ``job_id``."""
    return JobLogHandler(optimization_id=job_id, jobs=cast(JobStore, store))


def test_emit_stores_message(fake_store: FakeJobStore) -> None:
    """``emit`` stores the formatted log message."""
    handler = _make_handler(fake_store)
    record = _make_record("test message")

    handler.emit(record)

    logs = fake_store.get_logs("job-1")
    assert len(logs) == 1
    assert logs[0]["message"] == "test message"


def test_emit_stores_logger_name(fake_store: FakeJobStore) -> None:
    """``emit`` stores the originating logger name."""
    handler = _make_handler(fake_store)
    record = _make_record(logger_name="dspy.optimizer")

    handler.emit(record)

    logs = fake_store.get_logs("job-1")
    assert logs[0]["logger_name"] == "dspy.optimizer"


@pytest.mark.parametrize(
    ("level_int", "expected_name"),
    [
        (logging.DEBUG, "DEBUG"),
        (logging.INFO, "INFO"),
        (logging.WARNING, "WARNING"),
        (logging.ERROR, "ERROR"),
        (logging.CRITICAL, "CRITICAL"),
    ],
)
def test_emit_stores_level_name(fake_store: FakeJobStore, level_int: int, expected_name: str) -> None:
    """``emit`` stores the log level name."""
    handler = _make_handler(fake_store)
    record = _make_record(level=level_int)

    handler.emit(record)

    logs = fake_store.get_logs("job-1")
    assert logs[0]["level"] == expected_name


def test_emit_stores_utc_timestamp(fake_store: FakeJobStore) -> None:
    """``emit`` stores a UTC-aware timestamp."""
    handler = _make_handler(fake_store)
    record = _make_record()

    handler.emit(record)

    logs = fake_store.get_logs("job-1")
    ts = logs[0]["timestamp"]
    assert ts is not None
    assert ts.tzinfo is not None
    assert ts.utcoffset().total_seconds() == 0  # UTC


def test_emit_multiple_records_preserves_order(fake_store: FakeJobStore) -> None:
    """Multiple ``emit`` calls keep records in chronological order."""
    handler = _make_handler(fake_store)
    messages = ["first", "second", "third"]
    for msg in messages:
        handler.emit(_make_record(msg))

    logs = fake_store.get_logs("job-1")
    assert [entry["message"] for entry in logs] == messages


def test_emit_drops_record_from_unregistered_thread(fake_store: FakeJobStore) -> None:
    """Records emitted by an unregistered thread are silently dropped."""
    handler = _make_handler(fake_store)

    result: list[bool] = []

    def _emit_from_other_thread() -> None:
        """Emit a record from an unregistered worker thread."""
        record = _make_record("should be dropped")
        handler.emit(record)
        result.append(True)

    t = threading.Thread(target=_emit_from_other_thread)
    t.start()
    t.join()

    # The other thread completed without error, but no log was stored.
    assert result == [True]
    assert fake_store.get_logs("job-1") == []


def test_register_current_thread_allows_records(fake_store: FakeJobStore) -> None:
    """``register_current_thread`` lets a new thread's records pass the filter."""
    handler = _make_handler(fake_store)

    def _emit_from_registered_thread() -> None:
        """Register the current thread, then emit a record from it."""
        handler.register_current_thread()
        handler.emit(_make_record("registered thread msg"))

    t = threading.Thread(target=_emit_from_registered_thread)
    t.start()
    t.join()

    logs = fake_store.get_logs("job-1")
    assert len(logs) == 1
    assert logs[0]["message"] == "registered thread msg"


def test_emit_swallows_db_error(fake_store: FakeJobStore) -> None:
    """``emit`` must not propagate exceptions from the job store."""
    store = FakeJobStore()

    def _raise(*args: object, **kwargs: object) -> None:
        """Always raise to simulate a DB outage."""
        raise RuntimeError("DB is down")

    store.append_log = _raise  # type: ignore[method-assign]
    handler = _make_handler(store)

    # Should complete without raising.
    handler.emit(_make_record("will fail to persist"))


def test_emit_forwards_pair_index_when_set(fake_store: FakeJobStore) -> None:
    """``emit`` forwards the active pair index to ``append_log``."""
    handler = _make_handler(fake_store)
    set_current_pair_index(3)
    try:
        handler.emit(_make_record())
    finally:
        set_current_pair_index(None)

    assert fake_store.append_log_calls[0]["pair_index"] == 3


def test_emit_forwards_none_pair_index_when_unset(fake_store: FakeJobStore) -> None:
    """``emit`` forwards ``None`` when no pair index is set."""
    set_current_pair_index(None)
    handler = _make_handler(fake_store)

    handler.emit(_make_record())

    assert fake_store.append_log_calls[0]["pair_index"] is None


def test_pair_index_roundtrip_same_thread() -> None:
    """``set_current_pair_index`` round-trips through ``get_current_pair_index``."""
    set_current_pair_index(7)
    assert get_current_pair_index() == 7
    set_current_pair_index(None)
    assert get_current_pair_index() is None


def test_pair_index_is_thread_local() -> None:
    """The pair index is stored per-thread."""
    set_current_pair_index(42)

    seen: list[int | None] = []

    def _read_from_other() -> None:
        """Read the pair index from a thread that never set it."""
        seen.append(get_current_pair_index())

    t = threading.Thread(target=_read_from_other)
    t.start()
    t.join()

    # Other thread never called set_current_pair_index, so it gets None.
    assert seen == [None]
    # Main thread still has its value.
    assert get_current_pair_index() == 42
    set_current_pair_index(None)


@pytest.mark.parametrize(
    ("message", "expected_event", "expected_keys"),
    [
        (
            "Iteration 3: Selected program 1 score: 0.875",
            "optimizer_iteration",
            {"iteration": 3, "program": 1, "score": 0.875},
        ),
        (
            "Average Metric: 14.0 / 20.0 (70.0%)",
            "average_metric_snapshot",
            {"value": 14.0, "maximum": 20.0, "percent": 70.0},
        ),
        (
            "Iteration 5: All subsample scores perfect",
            "optimizer_iteration_perfect",
            {"iteration": 5, "perfect_subsamples": True},
        ),
        (
            "Iteration 2: Reflective mutation did not propose a new candidate",
            "optimizer_reflection_idle",
            {"iteration": 2, "mutation_proposed": False},
        ),
    ],
)
def test_extract_progress_known_patterns(message: str, expected_event: str, expected_keys: dict) -> None:
    """``_extract_progress_from_log`` recognises each known pattern."""
    events = list(_extract_progress_from_log(message))
    event_names = [e[0] for e in events]
    assert expected_event in event_names
    matched = next(e[1] for e in events if e[0] == expected_event)
    for key, val in expected_keys.items():
        assert matched[key] == val


def test_extract_progress_no_match_returns_empty() -> None:
    """A plain message yields no progress events."""
    events = list(_extract_progress_from_log("Just a regular log line with no metrics"))
    assert events == []


def test_extract_progress_multiple_patterns_in_one_line() -> None:
    """A single line may yield multiple progress events when several patterns match."""
    msg = "Iteration 1: Selected program 0 score: 0.5 — Average Metric: 10.0 / 20.0 (50.0%)"
    events = list(_extract_progress_from_log(msg))
    event_names = [e[0] for e in events]
    assert "optimizer_iteration" in event_names
    assert "average_metric_snapshot" in event_names


def test_emit_triggers_record_progress_for_known_pattern(fake_store: FakeJobStore) -> None:
    """``emit`` forwards extracted progress events to ``record_progress``."""
    handler = _make_handler(fake_store)
    record = _make_record("Iteration 1: Selected program 0 score: 0.9")

    handler.emit(record)

    assert len(fake_store.record_progress_calls) == 1
    opt_id, event_name, metrics = fake_store.record_progress_calls[0]
    assert opt_id == "job-1"
    assert event_name == "optimizer_iteration"
    assert metrics["score"] == pytest.approx(0.9)


def test_emit_does_not_call_record_progress_for_plain_message(
    fake_store: FakeJobStore,
) -> None:
    """``emit`` skips ``record_progress`` when no pattern matches."""
    handler = _make_handler(fake_store)
    handler.emit(_make_record("Nothing interesting here"))

    assert fake_store.record_progress_calls == []
