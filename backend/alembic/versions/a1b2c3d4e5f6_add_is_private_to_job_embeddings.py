"""add is_private to job_embeddings

Revision ID: a1b2c3d4e5f6
Revises: 342f7449be26
Create Date: 2026-05-03 12:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '342f7449be26'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'job_embeddings',
        sa.Column('is_private', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.create_index(op.f('ix_job_embeddings_is_private'), 'job_embeddings', ['is_private'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_job_embeddings_is_private'), table_name='job_embeddings')
    op.drop_column('job_embeddings', 'is_private')
