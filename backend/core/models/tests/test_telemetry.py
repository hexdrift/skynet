"""Tests for ProgressEvent and JobLogEntry telemetry models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.models.telemetry import JobLogEntry, ProgressEvent


def test_progress_event_minimal_construction() -> None:
    """Verify ProgressEvent accepts a timestamp and defaults event/metrics."""
    ts = datetime.now(tz=UTC)
    event = ProgressEvent(timestamp=ts)

    assert event.timestamp == ts
    assert event.event is None
    assert event.metrics == {}


def test_progress_event_persists_metrics() -> None:
    """Verify ProgressEvent stores a populated metrics dict and event label."""
    event = ProgressEvent(
        timestamp=datetime.now(tz=UTC),
        event="iteration_complete",
        metrics={"step": 1, "score": 0.42},
    )

    assert event.event == "iteration_complete"
    assert event.metrics == {"step": 1, "score": 0.42}


def test_progress_event_requires_timestamp() -> None:
    """Verify ProgressEvent rejects construction without a timestamp."""
    with pytest.raises(ValidationError):
        ProgressEvent.model_validate({})


def test_job_log_entry_round_trip() -> None:
    """Verify JobLogEntry persists every required field."""
    ts = datetime.now(tz=UTC)
    entry = JobLogEntry(timestamp=ts, level="INFO", logger="dspy.optimize", message="started")

    assert entry.timestamp == ts
    assert entry.level == "INFO"
    assert entry.logger == "dspy.optimize"
    assert entry.message == "started"


def test_job_log_entry_requires_message() -> None:
    """Verify JobLogEntry rejects construction missing the message field."""
    with pytest.raises(ValidationError):
        JobLogEntry.model_validate(
            {"timestamp": datetime.now(tz=UTC), "level": "INFO", "logger": "dspy"}
        )
