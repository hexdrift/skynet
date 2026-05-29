"""add job attempts and code version

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-27 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add retry accounting and code-version compatibility columns."""
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0 NOT NULL")
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS code_version VARCHAR(40)")
    op.create_index(
        op.f("ix_jobs_code_version"),
        "jobs",
        ["code_version"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Remove retry accounting and code-version compatibility columns."""
    op.drop_index(op.f("ix_jobs_code_version"), table_name="jobs", if_exists=True)
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS code_version")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS attempts")
