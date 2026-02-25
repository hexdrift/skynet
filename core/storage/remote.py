"""PostgreSQL database backend for job storage.

Provides RemoteDBJobStore for persisting job state to a PostgreSQL database
using the same SQLAlchemy models as LocalDBJobStore.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from .local import Base, JobModel, LogEntryModel, ProgressEventModel

logger = logging.getLogger(__name__)

MAX_PROGRESS_EVENTS = 5000
MAX_LOG_ENTRIES = 5000


class RemoteDBJobStore:
    """PostgreSQL-backed job storage using SQLAlchemy.

    Reuses the same SQLAlchemy models as LocalDBJobStore but connects
    to a PostgreSQL database. No threading lock needed — PostgreSQL
    handles concurrent access natively.

    Args:
        db_url: PostgreSQL connection string (e.g., "postgresql://user:pass@host:5432/db").
    """

    def __init__(self, db_url: str) -> None:
        self._engine = create_engine(db_url, echo=False, pool_pre_ping=True)
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)
        logger.info("Initialized PostgreSQL database at %s", db_url.split("@")[-1] if "@" in db_url else db_url)

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
        session = self._get_session()
        try:
            job = session.query(JobModel).filter(JobModel.job_id == job_id).first()
            if not job:
                raise KeyError(f"Job '{job_id}' not found")
            return self._job_to_dict(job)
        finally:
            session.close()

    def job_exists(self, job_id: str) -> bool:
        session = self._get_session()
        try:
            return session.query(JobModel).filter(JobModel.job_id == job_id).first() is not None
        finally:
            session.close()

    def delete_job(self, job_id: str) -> None:
        session = self._get_session()
        try:
            session.query(LogEntryModel).filter(LogEntryModel.job_id == job_id).delete()
            session.query(ProgressEventModel).filter(ProgressEventModel.job_id == job_id).delete()
            session.query(JobModel).filter(JobModel.job_id == job_id).delete()
            session.commit()
        finally:
            session.close()

    def recover_orphaned_jobs(self) -> int:
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
        now = datetime.now(timezone.utc)
        session = self._get_session()
        try:
            job = session.query(JobModel).filter(JobModel.job_id == job_id).first()
            if not job:
                return

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
        session = self._get_session()
        try:
            return session.query(ProgressEventModel).filter(ProgressEventModel.job_id == job_id).count()
        finally:
            session.close()

    def append_log(self, job_id: str, *, level: str, logger_name: str, message: str, timestamp: Optional[datetime] = None) -> None:
        ts = timestamp or datetime.now(timezone.utc)
        session = self._get_session()
        try:
            exists = session.query(JobModel.job_id).filter(JobModel.job_id == job_id).scalar() is not None
            if not exists:
                return

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
        session = self._get_session()
        try:
            q = session.query(LogEntryModel).filter(LogEntryModel.job_id == job_id)
            if level:
                q = q.filter(LogEntryModel.level == level)
            return q.count()
        finally:
            session.close()

    def list_jobs(self, *, status: Optional[str] = None, username: Optional[str] = None, job_type: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        session = self._get_session()
        try:
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
        session = self._get_session()
        try:
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
