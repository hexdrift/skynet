"""add api_tokens table

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-05-29 01:00:00.000000

Adds the ``api_tokens`` table backing user-generated personal access tokens
for programmatic backend access. One row per user (``username`` primary key),
so generating a new token rotates the previous one. Only the SHA-256 hash of
the issued token is stored — the plaintext is shown to the user once, at
creation, and never persisted. ``token_hash`` is uniquely indexed for the
constant-cost auth lookup.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the api_tokens table and the token-hash lookup index."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS api_tokens (
            username VARCHAR(255) PRIMARY KEY,
            token_hash VARCHAR(64) NOT NULL,
            last4 VARCHAR(4) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            last_used_at TIMESTAMP WITH TIME ZONE
        )
        """
    )
    op.create_index(
        "ix_api_tokens_token_hash",
        "api_tokens",
        ["token_hash"],
        unique=True,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop the token-hash index and the api_tokens table."""
    op.drop_index("ix_api_tokens_token_hash", table_name="api_tokens", if_exists=True)
    op.execute("DROP TABLE IF EXISTS api_tokens")
