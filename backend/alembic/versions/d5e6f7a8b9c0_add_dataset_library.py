"""add datasets and dataset_blobs tables

Revision ID: d5e6f7a8b9c0
Revises: b4c5d6e7f8a9
Create Date: 2026-06-08 09:00:00.000000

Adds the personal dataset-library storage. ``datasets`` is the lean metadata
table (one row per saved file); the row bytes live one-to-one in
``dataset_blobs`` so the metadata table stays narrow and the bytes can later
move behind an object-store seam. ``stored_bytes`` (compressed) is summed for
the per-user quota; ``byte_size`` (uncompressed) is the size shown to the user.
``(owner_username, content_hash)`` is indexed so a re-save of identical bytes
can dedupe. The blob row is deleted with its parent via the cascading FK.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the datasets and dataset_blobs tables and their indexes."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS datasets (
            id VARCHAR(36) PRIMARY KEY,
            owner_username VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            source VARCHAR(32) NOT NULL DEFAULT 'upload',
            row_count INTEGER NOT NULL,
            column_count INTEGER NOT NULL,
            byte_size BIGINT NOT NULL,
            stored_bytes BIGINT NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            column_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.create_index(
        "ix_datasets_owner_username",
        "datasets",
        ["owner_username"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_datasets_owner_content_hash",
        "datasets",
        ["owner_username", "content_hash"],
        if_not_exists=True,
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dataset_blobs (
            dataset_id VARCHAR(36) PRIMARY KEY REFERENCES datasets(id) ON DELETE CASCADE,
            content_type VARCHAR(16) NOT NULL,
            compression VARCHAR(16) NOT NULL,
            data BYTEA NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    """Drop the dataset_blobs and datasets tables and their indexes."""
    op.execute("DROP TABLE IF EXISTS dataset_blobs")
    op.drop_index("ix_datasets_owner_content_hash", table_name="datasets", if_exists=True)
    op.drop_index("ix_datasets_owner_username", table_name="datasets", if_exists=True)
    op.execute("DROP TABLE IF EXISTS datasets")
