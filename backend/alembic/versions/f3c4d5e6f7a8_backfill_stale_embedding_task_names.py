"""backfill stale job_embeddings.task_name from payload_overview

Revision ID: f3c4d5e6f7a8
Revises: f2b3c4d5e6f7
Create Date: 2026-06-05 10:00:00.000000

Renaming a job after it was embedded updated ``payload_overview.name`` but left
the denormalized ``job_embeddings.task_name`` snapshot — the value the Explore
corpus and search read for the display label — untouched, so renamed runs kept
surfacing their pre-rename name. The rename handler now propagates the new name
to the embedding row; this heals the rows that drifted before that fix landed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from core.config import embeddings_schema_enabled

revision: str = "f3c4d5e6f7a8"
down_revision: str | Sequence[str] | None = "f2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Refresh stale embedded display names from the live payload overview."""
    # job_embeddings exists only under the semantic backend; lexical/bm25 skip it.
    if not embeddings_schema_enabled():
        return
    op.execute(
        "UPDATE job_embeddings je "
        "SET task_name = j.payload_overview->>'name' "
        "FROM jobs j "
        "WHERE j.optimization_id = je.optimization_id "
        "AND j.payload_overview->>'name' IS NOT NULL "
        "AND je.task_name IS DISTINCT FROM j.payload_overview->>'name'"
    )


def downgrade() -> None:
    """Irreversible: the pre-backfill stale snapshots are not worth restoring."""
