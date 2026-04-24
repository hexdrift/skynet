"""PostgreSQL database backend for job storage.

Provides RemoteDBJobStore for persisting job state to a PostgreSQL database.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import Session, sessionmaker

from ..constants import STRUCTURAL_PROGRESS_EVENTS
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
        self._engine = create_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            pool_timeout=30,
        )
        self._bootstrap_pgvector()
        Base.metadata.create_all(self._engine)
        self._bootstrap_vector_indexes()
        self._session_factory = sessionmaker(bind=self._engine)
        logger.info("Initialized PostgreSQL database at %s", db_url.split("@")[-1] if "@" in db_url else db_url)

        with self._engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'job_logs' AND column_name = 'pair_index'"
                )
            )
            if result.fetchone() is None:
                conn.execute(text("ALTER TABLE job_logs ADD COLUMN pair_index INTEGER"))
                conn.commit()
                logger.info("Migration: added 'pair_index' column to job_logs table")

        self._migrate_job_embeddings_columns()

    def _bootstrap_pgvector(self) -> None:
        """Ensure the pgvector extension exists before creating Vector columns.

        Safe to call repeatedly. If the database role lacks the privilege
        to install the extension, the log line below is the operator's
        hint to run ``CREATE EXTENSION vector`` once out-of-band.
        """
        try:
            with self._engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
        except Exception as exc:
            logger.warning(
                "pgvector extension bootstrap failed (%s). "
                "Recommendation service will be unavailable until an admin runs "
                "'CREATE EXTENSION vector' on the database.",
                exc,
            )

    def _migrate_job_embeddings_columns(self) -> None:
        """Add Phase 2 columns (quality gate + dashboard projection) on warm databases.

        ``create_all`` adds columns for fresh installs; this fills the gap for
        anyone who has an older ``job_embeddings`` table from Phase 1. Each
        ADD COLUMN is IF NOT EXISTS so the migration is idempotent.
        """
        migrations = [
            "ALTER TABLE job_embeddings ADD COLUMN IF NOT EXISTS is_recommendable BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE job_embeddings ADD COLUMN IF NOT EXISTS baseline_metric DOUBLE PRECISION",
            "ALTER TABLE job_embeddings ADD COLUMN IF NOT EXISTS optimized_metric DOUBLE PRECISION",
            "ALTER TABLE job_embeddings ADD COLUMN IF NOT EXISTS summary_text TEXT",
            "ALTER TABLE job_embeddings ADD COLUMN IF NOT EXISTS signature_code TEXT",
            "ALTER TABLE job_embeddings ADD COLUMN IF NOT EXISTS metric_name VARCHAR(255)",
            "ALTER TABLE job_embeddings ADD COLUMN IF NOT EXISTS optimizer_name VARCHAR(64)",
            "ALTER TABLE job_embeddings ADD COLUMN IF NOT EXISTS optimizer_kwargs JSON",
            "ALTER TABLE job_embeddings ADD COLUMN IF NOT EXISTS module_name VARCHAR(128)",
            "ALTER TABLE job_embeddings ADD COLUMN IF NOT EXISTS task_name VARCHAR(255)",
            "ALTER TABLE job_embeddings ADD COLUMN IF NOT EXISTS projection_x DOUBLE PRECISION",
            "ALTER TABLE job_embeddings ADD COLUMN IF NOT EXISTS projection_y DOUBLE PRECISION",
            (
                "CREATE INDEX IF NOT EXISTS ix_job_embeddings_recommendable "
                "ON job_embeddings (is_recommendable) WHERE is_recommendable = TRUE"
            ),
        ]
        try:
            with self._engine.connect() as conn:
                for stmt in migrations:
                    conn.execute(text(stmt))
                conn.commit()
        except Exception as exc:
            logger.warning("job_embeddings Phase-2 migration skipped: %s", exc)

    def _bootstrap_vector_indexes(self) -> None:
        """Create HNSW cosine indexes on the job_embeddings vector columns.

        SQLAlchemy's create_all can't express HNSW, and we don't want to
        pay for a reindex on every restart — the IF NOT EXISTS guard
        makes the call free on warm databases.
        """
        statements = [
            (
                "CREATE INDEX IF NOT EXISTS idx_job_embeddings_summary_hnsw "
                "ON job_embeddings USING hnsw (embedding_summary vector_cosine_ops)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS idx_job_embeddings_code_hnsw "
                "ON job_embeddings USING hnsw (embedding_code vector_cosine_ops)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS idx_job_embeddings_schema_hnsw "
                "ON job_embeddings USING hnsw (embedding_schema vector_cosine_ops)"
            ),
        ]
        try:
            with self._engine.connect() as conn:
                for stmt in statements:
                    conn.execute(text(stmt))
                conn.commit()
        except Exception as exc:
            logger.warning("HNSW index bootstrap skipped: %s", exc)

    @property
    def engine(self):
        """The SQLAlchemy engine backing this store (for shared table operations)."""
        return self._engine

    def _get_session(self) -> Session:
        """Create and return a new SQLAlchemy session."""
        return self._session_factory()

    def _job_to_dict(self, job: JobModel) -> dict[str, Any]:
        """Convert a JobModel ORM instance to a plain dict with ISO-formatted timestamps."""
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

    def create_job(self, optimization_id: str, estimated_remaining_seconds: float | None = None) -> dict[str, Any]:
        """Create a new job record in the database and return its dict representation."""
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
            session.refresh(job)
            return self._job_to_dict(job)
        finally:
            session.close()

    def update_job(self, optimization_id: str, **kwargs: Any) -> None:
        """Update fields on an existing job; raises KeyError if not found.

        Datetime string values are automatically parsed; latest_metrics is merged instead of replaced.
        """
        datetime_fields = {"created_at", "started_at", "completed_at"}
        session = self._get_session()
        try:
            job = session.query(JobModel).filter(JobModel.optimization_id == optimization_id).first()
            if not job:
                raise KeyError(f"Job '{optimization_id}' not found")
            for key, value in kwargs.items():
                if not hasattr(job, key):
                    raise ValueError(f"Unknown field '{key}' on JobModel")
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

    def get_job(self, optimization_id: str) -> dict[str, Any]:
        """Retrieve a job by its ID; raises KeyError if not found."""
        session = self._get_session()
        try:
            job = session.query(JobModel).filter(JobModel.optimization_id == optimization_id).first()
            if not job:
                raise KeyError(f"Job '{optimization_id}' not found")
            return self._job_to_dict(job)
        finally:
            session.close()

    def job_exists(self, optimization_id: str) -> bool:
        """Return True if the job exists in the database."""
        session = self._get_session()
        try:
            return session.query(JobModel).filter(JobModel.optimization_id == optimization_id).first() is not None
        finally:
            session.close()

    def delete_job(self, optimization_id: str) -> None:
        """Delete a job and all its associated logs and progress events."""
        session = self._get_session()
        try:
            session.query(LogEntryModel).filter(LogEntryModel.optimization_id == optimization_id).delete()
            session.query(ProgressEventModel).filter(ProgressEventModel.optimization_id == optimization_id).delete()
            session.query(JobModel).filter(JobModel.optimization_id == optimization_id).delete()
            session.commit()
        finally:
            session.close()

    def get_jobs_status_by_ids(self, optimization_ids: list[str]) -> dict[str, str]:
        """Return a ``{id: status}`` map for the requested IDs.

        Runs a single ``SELECT ... WHERE optimization_id IN (...)``
        so batch existence + status checks cost one round trip
        regardless of how many IDs are supplied.

        Args:
            optimization_ids: Identifiers to look up.

        Returns:
            Mapping from existing job IDs to their current status
            string. Missing IDs are absent from the returned dict.
        """
        if not optimization_ids:
            return {}
        session = self._get_session()
        try:
            rows = (
                session.query(JobModel.optimization_id, JobModel.status)
                .filter(JobModel.optimization_id.in_(optimization_ids))
                .all()
            )
            return {r[0]: r[1] for r in rows}
        finally:
            session.close()

    def delete_jobs(self, optimization_ids: list[str]) -> int:
        """Hard-delete a batch of jobs in a single transaction.

        Drops the associated log and progress-event rows first
        (three bulk ``DELETE`` queries total) then commits once, so
        the round-trip cost is bounded regardless of batch size.

        Args:
            optimization_ids: Identifiers to delete. Missing IDs are
                tolerated — only rows that actually exist are
                removed.

        Returns:
            Number of job rows actually deleted.
        """
        if not optimization_ids:
            return 0
        session = self._get_session()
        try:
            session.query(LogEntryModel).filter(LogEntryModel.optimization_id.in_(optimization_ids)).delete(
                synchronize_session=False
            )
            session.query(ProgressEventModel).filter(ProgressEventModel.optimization_id.in_(optimization_ids)).delete(
                synchronize_session=False
            )
            deleted = (
                session.query(JobModel)
                .filter(JobModel.optimization_id.in_(optimization_ids))
                .delete(synchronize_session=False)
            )
            session.commit()
            return int(deleted or 0)
        finally:
            session.close()

    def recover_orphaned_jobs(self) -> int:
        """Mark running/validating jobs as failed after a service restart; returns count recovered."""
        session = self._get_session()
        try:
            now = datetime.now(timezone.utc)
            orphaned = session.query(JobModel).filter(JobModel.status.in_(["running", "validating"])).all()
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

    def recover_pending_jobs(self) -> list[str]:
        """Return IDs of still-pending jobs ordered by creation time."""
        session = self._get_session()
        try:
            jobs = (
                session.query(JobModel).filter(JobModel.status == "pending").order_by(JobModel.created_at.asc()).all()
            )
            return [j.optimization_id for j in jobs]
        finally:
            session.close()

    def set_payload_overview(self, optimization_id: str, overview: dict[str, Any]) -> None:
        """Store a summary overview of the job payload."""
        session = self._get_session()
        try:
            job = session.query(JobModel).filter(JobModel.optimization_id == optimization_id).first()
            if job:
                job.payload_overview = overview or {}
                job.username = (overview or {}).get("username")
                session.commit()
        finally:
            session.close()

    def record_progress(self, optimization_id: str, message: str | None, metrics: dict[str, Any]) -> None:
        """Record a progress event and merge metrics into the job's latest_metrics."""
        now = datetime.now(timezone.utc)
        session = self._get_session()
        try:
            job = session.query(JobModel).filter(JobModel.optimization_id == optimization_id).first()
            if not job:
                return

            event_count = (
                session.query(ProgressEventModel).filter(ProgressEventModel.optimization_id == optimization_id).count()
            )
            if event_count >= MAX_PROGRESS_EVENTS:
                # Evict the oldest non-structural event first — keep phase
                # markers (grid_pair_started, baseline_evaluated, etc.) so
                # the UI can still determine pipeline stage on long runs.
                # Only touch structural rows if nothing else is left.
                oldest = (
                    session.query(ProgressEventModel)
                    .filter(ProgressEventModel.optimization_id == optimization_id)
                    .filter(ProgressEventModel.event.notin_(STRUCTURAL_PROGRESS_EVENTS))
                    .order_by(ProgressEventModel.timestamp.asc())
                    .first()
                )
                if oldest is None:
                    oldest = (
                        session.query(ProgressEventModel)
                        .filter(ProgressEventModel.optimization_id == optimization_id)
                        .order_by(ProgressEventModel.timestamp.asc())
                        .first()
                    )
                if oldest:
                    session.delete(oldest)

            event = ProgressEventModel(
                optimization_id=optimization_id, timestamp=now, event=message, metrics=metrics or {}
            )
            session.add(event)

            if metrics:
                merged = dict(job.latest_metrics or {})
                merged.update(metrics)
                job.latest_metrics = merged

            session.commit()
        finally:
            session.close()

    def get_progress_events(self, optimization_id: str) -> list[dict[str, Any]]:
        """Retrieve all progress events for a job in chronological order."""
        session = self._get_session()
        try:
            events = (
                session.query(ProgressEventModel)
                .filter(ProgressEventModel.optimization_id == optimization_id)
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

    def get_progress_count(self, optimization_id: str) -> int:
        """Return the number of progress events recorded for a job."""
        session = self._get_session()
        try:
            return (
                session.query(ProgressEventModel).filter(ProgressEventModel.optimization_id == optimization_id).count()
            )
        finally:
            session.close()

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
        """Append a log entry; silently discards if job is gone; evicts oldest when at cap."""
        ts = timestamp or datetime.now(timezone.utc)
        session = self._get_session()
        try:
            exists = (
                session.query(JobModel.optimization_id).filter(JobModel.optimization_id == optimization_id).scalar()
                is not None
            )
            if not exists:
                return

            log_count = session.query(LogEntryModel).filter(LogEntryModel.optimization_id == optimization_id).count()
            if log_count >= MAX_LOG_ENTRIES:
                oldest = (
                    session.query(LogEntryModel)
                    .filter(LogEntryModel.optimization_id == optimization_id)
                    .order_by(LogEntryModel.timestamp.asc())
                    .first()
                )
                if oldest:
                    session.delete(oldest)

            entry = LogEntryModel(
                optimization_id=optimization_id,
                timestamp=ts,
                level=level,
                logger=logger_name,
                message=message,
                pair_index=pair_index,
            )
            session.add(entry)

            session.commit()
        finally:
            session.close()

    def get_logs(
        self,
        optimization_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        level: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve log entries for a job, ordered ascending, with optional level filter and pagination."""
        session = self._get_session()
        try:
            q = session.query(LogEntryModel).filter(LogEntryModel.optimization_id == optimization_id)
            if level:
                q = q.filter(LogEntryModel.level == level)
            q = q.order_by(LogEntryModel.timestamp.asc())
            if offset:
                q = q.offset(offset)
            if limit is not None:
                q = q.limit(limit)
            logs = q.all()
            return [
                {
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                    "level": log.level,
                    "logger": log.logger,
                    "message": log.message,
                    "pair_index": log.pair_index,
                }
                for log in logs
            ]
        finally:
            session.close()

    def get_log_count(self, optimization_id: str, *, level: str | None = None) -> int:
        """Return the number of log entries for a job, optionally filtered by level."""
        session = self._get_session()
        try:
            q = session.query(LogEntryModel).filter(LogEntryModel.optimization_id == optimization_id)
            if level:
                q = q.filter(LogEntryModel.level == level)
            return q.count()
        finally:
            session.close()

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

            progress_counts = (
                dict(
                    session.query(ProgressEventModel.optimization_id, func.count())
                    .filter(ProgressEventModel.optimization_id.in_(optimization_ids))
                    .group_by(ProgressEventModel.optimization_id)
                    .all()
                )
                if optimization_ids
                else {}
            )
            log_counts = (
                dict(
                    session.query(LogEntryModel.optimization_id, func.count())
                    .filter(LogEntryModel.optimization_id.in_(optimization_ids))
                    .group_by(LogEntryModel.optimization_id)
                    .all()
                )
                if optimization_ids
                else {}
            )

            result = []
            for j in jobs:
                d = self._job_to_dict(j)
                d["progress_count"] = progress_counts.get(j.optimization_id, 0)
                d["log_count"] = log_counts.get(j.optimization_id, 0)
                result.append(d)
            return result
        finally:
            session.close()

    def count_jobs(
        self, *, status: str | None = None, username: str | None = None, optimization_type: str | None = None
    ) -> int:
        """Count jobs matching the given filters."""
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
