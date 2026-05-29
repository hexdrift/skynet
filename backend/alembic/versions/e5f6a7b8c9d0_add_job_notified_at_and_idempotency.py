"""add job notified_at and idempotency_key

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-27 13:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add notification dedup column + client idempotency key with a partial unique index.

    The unique guard is partial on ``idempotency_key IS NOT NULL`` so jobs
    submitted without a key (the common path) are unaffected; only retried
    submissions sharing ``(username, idempotency_key)`` collide.
    """
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS notified_at TIMESTAMP WITH TIME ZONE")
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128)")
    op.create_index(
        op.f("ix_jobs_username_idempotency_key"),
        "jobs",
        ["username", "idempotency_key"],
        unique=False,
        if_not_exists=True,
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_username_idempotency_key "
        "ON jobs (username, idempotency_key) WHERE idempotency_key IS NOT NULL"
    )


def downgrade() -> None:
    """Drop the idempotency + notification columns and their indexes."""
    op.execute("DROP INDEX IF EXISTS uq_jobs_username_idempotency_key")
    op.drop_index(op.f("ix_jobs_username_idempotency_key"), table_name="jobs", if_exists=True)
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS idempotency_key")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS notified_at")
