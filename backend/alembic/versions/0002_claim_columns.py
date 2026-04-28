"""Multi-pod claim queue (Wave 2).

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01 00:00:01.000000

Adds the columns and index ``RemoteDBJobStore.claim_next_job`` relies
on for ``SELECT ... FOR UPDATE SKIP LOCKED``-style work distribution
across multiple backend pods. After this revision the orphan-recovery
loop also has the ``lease_expires_at`` index it needs for cheap
"any expired leases?" scans.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add claim/lease columns to ``jobs`` and the lease-expiry index."""
    op.add_column("jobs", sa.Column("claimed_by", sa.String(64), nullable=True))
    op.add_column("jobs", sa.Column("claimed_at", sa.DateTime(), nullable=True))
    op.add_column("jobs", sa.Column("lease_expires_at", sa.DateTime(), nullable=True))
    op.create_index("ix_jobs_lease_expires_at", "jobs", ["lease_expires_at"])


def downgrade() -> None:
    """Drop the index and the three claim columns."""
    op.drop_index("ix_jobs_lease_expires_at", table_name="jobs")
    op.drop_column("jobs", "lease_expires_at")
    op.drop_column("jobs", "claimed_at")
    op.drop_column("jobs", "claimed_by")
