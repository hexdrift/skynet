"""drop projection_x and projection_y from job_embeddings

Revision ID: a4b5c6d7e8f9
Revises: d0e1f2a3b4c5
Create Date: 2026-06-01 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the projection coordinate columns, retiring the explore scatter-map feature."""
    op.execute("ALTER TABLE job_embeddings DROP COLUMN IF EXISTS projection_x")
    op.execute("ALTER TABLE job_embeddings DROP COLUMN IF EXISTS projection_y")


def downgrade() -> None:
    """Re-add the baseline projection columns so a full downgrade chain stays consistent."""
    op.add_column("job_embeddings", sa.Column("projection_x", sa.Float(), nullable=True))
    op.add_column("job_embeddings", sa.Column("projection_y", sa.Float(), nullable=True))
