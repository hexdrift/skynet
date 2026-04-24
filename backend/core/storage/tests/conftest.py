"""Local fixtures for storage contract tests.

FakeJobStore is defined here (not imported from core.api.tests.conftest) to
keep the storage test package self-contained (DAMP over clever cross-package
imports) and to extend it with the methods the api-tier fake deliberately
omitted (create_job, record_progress, append_log, bulk helpers, recovery).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest


class FakeJobStore:
    """Full in-memory implementation of the JobStore protocol.

    Covers every method declared in core.storage.base.JobStore so that the
    contract tests can exercise all guarantees without a real database.
    """

    def __init__(self) -> None:
        """Initialize empty in-memory stores for jobs, logs, and progress."""
        self._jobs: dict[str, dict] = {}
        self._logs: dict[str, list] = {}
        self._progress: dict[str, list] = {}

    def seed_job(self, optimization_id: str, **fields: Any) -> dict:
        """Insert a pre-populated job row with sensible defaults; returns the row dict."""
        now = datetime.now(timezone.utc).isoformat()
        job = {
            "optimization_id": optimization_id,
            "status": "pending",
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "estimated_remaining_seconds": None,
            "payload_overview": {},
            "payload": {},
            "result": None,
            "latest_metrics": {},
            "message": None,
            **fields,
        }
        self._jobs[optimization_id] = job
        self._logs.setdefault(optimization_id, [])
        self._progress.setdefault(optimization_id, [])
        return job

    def create_job(
        self,
        optimization_id: str,
        estimated_remaining_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Create a pending job row and return a copy of the stored dict."""
        now = datetime.now(timezone.utc).isoformat()
        job: dict[str, Any] = {
            "optimization_id": optimization_id,
            "status": "pending",
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "estimated_remaining_seconds": estimated_remaining_seconds,
            "payload_overview": {},
            "payload": {},
            "result": None,
            "latest_metrics": {},
            "message": None,
        }
        self._jobs[optimization_id] = job
        self._logs[optimization_id] = []
        self._progress[optimization_id] = []
        return dict(job)

    def update_job(self, optimization_id: str, **kwargs: Any) -> None:
        """Merge kwargs into the stored job row."""
        self._jobs[optimization_id].update(kwargs)

    def get_job(self, optimization_id: str) -> dict[str, Any]:
        """Return a copy of the job dict; raises KeyError if not found."""
        if optimization_id not in self._jobs:
            raise KeyError(optimization_id)
        return dict(self._jobs[optimization_id])

    def job_exists(self, optimization_id: str) -> bool:
        """Return True if a job with the given ID exists in the store."""
        return optimization_id in self._jobs

    def delete_job(self, optimization_id: str) -> None:
        """Remove the job and its logs/progress; silently ignores missing IDs."""
        self._jobs.pop(optimization_id, None)
        self._logs.pop(optimization_id, None)
        self._progress.pop(optimization_id, None)

    def get_jobs_status_by_ids(self, optimization_ids: list[str]) -> dict[str, str]:
        """Return a {id: status} map for each ID that exists in the store."""
        return {
            oid: self._jobs[oid]["status"]
            for oid in optimization_ids
            if oid in self._jobs
        }

    def delete_jobs(self, optimization_ids: list[str]) -> int:
        """Delete a batch of jobs; returns the count of rows actually removed."""
        removed = 0
        for oid in set(optimization_ids):
            if oid in self._jobs:
                self._jobs.pop(oid)
                self._logs.pop(oid, None)
                self._progress.pop(oid, None)
                removed += 1
        return removed

    def record_progress(
        self,
        optimization_id: str,
        message: str | None,
        metrics: dict[str, Any],
    ) -> None:
        """Append a progress event for the given job."""
        self._progress.setdefault(optimization_id, []).append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": message,
                "metrics": dict(metrics),
            }
        )

    def get_progress_events(self, optimization_id: str) -> list[dict[str, Any]]:
        """Return a copy of all progress events for the given job."""
        return list(self._progress.get(optimization_id, []))

    def get_progress_count(self, optimization_id: str) -> int:
        """Return the number of progress events recorded for the given job."""
        return len(self._progress.get(optimization_id, []))

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
        """Append a log entry for the given job."""
        self._logs.setdefault(optimization_id, []).append(
            {
                "level": level,
                "logger_name": logger_name,
                "message": message,
                "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
                "pair_index": pair_index,
            }
        )

    def get_logs(
        self,
        optimization_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        level: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return log entries for the job with optional level filter and pagination."""
        entries = list(self._logs.get(optimization_id, []))
        if level is not None:
            entries = [e for e in entries if e["level"] == level]
        entries = entries[offset:]
        if limit is not None:
            entries = entries[:limit]
        return entries

    def get_log_count(self, optimization_id: str, *, level: str | None = None) -> int:
        """Return the number of log entries for a job, optionally filtered by level."""
        entries = self._logs.get(optimization_id, [])
        if level is not None:
            return sum(1 for e in entries if e["level"] == level)
        return len(entries)

    def set_payload_overview(self, optimization_id: str, overview: dict[str, Any]) -> None:
        """Store the payload overview dict on the job, replacing any previous value."""
        self._jobs[optimization_id]["payload_overview"] = dict(overview)

    def list_jobs(
        self,
        *,
        status: str | None = None,
        username: str | None = None,
        optimization_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return jobs matching the given filters with pagination applied."""
        rows = list(self._jobs.values())
        if status is not None:
            rows = [r for r in rows if r.get("status") == status]
        if username is not None:
            rows = [r for r in rows if r.get("payload_overview", {}).get("username") == username]
        if optimization_type is not None:
            rows = [r for r in rows if r.get("payload_overview", {}).get("job_type") == optimization_type]
        return rows[offset : offset + limit]

    def count_jobs(
        self,
        *,
        status: str | None = None,
        username: str | None = None,
        optimization_type: str | None = None,
    ) -> int:
        """Return the count of jobs matching the given filters."""
        return len(
            self.list_jobs(
                status=status,
                username=username,
                optimization_type=optimization_type,
                limit=10**9,
                offset=0,
            )
        )

    def recover_orphaned_jobs(self) -> int:
        """Mark running/validating jobs as failed.

        In-memory semantics: any job with status 'running' or 'validating'
        is transitioned to 'failed' and its message is updated.
        """
        recovered = 0
        for job in self._jobs.values():
            if job["status"] in ("running", "validating"):
                job["status"] = "failed"
                job["message"] = "Recovered by restart"
                recovered += 1
        return recovered

    def recover_pending_jobs(self) -> list[str]:
        """Return IDs of pending jobs ordered by created_at ascending."""
        pending = [j for j in self._jobs.values() if j["status"] == "pending"]
        pending.sort(key=lambda j: j["created_at"])
        return [j["optimization_id"] for j in pending]


@pytest.fixture
def store() -> FakeJobStore:
    """Return a fresh FakeJobStore instance for each test function."""
    return FakeJobStore()
