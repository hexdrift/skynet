"""add general_access to share links and the share-grants table

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-05-29 21:00:00.000000

Extends optimization sharing into a Google-Drive-style ACL. Adds
``general_access`` to ``optimization_share_links`` (the active row per
optimization is the sharing config; ``'restricted'`` by default, ``'anyone'``
for an anonymous view-only link) and creates ``optimization_share_grants`` for
per-user member grants (``viewer`` / ``editor`` / ``owner``). The
``(optimization_id, grantee_username)`` primary key lets re-invites replace a
grant; ``optimization_id`` is indexed for the owner-side member list.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add general_access and create the optimization_share_grants table."""
    op.execute(
        "ALTER TABLE optimization_share_links "
        "ADD COLUMN IF NOT EXISTS general_access VARCHAR(16) NOT NULL DEFAULT 'restricted'"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS optimization_share_grants (
            optimization_id VARCHAR(36) NOT NULL,
            grantee_username VARCHAR(255) NOT NULL,
            role VARCHAR(16) NOT NULL,
            created_by VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            PRIMARY KEY (optimization_id, grantee_username)
        )
        """
    )
    op.create_index(
        "ix_optimization_share_grants_optimization_id",
        "optimization_share_grants",
        ["optimization_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop the share-grants table and the general_access column."""
    op.drop_index(
        "ix_optimization_share_grants_optimization_id",
        table_name="optimization_share_grants",
        if_exists=True,
    )
    op.execute("DROP TABLE IF EXISTS optimization_share_grants")
    op.execute("ALTER TABLE optimization_share_links DROP COLUMN IF EXISTS general_access")
