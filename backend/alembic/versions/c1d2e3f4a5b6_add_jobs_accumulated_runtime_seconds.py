"""add jobs.accumulated_runtime_seconds for cross-resume runtime accounting

Revision ID: c1d2e3f4a5b6
Revises: b9c0d1e2f3a4
Create Date: 2026-06-21 12:00:00.000000

Adds ``jobs.accumulated_runtime_seconds``, the running sum of every *completed*
optimization leg's wall-clock duration. ``requeue_for_resume`` folds the just
finished leg into it before clearing ``started_at``/``completed_at``, so the
elapsed timer reports net active compute across resumes — the paused gap between
a failed leg and its resume is never counted. Existing rows start at 0 (a prior
leg's timing is unrecoverable once ``started_at`` was overwritten), so there is
nothing to backfill; the write path maintains it going forward. SQLite test
schemas come from ``create_all`` with the column's ``server_default`` of 0.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b9c0d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the ``jobs.accumulated_runtime_seconds`` column."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS "
        "accumulated_runtime_seconds DOUBLE PRECISION NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    """Drop the ``jobs.accumulated_runtime_seconds`` column."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS accumulated_runtime_seconds")
