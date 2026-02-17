"""Local SQLite database backend for job storage.

Provides SQLAlchemy models and LocalDBJobStore for persisting job state
to a local SQLite database.
"""

import logging
import os
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


class LocalDBJobStore:
    """SQLite-backed job storage using SQLAlchemy.

    Provides persistent local storage for job data. Data survives restarts.

    Args:
        db_path: Path to SQLite database file. Defaults to 'dspy_jobs.db'.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or os.getenv("LOCAL_DB_PATH", DEFAULT_DB_PATH)
        self._engine = create_engine(f"sqlite:///{self._db_path}", echo=False)
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)
        self._lock = Lock()
        logger.info("Initialized local SQLite database at %s", self._db_path)

    def _get_session(self) -> Session:
        return self._session_factory()

    def _job_to_dict(self, job: JobModel) -> Dict[str, Any]:
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
        with self._lock:
            session = self._get_session()
            try:
                return session.query(JobModel).filter(JobModel.job_id == job_id).first() is not None
            finally:
                session.close()

    def delete_job(self, job_id: str) -> None:
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

    def set_payload_overview(self, job_id: str, overview: Dict[str, Any]) -> None:
        with self._lock:
            session = self._get_session()
            try:
                job = session.query(JobModel).filter(JobModel.job_id == job_id).first()
                if job:
                    job.payload_overview = overview or {}
                    session.commit()
            finally:
                session.close()

    def record_progress(self, job_id: str, message: Optional[str], metrics: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        with self._lock:
            session = self._get_session()
            try:
                event = ProgressEventModel(job_id=job_id, timestamp=now, event=message, metrics=metrics or {})
                session.add(event)

                job = session.query(JobModel).filter(JobModel.job_id == job_id).first()
                if job:
                    if metrics:
                        merged = dict(job.latest_metrics or {})
                        merged.update(metrics)
                        job.latest_metrics = merged
                    if message:
                        job.message = message

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
        with self._lock:
            session = self._get_session()
            try:
                return session.query(ProgressEventModel).filter(ProgressEventModel.job_id == job_id).count()
            finally:
                session.close()

    def append_log(self, job_id: str, *, level: str, logger_name: str, message: str, timestamp: Optional[datetime] = None) -> None:
        ts = timestamp or datetime.now(timezone.utc)
        with self._lock:
            session = self._get_session()
            try:
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

    def get_logs(self, job_id: str) -> List[Dict[str, Any]]:
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
                    {"timestamp": log.timestamp.isoformat() if log.timestamp else None, "level": log.level, "logger": log.logger, "message": log.message}
                    for log in logs
                ]
            finally:
                session.close()

    def get_log_count(self, job_id: str) -> int:
        with self._lock:
            session = self._get_session()
            try:
                return session.query(LogEntryModel).filter(LogEntryModel.job_id == job_id).count()
            finally:
                session.close()

    def list_jobs(self, *, status: Optional[str] = None, username: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        with self._lock:
            session = self._get_session()
            try:
                q = session.query(JobModel).order_by(JobModel.created_at.desc())
                if status:
                    q = q.filter(JobModel.status == status)
                if username:
                    # username is stored inside the payload_overview JSON column
                    all_jobs = q.all()
                    filtered = [j for j in all_jobs if (j.payload_overview or {}).get("username") == username]
                    return [self._job_to_dict(j) for j in filtered[offset:offset + limit]]
                jobs = q.offset(offset).limit(limit).all()
                return [self._job_to_dict(j) for j in jobs]
            finally:
                session.close()
