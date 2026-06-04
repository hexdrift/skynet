"""add composite index on job_logs(optimization_id, timestamp)

Revision ID: f1a2b3c4d5e6
Revises: c6d7e8f9a0b1
Create Date: 2026-06-04 09:00:00.000000

The per-job log reads (``get_logs`` ordered by timestamp) and the oldest-first
cap eviction in ``append_log`` previously relied on the single-column
``optimization_id`` index and sorted timestamps in memory. This composite index
serves both the filter and the ordering. Built ``CONCURRENTLY`` because
``job_logs`` is write-hot — a plain ``CREATE INDEX`` takes a SHARE lock that
would stall log appends for the duration of the build during a deploy.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "c6d7e8f9a0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the composite index concurrently, outside the migration txn."""
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_job_logs_optimization_timestamp",
            "job_logs",
            ["optimization_id", "timestamp"],
            unique=False,
            if_not_exists=True,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    """Drop the composite index concurrently."""
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_job_logs_optimization_timestamp",
            table_name="job_logs",
            if_exists=True,
            postgresql_concurrently=True,
        )
