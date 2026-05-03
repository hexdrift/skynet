"""Compatibility marker for the squashed quota baseline.

Revision ID: 0004
Revises: 342f7449be26
Create Date: 2026-05-03 12:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0004"
down_revision: str | None = "342f7449be26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Keep existing databases stamped at revision 0004 upgradeable."""


def downgrade() -> None:
    """Keep the squashed baseline unchanged when downgrading to revision 342f7449be26."""
