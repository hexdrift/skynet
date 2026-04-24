"""SQLAlchemy ORM models for job storage.

Defines the shared database models used by the PostgreSQL storage backend.
"""

from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, PrimaryKeyConstraint, String, Text
from sqlalchemy.orm import DeclarativeBase

EMBEDDING_DIM = 512


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""

    pass


class JobModel(Base):
    """SQLAlchemy model for the jobs table."""

    __tablename__ = "jobs"

    optimization_id = Column(String(36), primary_key=True)
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
    username = Column(String(255), nullable=True)


class ProgressEventModel(Base):
    """SQLAlchemy model for the job_progress_events table."""

    __tablename__ = "job_progress_events"

    optimization_id = Column(String(36), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    event = Column(String(255), nullable=True)
    metrics = Column(JSON, default=dict)

    __table_args__ = (PrimaryKeyConstraint("optimization_id", "timestamp"),)


class LogEntryModel(Base):
    """SQLAlchemy model for the job_logs table."""

    __tablename__ = "job_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    optimization_id = Column(String(36), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    level = Column(String(20), nullable=False)
    logger = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    pair_index = Column(Integer, nullable=True)


class TemplateModel(Base):
    """SQLAlchemy model for the job_templates table."""

    __tablename__ = "job_templates"

    template_id = Column(String(36), primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    username = Column(String(255), nullable=False)
    config = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


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

    optimization_id = Column(String(36), primary_key=True)
    user_id = Column(String(255), nullable=True, index=True)
    optimization_type = Column(String(32), nullable=True, index=True)
    winning_model = Column(String(255), nullable=True)
    winning_rank = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    embedding_summary = Column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_code = Column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_schema = Column(Vector(EMBEDDING_DIM), nullable=True)
    is_recommendable = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    baseline_metric = Column(Float, nullable=True)
    optimized_metric = Column(Float, nullable=True)
    summary_text = Column(Text, nullable=True)
    signature_code = Column(Text, nullable=True)
    metric_name = Column(String(255), nullable=True)
    optimizer_name = Column(String(64), nullable=True)
    optimizer_kwargs = Column(JSON, nullable=True)
    module_name = Column(String(128), nullable=True)
    task_name = Column(String(255), nullable=True)
    projection_x = Column(Float, nullable=True)
    projection_y = Column(Float, nullable=True)
