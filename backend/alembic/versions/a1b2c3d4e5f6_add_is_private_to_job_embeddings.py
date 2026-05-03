"""add is_private to job_embeddings

Revision ID: a1b2c3d4e5f6
Revises: 0005
Create Date: 2026-05-03 12:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE job_embeddings ADD COLUMN IF NOT EXISTS is_private BOOLEAN DEFAULT false NOT NULL")
    op.create_index(
        op.f('ix_job_embeddings_is_private'),
        'job_embeddings',
        ['is_private'],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_job_embeddings_is_private'), table_name='job_embeddings', if_exists=True)
    op.execute("ALTER TABLE job_embeddings DROP COLUMN IF EXISTS is_private")
