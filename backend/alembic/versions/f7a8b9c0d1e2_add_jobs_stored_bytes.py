"""add jobs.stored_bytes for unified storage accounting

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-08 12:00:00.000000

Adds the precomputed ``jobs.stored_bytes`` column that backs the unified
per-user storage budget. It holds the serialized byte size of the job's JSON
columns (``payload`` + ``result`` + ``payload_overview``) so the per-user total
is a single indexed SUM instead of a scan that re-serializes every payload. The
write path maintains it going forward; this migration backfills existing rows
once. The backfill uses Postgres' ``octet_length(<col>::text)`` and is skipped
on other dialects (SQLite test schemas come from ``create_all`` with the
column's ``server_default`` of 0).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``jobs.stored_bytes`` and backfill it from existing JSON columns."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS stored_bytes BIGINT NOT NULL DEFAULT 0")
    op.execute(
        """
        UPDATE jobs
        SET stored_bytes =
            COALESCE(octet_length(payload::text), 0)
            + COALESCE(octet_length(result::text), 0)
            + COALESCE(octet_length(payload_overview::text), 0)
        """
    )


def downgrade() -> None:
    """Drop the ``jobs.stored_bytes`` column."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS stored_bytes")
