"""Local SQLite database backend for job storage.

Provides SQLAlchemy models and LocalDBJobStore for persisting job state
to a local SQLite database when remote DB is unavailable.
"""

import json
import logging
import os
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text, create_engine
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
    estimated_total_seconds = Column(Float, nullable=True)
    message = Column(Text, nullable=True)
    latest_metrics = Column(JSON, default=dict)
    result = Column(JSON, nullable=True)
    payload_overview = Column(JSON, default=dict)
    payload = Column(JSON, nullable=True)


class ProgressEventModel(Base):
    """SQLAlchemy model for the job_progress_events table."""

    __tablename__ = "job_progress_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    event = Column(String(255), nullable=True)
    metrics = Column(JSON, default=dict)


class LogEntryModel(Base):
    """SQLAlchemy model for the job_logs table."""

    __tablename__ = "job_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    level = Column(String(20), nullable=False)
    logger = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)


class LocalDBJobStore:
    """SQLite-backed job storage using SQLAlchemy.

    Provides persistent local storage for job data when remote DB
    is not available. Data survives restarts.

    Args:
        db_path: Path to SQLite database file. Defaults to 'dspy_jobs.db'.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize the local SQLite database.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path or os.getenv("LOCAL_DB_PATH", DEFAULT_DB_PATH)
        self._engine = create_engine(f"sqlite:///{self._db_path}", echo=False)
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)
        self._lock = Lock()
        logger.info("Initialized local SQLite database at %s", self._db_path)

    def _get_session(self) -> Session:
        """Create a new database session.

        Returns:
            Session: SQLAlchemy session instance.
        """
        return self._session_factory()

    def create_job(
        self,
        job_id: str,
        estimated_total_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Create a new job record in the local database.

        Args:
            job_id: Unique job identifier.
            estimated_total_seconds: Optional time estimate.

        Returns:
            Dict containing the initial job state.
        """
        now = datetime.now(timezone.utc)
        job = JobModel(
            job_id=job_id,
            status="pending",
            created_at=now,
            estimated_total_seconds=estimated_total_seconds,
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
            "estimated_total_seconds": estimated_total_seconds,
            "message": None,
            "latest_metrics": {},
            "result": None,
            "payload_overview": {},
        }

    def update_job(self, job_id: str, **kwargs: Any) -> None:
        """Update job fields in the local database.

        Args:
            job_id: Job identifier.
            **kwargs: Fields to update.
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
        """Retrieve job data from the local database.

        Args:
            job_id: Job identifier.

        Returns:
            Dict containing job state.

        Raises:
            KeyError: If job does not exist.
        """
        with self._lock:
            session = self._get_session()
            try:
                job = session.query(JobModel).filter(JobModel.job_id == job_id).first()
                if not job:
                    raise KeyError(f"Job '{job_id}' not found")

                return {
                    "job_id": job.job_id,
                    "status": job.status,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                    "estimated_total_seconds": job.estimated_total_seconds,
                    "message": job.message,
                    "latest_metrics": job.latest_metrics or {},
                    "result": job.result,
                    "payload_overview": job.payload_overview or {},
                    "payload": job.payload,
                }
            finally:
                session.close()

    def record_progress(
        self,
        job_id: str,
        message: Optional[str],
        metrics: Dict[str, Any],
    ) -> None:
        """Record a progress event for a job.

        Args:
            job_id: Job identifier.
            message: Optional status message.
            metrics: Metric payload.
        """
        now = datetime.now(timezone.utc)

        with self._lock:
            session = self._get_session()
            try:
                event = ProgressEventModel(
                    job_id=job_id,
                    timestamp=now,
                    event=message,
                    metrics=metrics or {},
                )
                session.add(event)

                job = session.query(JobModel).filter(JobModel.job_id == job_id).first()
                if job:
                    if metrics:
                        merged = dict(job.latest_metrics or {})
                        merged.update(metrics)
                        job.latest_metrics = merged
                    if message:
                        job.message = message

                event_count = (
                    session.query(ProgressEventModel)
                    .filter(ProgressEventModel.job_id == job_id)
                    .count()
                )
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
        """Retrieve all progress events for a job.

        Args:
            job_id: Job identifier.

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
                    {
                        "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                        "event": e.event,
                        "metrics": e.metrics or {},
                    }
                    for e in events
                ]
            finally:
                session.close()

    def append_log(
        self,
        job_id: str,
        *,
        level: str,
        logger_name: str,
        message: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Append a log entry for the job.

        Args:
            job_id: Job identifier.
            level: Log level string.
            logger_name: Logger name.
            message: Log message.
            timestamp: Optional timestamp.
        """
        ts = timestamp or datetime.now(timezone.utc)

        with self._lock:
            session = self._get_session()
            try:
                entry = LogEntryModel(
                    job_id=job_id,
                    timestamp=ts,
                    level=level,
                    logger=logger_name,
                    message=message,
                )
                session.add(entry)

                log_count = (
                    session.query(LogEntryModel)
                    .filter(LogEntryModel.job_id == job_id)
                    .count()
                )
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

    def get_logs(self, job_id: str) -> List[Dict[str, Any]]:
        """Retrieve all log entries for a job.

        Args:
            job_id: Job identifier.

        Returns:
            List of log entry dictionaries.
        """
        with self._lock:
            session = self._get_session()
            try:
                logs = (
                    session.query(LogEntryModel)
                    .filter(LogEntryModel.job_id == job_id)
                    .order_by(LogEntryModel.timestamp.asc())
                    .all()
                )
                return [
                    {
                        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                        "level": log.level,
                        "logger": log.logger,
                        "message": log.message,
                    }
                    for log in logs
                ]
            finally:
                session.close()

    def set_payload_overview(self, job_id: str, overview: Dict[str, Any]) -> None:
        """Store payload overview metadata.

        Args:
            job_id: Job identifier.
            overview: Payload overview dictionary.
        """
        with self._lock:
            session = self._get_session()
            try:
                job = session.query(JobModel).filter(JobModel.job_id == job_id).first()
                if job:
                    job.payload_overview = overview or {}
                    session.commit()
            finally:
                session.close()

    def job_exists(self, job_id: str) -> bool:
        """Check if a job exists in the local database.

        Args:
            job_id: Job identifier.

        Returns:
            bool: True if job exists.
        """
        with self._lock:
            session = self._get_session()
            try:
                job = session.query(JobModel).filter(JobModel.job_id == job_id).first()
                return job is not None
            finally:
                session.close()

    def delete_job(self, job_id: str) -> None:
        """Delete all data for a job.

        Args:
            job_id: Job identifier.
        """
        with self._lock:
            session = self._get_session()
            try:
                session.query(LogEntryModel).filter(LogEntryModel.job_id == job_id).delete()
                session.query(ProgressEventModel).filter(
                    ProgressEventModel.job_id == job_id
                ).delete()
                session.query(JobModel).filter(JobModel.job_id == job_id).delete()
                session.commit()
            finally:
                session.close()
