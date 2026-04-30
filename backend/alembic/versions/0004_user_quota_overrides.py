"""Current baseline schema including live per-user quota overrides.

Revision ID: 0004
Revises:
Create Date: 2026-04-30 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 512


def upgrade() -> None:
    """Create the current application schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "jobs",
        sa.Column("optimization_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("estimated_remaining_seconds", sa.Float(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("latest_metrics", postgresql.JSONB(), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("payload_overview", postgresql.JSONB(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("optimization_type", sa.String(length=64), nullable=True),
        sa.Column("claimed_by", sa.String(length=64), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("optimization_id"),
        if_not_exists=True,
    )
    op.create_index("ix_jobs_status", "jobs", ["status"], if_not_exists=True)
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"], if_not_exists=True)
    op.create_index("ix_jobs_username", "jobs", ["username"], if_not_exists=True)
    op.create_index("ix_jobs_optimization_type", "jobs", ["optimization_type"], if_not_exists=True)
    op.create_index("ix_jobs_status_created_at", "jobs", ["status", "created_at"], if_not_exists=True)
    op.create_index("ix_jobs_lease_expires_at", "jobs", ["lease_expires_at"], if_not_exists=True)

    op.create_table(
        "job_progress_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("optimization_id", sa.String(length=36), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("event", sa.String(length=255), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_job_progress_events_optimization_id",
        "job_progress_events",
        ["optimization_id"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_job_progress_events_optimization_timestamp",
        "job_progress_events",
        ["optimization_id", "timestamp"],
        if_not_exists=True,
    )

    op.create_table(
        "job_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("optimization_id", sa.String(length=36), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("logger", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("pair_index", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index("ix_job_logs_optimization_id", "job_logs", ["optimization_id"], if_not_exists=True)

    op.create_table(
        "job_templates",
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("template_id"),
        if_not_exists=True,
    )

    op.create_table(
        "user_quota_overrides",
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("quota", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("username"),
        if_not_exists=True,
    )

    op.create_table(
        "job_embeddings",
        sa.Column("optimization_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("optimization_type", sa.String(length=32), nullable=True),
        sa.Column("winning_model", sa.String(length=255), nullable=True),
        sa.Column("winning_rank", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("embedding_summary", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("embedding_code", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("embedding_schema", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("is_recommendable", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("baseline_metric", sa.Float(), nullable=True),
        sa.Column("optimized_metric", sa.Float(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("signature_code", sa.Text(), nullable=True),
        sa.Column("metric_name", sa.String(length=255), nullable=True),
        sa.Column("optimizer_name", sa.String(length=64), nullable=True),
        sa.Column("optimizer_kwargs", postgresql.JSONB(), nullable=True),
        sa.Column("module_name", sa.String(length=128), nullable=True),
        sa.Column("task_name", sa.String(length=255), nullable=True),
        sa.Column("projection_x", sa.Float(), nullable=True),
        sa.Column("projection_y", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("optimization_id"),
        if_not_exists=True,
    )
    op.create_index("ix_job_embeddings_user_id", "job_embeddings", ["user_id"], if_not_exists=True)
    op.create_index(
        "ix_job_embeddings_optimization_type",
        "job_embeddings",
        ["optimization_type"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_job_embeddings_is_recommendable",
        "job_embeddings",
        ["is_recommendable"],
        if_not_exists=True,
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_job_embeddings_summary_hnsw "
        "ON job_embeddings USING hnsw (embedding_summary vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_job_embeddings_code_hnsw "
        "ON job_embeddings USING hnsw (embedding_code vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_job_embeddings_schema_hnsw "
        "ON job_embeddings USING hnsw (embedding_schema vector_cosine_ops)"
    )


def downgrade() -> None:
    """Drop the current application schema."""
    op.execute("DROP INDEX IF EXISTS idx_job_embeddings_schema_hnsw")
    op.execute("DROP INDEX IF EXISTS idx_job_embeddings_code_hnsw")
    op.execute("DROP INDEX IF EXISTS idx_job_embeddings_summary_hnsw")
    op.drop_index("ix_job_embeddings_is_recommendable", table_name="job_embeddings", if_exists=True)
    op.drop_index("ix_job_embeddings_optimization_type", table_name="job_embeddings", if_exists=True)
    op.drop_index("ix_job_embeddings_user_id", table_name="job_embeddings", if_exists=True)
    op.drop_table("job_embeddings", if_exists=True)
    op.drop_table("user_quota_overrides", if_exists=True)
    op.drop_table("job_templates", if_exists=True)
    op.drop_index("ix_job_logs_optimization_id", table_name="job_logs", if_exists=True)
    op.drop_table("job_logs", if_exists=True)
    op.drop_index("ix_job_progress_events_optimization_timestamp", table_name="job_progress_events", if_exists=True)
    op.drop_index("ix_job_progress_events_optimization_id", table_name="job_progress_events", if_exists=True)
    op.drop_table("job_progress_events", if_exists=True)
    op.drop_index("ix_jobs_lease_expires_at", table_name="jobs", if_exists=True)
    op.drop_index("ix_jobs_status_created_at", table_name="jobs", if_exists=True)
    op.drop_index("ix_jobs_optimization_type", table_name="jobs", if_exists=True)
    op.drop_index("ix_jobs_username", table_name="jobs", if_exists=True)
    op.drop_index("ix_jobs_created_at", table_name="jobs", if_exists=True)
    op.drop_index("ix_jobs_status", table_name="jobs", if_exists=True)
    op.drop_table("jobs", if_exists=True)
