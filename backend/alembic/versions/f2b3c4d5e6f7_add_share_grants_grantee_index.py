"""add index on optimization_share_grants(grantee_username)

Revision ID: f2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-04 09:05:00.000000

The composite primary key ``(optimization_id, grantee_username)`` leads with
``optimization_id``, so the "list everything shared with this user" queries
(``list_jobs_shared_with`` / ``list_jobs_visible_to`` / ``count_jobs_*``), which
filter on ``grantee_username`` alone, could not use it and fell back to a scan.
Small table, but built ``CONCURRENTLY`` for consistency and to avoid any write
stall on the sharing path during deploy.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the grantee lookup index concurrently."""
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_optimization_share_grants_grantee",
            "optimization_share_grants",
            ["grantee_username"],
            unique=False,
            if_not_exists=True,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    """Drop the grantee lookup index concurrently."""
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_optimization_share_grants_grantee",
            table_name="optimization_share_grants",
            if_exists=True,
            postgresql_concurrently=True,
        )
