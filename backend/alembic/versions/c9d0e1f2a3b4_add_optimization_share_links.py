"""add optimization_share_links table

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-05-29 20:00:00.000000

Adds the ``optimization_share_links`` table backing public, read-only share
links for optimizations (the Share button / ``/share/<token>`` page). The
``token`` is the unguessable capability id embedded in the public URL and is
stored in plaintext because it is the public identifier, not a credential
hash. ``optimization_id`` is indexed for the owner-side lookup; ``revoked_at``
gates public access (NULL = live, set = 404). Rows are deleted with their
optimization.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the optimization_share_links table and its lookup index."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS optimization_share_links (
            token VARCHAR(48) PRIMARY KEY,
            optimization_id VARCHAR(36) NOT NULL,
            created_by VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            revoked_at TIMESTAMP WITH TIME ZONE
        )
        """
    )
    op.create_index(
        "ix_optimization_share_links_optimization_id",
        "optimization_share_links",
        ["optimization_id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop the lookup index and the optimization_share_links table."""
    op.drop_index(
        "ix_optimization_share_links_optimization_id",
        table_name="optimization_share_links",
        if_exists=True,
    )
    op.execute("DROP TABLE IF EXISTS optimization_share_links")
