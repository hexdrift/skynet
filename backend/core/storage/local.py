"""Local SQLite database backend for job storage.

Provides SQLAlchemy models and LocalDBJobStore for persisting job state
to a local SQLite database.
"""

import logging
import os
import json
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Column, DateTime, Float, Integer, PrimaryKeyConstraint, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "dspy_jobs.db"
MAX_PROGRESS_EVENTS = 5000
MAX_LOG_ENTRIES = 5000


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""

    pass


class JobModel(Base):
    """SQLAlchemy model for the jobs table."""

    __tablename__ = "jobs"

    job_id = Column(String(36), primary_key=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    estimated_remaining_seconds = Column(Float, nullable=True)
    message = Column(Text, nullable=True)
    latest_metrics = Column(JSON, default=dict)
    result = Column(JSON, nullable=True)
    payload_overview = Column(JSON, default=dict)
    payload = Column(JSON, nullable=True)
    username = Column(String(255), nullable=True)  # index created by _apply_migrations


class ProgressEventModel(Base):
    """SQLAlchemy model for the job_progress_events table."""

    __tablename__ = "job_progress_events"

    job_id = Column(String(36), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    event = Column(String(255), nullable=True)
    metrics = Column(JSON, default=dict)

    __table_args__ = (PrimaryKeyConstraint("job_id", "timestamp"),)


class LogEntryModel(Base):
    """SQLAlchemy model for the job_logs table."""

    __tablename__ = "job_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    level = Column(String(20), nullable=False)
    logger = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)


class TemplateModel(Base):
    """SQLAlchemy model for the job_templates table."""

    __tablename__ = "job_templates"

    template_id = Column(String(36), primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    username = Column(String(255), nullable=False)
    config = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class LocalDBJobStore:
    """SQLite-backed job storage using SQLAlchemy.

    Provides persistent local storage for job data. Data survives restarts.

    Args:
        db_path: Path to SQLite database file. Defaults to 'dspy_jobs.db'.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize the local SQLite job store.

        Args:
            db_path: Path to the SQLite database file. Falls back to the
                LOCAL_DB_PATH environment variable, then 'dspy_jobs.db'.
        """
        self._db_path = db_path or os.getenv("LOCAL_DB_PATH", DEFAULT_DB_PATH)
        self._engine = create_engine(f"sqlite:///{self._db_path}", echo=False)
        Base.metadata.create_all(self._engine)
        self._apply_migrations()
        self._session_factory = sessionmaker(bind=self._engine)
        self._lock = Lock()
        logger.info("Initialized local SQLite database at %s", self._db_path)

    @property
    def engine(self):
        """Expose the SQLAlchemy engine for shared table operations."""
        return self._engine

    def _apply_migrations(self) -> None:
        """Add columns and indexes missing from existing DB files that create_all cannot alter."""
        from sqlalchemy import text
        with self._engine.connect() as conn:
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(jobs)"))}
            if "username" not in cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN username TEXT"))
                logger.info("Migration: added 'username' column to jobs table")
            # Idempotent: creates index only if it doesn't already exist.
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_jobs_username ON jobs(username)"))

            # Backfill username for rows created before the username column existed.
            rows = conn.execute(
                text("SELECT job_id, payload_overview FROM jobs WHERE username IS NULL")
            ).fetchall()
            updated = 0
            for row in rows:
                job_id = row[0]
                overview_raw = row[1]
                overview: Dict[str, Any] = {}
                if isinstance(overview_raw, dict):
                    overview = overview_raw
                elif isinstance(overview_raw, str):
                    try:
                        parsed = json.loads(overview_raw)
                        if isinstance(parsed, dict):
                            overview = parsed
                    except Exception:
                        pass
                username = overview.get("username")
                if username:
                    conn.execute(
                        text("UPDATE jobs SET username = :username WHERE job_id = :job_id"),
                        {"username": username, "job_id": job_id},
                    )
                    updated += 1
            if updated:
                logger.info("Migration: backfilled username for %d existing jobs", updated)
            conn.commit()

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
            "job_id": job.job_id,
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

    def create_job(self, job_id: str, estimated_remaining_seconds: Optional[float] = None) -> Dict[str, Any]:
        """Create a new job record in the SQLite database.

        Args:
            job_id: Unique identifier for the job.
            estimated_remaining_seconds: Optional initial time estimate.

        Returns:
            Dictionary representation of the newly created job.
        """
        now = datetime.now(timezone.utc)
        job = JobModel(
            job_id=job_id,
            status="pending",
            created_at=now,
            estimated_remaining_seconds=estimated_remaining_seconds,
            latest_metrics={},
            payload_overview={},
        )
        with self._lock:
            session = self._get_session()
            try:
                session.add(job)
                session.commit()
            finally:
                session.close()
        return {
            "job_id": job_id,
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

    def update_job(self, job_id: str, **kwargs: Any) -> None:
        """Update fields on an existing job.

        Args:
            job_id: Identifier of the job to update.
            **kwargs: Field names and values to set. Datetime string values
                are automatically parsed, and latest_metrics is merged.
        """
        datetime_fields = {"created_at", "started_at", "completed_at"}
        with self._lock:
            session = self._get_session()
            try:
                job = session.query(JobModel).filter(JobModel.job_id == job_id).first()
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

    def get_job(self, job_id: str) -> Dict[str, Any]:
        """Retrieve a single job by its identifier.

        Args:
            job_id: Identifier of the job to retrieve.

        Returns:
            Dictionary representation of the job.

        Raises:
            KeyError: If the job does not exist.
        """
        with self._lock:
            session = self._get_session()
            try:
                job = session.query(JobModel).filter(JobModel.job_id == job_id).first()
                if not job:
                    raise KeyError(f"Job '{job_id}' not found")
                return self._job_to_dict(job)
            finally:
                session.close()

    def job_exists(self, job_id: str) -> bool:
        """Check whether a job exists in the store.

        Args:
            job_id: Identifier of the job to check.

        Returns:
            True if the job exists, False otherwise.
        """
        with self._lock:
            session = self._get_session()
            try:
                return session.query(JobModel).filter(JobModel.job_id == job_id).first() is not None
            finally:
                session.close()

    def delete_job(self, job_id: str) -> None:
        """Delete a job and all its associated logs and progress events.

        Args:
            job_id: Identifier of the job to delete.
        """
        with self._lock:
            session = self._get_session()
            try:
                session.query(LogEntryModel).filter(LogEntryModel.job_id == job_id).delete()
                session.query(ProgressEventModel).filter(ProgressEventModel.job_id == job_id).delete()
                session.query(JobModel).filter(JobModel.job_id == job_id).delete()
                session.commit()
            finally:
                session.close()

    def recover_orphaned_jobs(self) -> int:
        """Mark running/validating jobs as failed after a service restart.

        Returns:
            Number of orphaned jobs recovered.
        """
        with self._lock:
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
        """Retrieve job IDs that are still pending, ordered by creation time.

        Returns:
            List of pending job IDs.
        """
        with self._lock:
            session = self._get_session()
            try:
                jobs = (
                    session.query(JobModel)
                    .filter(JobModel.status == "pending")
                    .order_by(JobModel.created_at.asc())
                    .all()
                )
                return [j.job_id for j in jobs]
            finally:
                session.close()

    def set_payload_overview(self, job_id: str, overview: Dict[str, Any]) -> None:
        """Store a summary overview of the job payload.

        Args:
            job_id: Identifier of the job.
            overview: Dictionary of overview fields to persist.
        """
        with self._lock:
            session = self._get_session()
            try:
                job = session.query(JobModel).filter(JobModel.job_id == job_id).first()
                if job:
                    job.payload_overview = overview or {}
                    job.username = (overview or {}).get("username")
                    session.commit()
            finally:
                session.close()

    def record_progress(self, job_id: str, message: Optional[str], metrics: Dict[str, Any]) -> None:
        """Record a progress event and merge metrics into the job's latest_metrics.

        Args:
            job_id: Identifier of the job.
            message: Optional human-readable progress description.
            metrics: Dictionary of metric key-value pairs to merge.
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            session = self._get_session()
            try:
                job = session.query(JobModel).filter(JobModel.job_id == job_id).first()
                if not job:
                    return  # job deleted (cancelled); discard to prevent orphan rows

                event = ProgressEventModel(job_id=job_id, timestamp=now, event=message, metrics=metrics or {})
                session.add(event)

                if metrics:
                    merged = dict(job.latest_metrics or {})
                    merged.update(metrics)
                    job.latest_metrics = merged

                event_count = session.query(ProgressEventModel).filter(ProgressEventModel.job_id == job_id).count()
                if event_count > MAX_PROGRESS_EVENTS:
                    oldest = (
                        session.query(ProgressEventModel)
                        .filter(ProgressEventModel.job_id == job_id)
                        .order_by(ProgressEventModel.timestamp.asc())
                        .first()
                    )
                    if oldest:
                        session.delete(oldest)

                session.commit()
            finally:
                session.close()

    def get_progress_events(self, job_id: str) -> List[Dict[str, Any]]:
        """Retrieve all progress events for a job in chronological order.

        Args:
            job_id: Identifier of the job.

        Returns:
            List of progress event dictionaries.
        """
        with self._lock:
            session = self._get_session()
            try:
                events = (
                    session.query(ProgressEventModel)
                    .filter(ProgressEventModel.job_id == job_id)
                    .order_by(ProgressEventModel.timestamp.asc())
                    .all()
                )
                return [
                    {"timestamp": e.timestamp.isoformat() if e.timestamp else None, "event": e.event, "metrics": e.metrics or {}}
                    for e in events
                ]
            finally:
                session.close()

    def get_progress_count(self, job_id: str) -> int:
        """Return the number of progress events recorded for a job.

        Args:
            job_id: Identifier of the job.

        Returns:
            Count of progress events.
        """
        with self._lock:
            session = self._get_session()
            try:
                return session.query(ProgressEventModel).filter(ProgressEventModel.job_id == job_id).count()
            finally:
                session.close()

    def append_log(self, job_id: str, *, level: str, logger_name: str, message: str, timestamp: Optional[datetime] = None) -> None:
        """Append a log entry to a job's log history.

        Silently discards entries if the job has been deleted. Enforces a
        maximum of MAX_LOG_ENTRIES per job by removing the oldest entry.

        Args:
            job_id: Identifier of the job.
            level: Log level (e.g. "INFO", "ERROR").
            logger_name: Name of the logger that produced the entry.
            message: Log message text.
            timestamp: Optional explicit timestamp; defaults to now (UTC).
        """
        ts = timestamp or datetime.now(timezone.utc)
        with self._lock:
            session = self._get_session()
            try:
                exists = session.query(JobModel.job_id).filter(JobModel.job_id == job_id).scalar() is not None
                if not exists:
                    return  # job deleted (cancelled); discard to prevent orphan rows

                entry = LogEntryModel(job_id=job_id, timestamp=ts, level=level, logger=logger_name, message=message)
                session.add(entry)

                log_count = session.query(LogEntryModel).filter(LogEntryModel.job_id == job_id).count()
                if log_count > MAX_LOG_ENTRIES:
                    oldest = (
                        session.query(LogEntryModel)
                        .filter(LogEntryModel.job_id == job_id)
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
            offset: Number of entries to skip. Defaults to 0.
            level: Optional log level filter.

        Returns:
            List of log entry dictionaries ordered by timestamp ascending.
        """
        with self._lock:
            session = self._get_session()
            try:
                q = (
                    session.query(LogEntryModel)
                    .filter(LogEntryModel.job_id == job_id)
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
                    {"timestamp": log.timestamp.isoformat() if log.timestamp else None, "level": log.level, "logger": log.logger, "message": log.message}
                    for log in logs
                ]
            finally:
                session.close()

    def get_log_count(self, job_id: str, *, level: Optional[str] = None) -> int:
        """Return the number of log entries for a job.

        Args:
            job_id: Identifier of the job.
            level: Optional log level filter.

        Returns:
            Count of matching log entries.
        """
        with self._lock:
            session = self._get_session()
            try:
                q = session.query(LogEntryModel).filter(LogEntryModel.job_id == job_id)
                if level:
                    q = q.filter(LogEntryModel.level == level)
                return q.count()
            finally:
                session.close()

    def list_jobs(self, *, status: Optional[str] = None, username: Optional[str] = None, job_type: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """List jobs with optional filtering and pagination.

        Args:
            status: Filter by job status.
            username: Filter by username.
            job_type: Filter by job type.
            limit: Maximum number of jobs to return. Defaults to 50.
            offset: Number of jobs to skip. Defaults to 0.

        Returns:
            List of job dictionaries with progress and log counts, ordered
            by creation time descending.
        """
        with self._lock:
            session = self._get_session()
            try:
                from sqlalchemy import func
                q = session.query(JobModel).order_by(JobModel.created_at.desc())
                if status:
                    q = q.filter(JobModel.status == status)
                if username:
                    q = q.filter(JobModel.username == username)
                if job_type:
                    q = q.filter(JobModel.payload_overview["job_type"].as_string() == job_type)
                jobs = q.offset(offset).limit(limit).all()
                job_ids = [j.job_id for j in jobs]

                progress_counts = dict(
                    session.query(ProgressEventModel.job_id, func.count())
                    .filter(ProgressEventModel.job_id.in_(job_ids))
                    .group_by(ProgressEventModel.job_id).all()
                ) if job_ids else {}
                log_counts = dict(
                    session.query(LogEntryModel.job_id, func.count())
                    .filter(LogEntryModel.job_id.in_(job_ids))
                    .group_by(LogEntryModel.job_id).all()
                ) if job_ids else {}

                result = []
                for j in jobs:
                    d = self._job_to_dict(j)
                    d["progress_count"] = progress_counts.get(j.job_id, 0)
                    d["log_count"] = log_counts.get(j.job_id, 0)
                    result.append(d)
                return result
            finally:
                session.close()

    def count_jobs(self, *, status: Optional[str] = None, username: Optional[str] = None, job_type: Optional[str] = None) -> int:
        """Count jobs matching the given filters.

        Args:
            status: Filter by job status.
            username: Filter by username.
            job_type: Filter by job type.

        Returns:
            Number of matching jobs.
        """
        with self._lock:
            session = self._get_session()
            try:
                from sqlalchemy import func
                q = session.query(func.count(JobModel.job_id))
                if status:
                    q = q.filter(JobModel.status == status)
                if username:
                    q = q.filter(JobModel.username == username)
                if job_type:
                    q = q.filter(JobModel.payload_overview["job_type"].as_string() == job_type)
                return q.scalar() or 0
            finally:
                session.close()
