"""Create the fresh PostgreSQL schema for an on-premises deployment."""

from __future__ import annotations

from alembic import op
from core.storage.models import Base

revision = "0001_onprem"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the complete extension-free on-premises baseline."""
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """Drop the on-premises baseline schema."""
    Base.metadata.drop_all(bind=op.get_bind())
