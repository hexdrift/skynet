"""JobStore Protocol defining the contract for all storage backends."""

from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class JobStore(Protocol):
    """Protocol that all job storage backends must satisfy."""

    def create_job(self, optimization_id: str, estimated_remaining_seconds: float | None = None) -> dict[str, Any]:
        """Create a new job record in the store.

        Args:
            optimization_id: Unique identifier for the job.
            estimated_remaining_seconds: Optional initial time estimate.

        Returns:
            Dictionary representation of the newly created job.
        """
        ...

    def update_job(self, optimization_id: str, **kwargs: Any) -> None:
        """Update fields on an existing job.

        Args:
            optimization_id: Identifier of the job to update.
            **kwargs: Field names and values to set.

        Returns:
            None.
        """
        ...

    def get_job(self, optimization_id: str) -> dict[str, Any]:
        """Retrieve a single job by its identifier.

        Args:
            optimization_id: Identifier of the job to retrieve.

        Returns:
            Dictionary representation of the job.

        Raises:
            KeyError: If the job does not exist.
        """
        ...

    def job_exists(self, optimization_id: str) -> bool:
        """Check whether a job exists in the store.

        Args:
            optimization_id: Identifier of the job to check.

        Returns:
            True if the job exists, False otherwise.
        """
        ...

    def delete_job(self, optimization_id: str) -> None:
        """Delete a job and all its associated data.

        Args:
            optimization_id: Identifier of the job to delete.

        Returns:
            None.
        """
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
        """Record a progress event for a job.

        Args:
            optimization_id: Identifier of the job.
            message: Optional human-readable progress description.
            metrics: Dictionary of metric key-value pairs.

        Returns:
            None.
        """
        ...

    def get_progress_events(self, optimization_id: str) -> list[dict[str, Any]]:
        """Retrieve all progress events for a job in chronological order.

        Args:
            optimization_id: Identifier of the job.

        Returns:
            List of progress event dictionaries.
        """
        ...

    def get_progress_count(self, optimization_id: str) -> int:
        """Return the number of progress events recorded for a job.

        Args:
            optimization_id: Identifier of the job.

        Returns:
            Count of progress events.
        """
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
        """Append a log entry to a job's log history.

        Args:
            optimization_id: Identifier of the job.
            level: Log level (e.g. "INFO", "ERROR").
            logger_name: Name of the logger that produced the entry.
            message: Log message text.
            timestamp: Optional explicit timestamp; defaults to now.
            pair_index: Optional grid-search pair index the log belongs to.

        Returns:
            None.
        """
        ...

    def get_logs(
        self,
        optimization_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        level: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve log entries for a job with optional filtering and pagination.

        Args:
            optimization_id: Identifier of the job.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip.
            level: Optional log level filter.

        Returns:
            List of log entry dictionaries.
        """
        ...

    def get_log_count(self, optimization_id: str, *, level: str | None = None) -> int:
        """Return the number of log entries for a job.

        Args:
            optimization_id: Identifier of the job.
            level: Optional log level filter.

        Returns:
            Count of matching log entries.
        """
        ...

    def set_payload_overview(self, optimization_id: str, overview: dict[str, Any]) -> None:
        """Store a summary overview of the job payload.

        Args:
            optimization_id: Identifier of the job.
            overview: Dictionary of overview fields to persist.

        Returns:
            None.
        """
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
        """List jobs with optional filtering and pagination.

        Args:
            status: Filter by job status.
            username: Filter by username.
            optimization_type: Filter by job type.
            limit: Maximum number of jobs to return. Defaults to 50.
            offset: Number of jobs to skip. Defaults to 0.

        Returns:
            List of job dictionaries ordered by creation time descending.
        """
        ...

    def count_jobs(
        self,
        *,
        status: str | None = None,
        username: str | None = None,
        optimization_type: str | None = None,
    ) -> int:
        """Count jobs matching the given filters.

        Args:
            status: Filter by job status.
            username: Filter by username.
            optimization_type: Filter by job type.

        Returns:
            Number of matching jobs.
        """
        ...

    def recover_orphaned_jobs(self) -> int:
        """Mark running/validating jobs as failed after a service restart.

        Returns:
            Number of orphaned jobs recovered.
        """
        ...

    def recover_pending_jobs(self) -> list[str]:
        """Retrieve optimization IDs that are still pending, ordered by creation time.

        Returns:
            List of pending optimization IDs.
        """
        ...
