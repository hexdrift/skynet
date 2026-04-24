"""JobStore Protocol defining the contract for all storage backends."""

from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class JobStore(Protocol):
    """Protocol that all job storage backends must satisfy."""

    def create_job(self, optimization_id: str, estimated_remaining_seconds: float | None = None) -> dict[str, Any]:
        """Create a new job record and return its dict representation."""
        ...

    def update_job(self, optimization_id: str, **kwargs: Any) -> None:
        """Update fields on an existing job."""
        ...

    def get_job(self, optimization_id: str) -> dict[str, Any]:
        """Retrieve a job by its ID; raises KeyError if not found."""
        ...

    def job_exists(self, optimization_id: str) -> bool:
        """Return True if the job exists in the store."""
        ...

    def delete_job(self, optimization_id: str) -> None:
        """Delete a job and all its associated data (logs, progress events)."""
        ...

    def get_jobs_status_by_ids(self, optimization_ids: list[str]) -> dict[str, str]:
        """Return a ``{id: status}`` map for the requested IDs.

        Used by the bulk-delete endpoint to partition a batch into
        deletable / non-terminal / not-found in a single round trip,
        instead of running N individual ``get_job`` calls.

        Args:
            optimization_ids: Identifiers to look up.

        Returns:
            Mapping from existing job IDs to their current status
            string. IDs that don't exist are simply absent from the
            returned dict.
        """
        ...

    def delete_jobs(self, optimization_ids: list[str]) -> int:
        """Hard-delete a batch of jobs and their associated rows.

        Implementations should run this in a single transaction with
        bulk ``DELETE ... WHERE id IN (...)`` queries so the cost is
        O(1) round trips instead of O(n).

        Args:
            optimization_ids: Identifiers to delete. Duplicates and
                missing IDs are tolerated — the method deletes
                whatever subset currently exists.

        Returns:
            Number of job rows actually removed.
        """
        ...

    def record_progress(self, optimization_id: str, message: str | None, metrics: dict[str, Any]) -> None:
        """Record a progress event for a job."""
        ...

    def get_progress_events(self, optimization_id: str) -> list[dict[str, Any]]:
        """Retrieve all progress events for a job in chronological order."""
        ...

    def get_progress_count(self, optimization_id: str) -> int:
        """Return the number of progress events recorded for a job."""
        ...

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
        """Append a log entry to a job's log history."""
        ...

    def get_logs(
        self,
        optimization_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        level: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve log entries for a job with optional level filter and pagination."""
        ...

    def get_log_count(self, optimization_id: str, *, level: str | None = None) -> int:
        """Return the number of log entries for a job, optionally filtered by level."""
        ...

    def set_payload_overview(self, optimization_id: str, overview: dict[str, Any]) -> None:
        """Store a summary overview of the job payload."""
        ...

    def list_jobs(
        self,
        *,
        status: str | None = None,
        username: str | None = None,
        optimization_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List jobs with optional filtering and pagination, ordered by creation time descending."""
        ...

    def count_jobs(
        self,
        *,
        status: str | None = None,
        username: str | None = None,
        optimization_type: str | None = None,
    ) -> int:
        """Count jobs matching the given filters."""
        ...

    def recover_orphaned_jobs(self) -> int:
        """Mark running/validating jobs as failed after a service restart; returns count recovered."""
        ...

    def recover_pending_jobs(self) -> list[str]:
        """Return IDs of still-pending jobs ordered by creation time."""
        ...
