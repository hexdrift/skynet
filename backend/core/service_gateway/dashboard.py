"""Public dashboard aggregator for the anonymous /explore page (PER-11 Feature B).

Pipeline:

1. Fingerprint check — cheap ``COUNT(*) + MAX(created_at)`` query gates the
   expensive recompute. Same fingerprint = serve cached payload.
2. Bulk fetch — every embedded job's lightweight metadata + the
   ``embedding_summary`` vector itself. Heavy fields (``signature_code``,
   ``optimizer_kwargs``, ``metric_name``, ``winning_rank``,
   ``is_recommendable``) are not used by the explore UI and are dropped to
   keep the payload under ~5 MB (gzipped) at 100k points.
3. Projection — UMAP when ``umap-learn`` is installed (preserves local
   structure that PCA flattens), PCA fallback otherwise.
4. Cluster hierarchy — Ward linkage on the 2D coords, cut at 5 fixed
   granularities so the frontend slider just looks up the precomputed
   level instead of re-running clustering.
5. Cache — keyed by fingerprint, 5 min TTL. UMAP on 100k×768 takes seconds.

No personal information is exposed. ``user_id`` is never projected.
``signature_code`` is dropped from the bulk response (it is not consumed
by the explore page).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# numpy underpins both projection paths — degrade gracefully when absent.
try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

# umap-learn ships under the [recommendations] extra. Optional at runtime —
# we fall back to PCA when it isn't installed.
try:
    import umap as _umap
except ImportError:
    _umap = None  # type: ignore[assignment]

# scipy is a hard dep, but guard anyway so an import-time error in scipy
# can't take down the dashboard.
try:
    from scipy.cluster.hierarchy import fcluster, linkage
except ImportError:
    fcluster = None  # type: ignore[assignment]
    linkage = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# Cluster counts per granularity level. Slider value 0..4 picks the index.
CLUSTER_LEVEL_K: tuple[int, ...] = (2, 4, 8, 16, 32)
CLUSTER_LEVELS = len(CLUSTER_LEVEL_K)

# Defensive ceiling. The /explore page is designed for up to 100k points;
# beyond that, UMAP on the request thread becomes a real outage risk.
MAX_POINTS = 100_000

# Free-text fields are truncated for the bulk response. Full text is
# only useful when a point is selected — and the truncated text is what
# the tooltip / detail panel header already render.
SUMMARY_TEXT_MAX = 200

_CACHE_TTL_SECONDS = 300
_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {"fingerprint": None, "at": 0.0, "payload": None}


def _fit_pca_2d(vectors: list[list[float]]) -> list[tuple[float, float]]:
    """Project L2-normalised vectors to 2D via SVD.

    Returns ``[]`` when numpy isn't available or the matrix has fewer
    than two rows — the dashboard renders a welcoming empty state in
    either case. A fixed sign convention (flip each component so the
    largest-magnitude entry in its column is positive) keeps the
    picture stable across reruns: SVD's component sign is otherwise
    arbitrary and would mirror the scatter on every recompute.

    Args:
        vectors: Embedding rows, each already L2-normalised.

    Returns:
        ``(x, y)`` per input row, scaled so the largest magnitude is 1.0.
    """
    if len(vectors) < 2:
        return [(0.0, 0.0)] * len(vectors)
    if np is None:
        logger.debug("numpy unavailable — projection returns 0,0 for every point")
        return [(0.0, 0.0)] * len(vectors)

    try:
        matrix = np.asarray(vectors, dtype=float)
        centered = matrix - matrix.mean(axis=0, keepdims=True)
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        components = vh[:2]
        coords = centered @ components.T
        for axis in range(coords.shape[1]):
            column = coords[:, axis]
            if column.size == 0:
                continue
            anchor_idx = int(np.argmax(np.abs(column)))
            if column[anchor_idx] < 0:
                coords[:, axis] = -column
        scale = float(np.max(np.abs(coords))) or 1.0
        normalised = coords / scale
        return [(float(x), float(y)) for x, y in normalised]
    except Exception as exc:
        logger.warning("PCA projection failed: %s", exc)
        return [(0.0, 0.0)] * len(vectors)


def _fit_umap_2d(vectors: list[list[float]]) -> list[tuple[float, float]] | None:
    """Project to 2D via UMAP, returning ``None`` on failure or missing dep.

    UMAP preserves local structure that PCA flattens — runs that share a
    prompt template stay co-located even when global variance is dominated
    by an unrelated axis. The trade-off is compute time: ~10-30s on 100k
    rows, hence the cache.

    Args:
        vectors: Embedding rows.

    Returns:
        ``(x, y)`` per input row scaled to [-1, 1], or ``None`` if UMAP
        isn't installed, numpy is missing, the input is too small, or the
        fit raised.
    """
    if _umap is None or np is None or len(vectors) < 4:
        return None
    try:
        matrix = np.asarray(vectors, dtype=float)
        n = matrix.shape[0]
        n_neighbors = min(15, max(2, n - 1))
        reducer = _umap.UMAP(
            n_neighbors=n_neighbors,
            min_dist=0.1,
            n_components=2,
            random_state=42,
            init="random",
        )
        coords = reducer.fit_transform(matrix)
        scale = float(np.max(np.abs(coords))) or 1.0
        normalised = coords / scale
        return [(float(x), float(y)) for x, y in normalised]
    except Exception as exc:
        logger.warning("UMAP projection failed: %s; falling back to PCA", exc)
        return None


def _project_2d(vectors: list[list[float]]) -> list[tuple[float, float]]:
    """Project to 2D, preferring UMAP when available.

    Args:
        vectors: Embedding rows.

    Returns:
        ``(x, y)`` per input row, scaled so the largest magnitude is 1.0.
    """
    umap_coords = _fit_umap_2d(vectors)
    if umap_coords is not None:
        return umap_coords
    return _fit_pca_2d(vectors)


def _compute_cluster_levels(coords: list[tuple[float, float]]) -> list[list[int]]:
    """Compute cluster_id per point at each granularity level in CLUSTER_LEVEL_K.

    Hierarchical Ward linkage on the 2D coords (already cheap by then —
    100k points × 2 dims fits comfortably) cut at fixed cluster counts.
    The frontend slider picks an index into the returned outer list; no
    re-clustering happens on the client.

    Args:
        coords: 2D projection from :func:`_project_2d`.

    Returns:
        A list of length :data:`CLUSTER_LEVELS`. Each inner list holds
        ``len(coords)`` integer cluster IDs (zero-indexed, dense within
        the level). On failure, every point is assigned to cluster 0.
    """
    n = len(coords)
    if n == 0 or fcluster is None or linkage is None or np is None:
        return [[0] * n for _ in CLUSTER_LEVEL_K]
    if n < 4:
        return [list(range(n)) for _ in CLUSTER_LEVEL_K]
    try:
        matrix = np.asarray(coords, dtype=float)
        z = linkage(matrix, method="ward")
        out: list[list[int]] = []
        for k in CLUSTER_LEVEL_K:
            effective_k = min(k, n)
            labels = fcluster(z, t=effective_k, criterion="maxclust")
            out.append([int(label) - 1 for label in labels])
        return out
    except Exception as exc:
        logger.warning("Hierarchical clustering failed: %s", exc)
        return [[0] * n for _ in CLUSTER_LEVEL_K]


def _fetch_fingerprint(session: Session) -> str:
    """Cheap content fingerprint over ``job_embeddings``.

    Used as the cache key. If the row count or the most recent
    ``created_at`` changes, the fingerprint changes and we recompute
    the projection + clustering.

    Args:
        session: Active SQLAlchemy session.

    Returns:
        ``"<count>|<max_created_at>"`` — opaque but compact.
    """
    row = (
        session.execute(
            text(
                "SELECT COUNT(*) AS n, MAX(created_at) AS max_ts "
                "FROM job_embeddings "
                "WHERE embedding_summary IS NOT NULL"
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return "0|none"
    max_ts = row["max_ts"]
    return f"{int(row['n'])}|{max_ts.isoformat() if max_ts else 'none'}"


def _fetch_projection_rows(session: Session) -> list[dict[str, Any]]:
    """Pull every row needed to render the scatter, capped at :data:`MAX_POINTS`.

    Embedding columns are streamed as SQL text (pgvector cast) and parsed
    in Python because SQLAlchemy's pgvector binding returns them as numpy
    arrays — we convert to ``list[float]`` up front so the downstream
    code only sees one representation.

    Args:
        session: An open SQLAlchemy session bound to the job-store engine.

    Returns:
        Row dicts containing point metadata plus a ``_vector`` list. Heavy
        fields (signature_code, optimizer_kwargs, metric_name) are
        intentionally omitted — they are not used by the explore UI and
        bloat the bulk response.
    """
    rows = (
        session.execute(
            text(
                "SELECT optimization_id, optimization_type, winning_model, "
                "baseline_metric, optimized_metric, summary_text, task_name, "
                "module_name, optimizer_name, created_at, "
                "embedding_summary::text AS embedding_summary_text "
                "FROM job_embeddings "
                "WHERE embedding_summary IS NOT NULL "
                "ORDER BY created_at DESC "
                f"LIMIT {MAX_POINTS}"
            )
        )
        .mappings()
        .all()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        vector = _parse_pgvector_literal(row.get("embedding_summary_text"))
        if vector is None:
            continue
        summary = row["summary_text"]
        if isinstance(summary, str) and len(summary) > SUMMARY_TEXT_MAX:
            summary = summary[:SUMMARY_TEXT_MAX].rstrip() + "…"
        out.append(
            {
                "optimization_id": row["optimization_id"],
                "optimization_type": row["optimization_type"],
                "winning_model": row["winning_model"],
                "baseline_metric": _as_float(row["baseline_metric"]),
                "optimized_metric": _as_float(row["optimized_metric"]),
                "summary_text": summary,
                "task_name": row["task_name"],
                "module_name": row["module_name"],
                "optimizer_name": row["optimizer_name"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "_vector": vector,
            }
        )
    return out


def _parse_pgvector_literal(value: Any) -> list[float] | None:
    """Parse ``'[0.1,0.2,...]'`` back into a Python list of floats.

    Args:
        value: The pgvector literal as a string, list, or ``None``.

    Returns:
        Floats parsed from the literal, or ``None`` if unparseable.
    """
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
    """Best-effort coerce ``value`` to ``float``; return ``None`` on ``None`` or parse failure.

    Args:
        value: Anything ``float()`` might accept.

    Returns:
        The parsed float, or ``None`` if conversion fails.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_public_dashboard(*, job_store: Any) -> dict[str, Any]:
    """Return the payload for ``GET /dashboard/public``.

    Cached by content fingerprint with a 5 min TTL. UMAP + clustering is
    expensive (seconds at 100k rows); recomputing per request would
    spike CPU under traffic.

    Args:
        job_store: A store exposing a SQLAlchemy ``engine`` attribute.

    Returns:
        ``{"points": [...], "meta": {...}}``. Each point carries
        ``cluster_levels: list[int]`` of length :data:`CLUSTER_LEVELS`,
        and ``meta`` exposes the per-level cluster counts so the
        frontend can label the slider.
    """
    engine = job_store.engine
    with Session(engine) as session:
        fingerprint = _fetch_fingerprint(session)
        now = time.time()
        with _LOCK:
            cached = _CACHE
            if (
                cached["fingerprint"] == fingerprint
                and cached["payload"] is not None
                and now - float(cached["at"]) < _CACHE_TTL_SECONDS
            ):
                return cached["payload"]
        rows = _fetch_projection_rows(session)
        coords = _project_2d([r["_vector"] for r in rows])
        cluster_levels = _compute_cluster_levels(coords)
        points: list[dict[str, Any]] = []
        for idx, (row, (x, y)) in enumerate(zip(rows, coords, strict=False)):
            row.pop("_vector", None)
            row["x"] = x
            row["y"] = y
            row["cluster_levels"] = [level[idx] for level in cluster_levels]
            points.append(row)
        payload = {
            "points": points,
            "meta": {
                "count": len(points),
                "level_cluster_counts": list(CLUSTER_LEVEL_K),
            },
        }
        with _LOCK:
            _CACHE["fingerprint"] = fingerprint
            _CACHE["at"] = now
            _CACHE["payload"] = payload
        return payload


def invalidate_projection_cache() -> None:
    """Force the next ``fetch_public_dashboard`` call to recompute."""
    with _LOCK:
        _CACHE["fingerprint"] = None
        _CACHE["at"] = 0.0
        _CACHE["payload"] = None
