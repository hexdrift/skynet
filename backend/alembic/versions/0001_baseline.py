"""Baseline schema (Wave 1).

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000

Captures the schema as it existed before the multi-pod claim queue
landed. The follow-up revision ``0002_claim_columns`` adds the columns
the DB-backed work queue depends on (``claimed_by``, ``claimed_at``,
``lease_expires_at``) plus the lease-expiry index.

Splitting the schema this way means an operator who already deployed
the Wave-1 schema out-of-band can stamp this revision and apply just
the delta on upgrade — the typical Alembic pattern for adopting
migration tooling on a live database.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 512


def upgrade() -> None:
    """Create every Wave-1 table + the pgvector extension and HNSW indexes."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "jobs",
        sa.Column("optimization_id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("estimated_remaining_seconds", sa.Float(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("latest_metrics", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("payload_overview", sa.JSON(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("username", sa.String(255), nullable=True),
    )
    op.create_index("ix_jobs_status_created_at", "jobs", ["status", "created_at"])

    op.create_table(
        "job_progress_events",
        sa.Column("optimization_id", sa.String(36), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("event", sa.String(255), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("optimization_id", "timestamp"),
    )
    op.create_index(
        "ix_job_progress_events_optimization_id",
        "job_progress_events",
        ["optimization_id"],
    )

    op.create_table(
        "job_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("optimization_id", sa.String(36), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("logger", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("pair_index", sa.Integer(), nullable=True),
    )
    op.create_index("ix_job_logs_optimization_id", "job_logs", ["optimization_id"])

    op.create_table(
        "job_templates",
        sa.Column("template_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "job_embeddings",
        sa.Column("optimization_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("optimization_type", sa.String(32), nullable=True),
        sa.Column("winning_model", sa.String(255), nullable=True),
        sa.Column("winning_rank", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("embedding_summary", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("embedding_code", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("embedding_schema", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column(
            "is_recommendable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("baseline_metric", sa.Float(), nullable=True),
        sa.Column("optimized_metric", sa.Float(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("signature_code", sa.Text(), nullable=True),
        sa.Column("metric_name", sa.String(255), nullable=True),
        sa.Column("optimizer_name", sa.String(64), nullable=True),
        sa.Column("optimizer_kwargs", sa.JSON(), nullable=True),
        sa.Column("module_name", sa.String(128), nullable=True),
        sa.Column("task_name", sa.String(255), nullable=True),
        sa.Column("projection_x", sa.Float(), nullable=True),
        sa.Column("projection_y", sa.Float(), nullable=True),
    )
    op.create_index("ix_job_embeddings_user_id", "job_embeddings", ["user_id"])
    op.create_index(
        "ix_job_embeddings_optimization_type", "job_embeddings", ["optimization_type"]
    )
    op.execute(
        "CREATE INDEX ix_job_embeddings_recommendable "
        "ON job_embeddings (is_recommendable) WHERE is_recommendable = TRUE"
    )

    op.execute(
        "CREATE INDEX idx_job_embeddings_summary_hnsw "
        "ON job_embeddings USING hnsw (embedding_summary vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX idx_job_embeddings_code_hnsw "
        "ON job_embeddings USING hnsw (embedding_code vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX idx_job_embeddings_schema_hnsw "
        "ON job_embeddings USING hnsw (embedding_schema vector_cosine_ops)"
    )


def downgrade() -> None:
    """Drop everything created by ``upgrade``.

    The pgvector extension is left in place — dropping it would break
    any other database/role that depends on it. Removing the extension
    is an operator decision, not a migration concern.
    """
    op.execute("DROP INDEX IF EXISTS idx_job_embeddings_schema_hnsw")
    op.execute("DROP INDEX IF EXISTS idx_job_embeddings_code_hnsw")
    op.execute("DROP INDEX IF EXISTS idx_job_embeddings_summary_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_job_embeddings_recommendable")
    op.drop_index("ix_job_embeddings_optimization_type", table_name="job_embeddings")
    op.drop_index("ix_job_embeddings_user_id", table_name="job_embeddings")
    op.drop_table("job_embeddings")
    op.drop_table("job_templates")
    op.drop_index("ix_job_logs_optimization_id", table_name="job_logs")
    op.drop_table("job_logs")
    op.drop_index(
        "ix_job_progress_events_optimization_id", table_name="job_progress_events"
    )
    op.drop_table("job_progress_events")
    op.drop_index("ix_jobs_status_created_at", table_name="jobs")
    op.drop_table("jobs")
