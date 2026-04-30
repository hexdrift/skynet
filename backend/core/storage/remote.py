"""PostgreSQL database backend for job storage.

Provides RemoteDBJobStore for persisting job state to a PostgreSQL database.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlparse

from sqlalchemy import Engine, create_engine, func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from ..config import settings
from ..constants import STRUCTURAL_PROGRESS_EVENTS
from .base import JobRecord, LogEntryRecord, ProgressEventRecord
from .models import Base, JobModel, LogEntryModel, ProgressEventModel, UserQuotaAuditModel, UserQuotaOverrideModel

logger = logging.getLogger(__name__)

MAX_PROGRESS_EVENTS = 5000
MAX_LOG_ENTRIES = 5000
_IMMUTABLE_JOB_COLUMNS = frozenset({"optimization_id"})


class RemoteDBJobStore:
    """PostgreSQL-backed job storage using SQLAlchemy.

    No threading lock needed — PostgreSQL handles concurrent access natively.
    """

    def __init__(self, db_url: str) -> None:
        """Build the SQLAlchemy engine, bootstrap pgvector, and create tables.

        Pool sizing follows ``settings.worker_threads`` with a conservative
        floor so a configured worker pool has enough connections available.

        Args:
            db_url: PostgreSQL DSN to connect to.
        """
        pool_size = max(settings.worker_threads, 10)
        max_overflow = max(settings.worker_threads, 20)
        self.vector_search_enabled = False
        self._max_progress_events = settings.progress_events_per_job_cap
        self._max_log_entries = settings.log_entries_per_job_cap
        self._engine = create_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=3600,
            pool_timeout=30,
        )
        vector_extension_ready = self._bootstrap_pgvector()
        Base.metadata.create_all(self._engine)
        vector_indexes_ready = self._bootstrap_vector_indexes()
        self.vector_search_enabled = vector_extension_ready and vector_indexes_ready
        self._session_factory = sessionmaker(bind=self._engine)
        parsed_url = urlparse(db_url)
        db_location = parsed_url.hostname or "<masked>"
        if parsed_url.port:
            db_location = f"{db_location}:{parsed_url.port}"
        logger.info("Initialized PostgreSQL database at %s", db_location)

    @property
    def _progress_events_cap(self) -> int:
        """Return the per-job progress-event retention cap."""
        return getattr(self, "_max_progress_events", MAX_PROGRESS_EVENTS)

    @property
    def _log_entries_cap(self) -> int:
        """Return the per-job log-entry retention cap."""
        return getattr(self, "_max_log_entries", MAX_LOG_ENTRIES)

    def _bootstrap_pgvector(self) -> bool:
        """Ensure the pgvector extension exists before creating Vector columns.

        Safe to call repeatedly. If the database role lacks the privilege
        to install the extension, the log line below is the operator's
        hint to run ``CREATE EXTENSION vector`` once out-of-band.
        """
        try:
            with self._engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
            return True
        except SQLAlchemyError as exc:
            logger.warning(
                "pgvector extension bootstrap failed (%s). "
                "Recommendation service will be unavailable until an admin runs "
                "'CREATE EXTENSION vector' on the database.",
                exc,
            )
            return False

    def _bootstrap_vector_indexes(self) -> bool:
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
            return True
        except SQLAlchemyError as exc:
            logger.warning("HNSW index bootstrap skipped: %s", exc)
            return False

    @property
    def engine(self) -> Engine:
        """Return the SQLAlchemy engine backing this store.

        Exposed so callers can run shared table operations (direct
        DDL, joined queries) outside the ORM session factory.

        Returns:
            The configured SQLAlchemy engine.
        """
        return self._engine

    def _get_session(self) -> Session:
        """Create and return a new SQLAlchemy session.

        Returns:
            A new session; the caller is responsible for closing it.
        """
        return self._session_factory()

    def _job_to_dict(self, job: JobModel) -> JobRecord:
        """Convert a JobModel ORM instance to its TypedDict representation.

        Args:
            job: SQLAlchemy ORM row to serialize.

        Returns:
            A ``JobRecord`` with ISO-formatted timestamps and JSON columns
            normalized to plain dicts.
        """
        return cast(
            JobRecord,
            {
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
                "username": job.username,
                "optimization_type": job.optimization_type,
            },
        )

    def create_job(self, optimization_id: str, estimated_remaining_seconds: float | None = None) -> JobRecord:
        """Create a new job record in the database.

        Args:
            optimization_id: Unique identifier for the new job.
            estimated_remaining_seconds: Initial ETA, or ``None`` if unknown.

        Returns:
            The newly inserted row as a ``JobRecord``.
        """
        now = datetime.now(UTC)
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
        """Update fields on an existing job.

        Datetime string values are automatically parsed from ISO format;
        ``latest_metrics`` is merged into the existing mapping rather
        than replacing it.

        Args:
            optimization_id: ID of the job to update.
            **kwargs: Column values to overwrite.

        Raises:
            KeyError: When the job does not exist.
            ValueError: When ``kwargs`` contains a column name absent from ``JobModel``.
        """
        datetime_fields = {"created_at", "started_at", "completed_at"}
        mutable_columns = set(JobModel.__table__.columns.keys()) - _IMMUTABLE_JOB_COLUMNS
        invalid_fields = sorted(set(kwargs) - mutable_columns)
        if invalid_fields:
            raise ValueError(f"Unknown field '{invalid_fields[0]}' on JobModel")

        session = self._get_session()
        try:
            job = (
                session.query(JobModel)
                .filter(JobModel.optimization_id == optimization_id)
                .with_for_update()
                .first()
            )
            if not job:
                raise KeyError(f"Job '{optimization_id}' not found")
            for key, value in kwargs.items():
                if key in datetime_fields and isinstance(value, str):
                    value = datetime.fromisoformat(value)
                if key == "latest_metrics" and job.latest_metrics:
                    merged = dict(job.latest_metrics)
                    merged.update(value)
                    setattr(job, key, merged)
                else:
                    setattr(job, key, value)
            session.commit()
        finally:
            session.close()

    def get_job(self, optimization_id: str) -> JobRecord:
        """Retrieve a job by its ID.

        Args:
            optimization_id: ID of the job to fetch.

        Returns:
            The matching ``JobRecord``.

        Raises:
            KeyError: When the job does not exist.
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
        """Return ``True`` if the job exists in the database.

        Args:
            optimization_id: ID to check.

        Returns:
            Whether the row is present.
        """
        session = self._get_session()
        try:
            return session.query(JobModel).filter(JobModel.optimization_id == optimization_id).first() is not None
        finally:
            session.close()

    def delete_job(self, optimization_id: str) -> None:
        """Delete a job and all its associated logs and progress events.

        Missing IDs are a silent no-op.

        Args:
            optimization_id: ID of the job to remove.
        """
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
            optimization_ids: IDs to look up.

        Returns:
            Mapping of present IDs to their status strings; missing IDs
            are simply absent from the result.
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
            optimization_ids: IDs to remove. Duplicates and missing IDs are tolerated.

        Returns:
            The number of job rows actually deleted.
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

    def get_user_quota_override(self, username: str) -> tuple[bool, int | None]:
        """Return the live quota override row for ``username`` if present.

        Args:
            username: User identifier to resolve case-insensitively.

        Returns:
            ``(False, None)`` when no row exists, otherwise ``(True, quota)``.
            A present ``None`` quota means unlimited.
        """
        normalized_username = username.strip().lower()
        if not normalized_username:
            return False, None
        session = self._get_session()
        try:
            row = session.get(UserQuotaOverrideModel, normalized_username)
            if row is None:
                return False, None
            return True, row.quota
        finally:
            session.close()

    def get_effective_user_quota(self, username: str) -> int | None:
        """Resolve a user's quota from live DB override, then static config.

        Args:
            username: User identifier to resolve.

        Returns:
            The numeric quota, or ``None`` for unlimited.
        """
        has_override, quota = self.get_user_quota_override(username)
        if has_override:
            return quota
        return settings.get_user_quota(username)

    def set_user_quota_override(self, username: str, quota: int | None, updated_by: str | None = None) -> None:
        """Create or update the live quota override for a user.

        Args:
            username: User identifier to store case-insensitively.
            quota: Numeric quota, or ``None`` for unlimited.
            updated_by: Optional operator identifier for audit context.

        Raises:
            ValueError: When ``username`` is blank or ``quota`` is below one.
        """
        normalized_username = username.strip().lower()
        if not normalized_username:
            raise ValueError("username must not be blank")
        if quota is not None and quota < 1:
            raise ValueError("quota must be at least 1")
        session = self._get_session()
        try:
            row = session.get(UserQuotaOverrideModel, normalized_username)
            if row is None:
                row = UserQuotaOverrideModel(username=normalized_username)
                session.add(row)
            row.quota = quota
            row.updated_at = datetime.now(UTC)
            row.updated_by = updated_by
            session.commit()
        finally:
            session.close()

    def delete_user_quota_override(self, username: str) -> bool:
        """Delete a live quota override so config fallback applies again.

        Args:
            username: User identifier to clear case-insensitively.

        Returns:
            Whether a row was deleted.
        """
        normalized_username = username.strip().lower()
        if not normalized_username:
            return False
        session = self._get_session()
        try:
            deleted = (
                session.query(UserQuotaOverrideModel)
                .filter(UserQuotaOverrideModel.username == normalized_username)
                .delete()
            )
            session.commit()
            return bool(deleted)
        finally:
            session.close()

    def list_user_quota_overrides(self) -> list[dict[str, Any]]:
        """Return all live quota overrides ordered by username.

        Returns:
            A list of override rows with ISO-formatted ``updated_at`` values.
        """
        session = self._get_session()
        try:
            rows = session.query(UserQuotaOverrideModel).order_by(UserQuotaOverrideModel.username.asc()).all()
            return [
                {
                    "username": row.username,
                    "quota": row.quota,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    "updated_by": row.updated_by,
                }
                for row in rows
            ]
        finally:
            session.close()

    def record_user_quota_audit(
        self,
        *,
        actor: str,
        target_username: str,
        action: str,
        old_quota: int | None,
        new_quota: int | None,
    ) -> None:
        """Record a quota administration audit event.

        Args:
            actor: Admin user who made the change.
            target_username: User whose quota changed.
            action: Operation name such as ``set`` or ``delete``.
            old_quota: Previous live quota, or ``None`` for unlimited/no row.
            new_quota: New live quota, or ``None`` for unlimited/default fallback.
        """
        session = self._get_session()
        try:
            session.add(
                UserQuotaAuditModel(
                    actor=actor.strip().lower(),
                    target_username=target_username.strip().lower(),
                    action=action,
                    old_quota=old_quota,
                    new_quota=new_quota,
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()
        finally:
            session.close()

    def list_user_quota_audit_events(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent quota administration audit events.

        Args:
            limit: Maximum number of recent events to return.

        Returns:
            Recent audit events ordered newest-first.
        """
        session = self._get_session()
        try:
            rows = (
                session.query(UserQuotaAuditModel)
                .order_by(UserQuotaAuditModel.created_at.desc(), UserQuotaAuditModel.id.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": row.id,
                    "actor": row.actor,
                    "target_username": row.target_username,
                    "action": row.action,
                    "old_quota": row.old_quota,
                    "new_quota": row.new_quota,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]
        finally:
            session.close()

    def recover_orphaned_jobs(self) -> int:
        """Reclaim jobs whose worker lease has expired.

        With the DB-backed claim queue, a "stuck" job is one whose
        ``lease_expires_at`` is in the past — the previous worker is presumed
        dead. Such jobs are transitioned to ``failed`` so the user isn't left
        with a permanently "running" row, and a healthy peer pod is free to
        accept new work in the freed slot.

        Rows that have *no* claim at all (``claimed_by IS NULL`` while still
        somehow in ``running``/``validating``) are also recovered, covering
        the bootstrapping case of a fleet that just upgraded from the legacy
        in-memory queue.

        Returns:
            The number of jobs transitioned to ``failed``.
        """
        session = self._get_session()
        try:
            now = datetime.now(UTC)
            orphaned = (
                session.query(JobModel)
                .filter(JobModel.status.in_(["running", "validating"]))
                .filter(
                    (JobModel.lease_expires_at.is_(None)) | (JobModel.lease_expires_at < now)
                )
                .all()
            )
            for job in orphaned:
                job.status = "failed"  # type: ignore[assignment]
                job.message = "Job interrupted by service restart"  # type: ignore[assignment]
                job.completed_at = now  # type: ignore[assignment]
                job.claimed_by = None  # type: ignore[assignment]
                job.claimed_at = None  # type: ignore[assignment]
                job.lease_expires_at = None  # type: ignore[assignment]
            session.commit()
            count = len(orphaned)
            if count:
                logger.warning("Recovered %d orphaned jobs (expired lease)", count)
            return count
        finally:
            session.close()

    def claim_next_job(
        self,
        worker_id: str,
        lease_seconds: float,
    ) -> JobRecord | None:
        """Atomically claim the oldest pending job using FOR UPDATE SKIP LOCKED.

        Two pods running this method concurrently are guaranteed to see
        disjoint result sets — Postgres' ``SKIP LOCKED`` causes each session
        to silently jump over rows the other has already row-locked. The
        outer ``UPDATE`` then writes the lease metadata, completing the claim
        in one round trip.

        On non-PostgreSQL dialects (eg. SQLite in tests) the query falls back
        to a non-locking SELECT-then-UPDATE; that is racy but tests run
        single-threaded so it is sufficient.

        Args:
            worker_id: Identifier of the calling worker (typically pod name).
            lease_seconds: Lease duration; the worker must call
                :meth:`extend_lease` before it expires.

        Returns:
            The claimed ``JobRecord`` or ``None`` if no job was available.
        """
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")

        dialect = self._engine.dialect.name
        if dialect == "postgresql":
            return self._claim_next_job_postgres(worker_id, lease_seconds)
        return self._claim_next_job_fallback(worker_id, lease_seconds)

    def _claim_next_job_postgres(self, worker_id: str, lease_seconds: float) -> JobRecord | None:
        """PostgreSQL fast path using ``FOR UPDATE SKIP LOCKED``."""
        sql = text(
            """
            UPDATE jobs
            SET status = 'validating',
                claimed_by = :worker_id,
                claimed_at = :now,
                lease_expires_at = :lease_until
            WHERE optimization_id = (
                SELECT optimization_id FROM jobs
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING optimization_id
            """
        )
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=lease_seconds)
        with self._engine.begin() as conn:
            result = conn.execute(
                sql,
                {"worker_id": worker_id, "now": now, "lease_until": lease_until},
            )
            row = result.fetchone()
            if row is None:
                return None
            optimization_id = row[0]

        # Re-load the full row through the ORM so the returned dict matches
        # the shape of the rest of the API.
        return self.get_job(optimization_id)

    def _claim_next_job_fallback(self, worker_id: str, lease_seconds: float) -> JobRecord | None:
        """Best-effort claim for non-Postgres backends (tests).

        Holds an exclusive transaction so concurrent claims are serialized at
        the engine level. Not race-safe across processes but adequate for
        single-process test runs.
        """
        session = self._get_session()
        try:
            now = datetime.now(UTC)
            lease_until = now + timedelta(seconds=lease_seconds)
            job = (
                session.query(JobModel)
                .filter(JobModel.status == "pending")
                .order_by(JobModel.created_at.asc())
                .first()
            )
            if job is None:
                return None
            job.status = "validating"  # type: ignore[assignment]
            job.claimed_by = worker_id  # type: ignore[assignment]
            job.claimed_at = now  # type: ignore[assignment]
            job.lease_expires_at = lease_until  # type: ignore[assignment]
            session.commit()
            session.refresh(job)
            return self._job_to_dict(job)
        finally:
            session.close()

    def extend_lease(
        self,
        optimization_id: str,
        worker_id: str,
        lease_seconds: float,
    ) -> bool:
        """Extend the lease iff this worker still owns the claim.

        Args:
            optimization_id: ID of the job whose lease to extend.
            worker_id: Worker identity that originally claimed the job.
            lease_seconds: New lease duration measured from now.

        Returns:
            ``True`` when the lease was extended; ``False`` when the row no
            longer belongs to this worker (caller should abort processing).
        """
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        sql = text(
            """
            UPDATE jobs
            SET lease_expires_at = :lease_until
            WHERE optimization_id = :oid
              AND claimed_by = :worker_id
            """
        )
        lease_until = datetime.now(UTC) + timedelta(seconds=lease_seconds)
        with self._engine.begin() as conn:
            result = conn.execute(
                sql,
                {"oid": optimization_id, "worker_id": worker_id, "lease_until": lease_until},
            )
            return (result.rowcount or 0) > 0

    def release_job(self, optimization_id: str, worker_id: str) -> bool:
        """Clear claim metadata for a job, only if this worker owns it.

        Args:
            optimization_id: ID of the job to release.
            worker_id: Worker identity that claimed it.

        Returns:
            Whether claim metadata was actually cleared.
        """
        sql = text(
            """
            UPDATE jobs
            SET claimed_by = NULL,
                claimed_at = NULL,
                lease_expires_at = NULL
            WHERE optimization_id = :oid
              AND claimed_by = :worker_id
            """
        )
        with self._engine.begin() as conn:
            result = conn.execute(sql, {"oid": optimization_id, "worker_id": worker_id})
            return (result.rowcount or 0) > 0

    def recover_pending_jobs(self) -> list[str]:
        """Return IDs of still-pending jobs ordered oldest first.

        Returns:
            Pending job IDs in FIFO order so the scheduler can
            re-enqueue them on boot.
        """
        session = self._get_session()
        try:
            jobs = (
                session.query(JobModel).filter(JobModel.status == "pending").order_by(JobModel.created_at.asc()).all()
            )
            return [str(j.optimization_id) for j in jobs]
        finally:
            session.close()

    def set_payload_overview(self, optimization_id: str, overview: dict[str, Any]) -> None:
        """Store a summary overview of the job payload.

        The ``username`` field, if present in ``overview``, is hoisted
        to the job row so list queries don't need to parse JSON.
        Missing IDs are a silent no-op.

        Args:
            optimization_id: ID of the job to update.
            overview: Summary fields to persist.
        """
        session = self._get_session()
        try:
            job = session.query(JobModel).filter(JobModel.optimization_id == optimization_id).first()
            if job:
                job.payload_overview = overview or {}  # type: ignore[assignment]
                if "username" in (overview or {}):
                    job.username = (overview or {}).get("username")  # type: ignore[assignment]
                if "optimization_type" in (overview or {}):
                    job.optimization_type = (overview or {}).get("optimization_type")  # type: ignore[assignment]
                session.commit()
        finally:
            session.close()

    def record_progress(self, optimization_id: str, message: str | None, metrics: dict[str, Any]) -> None:
        """Record a progress event and merge metrics into the job's ``latest_metrics``.

        When the per-job event count hits the configured retention cap,
        evicts the oldest non-structural event first so UI phase
        markers (baseline, pair-started, etc.) survive the cap on
        long runs. Silent no-op if the job has been deleted.

        Args:
            optimization_id: ID of the job emitting the event.
            message: Human-readable event marker, or ``None``.
            metrics: Metric snapshot to merge into ``latest_metrics``.
        """
        now = datetime.now(UTC)
        session = self._get_session()
        try:
            job = (
                session.query(JobModel)
                .filter(JobModel.optimization_id == optimization_id)
                .with_for_update()
                .first()
            )
            if not job:
                return

            event_count = (
                session.query(ProgressEventModel).filter(ProgressEventModel.optimization_id == optimization_id).count()
            )
            if event_count >= self._progress_events_cap:
                # Evict the oldest non-structural event first — keep phase
                # markers (grid_pair_started, baseline_evaluated, etc.) so
                # the UI can still determine pipeline stage on long runs.
                # Only touch structural rows if nothing else is left.
                oldest = (
                    session.query(ProgressEventModel)
                    .filter(ProgressEventModel.optimization_id == optimization_id)
                    .filter(ProgressEventModel.event.notin_(STRUCTURAL_PROGRESS_EVENTS))
                    .order_by(ProgressEventModel.timestamp.asc(), ProgressEventModel.id.asc())
                    .first()
                )
                if oldest is None:
                    oldest = (
                        session.query(ProgressEventModel)
                        .filter(ProgressEventModel.optimization_id == optimization_id)
                        .order_by(ProgressEventModel.timestamp.asc(), ProgressEventModel.id.asc())
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
                job.latest_metrics = merged  # type: ignore[assignment]

            session.commit()
        finally:
            session.close()

    def get_progress_events(self, optimization_id: str) -> list[ProgressEventRecord]:
        """Retrieve all progress events for a job in chronological order.

        Args:
            optimization_id: ID of the job to inspect.

        Returns:
            Events ordered oldest-first.
        """
        session = self._get_session()
        try:
            events = (
                session.query(ProgressEventModel)
                .filter(ProgressEventModel.optimization_id == optimization_id)
                .order_by(ProgressEventModel.timestamp.asc(), ProgressEventModel.id.asc())
                .all()
            )
            return [
                cast(
                    ProgressEventRecord,
                    {
                        "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                        "event": e.event,
                        "metrics": e.metrics or {},
                    },
                )
                for e in events
            ]
        finally:
            session.close()

    def get_progress_count(self, optimization_id: str) -> int:
        """Return the number of progress events recorded for a job.

        Args:
            optimization_id: ID of the job to inspect.

        Returns:
            Number of stored events.
        """
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
        """Append a log entry for a job.

        Silently discards the entry if the job no longer exists (a
        late log from a cleaned-up run is not an error). When the
        per-job log count reaches the configured retention cap, the oldest
        entry is evicted before the new one is inserted.

        Args:
            optimization_id: ID of the job emitting the log.
            level: Log level string (``INFO``, ``ERROR``, ...).
            logger_name: Originating logger name.
            message: Log line content.
            timestamp: Optional override for the entry timestamp; defaults to ``now``.
            pair_index: Optional grid-pair index when emitted from a sweep.
        """
        ts = timestamp or datetime.now(UTC)
        session = self._get_session()
        try:
            job = (
                session.query(JobModel)
                .filter(JobModel.optimization_id == optimization_id)
                .with_for_update()
                .first()
            )
            if job is None:
                logger.warning("Discarding log entry for missing job %s", optimization_id)
                return

            log_count = session.query(LogEntryModel).filter(LogEntryModel.optimization_id == optimization_id).count()
            if log_count >= self._log_entries_cap:
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
    ) -> list[LogEntryRecord]:
        """Retrieve log entries for a job, ordered ascending.

        Args:
            optimization_id: ID of the job to inspect.
            limit: Maximum number of entries to return; ``None`` means no cap.
            offset: Number of entries to skip.
            level: When set, restricts results to the given level.

        Returns:
            Matching log entries in chronological order.
        """
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
                cast(
                    LogEntryRecord,
                    {
                        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                        "level": log.level,
                        "logger": log.logger,
                        "message": log.message,
                        "pair_index": log.pair_index,
                    },
                )
                for log in logs
            ]
        finally:
            session.close()

    def get_log_count(self, optimization_id: str, *, level: str | None = None) -> int:
        """Return the number of log entries for a job, optionally filtered by level.

        Args:
            optimization_id: ID of the job to inspect.
            level: When set, counts only entries at this level.

        Returns:
            Number of matching log entries.
        """
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
    ) -> list[JobRecord]:
        """List jobs with optional filtering and pagination, newest first.

        Progress and log counts are folded in via two aggregate
        queries so each returned row includes ``progress_count`` and
        ``log_count`` without N extra round trips.

        Args:
            status: Restrict to jobs with this status when set.
            username: Restrict to jobs owned by this user when set.
            optimization_type: Restrict to a particular run type when set.
            limit: Maximum number of rows to return.
            offset: Number of rows to skip from the start.

        Returns:
            Matching ``JobRecord`` rows in newest-first order with
            ``progress_count`` and ``log_count`` populated.
        """
        session = self._get_session()
        try:
            q = session.query(JobModel).order_by(JobModel.created_at.desc())
            if status:
                q = q.filter(JobModel.status == status)
            if username:
                q = q.filter(JobModel.username == username)
            if optimization_type:
                q = q.filter(JobModel.optimization_type == optimization_type)
            jobs = q.offset(offset).limit(limit).all()
            optimization_ids = [j.optimization_id for j in jobs]

            progress_counts: dict[str, int] = (
                {
                    row[0]: row[1]
                    for row in session.query(ProgressEventModel.optimization_id, func.count())
                    .filter(ProgressEventModel.optimization_id.in_(optimization_ids))
                    .group_by(ProgressEventModel.optimization_id)
                    .all()
                }
                if optimization_ids
                else {}
            )
            log_counts: dict[str, int] = (
                {
                    row[0]: row[1]
                    for row in session.query(LogEntryModel.optimization_id, func.count())
                    .filter(LogEntryModel.optimization_id.in_(optimization_ids))
                    .group_by(LogEntryModel.optimization_id)
                    .all()
                }
                if optimization_ids
                else {}
            )

            result: list[JobRecord] = []
            for j in jobs:
                d = self._job_to_dict(j)
                oid = str(j.optimization_id)
                d["progress_count"] = progress_counts.get(oid, 0)
                d["log_count"] = log_counts.get(oid, 0)
                result.append(d)
            return result
        finally:
            session.close()

    def count_jobs(
        self, *, status: str | None = None, username: str | None = None, optimization_type: str | None = None
    ) -> int:
        """Count jobs matching the given filters.

        Args:
            status: Restrict count to this status when set.
            username: Restrict count to this owner when set.
            optimization_type: Restrict count to this run type when set.

        Returns:
            Number of matching rows.
        """
        session = self._get_session()
        try:
            q = session.query(func.count(JobModel.optimization_id))
            if status:
                q = q.filter(JobModel.status == status)
            if username:
                q = q.filter(JobModel.username == username)
            if optimization_type:
                q = q.filter(JobModel.optimization_type == optimization_type)
            return q.scalar() or 0
        finally:
            session.close()
