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
4. Cache — keyed by fingerprint, 5 min TTL. UMAP on 100k×768 takes seconds.

No personal information is exposed. ``user_id`` is never projected.
``signature_code`` is dropped from the bulk response (it is not consumed
by the explore page). Jobs flagged ``is_private`` are excluded from both
the fingerprint and the bulk fetch, so they never appear on the map and
do not invalidate the cache when added.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..api.routers._helpers import compute_compare_fingerprint
from ..config import settings
from ..constants import (
    PAYLOAD_OVERVIEW_DESCRIPTION,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
    PAYLOAD_OVERVIEW_TASK_FINGERPRINT,
)
from .embedding_pipeline.embeddings import get_embedder

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

logger = logging.getLogger(__name__)


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


def _fetch_fingerprint(session: Session) -> str:
    """Cheap content fingerprint over the searchable corpus.

    Used as the cache key. Includes both embedded and unembedded public
    success jobs so backfill progress (or new submissions while embeddings
    are off) reliably invalidates the cached scatter payload.

    Args:
        session: Active SQLAlchemy session.

    Returns:
        ``"<embedded>|<embedded_max_ts>|<unembedded>|<unembedded_max_ts>"``
        — opaque but compact.
    """
    embedded = (
        session.execute(
            text(
                "SELECT COUNT(*) AS n, MAX(je.created_at) AS max_ts "
                "FROM job_embeddings je "
                "INNER JOIN jobs j ON j.optimization_id = je.optimization_id "
                "WHERE j.status = 'success' "
                "AND je.embedding_summary IS NOT NULL AND je.is_private = FALSE"
            )
        )
        .mappings()
        .first()
    )
    unembedded = (
        session.execute(
            text(
                "SELECT COUNT(*) AS n, MAX(j.created_at) AS max_ts "
                "FROM jobs j "
                "LEFT JOIN job_embeddings je ON je.optimization_id = j.optimization_id "
                "WHERE j.status = 'success' "
                "AND (je.optimization_id IS NULL OR je.embedding_summary IS NULL) "
                "AND NOT COALESCE((j.payload_overview->>'is_private')::boolean, FALSE)"
            )
        )
        .mappings()
        .first()
    )
    e_n = int(embedded["n"]) if embedded else 0
    e_ts = embedded["max_ts"] if embedded else None
    u_n = int(unembedded["n"]) if unembedded else 0
    u_ts = unembedded["max_ts"] if unembedded else None
    return (
        f"{e_n}|{e_ts.isoformat() if e_ts else 'none'}|"
        f"{u_n}|{u_ts.isoformat() if u_ts else 'none'}"
    )


def _fetch_projection_rows(session: Session) -> list[dict[str, Any]]:
    """Pull every row needed to render the scatter, capped at :data:`MAX_POINTS`.

    Embedding columns are streamed as SQL text (pgvector cast) and parsed
    in Python because SQLAlchemy's pgvector binding returns them as numpy
    arrays — we convert to ``list[float]`` up front so the downstream
    code only sees one representation.

    Every public success row is its own point: the map's grouping is the
    frontend's ``task_fingerprint`` bucket, not ``compare_fingerprint``.
    Identical-task jobs whose embeddings collide naturally overlap at the
    same canvas coordinate — that overlap, plus the variation ring the
    frontend draws when ``buildVariationGroups`` finds siblings sharing a
    task, is how the UI signals "this dot fronts N runs of the same task".
    Collapsing on the backend would silently hide siblings from the
    variation count and the detail-panel picker.

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
                "SELECT je.optimization_id, je.optimization_type, je.winning_model, "
                "je.baseline_metric, je.optimized_metric, je.summary_text, "
                f"COALESCE(je.task_name, j.payload_overview->>'{PAYLOAD_OVERVIEW_NAME}') AS task_name, "
                "je.module_name, je.optimizer_name, je.created_at, "
                "je.embedding_summary::text AS embedding_summary_text, "
                "j.payload_overview AS payload_overview "
                "FROM job_embeddings je "
                "INNER JOIN jobs j ON j.optimization_id = je.optimization_id "
                "WHERE j.status = 'success' "
                "AND je.embedding_summary IS NOT NULL AND je.is_private = FALSE "
                "ORDER BY je.created_at DESC, je.optimization_id DESC "
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
        overview = row.get("payload_overview") or {}
        if not isinstance(overview, dict):
            overview = {}
        optimization_id = row["optimization_id"]
        compare_fp = compute_compare_fingerprint(optimization_id, overview)
        task_fp = overview.get(PAYLOAD_OVERVIEW_TASK_FINGERPRINT)
        if not isinstance(task_fp, str) or not task_fp:
            task_fp = None
        summary = row["summary_text"]
        if isinstance(summary, str) and len(summary) > SUMMARY_TEXT_MAX:
            summary = summary[:SUMMARY_TEXT_MAX].rstrip() + "…"
        out.append(
            {
                "optimization_id": optimization_id,
                "optimization_type": row["optimization_type"],
                "winning_model": row["winning_model"],
                "baseline_metric": _as_float(row["baseline_metric"]),
                "optimized_metric": _as_float(row["optimized_metric"]),
                "summary_text": summary,
                "task_name": row["task_name"],
                "module_name": row["module_name"],
                "optimizer_name": row["optimizer_name"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "task_fingerprint": task_fp,
                "compare_fingerprint": compare_fp,
                "siblings": [],
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


def _fetch_unembedded_points(session: Session) -> list[dict[str, Any]]:
    """Return public success-state jobs that lack an embedding row.

    These points are surfaced so the explore corpus count and lexical
    search results reflect the full archive — not just the rows that
    happen to be embedded right now. They carry ``x=0, y=0`` because
    there's no vector to project; the map renderer should treat them as
    off-canvas (or render them in a separate region), since piling them
    at the origin would otherwise visually overstate that cluster.

    Args:
        session: An open SQLAlchemy session bound to the job-store engine.

    Returns:
        A list of point dicts in the same shape as
        :func:`_fetch_projection_rows`, minus ``_vector`` /
        ``compare_fingerprint`` / ``task_fingerprint``.
    """
    rows = (
        session.execute(
            text(
                "SELECT j.optimization_id, "
                "COALESCE(je.optimization_type, j.optimization_type) AS optimization_type, "
                f"COALESCE(je.winning_model, j.payload_overview->>'{PAYLOAD_OVERVIEW_MODEL_NAME}') "
                "AS winning_model, "
                "je.baseline_metric, je.optimized_metric, "
                "je.summary_text, "
                f"COALESCE(je.task_name, j.payload_overview->>'{PAYLOAD_OVERVIEW_NAME}') AS task_name, "
                f"COALESCE(je.module_name, j.payload_overview->>'{PAYLOAD_OVERVIEW_MODULE_NAME}') "
                "AS module_name, "
                f"COALESCE(je.optimizer_name, j.payload_overview->>'{PAYLOAD_OVERVIEW_OPTIMIZER_NAME}') "
                "AS optimizer_name, "
                "j.created_at, "
                f"j.payload_overview->>'{PAYLOAD_OVERVIEW_DESCRIPTION}' AS task_description "
                "FROM jobs j "
                "LEFT JOIN job_embeddings je ON je.optimization_id = j.optimization_id "
                "WHERE j.status = 'success' "
                "AND (je.optimization_id IS NULL OR je.embedding_summary IS NULL) "
                "AND NOT COALESCE((j.payload_overview->>'is_private')::boolean, FALSE) "
                "ORDER BY j.created_at DESC, j.optimization_id DESC "
                f"LIMIT {MAX_POINTS}"
            )
        )
        .mappings()
        .all()
    )
    points: list[dict[str, Any]] = []
    for row in rows:
        summary = row["summary_text"] or row.get("task_description")
        if isinstance(summary, str) and len(summary) > SUMMARY_TEXT_MAX:
            summary = summary[:SUMMARY_TEXT_MAX].rstrip() + "…"
        points.append(
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
                "x": 0.0,
                "y": 0.0,
                "siblings": [],
                "task_fingerprint": None,
                "compare_fingerprint": None,
                "has_coordinates": False,
            }
        )
    return points


def fetch_public_dashboard(*, job_store: Any) -> dict[str, Any]:
    """Return the payload for ``GET /dashboard/public``.

    Cached by content fingerprint with a 5 min TTL. UMAP is expensive
    (seconds at 100k rows); recomputing per request would spike CPU
    under traffic.

    The payload merges two sources so the /explore caption + lexical
    search reflect the full corpus, not just the embedded slice:

    * Embedded jobs come back with their UMAP/PCA coordinates and
      ``has_coordinates=True``.
    * Successful jobs missing an embedding row come back with placeholder
      coordinates and ``has_coordinates=False`` — they are searchable but
      should not be rendered on the scatter map.

    When ``settings.embeddings_enabled`` is false the projection step is
    skipped entirely and only the unembedded list is returned.

    Args:
        job_store: A store exposing a SQLAlchemy ``engine`` attribute.

    Returns:
        ``{"points": [...]}`` — one entry per public success-state job.
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

        if settings.embeddings_enabled:
            rows = _fetch_projection_rows(session)
            coords = _project_2d([r["_vector"] for r in rows])
            embedded_points: list[dict[str, Any]] = []
            for row, (x, y) in zip(rows, coords, strict=False):
                row.pop("_vector", None)
                row["x"] = x
                row["y"] = y
                row["has_coordinates"] = True
                embedded_points.append(row)
        else:
            embedded_points = []

        unembedded_points = _fetch_unembedded_points(session)
        payload = {"points": embedded_points + unembedded_points}
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


SEARCH_SORT_RELEVANCE = "relevance"
SEARCH_SORT_RECENT = "recent"
SEARCH_SORT_GAIN = "gain"
SEARCH_SORTS = (SEARCH_SORT_RELEVANCE, SEARCH_SORT_RECENT, SEARCH_SORT_GAIN)

SEARCH_PAGE_SIZE_DEFAULT = 30
SEARCH_PAGE_SIZE_MAX = 50
SEARCH_MATCHED_IDS_CAP = 5_000


def _dedup_ranked_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[str], dict[str, float | None]]:
    """Collapse ranked rows to leader ids by ``compare_fingerprint``.

    The first occurrence of each ``compare_fingerprint`` is kept; the caller
    is responsible for ordering rows so that the desired leader comes first.
    Rows missing a ``compare_fingerprint`` (legacy / no ``task_fingerprint``)
    fall back to their own ``optimization_id`` so they never collapse into a
    bogus group.

    Args:
        rows: Mapping rows with ``optimization_id``, ``payload_overview``,
            and ``relevance`` keys, in the caller's chosen sort order.

    Returns:
        ``(ordered_leader_ids, relevance_by_id)``. The relevance map only
        contains entries for leaders.
    """
    seen: set[str] = set()
    leaders: list[str] = []
    relevance_by_id: dict[str, float | None] = {}
    for row in rows:
        opt_id = row["optimization_id"]
        overview = row.get("payload_overview") or {}
        if not isinstance(overview, dict):
            overview = {}
        compare_fp = compute_compare_fingerprint(opt_id, overview)
        key = compare_fp or f"_no_fp:{opt_id}"
        if key in seen:
            continue
        seen.add(key)
        leaders.append(opt_id)
        relevance_by_id[opt_id] = _as_float(row.get("relevance"))
    return leaders, relevance_by_id


def _vector_literal(vector: list[float]) -> str:
    """Format a Python float list as a pgvector text literal.

    Args:
        vector: The query embedding as a list of floats.

    Returns:
        The pgvector ``"[v1,v2,...]"`` literal — pgvector parses this on input.
    """
    return "[" + ",".join(f"{v:.7f}" for v in vector) + "]"


def search_optimizations(
    *,
    job_store: Any,
    query: str | None,
    models: list[str] | None = None,
    optimizers: list[str] | None = None,
    optimization_types: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: str = SEARCH_SORT_RELEVANCE,
    page: int = 1,
    size: int = SEARCH_PAGE_SIZE_DEFAULT,
    owner_username: str | None = None,
) -> dict[str, Any]:
    """Search the optimization corpus, semantic when possible, lexical otherwise.

    Dispatch rules:

    * ``embeddings_enabled`` is off → lexical.
    * The corpus contains any success-state job that lacks a summary embedding
      → lexical (so partially-embedded corpora stay fully searchable instead
      of silently hiding the unembedded rows).
    * A query is supplied but the embedder can't encode it → lexical.
    * Otherwise → semantic (pgvector cosine similarity).

    Both paths support the same structured filters, paging, and sort modes.
    Lexical results have ``relevance = None`` since there's no continuous
    similarity score to surface.

    Args:
        job_store: Job store exposing the SQLAlchemy ``engine`` attribute.
        query: Free-text query (embedded server-side when semantic) or ``None``.
        models: Optional model whitelist (matches embedded ``winning_model`` or
            the payload-overview model name for unembedded jobs).
        optimizers: Optional optimizer whitelist.
        optimization_types: Optional ``optimization_type`` whitelist.
        date_from: Inclusive lower bound on ``created_at`` (date precision).
        date_to: Inclusive upper bound on ``created_at`` (date precision).
        sort: One of :data:`SEARCH_SORTS`.
        page: 1-indexed page number.
        size: Page size; clamped to ``[1, SEARCH_PAGE_SIZE_MAX]``.
        owner_username: When set, scope the search to jobs owned by this user
            (including their private rows) instead of the public corpus. The
            caller is responsible for verifying the requested owner matches the
            authenticated session.

    Returns:
        ``{"results": [...], "total": int, "matched_ids": [...], "search_type": str}``,
        where ``search_type`` is ``"semantic"`` or ``"lexical"`` depending on
        which dispatch branch served the query.
    """
    if sort not in SEARCH_SORTS:
        sort = SEARCH_SORT_RELEVANCE
    page = max(1, page)
    size = max(1, min(SEARCH_PAGE_SIZE_MAX, size))

    query_clean = (query or "").strip()

    use_lexical = not settings.embeddings_enabled
    query_vector: list[float] | None = None

    if not use_lexical:
        if _has_unembedded_success_jobs(job_store, owner_username=owner_username):
            use_lexical = True
        elif query_clean:
            query_vector = get_embedder().encode(query_clean, task="retrieval.query")
            if query_vector is None:
                logger.info("search_optimizations: query embedding unavailable, using lexical")
                use_lexical = True

    if use_lexical:
        return _search_lexical(
            job_store=job_store,
            query=query_clean,
            models=models,
            optimizers=optimizers,
            optimization_types=optimization_types,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
            page=page,
            size=size,
            owner_username=owner_username,
        )

    return _search_semantic(
        job_store=job_store,
        query_vector=query_vector,
        models=models,
        optimizers=optimizers,
        optimization_types=optimization_types,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        page=page,
        size=size,
        owner_username=owner_username,
    )


def _has_unembedded_success_jobs(
    job_store: Any, *, owner_username: str | None = None
) -> bool:
    """Return True if any in-scope successful job lacks a summary embedding row.

    Cheap ``LIMIT 1`` probe used to decide whether the search dispatcher
    should fall back to lexical matching. The query is index-friendly
    (``jobs.status`` is indexed) and short-circuits as soon as one
    qualifying row is found.

    Args:
        job_store: Job store exposing the SQLAlchemy ``engine`` attribute.
        owner_username: When set, restrict the probe to that user's jobs so a
            mine-corpus query isn't downgraded to lexical because some other
            user has unembedded rows.

    Returns:
        True when at least one in-scope success-state job has no embedding,
        False otherwise (including on transient query failure — we prefer
        the semantic path to a hard error).
    """
    scope_sql = (
        "j.username = :owner_username"
        if owner_username is not None
        else "NOT COALESCE((j.payload_overview->>'is_private')::boolean, FALSE)"
    )
    params: dict[str, Any] = {}
    if owner_username is not None:
        params["owner_username"] = owner_username
    try:
        with Session(job_store.engine) as session:
            row = session.execute(
                text(
                    "SELECT 1 FROM jobs j "
                    "LEFT JOIN job_embeddings je ON je.optimization_id = j.optimization_id "
                    "WHERE j.status = 'success' "
                    "AND (je.optimization_id IS NULL OR je.embedding_summary IS NULL) "
                    f"AND {scope_sql} "
                    "LIMIT 1"
                ),
                params,
            ).first()
            return row is not None
    except Exception as exc:
        logger.warning("Unembedded-job probe failed, assuming all embedded: %s", exc)
        return False


def _search_semantic(
    *,
    job_store: Any,
    query_vector: list[float] | None,
    models: list[str] | None,
    optimizers: list[str] | None,
    optimization_types: list[str] | None,
    date_from: date | None,
    date_to: date | None,
    sort: str,
    page: int,
    size: int,
    owner_username: str | None = None,
) -> dict[str, Any]:
    """Rank the embedded corpus by pgvector cosine similarity (or recency / gain).

    Args:
        job_store: Job store exposing the SQLAlchemy ``engine`` attribute.
        query_vector: Encoded query vector, or ``None`` when no probe is given.
        models: Optional ``winning_model`` whitelist.
        optimizers: Optional ``optimizer_name`` whitelist.
        optimization_types: Optional ``optimization_type`` whitelist.
        date_from: Inclusive lower bound on ``created_at``.
        date_to: Inclusive upper bound on ``created_at``.
        sort: One of :data:`SEARCH_SORTS`.
        page: 1-indexed page number.
        size: Page size (already clamped).
        owner_username: When set, scope to that user (including private rows)
            instead of the public corpus.

    Returns:
        ``{"results": [...], "total": int, "matched_ids": [...], "search_type": "semantic"}``.
    """
    use_similarity = query_vector is not None and sort == SEARCH_SORT_RELEVANCE

    # INNER JOIN with jobs so deleted/orphan embedding rows can't leak through,
    # and so the status filter is enforced regardless of how the embedding row
    # was written.
    from_sql = (
        "FROM job_embeddings je "
        "INNER JOIN jobs j ON j.optimization_id = je.optimization_id"
    )
    where_parts: list[str] = [
        "j.status = 'success'",
        "je.embedding_summary IS NOT NULL",
    ]
    params: dict[str, Any] = {}
    if owner_username is not None:
        where_parts.append("j.username = :owner_username")
        params["owner_username"] = owner_username
    else:
        where_parts.append("je.is_private = FALSE")
    if models:
        where_parts.append("je.winning_model = ANY(:models)")
        params["models"] = list(models)
    if optimizers:
        where_parts.append("je.optimizer_name = ANY(:optimizers)")
        params["optimizers"] = list(optimizers)
    if optimization_types:
        where_parts.append("je.optimization_type = ANY(:optimization_types)")
        params["optimization_types"] = list(optimization_types)
    if date_from is not None:
        where_parts.append("je.created_at >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        where_parts.append("je.created_at < :date_to_excl")
        params["date_to_excl"] = date_to + timedelta(days=1)

    where_sql = " AND ".join(where_parts)

    if use_similarity:
        params["query_vec"] = _vector_literal(query_vector)  # type: ignore[arg-type]
        order_sql = "je.embedding_summary <=> CAST(:query_vec AS vector) ASC, je.created_at DESC"
        relevance_sql = "1 - (je.embedding_summary <=> CAST(:query_vec AS vector))"
    elif sort == SEARCH_SORT_GAIN:
        order_sql = (
            "(COALESCE(je.optimized_metric, 0) - COALESCE(je.baseline_metric, 0)) DESC NULLS LAST, "
            "je.created_at DESC"
        )
        relevance_sql = "NULL::float"
    else:
        order_sql = "je.created_at DESC, je.optimization_id DESC"
        relevance_sql = "NULL::float"

    engine = job_store.engine
    with Session(engine) as session:
        # Pull every match in rank order, then dedup by compare_fingerprint in
        # Python — same logic as the projection so the result count matches
        # what the map shows.
        ranked_rows = (
            session.execute(
                text(
                    "SELECT je.optimization_id, j.payload_overview, "
                    f"{relevance_sql} AS relevance "
                    f"{from_sql} "
                    f"WHERE {where_sql} "
                    f"ORDER BY {order_sql} "
                    "LIMIT :ids_cap"
                ),
                {**params, "ids_cap": SEARCH_MATCHED_IDS_CAP},
            )
            .mappings()
            .all()
        )

        leaders, relevance_by_id = _dedup_ranked_rows(ranked_rows)
        total = len(leaders)
        offset = (page - 1) * size
        page_ids = leaders[offset : offset + size]

        page_rows: list[Mapping[str, Any]] = []
        if page_ids:
            # COALESCE the user-renamable fields against payload_overview so a
            # job that was renamed after embedding shows the current name in
            # the search results, not the stale embedded snapshot.
            page_rows = (
                session.execute(
                    text(
                        "SELECT je.optimization_id, je.optimization_type, je.winning_model, "
                        "je.baseline_metric, je.optimized_metric, je.summary_text, "
                        f"COALESCE(je.task_name, j.payload_overview->>'{PAYLOAD_OVERVIEW_NAME}') AS task_name, "
                        "je.module_name, je.optimizer_name, je.created_at "
                        f"{from_sql} "
                        "WHERE je.optimization_id = ANY(:page_ids)"
                    ),
                    {"page_ids": page_ids},
                )
                .mappings()
                .all()
            )

    by_id = {row["optimization_id"]: row for row in page_rows}
    results: list[dict[str, Any]] = []
    for opt_id in page_ids:
        row = by_id.get(opt_id)
        if row is None:
            continue
        summary = row["summary_text"]
        if isinstance(summary, str) and len(summary) > SUMMARY_TEXT_MAX:
            summary = summary[:SUMMARY_TEXT_MAX].rstrip() + "…"
        results.append(
            {
                "optimization_id": opt_id,
                "optimization_type": row["optimization_type"],
                "winning_model": row["winning_model"],
                "baseline_metric": _as_float(row["baseline_metric"]),
                "optimized_metric": _as_float(row["optimized_metric"]),
                "summary_text": summary,
                "task_name": row["task_name"],
                "module_name": row["module_name"],
                "optimizer_name": row["optimizer_name"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "relevance": relevance_by_id.get(opt_id),
            }
        )
    return {
        "results": results,
        "total": total,
        "matched_ids": leaders,
        "search_type": "semantic",
    }


# Lexical text matched against the union of these fields. The COALESCE order
# matters: embedded fields are authoritative (post-optimization winners,
# canonical summaries) and fall back to payload_overview values for jobs
# that haven't been embedded yet.
_LEXICAL_HAYSTACK_SQL = (
    "lower(coalesce("
    "  coalesce(je.task_name, j.payload_overview->>'name', '') || ' ' || "
    "  coalesce(je.summary_text, '') || ' ' || "
    "  coalesce(j.payload_overview->>'description', '') || ' ' || "
    "  coalesce(je.optimizer_name, j.payload_overview->>'optimizer_name', '') || ' ' || "
    "  coalesce(je.winning_model, j.payload_overview->>'model_name', '') || ' ' || "
    "  coalesce(je.module_name, j.payload_overview->>'module_name', ''), "
    "''))"
)


def _lexical_tokens(query: str) -> list[str]:
    """Split a free-text query into searchable lowercase tokens.

    Single-character tokens are dropped — they're either accidental
    whitespace artifacts or too noisy to be useful for ILIKE matching at
    the corpus sizes we expect.

    Args:
        query: Raw query string from the request.

    Returns:
        Lowercase tokens, deduped while preserving first-seen order.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in query.split():
        token = raw.strip().lower()
        if len(token) < 2:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _search_lexical(
    *,
    job_store: Any,
    query: str,
    models: list[str] | None,
    optimizers: list[str] | None,
    optimization_types: list[str] | None,
    date_from: date | None,
    date_to: date | None,
    sort: str,
    page: int,
    size: int,
    owner_username: str | None = None,
) -> dict[str, Any]:
    """Lexical ILIKE search across the corpus.

    Walks ``jobs LEFT JOIN job_embeddings`` so unembedded successful jobs
    are still returned — their text comes from ``payload_overview`` rather
    than the LLM-authored summary, and structured filters fall back to the
    payload values when the embedding row is missing.

    The relevance sort is degraded to recency, since lexical matching has
    no continuous similarity score and emitting a synthetic one would be
    misleading on the result badge.

    Args:
        job_store: Job store exposing the SQLAlchemy ``engine`` attribute.
        query: Pre-trimmed query string (empty string allowed).
        models: Optional model whitelist.
        optimizers: Optional optimizer whitelist.
        optimization_types: Optional ``optimization_type`` whitelist.
        date_from: Inclusive lower bound on ``created_at``.
        date_to: Inclusive upper bound on ``created_at``.
        sort: One of :data:`SEARCH_SORTS` (relevance is treated as recent).
        page: 1-indexed page number.
        size: Page size (already clamped).
        owner_username: When set, scope to that user (including private rows)
            instead of the public corpus.

    Returns:
        ``{"results": [...], "total": int, "matched_ids": [...], "search_type": "lexical"}``.
    """
    where_parts: list[str] = ["j.status = 'success'"]
    params: dict[str, Any] = {}
    if owner_username is not None:
        where_parts.append("j.username = :owner_username")
        params["owner_username"] = owner_username
    else:
        # Private flag may live in the embedding row OR the payload overview
        # (for jobs that haven't been embedded yet). Treat either as private.
        where_parts.append(
            "NOT COALESCE(je.is_private, "
            "(j.payload_overview->>'is_private')::boolean, FALSE)"
        )

    if models:
        where_parts.append(
            f"COALESCE(je.winning_model, j.payload_overview->>'{PAYLOAD_OVERVIEW_MODEL_NAME}') "
            "= ANY(:models)"
        )
        params["models"] = list(models)
    if optimizers:
        where_parts.append(
            f"COALESCE(je.optimizer_name, j.payload_overview->>'{PAYLOAD_OVERVIEW_OPTIMIZER_NAME}') "
            "= ANY(:optimizers)"
        )
        params["optimizers"] = list(optimizers)
    if optimization_types:
        where_parts.append(
            "COALESCE(je.optimization_type, j.optimization_type) = ANY(:optimization_types)"
        )
        params["optimization_types"] = list(optimization_types)
    if date_from is not None:
        where_parts.append("j.created_at >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        where_parts.append("j.created_at < :date_to_excl")
        params["date_to_excl"] = date_to + timedelta(days=1)

    tokens = _lexical_tokens(query)
    for idx, token in enumerate(tokens):
        param_name = f"tok_{idx}"
        where_parts.append(f"{_LEXICAL_HAYSTACK_SQL} LIKE :{param_name}")
        params[param_name] = f"%{token}%"

    where_sql = " AND ".join(where_parts)

    if sort == SEARCH_SORT_GAIN:
        order_sql = (
            "(COALESCE(je.optimized_metric, 0) - COALESCE(je.baseline_metric, 0)) DESC NULLS LAST, "
            "j.created_at DESC, j.optimization_id DESC"
        )
    else:
        order_sql = "j.created_at DESC, j.optimization_id DESC"

    select_cols = (
        "j.optimization_id, "
        "COALESCE(je.optimization_type, j.optimization_type) AS optimization_type, "
        f"COALESCE(je.winning_model, j.payload_overview->>'{PAYLOAD_OVERVIEW_MODEL_NAME}') "
        "AS winning_model, "
        "je.baseline_metric, je.optimized_metric, "
        "je.summary_text, "
        f"COALESCE(je.task_name, j.payload_overview->>'{PAYLOAD_OVERVIEW_NAME}') AS task_name, "
        f"COALESCE(je.module_name, j.payload_overview->>'{PAYLOAD_OVERVIEW_MODULE_NAME}') "
        "AS module_name, "
        f"COALESCE(je.optimizer_name, j.payload_overview->>'{PAYLOAD_OVERVIEW_OPTIMIZER_NAME}') "
        "AS optimizer_name, "
        "j.created_at, "
        f"j.payload_overview->>'{PAYLOAD_OVERVIEW_DESCRIPTION}' AS task_description"
    )

    engine = job_store.engine
    with Session(engine) as session:
        # Pull every match in rank order, then dedup by compare_fingerprint in
        # Python — same logic as the projection so the result count matches
        # what the map shows.
        ranked_rows = (
            session.execute(
                text(
                    "SELECT j.optimization_id, j.payload_overview, "
                    "NULL::float AS relevance "
                    "FROM jobs j "
                    "LEFT JOIN job_embeddings je ON je.optimization_id = j.optimization_id "
                    f"WHERE {where_sql} "
                    f"ORDER BY {order_sql} "
                    "LIMIT :ids_cap"
                ),
                {**params, "ids_cap": SEARCH_MATCHED_IDS_CAP},
            )
            .mappings()
            .all()
        )

        leaders, _relevance_by_id = _dedup_ranked_rows(ranked_rows)
        total = len(leaders)
        offset = (page - 1) * size
        page_ids = leaders[offset : offset + size]

        page_rows: list[Mapping[str, Any]] = []
        if page_ids:
            page_rows = (
                session.execute(
                    text(
                        f"SELECT {select_cols} FROM jobs j "
                        "LEFT JOIN job_embeddings je ON je.optimization_id = j.optimization_id "
                        "WHERE j.optimization_id = ANY(:page_ids)"
                    ),
                    {"page_ids": page_ids},
                )
                .mappings()
                .all()
            )

    by_id = {row["optimization_id"]: row for row in page_rows}
    results: list[dict[str, Any]] = []
    for opt_id in page_ids:
        row = by_id.get(opt_id)
        if row is None:
            continue
        # Prefer the LLM-authored summary; fall back to the user-supplied
        # task description so unembedded rows still have something to render
        # in the result snippet.
        summary = row["summary_text"] or row.get("task_description")
        if isinstance(summary, str) and len(summary) > SUMMARY_TEXT_MAX:
            summary = summary[:SUMMARY_TEXT_MAX].rstrip() + "…"
        results.append(
            {
                "optimization_id": opt_id,
                "optimization_type": row["optimization_type"],
                "winning_model": row["winning_model"],
                "baseline_metric": _as_float(row["baseline_metric"]),
                "optimized_metric": _as_float(row["optimized_metric"]),
                "summary_text": summary,
                "task_name": row["task_name"],
                "module_name": row["module_name"],
                "optimizer_name": row["optimizer_name"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "relevance": None,
            }
        )
    return {
        "results": results,
        "total": total,
        "matched_ids": leaders,
        "search_type": "lexical",
    }
