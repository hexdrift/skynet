"""add gepa_checkpoints and grid_pair_results tables for resumable optimizations

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-06-20 10:00:00.000000

Adds the storage that backs resuming a GEPA optimization that died mid-run.

``gepa_checkpoints`` holds the pickled ``gepa_state.bin`` (candidate population,
Pareto front, iteration counter, consumed metric-call budget) the GEPA engine
writes each iteration. Keyed by ``(optimization_id, pair_index)``: a single run
uses ``pair_index = -1``; a grid search keeps one row per in-flight model pair.

``grid_pair_results`` holds each completed grid pair's ``PairResult`` JSON, so a
resumed grid keeps finished pairs and re-runs only the rest.

Both tables' ``stored_bytes`` fold into the owner's "optimizations" footprint
while a resumable failure is pending; rows are removed with the parent job via
the cascading foreign key. Postgres-only DDL; SQLite test schemas come from
``create_all`` over the models.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b9c0d1e2f3a4"
down_revision: str | None = "a8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``gepa_checkpoints`` and ``grid_pair_results`` tables on Postgres."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS gepa_checkpoints (
            optimization_id VARCHAR(36) NOT NULL REFERENCES jobs(optimization_id) ON DELETE CASCADE,
            pair_index INTEGER NOT NULL DEFAULT -1,
            iteration INTEGER NOT NULL DEFAULT 0,
            data BYTEA NOT NULL,
            stored_bytes BIGINT NOT NULL DEFAULT 0,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            PRIMARY KEY (optimization_id, pair_index)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS grid_pair_results (
            optimization_id VARCHAR(36) NOT NULL REFERENCES jobs(optimization_id) ON DELETE CASCADE,
            pair_index INTEGER NOT NULL,
            result JSONB NOT NULL,
            stored_bytes BIGINT NOT NULL DEFAULT 0,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            PRIMARY KEY (optimization_id, pair_index)
        )
        """
    )


def downgrade() -> None:
    """Drop the ``grid_pair_results`` and ``gepa_checkpoints`` tables."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TABLE IF EXISTS grid_pair_results")
    op.execute("DROP TABLE IF EXISTS gepa_checkpoints")
