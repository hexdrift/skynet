"""add agent_conversations and agent_messages tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-27 10:00:00.000000

Adds persistence for the generalist agent's chat threads so users can
review and resume earlier conversations across refreshes and devices.
``agent_conversations`` holds the thread header (title, pinned/archived
flags); ``agent_messages`` holds individual turns with their tool-call
payloads stored as JSONB.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create agent_conversations + agent_messages with their indexes."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_conversations (
            id VARCHAR(36) PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            title VARCHAR(200) NOT NULL DEFAULT '',
            pinned BOOLEAN NOT NULL DEFAULT false,
            archived_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.create_index(
        "ix_agent_conversations_username",
        "agent_conversations",
        ["username"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_agent_conversations_user_updated",
        "agent_conversations",
        ["username", "updated_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_agent_conversations_user_pinned",
        "agent_conversations",
        ["username", "pinned"],
        unique=False,
        if_not_exists=True,
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_messages (
            id SERIAL PRIMARY KEY,
            conversation_id VARCHAR(36) NOT NULL REFERENCES agent_conversations(id) ON DELETE CASCADE,
            role VARCHAR(16) NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            tool_calls JSONB,
            model VARCHAR(128),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.create_index(
        "ix_agent_messages_conversation_id",
        "agent_messages",
        ["conversation_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_agent_messages_created_at",
        "agent_messages",
        ["created_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_agent_messages_conv_created",
        "agent_messages",
        ["conversation_id", "created_at"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop both tables (CASCADE on agent_messages.conversation_id covers FK)."""
    op.drop_index("ix_agent_messages_conv_created", table_name="agent_messages", if_exists=True)
    op.drop_index("ix_agent_messages_created_at", table_name="agent_messages", if_exists=True)
    op.drop_index("ix_agent_messages_conversation_id", table_name="agent_messages", if_exists=True)
    op.execute("DROP TABLE IF EXISTS agent_messages")
    op.drop_index("ix_agent_conversations_user_pinned", table_name="agent_conversations", if_exists=True)
    op.drop_index("ix_agent_conversations_user_updated", table_name="agent_conversations", if_exists=True)
    op.drop_index("ix_agent_conversations_username", table_name="agent_conversations", if_exists=True)
    op.execute("DROP TABLE IF EXISTS agent_conversations")
