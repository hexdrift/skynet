"""Add quota administration audit events.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-30 00:00:01.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the quota audit event table."""
    op.create_table(
        "user_quota_audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("target_username", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("old_quota", sa.Integer(), nullable=True),
        sa.Column("new_quota", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index("ix_user_quota_audit_events_actor", "user_quota_audit_events", ["actor"], if_not_exists=True)
    op.create_index(
        "ix_user_quota_audit_events_target_username",
        "user_quota_audit_events",
        ["target_username"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop the quota audit event table."""
    op.drop_index("ix_user_quota_audit_events_target_username", table_name="user_quota_audit_events", if_exists=True)
    op.drop_index("ix_user_quota_audit_events_actor", table_name="user_quota_audit_events", if_exists=True)
    op.drop_table("user_quota_audit_events", if_exists=True)
