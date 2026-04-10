"""PostgreSQL database backend for job storage.

Provides RemoteDBJobStore for persisting job state to a PostgreSQL database.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, JobModel, LogEntryModel, ProgressEventModel

logger = logging.getLogger(__name__)

MAX_PROGRESS_EVENTS = 5000
MAX_LOG_ENTRIES = 5000


class RemoteDBJobStore:
    """PostgreSQL-backed job storage using SQLAlchemy.

    Connects to a PostgreSQL database using shared SQLAlchemy ORM models.
    No threading lock needed — PostgreSQL handles concurrent access natively.

    Args:
        db_url: PostgreSQL connection string (e.g., "postgresql://user:pass@host:5432/db").
    """

    def __init__(self, db_url: str) -> None:
        """Initialize the PostgreSQL job store.

        Args:
            db_url: PostgreSQL connection string
                (e.g. "postgresql://user:pass@host:5432/db").
        """
        self._engine = create_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            pool_timeout=30,
        )
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)
        logger.info("Initialized PostgreSQL database at %s", db_url.split("@")[-1] if "@" in db_url else db_url)

        # ── Migrations ──
        with self._engine.connect() as conn:
            # Add pair_index column to job_logs if missing
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'job_logs' AND column_name = 'pair_index'"
            ))
            if result.fetchone() is None:
                conn.execute(text("ALTER TABLE job_logs ADD COLUMN pair_index INTEGER"))
                conn.commit()
                logger.info("Migration: added 'pair_index' column to job_logs table")

    @property
    def engine(self):
        """Expose the SQLAlchemy engine for shared table operations."""
        return self._engine

    def _get_session(self) -> Session:
        """Create a new SQLAlchemy session.

        Returns:
            A new database session.
        """
        return self._session_factory()

    def _job_to_dict(self, job: JobModel) -> Dict[str, Any]:
        """Convert a JobModel ORM instance to a plain dictionary.

        Args:
            job: SQLAlchemy job model instance.

        Returns:
            Dictionary representation of the job with ISO-formatted timestamps.
        """
        return {
            "optimization_id": job.optimization_id,
            "status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "estimated_remaining_seconds": job.estimated_remaining_seconds,
            "message": job.message,
            "latest_metrics": job.latest_metrics or {},
            "result": job.result,
            "payload_overview": job.payload_overview or {},
            "payload": job.payload,
        }

    def create_job(self, optimization_id: str, estimated_remaining_seconds: Optional[float] = None) -> Dict[str, Any]:
        """Create a new job record in the PostgreSQL database.

        Args:
            optimization_id: Unique identifier for the job.
            estimated_remaining_seconds: Optional initial time estimate.

        Returns:
            Dictionary representation of the newly created job.
        """
        now = datetime.now(timezone.utc)
        job = JobModel(
            optimization_id=optimization_id,
            status="pending",
            created_at=now,
            estimated_remaining_seconds=estimated_remaining_seconds,
            latest_metrics={},
            payload_overview={},
        )
        session = self._get_session()
        try:
            session.add(job)
            session.commit()
        finally:
            session.close()
        return {
            "optimization_id": optimization_id,
            "status": "pending",
            "created_at": now.isoformat(),
            "started_at": None,
            "completed_at": None,
            "estimated_remaining_seconds": estimated_remaining_seconds,
            "message": None,
            "latest_metrics": {},
            "result": None,
            "payload_overview": {},
        }

    def update_job(self, optimization_id: str, **kwargs: Any) -> None:
        """Update fields on an existing job.

        Args:
            optimization_id: Identifier of the job to update.
            **kwargs: Field names and values to set. Datetime string values
                are automatically parsed, and latest_metrics is merged.
        """
        datetime_fields = {"created_at", "started_at", "completed_at"}
        session = self._get_session()
        try:
            job = session.query(JobModel).filter(JobModel.optimization_id == optimization_id).first()
            if job:
                for key, value in kwargs.items():
                    if hasattr(job, key):
                        if key in datetime_fields and isinstance(value, str):
                            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        if key == "latest_metrics" and job.latest_metrics:
                            merged = dict(job.latest_metrics)
                            merged.update(value)
                            setattr(job, key, merged)
                        else:
                            setattr(job, key, value)
                session.commit()
        finally:
            session.close()

    def get_job(self, optimization_id: str) -> Dict[str, Any]:
        """Retrieve a single job by its identifier.

        Args:
            optimization_id: Identifier of the job to retrieve.

        Returns:
            Dictionary representation of the job.

        Raises:
            KeyError: If the job does not exist.
        """
        session = self._get_session()
        try:
            job = session.query(JobModel).filter(JobModel.optimization_id == optimization_id).first()
            if not job:
                raise KeyError(f"Job '{optimization_id}' not found")
            return self._job_to_dict(job)
        finally:
            session.close()

    def job_exists(self, optimization_id: str) -> bool:
        """Check whether a job exists in the store.

        Args:
            optimization_id: Identifier of the job to check.

        Returns:
            True if the job exists, False otherwise.
        """
        session = self._get_session()
        try:
            return session.query(JobModel).filter(JobModel.optimization_id == optimization_id).first() is not None
        finally:
            session.close()

    def delete_job(self, optimization_id: str) -> None:
        """Delete a job and all its associated logs and progress events.

        Args:
            optimization_id: Identifier of the job to delete.
        """
        session = self._get_session()
        try:
            session.query(LogEntryModel).filter(LogEntryModel.optimization_id == optimization_id).delete()
            session.query(ProgressEventModel).filter(ProgressEventModel.optimization_id == optimization_id).delete()
            session.query(JobModel).filter(JobModel.optimization_id == optimization_id).delete()
            session.commit()
        finally:
            session.close()

    def recover_orphaned_jobs(self) -> int:
        """Mark running/validating jobs as failed after a service restart.

        Returns:
            Number of orphaned jobs recovered.
        """
        session = self._get_session()
        try:
            now = datetime.now(timezone.utc)
            orphaned = (
                session.query(JobModel)
                .filter(JobModel.status.in_(["running", "validating"]))
                .all()
            )
            for job in orphaned:
                job.status = "failed"
                job.message = "Job interrupted by service restart"
                job.completed_at = now
            session.commit()
            count = len(orphaned)
            if count:
                logger.warning("Recovered %d orphaned jobs from previous crash", count)
            return count
        finally:
            session.close()

    def recover_pending_jobs(self) -> List[str]:
        """Retrieve optimization IDs that are still pending, ordered by creation time.

        Returns:
            List of pending optimization IDs.
        """
        session = self._get_session()
        try:
            jobs = (
                session.query(JobModel)
                .filter(JobModel.status == "pending")
                .order_by(JobModel.created_at.asc())
                .all()
            )
            return [j.optimization_id for j in jobs]
        finally:
            session.close()

    def set_payload_overview(self, optimization_id: str, overview: Dict[str, Any]) -> None:
        """Store a summary overview of the job payload.

        Args:
            optimization_id: Identifier of the job.
            overview: Dictionary of overview fields to persist.
        """
        session = self._get_session()
        try:
            job = session.query(JobModel).filter(JobModel.optimization_id == optimization_id).first()
            if job:
                job.payload_overview = overview or {}
                job.username = (overview or {}).get("username")
                session.commit()
        finally:
            session.close()

    def record_progress(self, optimization_id: str, message: Optional[str], metrics: Dict[str, Any]) -> None:
        """Record a progress event and merge metrics into the job's latest_metrics.

        Args:
            optimization_id: Identifier of the job.
            message: Optional human-readable progress description.
            metrics: Dictionary of metric key-value pairs to merge.
        """
        now = datetime.now(timezone.utc)
        session = self._get_session()
        try:
            job = session.query(JobModel).filter(JobModel.optimization_id == optimization_id).first()
            if not job:
                return

            event = ProgressEventModel(optimization_id=optimization_id, timestamp=now, event=message, metrics=metrics or {})
            session.add(event)

            if metrics:
                merged = dict(job.latest_metrics or {})
                merged.update(metrics)
                job.latest_metrics = merged

            event_count = session.query(ProgressEventModel).filter(ProgressEventModel.optimization_id == optimization_id).count()
            if event_count > MAX_PROGRESS_EVENTS:
                oldest = (
                    session.query(ProgressEventModel)
                    .filter(ProgressEventModel.optimization_id == optimization_id)
                    .order_by(ProgressEventModel.timestamp.asc())
                    .first()
                )
                if oldest:
                    session.delete(oldest)

            session.commit()
        finally:
            session.close()

    def get_progress_events(self, optimization_id: str) -> List[Dict[str, Any]]:
        """Retrieve all progress events for a job in chronological order.

        Args:
            optimization_id: Identifier of the job.

        Returns:
            List of progress event dictionaries.
        """
        session = self._get_session()
        try:
            events = (
                session.query(ProgressEventModel)
                .filter(ProgressEventModel.optimization_id == optimization_id)
                .order_by(ProgressEventModel.timestamp.asc())
                .all()
            )
            return [
                {"timestamp": e.timestamp.isoformat() if e.timestamp else None, "event": e.event, "metrics": e.metrics or {}}
                for e in events
            ]
        finally:
            session.close()

    def get_progress_count(self, optimization_id: str) -> int:
        """Return the number of progress events recorded for a job.

        Args:
            optimization_id: Identifier of the job.

        Returns:
            Count of progress events.
        """
        session = self._get_session()
        try:
            return session.query(ProgressEventModel).filter(ProgressEventModel.optimization_id == optimization_id).count()
        finally:
            session.close()

    def append_log(self, optimization_id: str, *, level: str, logger_name: str, message: str, timestamp: Optional[datetime] = None, pair_index: Optional[int] = None) -> None:
        """Append a log entry to a job's log history.

        Silently discards entries if the job has been deleted. Enforces a
        maximum of MAX_LOG_ENTRIES per job by removing the oldest entry.

        Args:
            optimization_id: Identifier of the job.
            level: Log level (e.g. "INFO", "ERROR").
            logger_name: Name of the logger that produced the entry.
            message: Log message text.
            timestamp: Optional explicit timestamp; defaults to now (UTC).
        """
        ts = timestamp or datetime.now(timezone.utc)
        session = self._get_session()
        try:
            exists = session.query(JobModel.optimization_id).filter(JobModel.optimization_id == optimization_id).scalar() is not None
            if not exists:
                return

            entry = LogEntryModel(optimization_id=optimization_id, timestamp=ts, level=level, logger=logger_name, message=message, pair_index=pair_index)
            session.add(entry)

            log_count = session.query(LogEntryModel).filter(LogEntryModel.optimization_id == optimization_id).count()
            if log_count > MAX_LOG_ENTRIES:
                oldest = (
                    session.query(LogEntryModel)
                    .filter(LogEntryModel.optimization_id == optimization_id)
                    .order_by(LogEntryModel.timestamp.asc())
                    .first()
                )
                if oldest:
                    session.delete(oldest)

            session.commit()
        finally:
            session.close()

    def get_logs(
        self,
        optimization_id: str,
        *,
        limit: Optional[int] = None,
        offset: int = 0,
        level: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve log entries for a job with optional filtering and pagination.

        Args:
            optimization_id: Identifier of the job.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip. Defaults to 0.
            level: Optional log level filter.

        Returns:
            List of log entry dictionaries ordered by timestamp ascending.
        """
        session = self._get_session()
        try:
            q = (
                session.query(LogEntryModel)
                .filter(LogEntryModel.optimization_id == optimization_id)
            )
            if level:
                q = q.filter(LogEntryModel.level == level)
            q = q.order_by(LogEntryModel.timestamp.asc())
            if offset:
                q = q.offset(offset)
            if limit is not None:
                q = q.limit(limit)
            logs = q.all()
            return [
                {"timestamp": log.timestamp.isoformat() if log.timestamp else None, "level": log.level, "logger": log.logger, "message": log.message, "pair_index": log.pair_index}
                for log in logs
            ]
        finally:
            session.close()

    def get_log_count(self, optimization_id: str, *, level: Optional[str] = None) -> int:
        """Return the number of log entries for a job.

        Args:
            optimization_id: Identifier of the job.
            level: Optional log level filter.

        Returns:
            Count of matching log entries.
        """
        session = self._get_session()
        try:
            q = session.query(LogEntryModel).filter(LogEntryModel.optimization_id == optimization_id)
            if level:
                q = q.filter(LogEntryModel.level == level)
            return q.count()
        finally:
            session.close()

    def list_jobs(self, *, status: Optional[str] = None, username: Optional[str] = None, optimization_type: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """List jobs with optional filtering and pagination.

        Args:
            status: Filter by job status.
            username: Filter by username.
            optimization_type: Filter by job type.
            limit: Maximum number of jobs to return. Defaults to 50.
            offset: Number of jobs to skip. Defaults to 0.

        Returns:
            List of job dictionaries with progress and log counts, ordered
            by creation time descending.
        """
        session = self._get_session()
        try:
            q = session.query(JobModel).order_by(JobModel.created_at.desc())
            if status:
                q = q.filter(JobModel.status == status)
            if username:
                q = q.filter(JobModel.username == username)
            if optimization_type:
                q = q.filter(JobModel.payload_overview["optimization_type"].as_string() == optimization_type)
            jobs = q.offset(offset).limit(limit).all()
            optimization_ids = [j.optimization_id for j in jobs]

            progress_counts = dict(
                session.query(ProgressEventModel.optimization_id, func.count())
                .filter(ProgressEventModel.optimization_id.in_(optimization_ids))
                .group_by(ProgressEventModel.optimization_id).all()
            ) if optimization_ids else {}
            log_counts = dict(
                session.query(LogEntryModel.optimization_id, func.count())
                .filter(LogEntryModel.optimization_id.in_(optimization_ids))
                .group_by(LogEntryModel.optimization_id).all()
            ) if optimization_ids else {}

            result = []
            for j in jobs:
                d = self._job_to_dict(j)
                d["progress_count"] = progress_counts.get(j.optimization_id, 0)
                d["log_count"] = log_counts.get(j.optimization_id, 0)
                result.append(d)
            return result
        finally:
            session.close()

    def count_jobs(self, *, status: Optional[str] = None, username: Optional[str] = None, optimization_type: Optional[str] = None) -> int:
        """Count jobs matching the given filters.

        Args:
            status: Filter by job status.
            username: Filter by username.
            optimization_type: Filter by job type.

        Returns:
            Number of matching jobs.
        """
        session = self._get_session()
        try:
            q = session.query(func.count(JobModel.optimization_id))
            if status:
                q = q.filter(JobModel.status == status)
            if username:
                q = q.filter(JobModel.username == username)
            if optimization_type:
                q = q.filter(JobModel.payload_overview["optimization_type"].as_string() == optimization_type)
            return q.scalar() or 0
        finally:
            session.close()
