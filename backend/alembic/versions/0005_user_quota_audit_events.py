"""Compatibility marker for the squashed quota audit baseline.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-03 12:30:01.000000
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Keep existing databases stamped at revision 0005 upgradeable."""


def downgrade() -> None:
    """Keep the squashed baseline unchanged when downgrading to revision 0004."""
