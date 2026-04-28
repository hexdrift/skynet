"""Worker test fixtures and the in-memory FakeJobStore used by the tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest


class FakeJobStore:
    """Worker-tier subset of the JobStore protocol backed by in-memory dicts.

    Implements only the methods the worker actually calls; the full protocol
    impl lives in ``core/storage/tests/conftest.py``.
    """

    def __init__(self) -> None:
        """Initialise empty in-memory storage and call-recording buffers."""
        self._jobs: dict[str, dict[str, Any]] = {}
        self._logs: dict[str, list[dict[str, Any]]] = {}
        self._progress: dict[str, list[tuple[str | None, dict[str, Any]]]] = {}
        self.append_log_calls: list[dict[str, Any]] = []
        self.record_progress_calls: list[tuple[str, str | None, dict[str, Any]]] = []

    def seed_job(self, optimization_id: str, **fields: Any) -> dict[str, Any]:
        """Create a queued job row with optional overrides and return it.

        Args:
            optimization_id: ID of the seeded job.
            **fields: Extra fields merged on top of the default row.

        Returns:
            The freshly created in-memory job record.
        """
        now = datetime.now(UTC).isoformat()
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
        """Return a copy of the seeded job record.

        Args:
            optimization_id: ID of the job to fetch.

        Returns:
            A shallow copy of the in-memory record.

        Raises:
            KeyError: When no job with the given ID exists.
        """
        if optimization_id not in self._jobs:
            raise KeyError(optimization_id)
        return dict(self._jobs[optimization_id])

    def update_job(self, optimization_id: str, **kwargs: Any) -> None:
        """Merge ``kwargs`` into the stored row.

        Args:
            optimization_id: ID of the job being updated.
            **kwargs: Fields to merge into the record.
        """
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
        """Persist a log entry and record the call for assertions.

        Args:
            optimization_id: ID of the job the log belongs to.
            level: Log level name (e.g. ``"INFO"``).
            logger_name: Name of the originating logger.
            message: Formatted log message.
            timestamp: When the record was emitted, or ``None``.
            pair_index: Grid-search pair index, or ``None``.
        """
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
        """Persist a progress event and record the call for assertions.

        Args:
            optimization_id: ID of the job the event belongs to.
            message: Phase label, or ``None``.
            metrics: Metric snapshot for this phase.
        """
        self._progress.setdefault(optimization_id, []).append((message, metrics))
        self.record_progress_calls.append((optimization_id, message, metrics))

    def get_logs(self, optimization_id: str, **_kwargs: Any) -> list[dict[str, Any]]:
        """Return all log entries recorded for a job.

        Args:
            optimization_id: ID of the job whose logs are requested.
            **_kwargs: Ignored; matches the JobStore protocol signature.

        Returns:
            A copy of the in-memory log list (empty if no logs).
        """
        return list(self._logs.get(optimization_id, []))


@pytest.fixture
def fake_store() -> FakeJobStore:
    """Yield a fresh FakeJobStore for a test."""
    return FakeJobStore()
