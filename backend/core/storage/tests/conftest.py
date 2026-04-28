"""Local fixtures for storage contract tests.

FakeJobStore is defined here (not imported from core.api.tests.conftest) to
keep the storage test package self-contained (DAMP over clever cross-package
imports) and to extend it with the methods the api-tier fake deliberately
omitted (create_job, record_progress, append_log, bulk helpers, recovery).
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest


class FakeJobStore:
    """Full in-memory implementation of the JobStore protocol.

    Covers every method declared in core.storage.base.JobStore so that the
    contract tests can exercise all guarantees without a real database.
    """

    def __init__(self) -> None:
        """Initialize empty in-memory tables."""
        self._jobs: dict[str, dict] = {}
        self._logs: dict[str, list] = {}
        self._progress: dict[str, list] = {}
        self._claim_lock = threading.Lock()

    def seed_job(self, optimization_id: str, **fields: Any) -> dict:
        """Insert a job row with optional field overrides."""
        now = datetime.now(UTC).isoformat()
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
        """Create a new pending job and return a copy of its dict row."""
        now = datetime.now(UTC).isoformat()
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
        """Overwrite fields on an existing job row."""
        self._jobs[optimization_id].update(kwargs)

    def get_job(self, optimization_id: str) -> dict[str, Any]:
        """Return a copy of the job row, raising ``KeyError`` if missing."""
        if optimization_id not in self._jobs:
            raise KeyError(optimization_id)
        return dict(self._jobs[optimization_id])

    def job_exists(self, optimization_id: str) -> bool:
        """Return ``True`` if the job has been seeded or created."""
        return optimization_id in self._jobs

    def delete_job(self, optimization_id: str) -> None:
        """Remove the job row and any associated logs/progress events."""
        self._jobs.pop(optimization_id, None)
        self._logs.pop(optimization_id, None)
        self._progress.pop(optimization_id, None)

    def get_jobs_status_by_ids(self, optimization_ids: list[str]) -> dict[str, str]:
        """Return a ``{id: status}`` mapping for the IDs that exist."""
        return {oid: self._jobs[oid]["status"] for oid in optimization_ids if oid in self._jobs}

    def delete_jobs(self, optimization_ids: list[str]) -> int:
        """Bulk-delete jobs and return the number of rows actually removed."""
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
        """Append a progress event to the in-memory event list."""
        self._progress.setdefault(optimization_id, []).append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "message": message,
                "metrics": dict(metrics),
            }
        )

    def get_progress_events(self, optimization_id: str) -> list[dict[str, Any]]:
        """Return a copy of the progress event list for the job."""
        return list(self._progress.get(optimization_id, []))

    def get_progress_count(self, optimization_id: str) -> int:
        """Return the number of progress events stored for the job."""
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
        """Append a log entry to the in-memory log list."""
        self._logs.setdefault(optimization_id, []).append(
            {
                "level": level,
                "logger_name": logger_name,
                "message": message,
                "timestamp": (timestamp or datetime.now(UTC)).isoformat(),
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
        """Return log entries for the job, optionally filtered/paginated."""
        entries = list(self._logs.get(optimization_id, []))
        if level is not None:
            entries = [e for e in entries if e["level"] == level]
        entries = entries[offset:]
        if limit is not None:
            entries = entries[:limit]
        return entries

    def get_log_count(self, optimization_id: str, *, level: str | None = None) -> int:
        """Return the count of log entries, optionally filtered by level."""
        entries = self._logs.get(optimization_id, [])
        if level is not None:
            return sum(1 for e in entries if e["level"] == level)
        return len(entries)

    def set_payload_overview(self, optimization_id: str, overview: dict[str, Any]) -> None:
        """Replace the payload overview for the given job."""
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
        """List jobs with optional filtering and pagination."""
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
        """Return the count of jobs that match the given filters."""
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
        """Reclaim in-flight jobs whose lease has expired."""
        now = datetime.now(UTC)
        recovered = 0
        for job in self._jobs.values():
            if job["status"] not in ("running", "validating"):
                continue
            lease_iso = job.get("lease_expires_at")
            lease_dt = datetime.fromisoformat(lease_iso) if isinstance(lease_iso, str) else None
            if lease_dt is None or lease_dt < now:
                job["status"] = "failed"
                job["message"] = "Job interrupted by service restart"
                job["claimed_by"] = None
                job["claimed_at"] = None
                job["lease_expires_at"] = None
                recovered += 1
        return recovered

    def recover_pending_jobs(self) -> list[str]:
        """Return pending job IDs in oldest-first order."""
        pending = [j for j in self._jobs.values() if j["status"] == "pending"]
        pending.sort(key=lambda j: j["created_at"])
        return [j["optimization_id"] for j in pending]

    def claim_next_job(self, worker_id: str, lease_seconds: float) -> dict[str, Any] | None:
        """Atomically claim the oldest pending job for ``worker_id``."""
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        with self._claim_lock:
            now = datetime.now(UTC)
            lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
            pending = sorted(
                (j for j in self._jobs.values() if j["status"] == "pending"),
                key=lambda j: j["created_at"],
            )
            if not pending:
                return None
            job = pending[0]
            job["status"] = "validating"
            job["claimed_by"] = worker_id
            job["claimed_at"] = now.isoformat()
            job["lease_expires_at"] = lease_until
            return dict(job)

    def extend_lease(self, optimization_id: str, worker_id: str, lease_seconds: float) -> bool:
        """Extend the lease only if this worker still owns the claim."""
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        with self._claim_lock:
            job = self._jobs.get(optimization_id)
            if job is None or job.get("claimed_by") != worker_id:
                return False
            job["lease_expires_at"] = (
                datetime.now(UTC) + timedelta(seconds=lease_seconds)
            ).isoformat()
            return True

    def release_job(self, optimization_id: str, worker_id: str) -> bool:
        """Clear claim metadata only if this worker still owns the claim."""
        with self._claim_lock:
            job = self._jobs.get(optimization_id)
            if job is None or job.get("claimed_by") != worker_id:
                return False
            job["claimed_by"] = None
            job["claimed_at"] = None
            job["lease_expires_at"] = None
            return True


@pytest.fixture
def store() -> FakeJobStore:
    """Yield a fresh ``FakeJobStore`` for each contract test."""
    return FakeJobStore()
