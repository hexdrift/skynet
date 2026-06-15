"""add user_storage_quota_overrides for per-user storage budgets

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-06-11 21:00:00.000000

Adds the ``user_storage_quota_overrides`` table backing the admin per-user
storage-budget override. A row holds a ``quota_bytes`` ceiling that replaces the
global ``settings.user_storage_quota_bytes`` default for that user. Postgres-only
DDL; SQLite test schemas come from ``create_all`` over the SQLAlchemy models.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``user_storage_quota_overrides`` table on Postgres."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_storage_quota_overrides (
            username VARCHAR(255) PRIMARY KEY,
            quota_bytes BIGINT NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_by VARCHAR(255)
        )
        """
    )


def downgrade() -> None:
    """Drop the ``user_storage_quota_overrides`` table."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TABLE IF EXISTS user_storage_quota_overrides")
