"""add general_role to share links (configurable anyone-link tier)

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-06-01 12:00:00.000000

Google-Drive-style links grant a configurable tier, not just anonymous view.
Adds ``general_role`` to ``optimization_share_links``: the tier an ``'anyone'``
link grants a *signed-in* visitor (``'viewer'`` or ``'editor'``; never
``'owner'``). Anonymous visitors stay on the read-only ``view`` tier regardless,
so a bare URL can never run inference on the owner's key. Defaults to
``'viewer'`` so existing anyone-links keep their read-only behavior.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the general_role column, defaulting existing links to viewer."""
    op.execute(
        "ALTER TABLE optimization_share_links "
        "ADD COLUMN IF NOT EXISTS general_role VARCHAR(16) NOT NULL DEFAULT 'viewer'"
    )


def downgrade() -> None:
    """Drop the general_role column."""
    op.execute("ALTER TABLE optimization_share_links DROP COLUMN IF EXISTS general_role")
