"""Harden storage indexes and progress-event identity.

Revision ID: 0003
Revises: 0002
Create Date: 2025-01-01 00:00:02.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add hot-path indexes and give progress events a surrogate key."""
    op.create_index("ix_jobs_status", "jobs", ["status"], if_not_exists=True)
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"], if_not_exists=True)
    op.create_index("ix_jobs_username", "jobs", ["username"], if_not_exists=True)
    op.add_column("jobs", sa.Column("optimization_type", sa.String(64), nullable=True))
    op.execute("UPDATE jobs SET optimization_type = payload_overview ->> 'optimization_type' WHERE payload_overview IS NOT NULL")
    op.create_index("ix_jobs_optimization_type", "jobs", ["optimization_type"], if_not_exists=True)

    for table_name, column_name in (
        ("jobs", "latest_metrics"),
        ("jobs", "result"),
        ("jobs", "payload_overview"),
        ("jobs", "payload"),
        ("job_progress_events", "metrics"),
        ("job_templates", "config"),
        ("job_embeddings", "optimizer_kwargs"),
    ):
        op.alter_column(
            table_name,
            column_name,
            type_=postgresql.JSONB(),
            postgresql_using=f"{column_name}::jsonb",
        )

    op.execute("ALTER TABLE job_progress_events ADD COLUMN IF NOT EXISTS id INTEGER")
    op.execute("CREATE SEQUENCE IF NOT EXISTS job_progress_events_id_seq")
    op.execute(
        "ALTER TABLE job_progress_events "
        "ALTER COLUMN id SET DEFAULT nextval('job_progress_events_id_seq')"
    )
    op.execute("UPDATE job_progress_events SET id = nextval('job_progress_events_id_seq') WHERE id IS NULL")
    op.alter_column("job_progress_events", "id", nullable=False)
    op.drop_constraint("job_progress_events_pkey", "job_progress_events", type_="primary")
    op.create_primary_key("job_progress_events_pkey", "job_progress_events", ["id"])
    op.create_index(
        "ix_job_progress_events_optimization_timestamp",
        "job_progress_events",
        ["optimization_id", "timestamp"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Restore the previous composite progress-event primary key."""
    op.drop_index("ix_job_progress_events_optimization_timestamp", table_name="job_progress_events", if_exists=True)
    op.drop_constraint("job_progress_events_pkey", "job_progress_events", type_="primary")
    op.create_primary_key("job_progress_events_pkey", "job_progress_events", ["optimization_id", "timestamp"])
    op.drop_column("job_progress_events", "id")
    op.execute("DROP SEQUENCE IF EXISTS job_progress_events_id_seq")
    for table_name, column_name in (
        ("job_embeddings", "optimizer_kwargs"),
        ("job_templates", "config"),
        ("job_progress_events", "metrics"),
        ("jobs", "payload"),
        ("jobs", "payload_overview"),
        ("jobs", "result"),
        ("jobs", "latest_metrics"),
    ):
        op.alter_column(
            table_name,
            column_name,
            type_=sa.JSON(),
            postgresql_using=f"{column_name}::json",
        )
    op.drop_index("ix_jobs_optimization_type", table_name="jobs", if_exists=True)
    op.drop_column("jobs", "optimization_type")
    op.drop_index("ix_jobs_username", table_name="jobs", if_exists=True)
    op.drop_index("ix_jobs_created_at", table_name="jobs", if_exists=True)
    op.drop_index("ix_jobs_status", table_name="jobs", if_exists=True)
