"""single-owner sharing: demote owner-tier grants to editor (+ merge heads)

Revision ID: c6d7e8f9a0b1
Revises: e1f2a3b4c5d6, b5c6d7e8f9a0
Create Date: 2026-06-01 13:00:00.000000

Skynet sharing moves to a single-owner model (Google-Drive My-Drive parity): an
optimization has exactly one owner, reassigned by outright transfer rather than
granted, so ``owner`` is no longer a member-grant role. Existing
``optimization_share_grants`` rows with ``role = 'owner'`` (former co-owners)
are demoted to ``'editor'`` so they keep edit/run access and remain resolvable
(``owner`` would otherwise no longer be a recognised grant role).

This revision also merges the two divergent heads on this branch — the sharing
lineage (``e1f2a3b4c5d6``, general_role) and the parallel ``b5c6d7e8f9a0``
(search_query_log) — back into a single head. The data migration only touches
the share-grants table created in ``d0e1f2a3b4c5``, a common ancestor of both,
so depending on both heads is safe.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c6d7e8f9a0b1"
down_revision: str | Sequence[str] | None = ("e1f2a3b4c5d6", "b5c6d7e8f9a0")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Demote any remaining owner-tier member grants to editor."""
    op.execute("UPDATE optimization_share_grants SET role = 'editor' WHERE role = 'owner'")


def downgrade() -> None:
    """No-op: the original owner-tier grants cannot be recovered.

    Splitting back into the two pre-merge heads is handled by Alembic from the
    ``down_revision`` tuple; the demotion is a one-way data change.
    """
