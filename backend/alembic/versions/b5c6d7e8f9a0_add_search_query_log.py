"""add search_query_log for trending public searches

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-06-01 13:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b5c6d7e8f9a0"
down_revision: str | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the anonymous public-search query log + a recency index for trending.

    ``IF NOT EXISTS`` mirrors the api_tokens / share_links migrations: the app
    runs ``Base.metadata.create_all`` on boot, so the table may already exist
    when migrations run — the create must be idempotent.
    """
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS search_query_log (
            id BIGSERIAL PRIMARY KEY,
            query_text VARCHAR(200) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.create_index(
        "ix_search_query_log_created_at",
        "search_query_log",
        ["created_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop the search query log and its recency index."""
    op.drop_index(
        "ix_search_query_log_created_at",
        table_name="search_query_log",
        if_exists=True,
    )
    op.execute("DROP TABLE IF EXISTS search_query_log")
