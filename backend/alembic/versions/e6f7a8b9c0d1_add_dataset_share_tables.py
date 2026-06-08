"""add dataset_share_links and dataset_share_grants tables

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-06-08 11:00:00.000000

Mirrors the optimization sharing ACL for the dataset library. Creates
``dataset_share_links`` (the active ``revoked_at IS NULL`` row per dataset is
the sharing config — ``general_access`` ``'restricted'`` / ``'anyone'`` with a
signed-in ``general_role``) and ``dataset_share_grants`` for per-user member
grants (``viewer`` / ``editor`` / ``owner``). Unlike the optimization tables,
both ``dataset_id`` foreign keys cascade so deleting a dataset clears its
sharing rows. ``grantee_username`` is indexed for the shared-with-me listing.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the dataset_share_links and dataset_share_grants tables."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dataset_share_links (
            token VARCHAR(48) PRIMARY KEY,
            dataset_id VARCHAR(36) NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
            created_by VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            revoked_at TIMESTAMP WITH TIME ZONE,
            general_access VARCHAR(16) NOT NULL DEFAULT 'restricted',
            general_role VARCHAR(16) NOT NULL DEFAULT 'viewer'
        )
        """
    )
    op.create_index(
        "ix_dataset_share_links_dataset_id",
        "dataset_share_links",
        ["dataset_id"],
        if_not_exists=True,
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dataset_share_grants (
            dataset_id VARCHAR(36) NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
            grantee_username VARCHAR(255) NOT NULL,
            role VARCHAR(16) NOT NULL,
            created_by VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            PRIMARY KEY (dataset_id, grantee_username)
        )
        """
    )
    op.create_index(
        "ix_dataset_share_grants_grantee",
        "dataset_share_grants",
        ["grantee_username"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop the dataset share-grants and share-links tables and their indexes."""
    op.drop_index(
        "ix_dataset_share_grants_grantee",
        table_name="dataset_share_grants",
        if_exists=True,
    )
    op.execute("DROP TABLE IF EXISTS dataset_share_grants")
    op.drop_index(
        "ix_dataset_share_links_dataset_id",
        table_name="dataset_share_links",
        if_exists=True,
    )
    op.execute("DROP TABLE IF EXISTS dataset_share_links")
