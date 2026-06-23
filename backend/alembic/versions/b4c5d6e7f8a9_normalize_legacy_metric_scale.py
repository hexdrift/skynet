"""normalize legacy 0-1 metric scores to the canonical 0-100 scale

Revision ID: b4c5d6e7f8a9
Revises: f3c4d5e6f7a8
Create Date: 2026-06-08 10:00:00.000000

Aggregate test metrics are stored on the 0-100 percentage scale that
``dspy.Evaluate`` reports. Runs from before that convention was settled
persisted the raw 0-1 fraction instead, so the store held two scales at once
and the UI papered over it with a ``value > 1 ? value : value * 100`` heuristic
that silently misread genuine sub-1% scores and turned a 0.3-point improvement
into "+30%".

This heals the drifted rows so every aggregate is 0-100. A row is legacy when
its ``optimized_test_metric`` is a fraction in ``(0, 1]`` — no real optimization
scores ``1%`` or less, and a finished run always has an optimized score, so that
field unambiguously reveals the row's scale. Per-example ``*_test_results``
scores stay 0-1/boolean (they are genuinely fractional) and counts, runtimes and
latencies are left untouched.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import context, op
from core.config import embeddings_schema_enabled

revision: str = "b4c5d6e7f8a9"
down_revision: str | Sequence[str] | None = "f3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCALE = 100.0
SCALAR_METRIC_KEYS = ("baseline_test_metric", "optimized_test_metric", "metric_improvement")
BOOTSTRAP_KEYS = ("ci95_lower", "ci95_upper", "mean_delta")


def _as_dict(value: Any) -> dict[str, Any] | None:
    """Coerce a jsonb column to a dict, tolerating a raw JSON string.

    Args:
        value: A value read from a jsonb column — a dict under the psycopg2
            jsonb typecaster, or a JSON string if that caster is absent.

    Returns:
        The decoded mapping, or ``None`` when the value is not an object.
    """
    if isinstance(value, str):
        value = json.loads(value)
    return value if isinstance(value, dict) else None


def _scale_num(value: Any) -> Any:
    """Multiply a real number by ``SCALE``; pass everything else through.

    Booleans are excluded so a stray ``True`` is never coerced to ``100``.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value * SCALE
    return value


def _scale_score_dict(scores: Any) -> Any:
    """Scale every numeric value in an objective-scores mapping."""
    mapping = _as_dict(scores)
    if mapping is None:
        return scores
    return {key: _scale_num(val) for key, val in mapping.items()}


def _scale_bootstrap(bootstrap: Any) -> Any:
    """Scale the CI bounds and mean delta of a paired-bootstrap block.

    ``resamples`` is a count and is left untouched.
    """
    mapping = _as_dict(bootstrap)
    if mapping is None:
        return bootstrap
    out = dict(mapping)
    for key in BOOTSTRAP_KEYS:
        if key in out:
            out[key] = _scale_num(out[key])
    return out


def _scale_result(result: dict[str, Any]) -> dict[str, Any]:
    """Scale the aggregate metric keys of a job ``result`` to 0-100.

    Touches the top-level scores, objective scores and bootstrap block plus the
    same fields mirrored under ``details``. Leaves per-example ``*_test_results``
    arrays, runtimes, latencies and counts alone.
    """
    out = dict(result)
    for key in SCALAR_METRIC_KEYS:
        if key in out:
            out[key] = _scale_num(out[key])
    if "objective_scores" in out:
        out["objective_scores"] = _scale_score_dict(out["objective_scores"])
    if "paired_bootstrap" in out:
        out["paired_bootstrap"] = _scale_bootstrap(out["paired_bootstrap"])
    details = _as_dict(out.get("details"))
    if details is not None:
        det = dict(details)
        for key in ("baseline_test_metric", "optimized_test_metric"):
            if key in det:
                det[key] = _scale_num(det[key])
        if "paired_bootstrap" in det:
            det["paired_bootstrap"] = _scale_bootstrap(det["paired_bootstrap"])
        for key in ("baseline_objective_scores", "optimized_objective_scores"):
            if key in det:
                det[key] = _scale_score_dict(det[key])
        out["details"] = det
    return out


def _scale_latest_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Scale the aggregate score fields of a ``latest_metrics`` block.

    ``tqdm_*`` progress fields are not metrics and are left untouched.
    """
    out = dict(metrics)
    for key in SCALAR_METRIC_KEYS:
        if key in out:
            out[key] = _scale_num(out[key])
    return out


def _is_legacy(result: dict[str, Any] | None, metrics: dict[str, Any] | None) -> bool:
    """Report whether a job's aggregate scores are on the legacy 0-1 scale.

    The optimized score is the discriminator: a finished run always has one and
    no real run scores ``1%`` or less, so a value in ``(0, 1]`` means the row
    was persisted as a fraction.
    """
    for src in (result, metrics):
        if not isinstance(src, dict):
            continue
        opt = src.get("optimized_test_metric")
        if isinstance(opt, bool):
            continue
        if isinstance(opt, (int, float)) and 0 < opt <= 1:
            return True
    return False


def _backfill_jobs_metric_scale() -> None:
    """Rescale every drifted ``jobs`` row's legacy 0-1 aggregates to 0-100.

    Online-only: each candidate row is read and rewritten with values computed
    in Python, which Alembic's offline ``--sql`` mode cannot serialize.
    """
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT optimization_id, result, latest_metrics FROM jobs "
            "WHERE result IS NOT NULL OR latest_metrics IS NOT NULL"
        )
    ).fetchall()
    for optimization_id, raw_result, raw_metrics in rows:
        result = _as_dict(raw_result)
        metrics = _as_dict(raw_metrics)
        if not _is_legacy(result, metrics):
            continue
        new_result = _scale_result(result) if result is not None else None
        new_metrics = _scale_latest_metrics(metrics) if metrics is not None else None
        bind.execute(
            sa.text(
                "UPDATE jobs SET "
                "result = CASE WHEN :has_result THEN CAST(:result AS jsonb) ELSE result END, "
                "latest_metrics = CASE WHEN :has_metrics THEN CAST(:metrics AS jsonb) "
                "ELSE latest_metrics END "
                "WHERE optimization_id = :oid"
            ),
            {
                "has_result": new_result is not None,
                "result": json.dumps(new_result) if new_result is not None else None,
                "has_metrics": new_metrics is not None,
                "metrics": json.dumps(new_metrics) if new_metrics is not None else None,
                "oid": optimization_id,
            },
        )


def upgrade() -> None:
    """Rescale legacy 0-1 aggregate metrics to 0-100 across jobs and embeddings."""
    # The jobs backfill reads rows and branches in Python, which Alembic's
    # offline (--sql) mode can't serialize — op.get_bind().execute() yields no
    # cursor there, so a schema-only dump (validate-migrations) crashes on it.
    # Skip it offline; the in-cluster Job runs online and backfills normally.
    if context.is_offline_mode():
        op.execute("-- offline --sql dump: per-row jobs metric backfill runs online only")
    else:
        _backfill_jobs_metric_scale()

    # job_embeddings exists only under the semantic backend; lexical/bm25 skip it.
    if embeddings_schema_enabled():
        op.execute(
            "UPDATE job_embeddings "
            "SET baseline_metric = baseline_metric * 100, "
            "optimized_metric = optimized_metric * 100 "
            "WHERE optimized_metric IS NOT NULL AND optimized_metric > 0 AND optimized_metric <= 1"
        )


def downgrade() -> None:
    """Irreversible: the original scale of each healed row is not recoverable."""
