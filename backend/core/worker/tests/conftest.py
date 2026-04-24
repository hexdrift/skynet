"""Shared fixtures for worker unit tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest


class FakeJobStore:
    """Minimal in-memory job store for worker unit tests.

    Only implements the methods the worker actually calls.
    """

    def __init__(self) -> None:
        """Initialize empty in-memory storage with call-capture lists."""
        self._jobs: dict[str, dict[str, Any]] = {}
        self._logs: dict[str, list[dict[str, Any]]] = {}
        self._progress: dict[str, list[tuple[str | None, dict[str, Any]]]] = {}
        self.append_log_calls: list[dict[str, Any]] = []
        self.record_progress_calls: list[tuple[str, str | None, dict[str, Any]]] = []

    def seed_job(self, optimization_id: str, **fields: Any) -> dict[str, Any]:
        """Insert a pre-populated job row with sensible defaults; returns the row dict."""
        now = datetime.now(timezone.utc).isoformat()
        job: dict[str, Any] = {
            "optimization_id": optimization_id,
            "status": "queued",
            "created_at": now,
            "payload": {},
            **fields,
        }
        self._jobs[optimization_id] = job
        return job

    def get_job(self, optimization_id: str) -> dict[str, Any]:
        """Return a copy of the job dict; raises KeyError if not found."""
        if optimization_id not in self._jobs:
            raise KeyError(optimization_id)
        return dict(self._jobs[optimization_id])

    def update_job(self, optimization_id: str, **kwargs: Any) -> None:
        """Merge kwargs into the stored job row."""
        self._jobs[optimization_id].update(kwargs)

    def append_log(
        self,
        optimization_id: str,
        *,
        level: str,
        logger_name: str,
        message: str,
        timestamp: datetime | None = None,
        pair_index: int | None = None,
    ) -> None:
        """Append a log entry and record the call for later inspection."""
        entry = {
            "optimization_id": optimization_id,
            "level": level,
            "logger_name": logger_name,
            "message": message,
            "timestamp": timestamp,
            "pair_index": pair_index,
        }
        self._logs.setdefault(optimization_id, []).append(entry)
        self.append_log_calls.append(entry)

    def record_progress(
        self,
        optimization_id: str,
        message: str | None,
        metrics: dict[str, Any],
    ) -> None:
        """Record a progress event and capture the call for later inspection."""
        self._progress.setdefault(optimization_id, []).append((message, metrics))
        self.record_progress_calls.append((optimization_id, message, metrics))

    def get_logs(self, optimization_id: str, **_kwargs: Any) -> list[dict[str, Any]]:
        """Return all stored log entries for the given job."""
        return list(self._logs.get(optimization_id, []))


@pytest.fixture
def fake_store() -> FakeJobStore:
    """Return a fresh FakeJobStore for each test function."""
    return FakeJobStore()
