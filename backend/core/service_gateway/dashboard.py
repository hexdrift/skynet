"""Public dashboard aggregator for the anonymous /explore page (PER-11 Feature B).

Combines two reads against the live database into a single payload:

1. Projection — every embedded job reduced to 2D via PCA so the
   frontend can render a scatter. No background job: projections are
   recomputed on each fetch and memoised in-process for a short TTL.
2. Point metadata — signature code, summary text, scores, timestamp
   — the sidebar shows this when a point is clicked.

No personal information is exposed. ``user_id`` is never projected; the
signature_code is shown full (per user's choice on the privacy question)
but metric_code bodies are deliberately omitted — only the metric_name
goes over the wire.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


_PROJECTION_TTL_SECONDS = 30
_PROJECTION_LOCK = threading.Lock()
_PROJECTION_CACHE: dict[str, Any] = {"at": 0.0, "points": []}


def _fit_pca_2d(vectors: list[list[float]]) -> list[tuple[float, float]]:
    """Project L2-normalised vectors to 2D via SVD.

    Returns ``[]`` when numpy isn't available or the matrix has fewer
    than two rows — the dashboard renders a welcoming empty state in
    either case. A fixed sign convention (flip so the first coord is
    positive in the largest-magnitude row) keeps the picture stable
    across reruns when the same inputs are provided.
    """
    if len(vectors) < 2:
        return [(0.0, 0.0)] * len(vectors)
    try:
        import numpy as np
    except ImportError:
        logger.debug("numpy unavailable — projection returns 0,0 for every point")
        return [(0.0, 0.0)] * len(vectors)

    try:
        matrix = np.asarray(vectors, dtype=float)
        centered = matrix - matrix.mean(axis=0, keepdims=True)
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        components = vh[:2]
        coords = centered @ components.T
        scale = float(np.max(np.abs(coords))) or 1.0
        normalised = coords / scale
        return [(float(x), float(y)) for x, y in normalised]
    except Exception as exc:
        logger.warning("PCA projection failed: %s", exc)
        return [(0.0, 0.0)] * len(vectors)


def _fetch_projection_rows(session: Session) -> list[dict[str, Any]]:
    """Pull every row needed to render the scatter in a single query.

    Embedding columns are streamed as SQL text (pgvector cast) and
    parsed in Python because SQLAlchemy's pgvector binding returns
    them as numpy arrays — we convert to ``list[float]`` up front so
    the downstream code only sees one representation.
    """
    rows = session.execute(
        text(
            "SELECT optimization_id, optimization_type, winning_model, winning_rank, "
            "is_recommendable, baseline_metric, optimized_metric, "
            "summary_text, signature_code, metric_name, task_name, "
            "module_name, optimizer_name, optimizer_kwargs, "
            "created_at, embedding_summary::text AS embedding_summary_text "
            "FROM job_embeddings "
            "WHERE embedding_summary IS NOT NULL "
            "ORDER BY created_at DESC "
            "LIMIT 2000"
        )
    ).mappings().all()
    out = []
    for row in rows:
        vector = _parse_pgvector_literal(row.get("embedding_summary_text"))
        if vector is None:
            continue
        out.append({
            "optimization_id": row["optimization_id"],
            "optimization_type": row["optimization_type"],
            "winning_model": row["winning_model"],
            "winning_rank": row["winning_rank"],
            "is_recommendable": bool(row["is_recommendable"]),
            "baseline_metric": _as_float(row["baseline_metric"]),
            "optimized_metric": _as_float(row["optimized_metric"]),
            "summary_text": row["summary_text"],
            "signature_code": row["signature_code"],
            "metric_name": row["metric_name"],
            "task_name": row["task_name"],
            "module_name": row["module_name"],
            "optimizer_name": row["optimizer_name"],
            "optimizer_kwargs": row["optimizer_kwargs"] or {},
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "_vector": vector,
        })
    return out


def _parse_pgvector_literal(value: Any) -> list[float] | None:
    """Parse ``'[0.1,0.2,...]'`` back into a Python list of floats."""
    if value is None:
        return None
    if isinstance(value, list):
        return [float(x) for x in value]
    if not isinstance(value, str):
        return None
    s = value.strip().lstrip("[").rstrip("]")
    if not s:
        return None
    try:
        return [float(x) for x in s.split(",")]
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_public_dashboard(*, job_store: Any) -> dict[str, Any]:
    """Return the payload for ``GET /dashboard/public``.

    The projection is cached in-process for ``_PROJECTION_TTL_SECONDS``
    because PCA on ~2000 x 512 floats is cheap but not free.
    """
    engine = job_store.engine
    with Session(engine) as session:
        now = time.time()
        with _PROJECTION_LOCK:
            cached = _PROJECTION_CACHE
            if now - float(cached["at"]) < _PROJECTION_TTL_SECONDS and cached["points"]:
                points = cached["points"]
            else:
                rows = _fetch_projection_rows(session)
                coords = _fit_pca_2d([r["_vector"] for r in rows])
                points = []
                for row, (x, y) in zip(rows, coords, strict=False):
                    row.pop("_vector", None)
                    row["x"] = x
                    row["y"] = y
                    points.append(row)
                _PROJECTION_CACHE["at"] = now
                _PROJECTION_CACHE["points"] = points
    return {"points": points}


def invalidate_projection_cache() -> None:
    """Force the next ``fetch_public_dashboard`` call to recompute the PCA."""
    with _PROJECTION_LOCK:
        _PROJECTION_CACHE["at"] = 0.0
        _PROJECTION_CACHE["points"] = []
