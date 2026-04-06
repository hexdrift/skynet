"""JobStore Protocol defining the contract for all storage backends."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class JobStore(Protocol):
    """Protocol that all job storage backends must satisfy."""

    def create_job(self, job_id: str, estimated_remaining_seconds: Optional[float] = None) -> Dict[str, Any]:
        """Create a new job record in the store.

        Args:
            job_id: Unique identifier for the job.
            estimated_remaining_seconds: Optional initial time estimate.

        Returns:
            Dictionary representation of the newly created job.
        """
        ...

    def update_job(self, job_id: str, **kwargs: Any) -> None:
        """Update fields on an existing job.

        Args:
            job_id: Identifier of the job to update.
            **kwargs: Field names and values to set.
        """
        ...

    def get_job(self, job_id: str) -> Dict[str, Any]:
        """Retrieve a single job by its identifier.

        Args:
            job_id: Identifier of the job to retrieve.

        Returns:
            Dictionary representation of the job.

        Raises:
            KeyError: If the job does not exist.
        """
        ...

    def job_exists(self, job_id: str) -> bool:
        """Check whether a job exists in the store.

        Args:
            job_id: Identifier of the job to check.

        Returns:
            True if the job exists, False otherwise.
        """
        ...

    def delete_job(self, job_id: str) -> None:
        """Delete a job and all its associated data.

        Args:
            job_id: Identifier of the job to delete.
        """
        ...

    def record_progress(self, job_id: str, message: Optional[str], metrics: Dict[str, Any]) -> None:
        """Record a progress event for a job.

        Args:
            job_id: Identifier of the job.
            message: Optional human-readable progress description.
            metrics: Dictionary of metric key-value pairs.
        """
        ...

    def get_progress_events(self, job_id: str) -> List[Dict[str, Any]]:
        """Retrieve all progress events for a job in chronological order.

        Args:
            job_id: Identifier of the job.

        Returns:
            List of progress event dictionaries.
        """
        ...

    def get_progress_count(self, job_id: str) -> int:
        """Return the number of progress events recorded for a job.

        Args:
            job_id: Identifier of the job.

        Returns:
            Count of progress events.
        """
        ...

    def append_log(
        self,
        job_id: str,
        *,
        level: str,
        logger_name: str,
        message: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Append a log entry to a job's log history.

        Args:
            job_id: Identifier of the job.
            level: Log level (e.g. "INFO", "ERROR").
            logger_name: Name of the logger that produced the entry.
            message: Log message text.
            timestamp: Optional explicit timestamp; defaults to now.
        """
        ...

    def get_logs(
        self,
        job_id: str,
        *,
        limit: Optional[int] = None,
        offset: int = 0,
        level: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve log entries for a job with optional filtering and pagination.

        Args:
            job_id: Identifier of the job.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip.
            level: Optional log level filter.

        Returns:
            List of log entry dictionaries.
        """
        ...

    def get_log_count(self, job_id: str, *, level: Optional[str] = None) -> int:
        """Return the number of log entries for a job.

        Args:
            job_id: Identifier of the job.
            level: Optional log level filter.

        Returns:
            Count of matching log entries.
        """
        ...

    def set_payload_overview(self, job_id: str, overview: Dict[str, Any]) -> None:
        """Store a summary overview of the job payload.

        Args:
            job_id: Identifier of the job.
            overview: Dictionary of overview fields to persist.
        """
        ...

    def list_jobs(
        self,
        *,
        status: Optional[str] = None,
        username: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List jobs with optional filtering and pagination.

        Args:
            status: Filter by job status.
            username: Filter by username.
            job_type: Filter by job type.
            limit: Maximum number of jobs to return. Defaults to 50.
            offset: Number of jobs to skip. Defaults to 0.

        Returns:
            List of job dictionaries ordered by creation time descending.
        """
        ...

    def count_jobs(
        self,
        *,
        status: Optional[str] = None,
        username: Optional[str] = None,
        job_type: Optional[str] = None,
    ) -> int:
        """Count jobs matching the given filters.

        Args:
            status: Filter by job status.
            username: Filter by username.
            job_type: Filter by job type.

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

    def recover_pending_jobs(self) -> List[str]:
        """Retrieve job IDs that are still pending, ordered by creation time.

        Returns:
            List of pending job IDs.
        """
        ...
