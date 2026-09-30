"""Drop the agent memory tables.

Revision ID: 0002_drop_agent_memory
Revises: 0001_onprem

The generalist agent's permanent memory feature was removed, so its three
tables go with it, along with every stored memory. Databases baselined after
the removal never had them, hence ``IF EXISTS``. They carry only primary keys,
so dropping the tables removes everything ``0001_onprem`` created for them.
``downgrade`` recreates them empty. Postgres-only, like the boot-time sync that
runs it; the SQLite test schema comes from the ORM models directly.
"""

from __future__ import annotations

from alembic import op

revision = "0002_drop_agent_memory"
down_revision = "0001_onprem"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop the agent memory log, summary and settings tables."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TABLE IF EXISTS agent_memory_settings")
    op.execute("DROP TABLE IF EXISTS agent_memory_summaries")
    op.execute("DROP TABLE IF EXISTS agent_memories")


def downgrade() -> None:
    """Recreate the agent memory tables empty."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_memories (
            username VARCHAR(255) NOT NULL,
            seq INTEGER NOT NULL,
            content VARCHAR(280) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            PRIMARY KEY (username, seq)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_memory_summaries (
            username VARCHAR(255) NOT NULL,
            block_size INTEGER NOT NULL,
            block_index INTEGER NOT NULL,
            content VARCHAR(280) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            PRIMARY KEY (username, block_size, block_index)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_memory_settings (
            username VARCHAR(255) PRIMARY KEY,
            wake_lines INTEGER,
            entry_chars INTEGER,
            recall_chars INTEGER,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
