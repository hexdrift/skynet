"""Drop the retired semantic-search embedding tables.

The on-prem baseline never created ``job_embeddings`` or
``conversation_embeddings``, but a store booted with ``SEARCH_BACKEND=semantic``
created both at runtime. Semantic search is gone, so drop them wherever they
exist. There is no downgrade: the tables held derived vectors only.
"""

from __future__ import annotations

from alembic import op

revision = "0002_drop_embeddings"
down_revision = "0001_onprem"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop both embedding tables when present."""
    op.execute("DROP TABLE IF EXISTS conversation_embeddings")
    op.execute("DROP TABLE IF EXISTS job_embeddings")


def downgrade() -> None:
    """Leave the tables dropped; their vectors cannot be reconstructed."""
