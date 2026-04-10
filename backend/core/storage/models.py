"""SQLAlchemy ORM models for job storage.

Defines the shared database models used by the PostgreSQL storage backend.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, Integer, PrimaryKeyConstraint, String, Text
from sqlalchemy.orm import DeclarativeBase


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
