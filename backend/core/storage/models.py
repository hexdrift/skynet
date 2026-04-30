"""SQLAlchemy ORM models for job storage.

Defines the shared database models used by the PostgreSQL storage backend.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIM = 512
JSON_STORE = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""


class JobModel(Base):
    """SQLAlchemy model for the jobs table.

    The ``claimed_by`` / ``claimed_at`` / ``lease_expires_at`` triplet implements
    a DB-backed work queue safe for multi-pod horizontal scaling: each worker
    atomically claims a row via ``SELECT ... FOR UPDATE SKIP LOCKED`` and
    extends the lease while it holds the job. A pod that crashes leaves an
    expired lease which any other pod is free to re-claim on its next poll.
    """

    __tablename__ = "jobs"

    optimization_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    estimated_remaining_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_metrics: Mapped[dict[str, Any]] = mapped_column(JSON_STORE, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON_STORE, nullable=True)
    payload_overview: Mapped[dict[str, Any]] = mapped_column(JSON_STORE, default=dict)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_STORE, nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    optimization_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    claimed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_jobs_status_created_at", "status", "created_at"),
        Index("ix_jobs_lease_expires_at", "lease_expires_at"),
    )


class ProgressEventModel(Base):
    """SQLAlchemy model for the job_progress_events table."""

    __tablename__ = "job_progress_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    optimization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    event: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON_STORE, default=dict)

    __table_args__ = (Index("ix_job_progress_events_optimization_timestamp", "optimization_id", "timestamp"),)


class LogEntryModel(Base):
    """SQLAlchemy model for the job_logs table."""

    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    optimization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    logger: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    pair_index: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TemplateModel(Base):
    """SQLAlchemy model for the job_templates table."""

    __tablename__ = "job_templates"

    template_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON_STORE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class UserQuotaOverrideModel(Base):
    """SQLAlchemy model for live per-user quota overrides."""

    __tablename__ = "user_quota_overrides"

    username: Mapped[str] = mapped_column(String(255), primary_key=True)
    quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class UserQuotaAuditModel(Base):
    """SQLAlchemy model for quota administration audit events."""

    __tablename__ = "user_quota_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_username: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    old_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class JobEmbeddingModel(Base):
    """Per-job embedding row backing the recommendation service.

    One row is written after a job finishes successfully. Three named
    aspects are embedded independently so a similarity search can
    weigh them separately (``summary`` = LLM-authored task description,
    ``code`` = signature + metric source, ``schema`` = dataset schema
    digest). All use the same ``jina-code-embeddings-0.5b`` model,
    MRL-truncated to ``EMBEDDING_DIM``.

    Metadata (``optimization_type``, ``winning_model``, ``winning_rank``)
    is denormalized from ``jobs`` so the search can filter and rerank
    without an extra join per-candidate.
    """

    __tablename__ = "job_embeddings"

    optimization_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    optimization_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    winning_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    winning_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    embedding_summary: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_code: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_schema: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    is_recommendable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    baseline_metric: Mapped[float | None] = mapped_column(Float, nullable=True)
    optimized_metric: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    optimizer_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    optimizer_kwargs: Mapped[dict[str, Any] | None] = mapped_column(JSON_STORE, nullable=True)
    module_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    task_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    projection_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    projection_y: Mapped[float | None] = mapped_column(Float, nullable=True)
