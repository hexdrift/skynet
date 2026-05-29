"""add agent_messages training metadata columns

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-28 00:00:00.000000

Adds the five nullable JSONB columns the generalist-agent training-ground
harness needs to score recorded turns. All columns are nullable —
pre-migration rows stay valid but are filtered out at load time via
``WHERE wizard_state_before IS NOT NULL``.

See ``backend/training_ground_SPEC.md`` §4 for the column purposes.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable JSONB training-metadata columns to agent_messages."""
    op.execute(
        """
        ALTER TABLE agent_messages
            ADD COLUMN IF NOT EXISTS wizard_state_before JSONB,
            ADD COLUMN IF NOT EXISTS wizard_state_after JSONB,
            ADD COLUMN IF NOT EXISTS allowed_tools JSONB,
            ADD COLUMN IF NOT EXISTS tool_schema_hashes JSONB,
            ADD COLUMN IF NOT EXISTS router_metadata JSONB
        """
    )
    # Speeds up the optimize CLI's window scan: it filters
    # ``wizard_state_before IS NOT NULL`` AND ``created_at >= :since``,
    # so a partial index over the assistant turns that carry metadata
    # avoids touching the legacy NULL-metadata rows.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_agent_messages_trainable
            ON agent_messages (created_at)
            WHERE wizard_state_before IS NOT NULL AND role = 'assistant'
        """
    )


def downgrade() -> None:
    """Drop the metadata columns + the trainable-rows partial index."""
    op.execute("DROP INDEX IF EXISTS ix_agent_messages_trainable")
    op.execute(
        """
        ALTER TABLE agent_messages
            DROP COLUMN IF EXISTS router_metadata,
            DROP COLUMN IF EXISTS tool_schema_hashes,
            DROP COLUMN IF EXISTS allowed_tools,
            DROP COLUMN IF EXISTS wizard_state_after,
            DROP COLUMN IF EXISTS wizard_state_before
        """
    )
