"""convert datetime columns to TIMESTAMPTZ

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-26 10:00:00.000000

Background: the prior schema declared timestamp columns as ``DateTime``
(no ``timezone=True``), which PostgreSQL stores as ``TIMESTAMP WITHOUT
TIME ZONE``. When a TZ-aware datetime is inserted into such a column,
PostgreSQL rotates the value to the session timezone before stripping
the offset. On any deployment whose PostgreSQL session timezone is not
UTC, the naive readback then differs from the originally written UTC
value, and downstream consumers that treat the naive value as UTC see
clock skew (manifested as ``elapsed_seconds=0`` until wall time catches
up).

This migration converts every job/log/template/quota/embedding timestamp
column to ``TIMESTAMP WITH TIME ZONE``. The ``USING ... AT TIME ZONE``
clause interprets each existing naive value as belonging to the session
timezone of whichever PostgreSQL instance originally wrote the row, so
the converted TIMESTAMPTZ represents the same wall-clock instant as the
original UTC ``datetime.now(UTC)`` call.

The ``LEGACY_NAIVE_TZ`` environment variable lets operators override the
assumed source timezone for the conversion (e.g. ``LEGACY_NAIVE_TZ=UTC``
when the database has always run with a UTC session). When unset, the
migration falls back to ``current_setting('timezone')``, which is the
running session's TZ — correct for the common case where the operator
runs the migration on a host with the same default TZ as the database
that wrote the legacy rows.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_COLUMNS: tuple[tuple[str, str], ...] = (
    ("jobs", "created_at"),
    ("jobs", "started_at"),
    ("jobs", "completed_at"),
    ("jobs", "claimed_at"),
    ("jobs", "lease_expires_at"),
    ("job_progress_events", "timestamp"),
    ("job_logs", "timestamp"),
    ("job_templates", "created_at"),
    ("user_quota_overrides", "updated_at"),
    ("user_quota_audit_events", "created_at"),
    ("job_embeddings", "created_at"),
)


def _legacy_tz_sql() -> str:
    """Render the SQL expression that names the source timezone.

    Returns:
        A quoted SQL literal (e.g. ``'Asia/Jerusalem'``) when
        ``LEGACY_NAIVE_TZ`` is set, otherwise the function call
        ``current_setting('timezone')``.
    """
    override = os.environ.get("LEGACY_NAIVE_TZ")
    if override:
        escaped = override.replace("'", "''")
        return f"'{escaped}'"
    return "current_setting('timezone')"


def upgrade() -> None:
    """Convert all datetime columns to TIMESTAMP WITH TIME ZONE."""
    legacy_tz = _legacy_tz_sql()
    for table, column in _COLUMNS:
        op.execute(
            f'ALTER TABLE {table} '
            f'ALTER COLUMN {column} '
            f'TYPE TIMESTAMP WITH TIME ZONE '
            f'USING {column} AT TIME ZONE {legacy_tz}'
        )


def downgrade() -> None:
    """Revert columns back to TIMESTAMP WITHOUT TIME ZONE in UTC."""
    for table, column in _COLUMNS:
        op.execute(
            f'ALTER TABLE {table} '
            f'ALTER COLUMN {column} '
            f'TYPE TIMESTAMP WITHOUT TIME ZONE '
            f"USING {column} AT TIME ZONE 'UTC'"
        )
