"""Public dashboard aggregator for the anonymous /explore page (PER-11 Feature B).

Builds the corpus point list that feeds the /explore list view's count,
filters, and model/optimizer options.

1. Fingerprint check — cheap counts plus source/index freshness maxima gate the
   expensive recompute. Same fingerprint = serve cached payload.
2. Bulk fetch — every public success job's lightweight metadata. Heavy
   fields (``signature_code``, ``optimizer_kwargs``, ``metric_name``,
   ``winning_rank``, ``is_recommendable``) are not used by the explore UI
   and are dropped to keep the response focused on searchable metadata.
3. Cache — keyed by fingerprint, 5 min TTL; any indexed refresh changes the
   fingerprint immediately.

No personal information is exposed. ``signature_code`` is dropped from the
bulk response (it is not consumed by the explore page). Jobs flagged
``is_private`` are excluded from both the fingerprint and the bulk fetch,
so they never appear in the corpus payload and do not invalidate the cache
when added.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, bindparam, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import settings
from ..constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_DESCRIPTION,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
)

logger = logging.getLogger(__name__)


# Free-text fields are truncated for the bulk response. Full text is
# only useful when a point is selected — and the truncated text is what
# the tooltip / detail panel header already render.
SUMMARY_TEXT_MAX = 200

_CACHE_TTL_SECONDS = 300
_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {"fingerprint": None, "at": 0.0, "payload": None}

# Explore is a catalog of user-facing optimization jobs, not the worker's
# shared jobs table. Keep this allowlist strict so new internal job types do
# not become publicly discoverable by default. A row with no recorded type
# anywhere predates the column and is a plain run: default to 'run' so it
# stays discoverable, matching the open paths (share.py / _helpers.py) that
# serve it. Distributed grid-pair child rows are scheduling internals of
# their parent grid — excluded here the same way RemoteDBJobStore's
# _top_level_jobs() keeps them out of listings.
_USER_FACING_CORPUS_SQL = (
    "(COALESCE(j.optimization_type, "
    f"j.payload_overview->>'{PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE}', "
    f"'{OPTIMIZATION_TYPE_RUN}') "
    f"IN ('{OPTIMIZATION_TYPE_RUN}', '{OPTIMIZATION_TYPE_GRID_SEARCH}') "
    "AND j.parent_optimization_id IS NULL)"
)

# "Shared with me" scope: restrict to optimizations the caller holds a member
# grant on AND does not own. Mirrors RemoteJobStore.list_jobs_shared_with —
# match on the lowercased grantee with no is_private gate, since the grant
# authorizes access to private runs the caller was explicitly invited to. The
# owner-exclusion makes "shared with me" mean runs *others* shared with the
# caller, never their own, even if a self-grant ever slips into the table.
# ``IS DISTINCT FROM`` is the NULL-safe inequality — it keeps rows whose owner
# column is NULL rather than dropping them the way ``<>`` would.
_SHARED_GRANT_SCOPE_SQL = (
    "j.optimization_id IN ("
    "SELECT optimization_id FROM optimization_share_grants "
    "WHERE grantee_username = :shared_with_username) "
    "AND j.username IS DISTINCT FROM :shared_with_username"
)


def _jobs_metric_sql(key: str) -> str:
    """Build the SQL expression reading one metric off a job's own scores.

    Grid jobs read ``result.best_pair`` first, everything else reads
    ``latest_metrics`` then ``result``. The ``jsonb_typeof`` guard skips
    non-numeric values instead of failing the whole search on one malformed
    row. ``CAST`` spelling (not ``::``) keeps the fragment executable
    on the sqlite test harness.

    Args:
        key: Metric key (``baseline_test_metric`` or ``optimized_test_metric``).

    Returns:
        A SQL expression yielding the metric as a double precision value, or
        NULL when no numeric source exists.
    """
    best_pair = (
        f"CASE WHEN jsonb_typeof(j.result->'best_pair'->'{key}') = 'number' "
        f"THEN CAST(j.result->'best_pair'->>'{key}' AS double precision) END"
    )
    latest = (
        f"CASE WHEN jsonb_typeof(j.latest_metrics->'{key}') = 'number' "
        f"THEN CAST(j.latest_metrics->>'{key}' AS double precision) END"
    )
    result = (
        f"CASE WHEN jsonb_typeof(j.result->'{key}') = 'number' "
        f"THEN CAST(j.result->>'{key}' AS double precision) END"
    )
    return (
        f"CASE WHEN j.payload_overview->>'{PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE}' "
        f"= '{OPTIMIZATION_TYPE_GRID_SEARCH}' "
        f"THEN COALESCE({best_pair}, {latest}) "
        f"ELSE COALESCE({latest}, {result}) END"
    )


_CORPUS_BASELINE_METRIC_SQL = _jobs_metric_sql("baseline_test_metric")
_CORPUS_OPTIMIZED_METRIC_SQL = _jobs_metric_sql("optimized_test_metric")


def _fetch_fingerprint(session: Session) -> str:
    """Cheap content fingerprint over the searchable corpus.

    Used as the cache key. The job completion timestamp makes a resumed
    optimization invalidate the cache even when its row already existed.

    Args:
        session: Active SQLAlchemy session.

    Returns:
        An opaque compact fingerprint containing counts and freshness maxima.
    """
    row = (
        session.execute(
            text(
                "SELECT COUNT(*) AS n, MAX(j.completed_at) AS completed_max_ts, "
                "MAX(j.created_at) AS created_max_ts "
                "FROM jobs j "
                "WHERE j.status = 'success' "
                f"AND {_USER_FACING_CORPUS_SQL} "
                "AND NOT COALESCE((j.payload_overview->>'is_private')::boolean, FALSE)"
            )
        )
        .mappings()
        .first()
    )
    n = int(row["n"]) if row else 0
    completed_ts = row["completed_max_ts"] if row else None
    created_ts = row["created_max_ts"] if row else None
    completed = completed_ts.isoformat() if completed_ts else "none"
    created = created_ts.isoformat() if created_ts else "none"
    return f"{n}|{completed}|{created}"


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


def _fetch_corpus_points(session: Session) -> list[dict[str, Any]]:
    """Return every public success-state job as a corpus point.

    Drives the /explore list view's corpus count, filters, and
    model/optimizer options, read straight off ``payload_overview``.

    Args:
        session: An open SQLAlchemy session bound to the job-store engine.

    Returns:
        A list of point dicts carrying the metadata the /explore payload
        exposes; heavy fields (signature_code, optimizer_kwargs,
        metric_name) are omitted.
    """
    rows = (
        session.execute(
            text(
                "SELECT j.optimization_id, "
                "j.optimization_type AS optimization_type, "
                f"j.payload_overview->>'{PAYLOAD_OVERVIEW_MODEL_NAME}' "
                "AS winning_model, "
                f"{_CORPUS_BASELINE_METRIC_SQL} AS baseline_metric, "
        f"{_CORPUS_OPTIMIZED_METRIC_SQL} AS optimized_metric, "
                f"j.payload_overview->>'{PAYLOAD_OVERVIEW_NAME}' AS task_name, "
                f"j.payload_overview->>'{PAYLOAD_OVERVIEW_MODULE_NAME}' "
                "AS module_name, "
                f"j.payload_overview->>'{PAYLOAD_OVERVIEW_OPTIMIZER_NAME}' "
                "AS optimizer_name, "
                "j.created_at, "
                f"j.payload_overview->>'{PAYLOAD_OVERVIEW_DESCRIPTION}' AS task_description "
                "FROM jobs j "
                "WHERE j.status = 'success' "
                f"AND {_USER_FACING_CORPUS_SQL} "
                "AND NOT COALESCE((j.payload_overview->>'is_private')::boolean, FALSE) "
                "ORDER BY j.created_at DESC, j.optimization_id DESC "
            )
        )
        .mappings()
        .all()
    )
    points: list[dict[str, Any]] = []
    for row in rows:
        summary = row["task_description"]
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
            }
        )
    return points


def fetch_public_dashboard(*, job_store: Any) -> dict[str, Any]:
    """Return the public corpus point list for ``GET /dashboard/public``.

    Cached by content fingerprint with a 5 min TTL so the corpus count,
    filters, and model/optimizer options the /explore list view derives
    aren't recomputed per request.

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

        payload = {"points": _fetch_corpus_points(session)}
        with _LOCK:
            _CACHE["fingerprint"] = fingerprint
            _CACHE["at"] = now
            _CACHE["payload"] = payload
        return payload


def invalidate_public_dashboard_cache() -> None:
    """Force the next ``fetch_public_dashboard`` call to recompute."""
    with _LOCK:
        _CACHE["fingerprint"] = None
        _CACHE["at"] = 0.0
        _CACHE["payload"] = None


# Each facet dimension is a column of the scoped corpus CTE plus the name of
# the bound list parameter that filters it, so one loop can build "all filters
# except this dimension's own" for every dimension.
_FACET_DIMENSIONS: tuple[tuple[str, str, str], ...] = (
    ("models", "model", "models"),
    ("optimizers", "optimizer", "optimizers"),
    ("modules", "module", "modules"),
    ("types", "run_type", "optimization_types"),
)

FACET_LIMIT_DEFAULT = 8
FACET_LIMIT_MAX = 50


def _facet_like_pattern(value_query: str) -> str:
    """Turn a free-text facet search into a substring ``ILIKE`` pattern.

    Args:
        value_query: The user's (already non-blank) search text.

    Returns:
        ``%text%`` with LIKE metacharacters escaped so a literal ``%`` or
        ``_`` in a model id matches itself rather than anything.
    """
    return "%" + re.sub(r"([\\%_])", r"\\\1", value_query.strip()) + "%"


def fetch_corpus_facets(
    *,
    job_store: Any,
    owner_username: str | None = None,
    shared_with_username: str | None = None,
    models: list[str] | None = None,
    optimizers: list[str] | None = None,
    optimization_types: list[str] | None = None,
    modules: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    value_query: str | None = None,
    limit: int = FACET_LIMIT_DEFAULT,
    dimension: str | None = None,
) -> dict[str, Any]:
    """Return the busiest filter values per dimension in one corpus, with counts.

    Backs ``GET /dashboard/facets`` so each /explore tab lists the filter
    options drawn from its OWN scope — the mine tab surfaces a user's private
    react runs, not just whatever appears in the public archive. Counts are
    conjunctive in the usual faceted-navigation sense: a value's count is the
    number of runs it would leave when combined with every *other* active
    filter, while its own dimension's selection is ignored (selections inside
    a dimension are OR'd, so applying them would zero out every unselected
    sibling). The free-text query is deliberately not part of the context.

    A dimension can hold thousands of distinct values (every model id ever
    optimized against), so no dimension is ever returned in full: each is
    capped at ``limit`` values ranked by contextual count, values the other
    filters rule out (count 0) are dropped rather than padded in, and the
    number of distinct values still available is reported separately so the
    UI can say "top 8 of 1,240" and offer search for the rest. ``value_query``
    is that search: a case-insensitive substring match on the raw value.
    The UI opens one dimension's picker at a time, so ``dimension`` restricts
    the work to that dimension; the others come back empty with a zero total.

    The scope predicate and the ``payload_overview`` derivation mirror :func:`_fetch_corpus_points` and :func:`_search_lexical`
    exactly, so every value returned here lines up with a run the same scope
    can actually filter to.

    Args:
        job_store: A store exposing a SQLAlchemy ``engine`` attribute.
        owner_username: When set, scope to that user's own jobs (including
            private rows) instead of the public corpus.
        shared_with_username: When set (and ``owner_username`` is not), scope to
            jobs shared with that user via a member grant.
        models: Active model filter, or ``None`` / empty for no filter.
        optimizers: Active optimizer / engine filter.
        optimization_types: Active run-type filter.
        modules: Active DSPy module filter.
        date_from: Inclusive lower bound on ``created_at`` (date precision).
        date_to: Inclusive upper bound on ``created_at`` (date precision).
        value_query: Optional substring to match values against; blank means
            no restriction.
        limit: Maximum values returned per dimension (``1..FACET_LIMIT_MAX``).
        dimension: One of ``models`` / ``optimizers`` / ``modules`` / ``types``
            to compute only that dimension, or ``None`` for all four.

    Returns:
        ``{"models": [...], "optimizers": [...], "modules": [...], "types": [...],
        "totals": {"models": int, ...}}`` — each list holds up to ``limit``
        ``{"value": str, "count": int}`` dicts with ``count > 0``, ordered by
        count descending then value, and ``totals`` gives the number of
        distinct values with a positive count per dimension (so a total larger
        than the list length means there is more to search for).

    Raises:
        ValueError: When ``dimension`` names no facet dimension.
    """
    if dimension is not None and dimension not in {name for name, _, _ in _FACET_DIMENSIONS}:
        raise ValueError(f"unknown facet dimension: {dimension!r}")
    params: dict[str, Any] = {}
    if owner_username is not None:
        scope_sql = "j.username = :owner_username"
        params["owner_username"] = owner_username
    elif shared_with_username is not None:
        scope_sql = _SHARED_GRANT_SCOPE_SQL
        params["shared_with_username"] = shared_with_username
    else:
        scope_sql = "NOT COALESCE((j.payload_overview->>'is_private')::boolean, FALSE)"
    date_parts: list[str] = []
    if date_from is not None:
        date_parts.append("AND j.created_at >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        date_parts.append("AND j.created_at < :date_to_excl")
        params["date_to_excl"] = date_to + timedelta(days=1)

    active: dict[str, list[str]] = {}
    for key, values in (
        ("models", models),
        ("optimizers", optimizers),
        ("modules", modules),
        ("optimization_types", optimization_types),
    ):
        if values:
            active[key] = list(values)
            params[key] = list(values)

    # Legacy rows predate the type column everywhere; they are plain runs
    # (see ``_USER_FACING_CORPUS_SQL``), so they count under 'run' rather
    # than vanishing from the type facet.
    corpus_cte = (
        "WITH corpus AS ("
        "SELECT "
        f"j.payload_overview->>'{PAYLOAD_OVERVIEW_MODEL_NAME}' "
        "AS model, "
        f"j.payload_overview->>'{PAYLOAD_OVERVIEW_OPTIMIZER_NAME}' "
        "AS optimizer, "
        f"j.payload_overview->>'{PAYLOAD_OVERVIEW_MODULE_NAME}' "
        "AS module, "
        "COALESCE(j.optimization_type, "
        f"j.payload_overview->>'{PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE}', "
        f"'{OPTIMIZATION_TYPE_RUN}') AS run_type "
        "FROM jobs j "
        f"WHERE j.status = 'success' AND {_USER_FACING_CORPUS_SQL} AND {scope_sql} "
        + " ".join(date_parts)
        + ")"
    )
    params["facet_limit"] = max(1, min(int(limit), FACET_LIMIT_MAX))
    match_sql = ""
    if value_query and value_query.strip():
        params["value_pattern"] = _facet_like_pattern(value_query)
        match_sql = " AND {column} ILIKE :value_pattern"

    selects: list[str] = []
    for name, column, param in _FACET_DIMENSIONS:
        if dimension is not None and name != dimension:
            continue
        others = [
            f"{other_column} = ANY(:{other_param})"
            for _, other_column, other_param in _FACET_DIMENSIONS
            if other_param != param and other_param in active
        ]
        context_sql = " AND ".join(others) if others else "TRUE"
        member_sql = f"{column} <> ''" + match_sql.format(column=column)
        count_sql = f"COUNT(*) FILTER (WHERE {context_sql})"
        selects.append(
            f"(SELECT '{name}' AS dim, {column} AS value, {count_sql} AS n "
            f"FROM corpus WHERE {member_sql} GROUP BY {column} "
            f"HAVING {count_sql} > 0 ORDER BY n DESC, value ASC LIMIT :facet_limit)"
        )
        # A NULL value row carries the dimension's distinct-value total, so
        # the list and its "of N" arrive in the same round-trip.
        selects.append(
            f"(SELECT '{name}' AS dim, NULL AS value, COUNT(DISTINCT {column}) AS n "
            f"FROM corpus WHERE {member_sql} AND {context_sql})"
        )
    sql = corpus_cte + " " + " UNION ALL ".join(selects)

    facets: dict[str, Any] = {name: [] for name, _, _ in _FACET_DIMENSIONS}
    totals: dict[str, int] = {name: 0 for name, _, _ in _FACET_DIMENSIONS}
    with Session(job_store.engine) as session:
        rows = session.execute(text(sql), params).mappings().all()
    for row in rows:
        if row["value"] is None:
            totals[str(row["dim"])] = int(row["n"])
        else:
            facets[str(row["dim"])].append({"value": str(row["value"]), "count": int(row["n"])})
    # UNION ALL does not promise to keep each branch's ORDER BY intact.
    for options in facets.values():
        options.sort(key=lambda option: (-option["count"], option["value"]))
    facets["totals"] = totals
    return facets


# ``recent`` orders newest-first, ``oldest`` oldest-first — the two date
# directions the UI exposes as "Newest"/"Oldest".
SEARCH_SORT_RELEVANCE = "relevance"
SEARCH_SORT_RECENT = "recent"
SEARCH_SORT_OLDEST = "oldest"
SEARCH_SORTS = (SEARCH_SORT_RELEVANCE, SEARCH_SORT_RECENT, SEARCH_SORT_OLDEST)

SEARCH_PAGE_SIZE_DEFAULT = 30
SEARCH_PAGE_SIZE_MAX = 50
SEARCH_MATCHED_IDS_CAP = 5_000

POPULAR_QUERIES_LIMIT_DEFAULT = 8
POPULAR_QUERIES_WINDOW_DAYS_DEFAULT = 30
_SEARCH_QUERY_LOG_MIN_LEN = 2
_SEARCH_QUERY_LOG_MAX_LEN = 200


def _normalize_query_for_log(query: str) -> str | None:
    """Normalize a query for trending storage, or None when it isn't worth logging.

    Lowercases, collapses internal whitespace, and caps length so trivially
    different spellings of the same search coalesce into one trending bucket.

    Args:
        query: The raw (already caller-trimmed) public query string.

    Returns:
        The normalized query, or ``None`` when it is shorter than
        :data:`_SEARCH_QUERY_LOG_MIN_LEN` and thus too noisy to count.
    """
    normalized = " ".join(query.split()).lower()[:_SEARCH_QUERY_LOG_MAX_LEN]
    if len(normalized) < _SEARCH_QUERY_LOG_MIN_LEN:
        return None
    return normalized


def record_public_search_query(job_store: Any, query: str) -> None:
    """Record one public search query for trending, best-effort.

    Called only on an explicit commit (Enter or opening a result) via
    ``POST /dashboard/search/log`` — never on every debounced keystroke — so
    half-typed prefixes don't pollute the trending counts. Writes a single
    anonymous row to ``search_query_log`` and never raises: logging is a side
    effect and must not break the caller when the store has no engine (test
    stubs) or the insert fails.

    Args:
        job_store: Job store exposing a SQLAlchemy ``engine`` attribute.
        query: The public query to record (normalized internally).
    """
    normalized = _normalize_query_for_log(query)
    if normalized is None:
        return
    try:
        with Session(job_store.engine) as session:
            session.execute(
                text(
                    "INSERT INTO search_query_log (query_text, created_at) "
                    "VALUES (:q, :ts)"
                ).bindparams(bindparam("ts", type_=DateTime(timezone=True))),
                {"q": normalized, "ts": datetime.now(UTC)},
            )
            session.commit()
    except Exception as exc:
        logger.debug("search query logging skipped: %s", exc)


def fetch_popular_queries(
    job_store: Any,
    *,
    limit: int = POPULAR_QUERIES_LIMIT_DEFAULT,
    window_days: int = POPULAR_QUERIES_WINDOW_DAYS_DEFAULT,
) -> list[dict[str, Any]]:
    """Return the most frequent public search queries over a recent window.

    Aggregates ``search_query_log`` into a top-N ranking by occurrence count,
    most popular first. Best-effort: returns an empty list when the store has
    no engine or the aggregate fails, so a missing/empty log never breaks the
    /explore zero-state (the UI falls back to corpus-frequency terms).

    Args:
        job_store: Job store exposing a SQLAlchemy ``engine`` attribute.
        limit: Maximum number of queries to return (clamped to ``[1, 50]``).
        window_days: Only count queries logged within this many days.

    Returns:
        A list of ``{"query": str, "count": int}`` dicts, ranked by count
        descending then query text.
    """
    limit = max(1, min(50, limit))
    cutoff = datetime.now(UTC) - timedelta(days=max(1, window_days))
    try:
        with Session(job_store.engine) as session:
            rows = session.execute(
                text(
                    "SELECT query_text, COUNT(*) AS n "
                    "FROM search_query_log "
                    "WHERE created_at >= :cutoff "
                    "GROUP BY query_text "
                    "ORDER BY n DESC, query_text ASC "
                    "LIMIT :limit"
                ).bindparams(bindparam("cutoff", type_=DateTime(timezone=True))),
                {"cutoff": cutoff, "limit": limit},
            ).all()
    except Exception as exc:
        logger.debug("popular query fetch failed: %s", exc)
        return []
    return [{"query": row[0], "count": int(row[1])} for row in rows]


def search_optimizations(
    *,
    job_store: Any,
    query: str | None,
    models: list[str] | None = None,
    optimizers: list[str] | None = None,
    optimization_types: list[str] | None = None,
    tasks: list[str] | None = None,
    modules: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: str = SEARCH_SORT_RELEVANCE,
    page: int = 1,
    size: int = SEARCH_PAGE_SIZE_DEFAULT,
    owner_username: str | None = None,
    shared_with_username: str | None = None,
) -> dict[str, Any]:
    """Search the optimization corpus with BM25 when available, ILIKE otherwise.

    BM25 serves a relevance-sorted query when ``search_bm25_enabled`` is on and
    the store has the ``pg_search`` index; every other request, and any BM25
    failure, goes to the ILIKE lexical search. Both paths support the same
    structured filters and paging. Lexical results have ``relevance = None``
    since there's no continuous similarity score to surface.

    Args:
        job_store: Job store exposing the SQLAlchemy ``engine`` attribute.
        query: Free-text query or ``None``.
        models: Optional model whitelist (matches the payload-overview model name).
        optimizers: Optional optimizer whitelist.
        optimization_types: Optional ``optimization_type`` whitelist.
        tasks: Optional ``task_name`` whitelist (matched against the same
            payload-overview value the corpus options derive from).
        modules: Optional ``module_name`` whitelist (matched against the same
            payload-overview value the corpus options derive from).
        date_from: Inclusive lower bound on ``created_at`` (date precision).
        date_to: Inclusive upper bound on ``created_at`` (date precision).
        sort: One of :data:`SEARCH_SORTS`.
        page: 1-indexed page number.
        size: Page size; clamped to ``[1, SEARCH_PAGE_SIZE_MAX]``.
        owner_username: When set, scope the search to jobs owned by this user
            (including their private rows) instead of the public corpus. The
            caller is responsible for verifying the requested owner matches the
            authenticated session.
        shared_with_username: When set (and ``owner_username`` is not), scope the
            search to jobs shared with this user via a member grant — runs they
            were invited to but do not own, including private ones the grant
            authorizes. The caller verifies the requested user is the session.

    Returns:
        ``{"results": [...], "total": int, "matched_ids": [...], "search_type": str}``,
        where ``search_type`` is ``"bm25"`` or ``"lexical"`` depending on
        which dispatch branch served the query.
    """
    if sort not in SEARCH_SORTS:
        sort = SEARCH_SORT_RELEVANCE
    page = max(1, page)
    size = max(1, min(SEARCH_PAGE_SIZE_MAX, size))

    query_clean = (query or "").strip()

    # BM25 ranks by relevance, so it only serves the relevance sort with a
    # query present; explicit recent/oldest sorts keep the ILIKE path's
    # ordering. Any pg_search failure degrades to the ILIKE search below.
    if (
        query_clean
        and sort == SEARCH_SORT_RELEVANCE
        and settings.search_bm25_enabled
        and getattr(job_store, "bm25_search_enabled", False)
    ):
        try:
            return _search_bm25(
                job_store=job_store,
                query=query_clean,
                models=models,
                optimizers=optimizers,
                optimization_types=optimization_types,
                tasks=tasks,
                modules=modules,
                date_from=date_from,
                date_to=date_to,
                page=page,
                size=size,
                owner_username=owner_username,
                shared_with_username=shared_with_username,
            )
        except SQLAlchemyError as exc:
            logger.warning(
                "BM25 search failed (%s); falling back to ILIKE lexical search.", exc
            )
    return _search_lexical(
        job_store=job_store,
        query=query_clean,
        models=models,
        optimizers=optimizers,
        optimization_types=optimization_types,
        tasks=tasks,
        modules=modules,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        page=page,
        size=size,
        owner_username=owner_username,
        shared_with_username=shared_with_username,
    )


# Lexical text matched against the union of these payload_overview fields.
_LEXICAL_HAYSTACK_SQL = (
    "lower(coalesce("
    "  coalesce(j.payload_overview->>'name', '') || ' ' || "
    "  coalesce(j.payload_overview->>'description', '') || ' ' || "
    "  coalesce(j.payload_overview->>'optimizer_name', '') || ' ' || "
    "  coalesce(j.payload_overview->>'model_name', '') || ' ' || "
    "  coalesce(j.payload_overview->>'module_name', ''), "
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
    tasks: list[str] | None,
    modules: list[str] | None,
    date_from: date | None,
    date_to: date | None,
    sort: str,
    page: int,
    size: int,
    owner_username: str | None = None,
    shared_with_username: str | None = None,
) -> dict[str, Any]:
    """Lexical ILIKE search across the corpus.

    Text and structured filters read ``payload_overview``, and each row's
    score pair comes from the job's own ``latest_metrics`` / ``result`` values.

    The relevance sort is degraded to recency, since lexical matching has
    no continuous similarity score and emitting a synthetic one would be
    misleading on the result badge.

    Args:
        job_store: Job store exposing the SQLAlchemy ``engine`` attribute.
        query: Pre-trimmed query string (empty string allowed).
        models: Optional model whitelist.
        optimizers: Optional optimizer whitelist.
        optimization_types: Optional ``optimization_type`` whitelist.
        tasks: Optional ``task_name`` whitelist.
        modules: Optional ``module_name`` whitelist.
        date_from: Inclusive lower bound on ``created_at``.
        date_to: Inclusive upper bound on ``created_at``.
        sort: One of :data:`SEARCH_SORTS` (relevance is treated as recent).
        page: 1-indexed page number.
        size: Page size (already clamped).
        owner_username: When set, scope to that user (including private rows)
            instead of the public corpus.
        shared_with_username: When set (and ``owner_username`` is not), scope to
            jobs shared with that user via a member grant.

    Returns:
        ``{"results": [...], "total": int, "matched_ids": [...], "search_type": "lexical"}``.
    """
    where_parts: list[str] = ["j.status = 'success'", _USER_FACING_CORPUS_SQL]
    params: dict[str, Any] = {}
    if owner_username is not None:
        where_parts.append("j.username = :owner_username")
        params["owner_username"] = owner_username
    elif shared_with_username is not None:
        where_parts.append(_SHARED_GRANT_SCOPE_SQL)
        params["shared_with_username"] = shared_with_username
    else:
        where_parts.append(
            "NOT COALESCE((j.payload_overview->>'is_private')::boolean, FALSE)"
        )

    if models:
        where_parts.append(
            f"j.payload_overview->>'{PAYLOAD_OVERVIEW_MODEL_NAME}' "
            "= ANY(:models)"
        )
        params["models"] = list(models)
    if optimizers:
        where_parts.append(
            f"j.payload_overview->>'{PAYLOAD_OVERVIEW_OPTIMIZER_NAME}' "
            "= ANY(:optimizers)"
        )
        params["optimizers"] = list(optimizers)
    if optimization_types:
        where_parts.append(
            "j.optimization_type = ANY(:optimization_types)"
        )
        params["optimization_types"] = list(optimization_types)
    # Same COALESCE expressions as the corpus options (``_fetch_corpus_points``)
    # so a picked chip's value always matches.
    if tasks:
        where_parts.append(
            f"j.payload_overview->>'{PAYLOAD_OVERVIEW_NAME}' "
            "= ANY(:tasks)"
        )
        params["tasks"] = list(tasks)
    if modules:
        where_parts.append(
            f"j.payload_overview->>'{PAYLOAD_OVERVIEW_MODULE_NAME}' "
            "= ANY(:modules)"
        )
        params["modules"] = list(modules)
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

    if sort == SEARCH_SORT_OLDEST:
        order_sql = "j.created_at ASC, j.optimization_id ASC"
    else:
        order_sql = "j.created_at DESC, j.optimization_id DESC"

    select_cols = (
        "j.optimization_id, "
        "j.optimization_type AS optimization_type, "
        f"j.payload_overview->>'{PAYLOAD_OVERVIEW_MODEL_NAME}' "
        "AS winning_model, "
        f"{_CORPUS_BASELINE_METRIC_SQL} AS baseline_metric, "
        f"{_CORPUS_OPTIMIZED_METRIC_SQL} AS optimized_metric, "
        f"j.payload_overview->>'{PAYLOAD_OVERVIEW_NAME}' AS task_name, "
        f"j.payload_overview->>'{PAYLOAD_OVERVIEW_MODULE_NAME}' "
        "AS module_name, "
        f"j.payload_overview->>'{PAYLOAD_OVERVIEW_OPTIMIZER_NAME}' "
        "AS optimizer_name, "
        "j.created_at, "
        f"j.payload_overview->>'{PAYLOAD_OVERVIEW_DESCRIPTION}' AS task_description"
    )

    engine = job_store.engine
    with Session(engine) as session:
        # Pull every match in rank order up to the id cap so total and
        # matched_ids cover the full result set, then page in Python.
        ranked_rows = (
            session.execute(
                text(
                    "SELECT j.optimization_id, j.payload_overview, "
                    "NULL::float AS relevance "
                    "FROM jobs j "
                    f"WHERE {where_sql} "
                    f"ORDER BY {order_sql} "
                    "LIMIT :ids_cap"
                ),
                {**params, "ids_cap": SEARCH_MATCHED_IDS_CAP},
            )
            .mappings()
            .all()
        )

        leaders = [row["optimization_id"] for row in ranked_rows]
        total = len(leaders)
        offset = (page - 1) * size
        page_ids = leaders[offset : offset + size]

        page_rows: list[Mapping[str, Any]] = []
        if page_ids:
            page_rows = (
                session.execute(
                    text(
                        f"SELECT {select_cols} FROM jobs j "
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
        summary = row["task_description"]
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


def _search_bm25(
    *,
    job_store: Any,
    query: str,
    models: list[str] | None,
    optimizers: list[str] | None,
    optimization_types: list[str] | None,
    tasks: list[str] | None,
    modules: list[str] | None,
    date_from: date | None,
    date_to: date | None,
    page: int,
    size: int,
    owner_username: str | None = None,
    shared_with_username: str | None = None,
) -> dict[str, Any]:
    """BM25-ranked lexical search over the jobs payload_overview corpus.

    Mirrors :func:`_search_lexical`'s structured filters and result assembly,
    but ranks by ParadeDB ``paradedb.score`` instead of recency and surfaces a
    real ``relevance`` per row. Requires the ``pg_search`` extension and the
    ``idx_jobs_bm25`` index (created best-effort at store init); the caller only
    routes here when ``job_store.bm25_search_enabled`` is true and wraps the call
    so any failure falls back to :func:`_search_lexical`.

    Args:
        job_store: Job store exposing the SQLAlchemy ``engine`` attribute.
        query: Pre-trimmed, non-empty query string (the BM25 match text).
        models: Optional model whitelist.
        optimizers: Optional optimizer whitelist.
        optimization_types: Optional ``optimization_type`` whitelist.
        tasks: Optional ``task_name`` whitelist.
        modules: Optional ``module_name`` whitelist.
        date_from: Inclusive lower bound on ``created_at``.
        date_to: Inclusive upper bound on ``created_at``.
        page: 1-indexed page number.
        size: Page size (already clamped).
        owner_username: When set, scope to that user (including private rows).
        shared_with_username: When set (and ``owner_username`` is not), scope to
            jobs shared with that user via a member grant.

    Returns:
        ``{"results": [...], "total": int, "matched_ids": [...], "search_type": "bm25"}``.
    """
    where_parts: list[str] = ["j.status = 'success'", _USER_FACING_CORPUS_SQL]
    params: dict[str, Any] = {}
    if owner_username is not None:
        where_parts.append("j.username = :owner_username")
        params["owner_username"] = owner_username
    elif shared_with_username is not None:
        where_parts.append(_SHARED_GRANT_SCOPE_SQL)
        params["shared_with_username"] = shared_with_username
    else:
        where_parts.append(
            "NOT COALESCE((j.payload_overview->>'is_private')::boolean, FALSE)"
        )

    if models:
        where_parts.append(
            f"j.payload_overview->>'{PAYLOAD_OVERVIEW_MODEL_NAME}' "
            "= ANY(:models)"
        )
        params["models"] = list(models)
    if optimizers:
        where_parts.append(
            f"j.payload_overview->>'{PAYLOAD_OVERVIEW_OPTIMIZER_NAME}' "
            "= ANY(:optimizers)"
        )
        params["optimizers"] = list(optimizers)
    if optimization_types:
        where_parts.append(
            "j.optimization_type = ANY(:optimization_types)"
        )
        params["optimization_types"] = list(optimization_types)
    if tasks:
        where_parts.append(
            f"j.payload_overview->>'{PAYLOAD_OVERVIEW_NAME}' "
            "= ANY(:tasks)"
        )
        params["tasks"] = list(tasks)
    if modules:
        where_parts.append(
            f"j.payload_overview->>'{PAYLOAD_OVERVIEW_MODULE_NAME}' "
            "= ANY(:modules)"
        )
        params["modules"] = list(modules)
    if date_from is not None:
        where_parts.append("j.created_at >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        where_parts.append("j.created_at < :date_to_excl")
        params["date_to_excl"] = date_to + timedelta(days=1)

    # BM25 match: @@@ against the indexed payload_overview corpus. paradedb.score
    # then ranks the matched rows. Both require the pg_search bm25 index on jobs.
    where_parts.append("j.payload_overview @@@ :bm25_query")
    params["bm25_query"] = query

    where_sql = " AND ".join(where_parts)

    select_cols = (
        "j.optimization_id, "
        "j.optimization_type AS optimization_type, "
        f"j.payload_overview->>'{PAYLOAD_OVERVIEW_MODEL_NAME}' "
        "AS winning_model, "
        f"{_CORPUS_BASELINE_METRIC_SQL} AS baseline_metric, "
        f"{_CORPUS_OPTIMIZED_METRIC_SQL} AS optimized_metric, "
        f"j.payload_overview->>'{PAYLOAD_OVERVIEW_NAME}' AS task_name, "
        f"j.payload_overview->>'{PAYLOAD_OVERVIEW_MODULE_NAME}' "
        "AS module_name, "
        f"j.payload_overview->>'{PAYLOAD_OVERVIEW_OPTIMIZER_NAME}' "
        "AS optimizer_name, "
        "j.created_at, "
        f"j.payload_overview->>'{PAYLOAD_OVERVIEW_DESCRIPTION}' AS task_description"
    )

    engine = job_store.engine
    with Session(engine) as session:
        ranked_rows = (
            session.execute(
                text(
                    "SELECT j.optimization_id, "
                    "paradedb.score(j.optimization_id) AS relevance "
                    "FROM jobs j "
                    f"WHERE {where_sql} "
                    "ORDER BY relevance DESC, j.created_at DESC, j.optimization_id DESC "
                    "LIMIT :ids_cap"
                ),
                {**params, "ids_cap": SEARCH_MATCHED_IDS_CAP},
            )
            .mappings()
            .all()
        )

        leaders = [row["optimization_id"] for row in ranked_rows]
        relevance_by_id = {
            row["optimization_id"]: _as_float(row.get("relevance")) for row in ranked_rows
        }
        total = len(leaders)
        offset = (page - 1) * size
        page_ids = leaders[offset : offset + size]

        page_rows: list[Mapping[str, Any]] = []
        if page_ids:
            page_rows = (
                session.execute(
                    text(
                        f"SELECT {select_cols} FROM jobs j "
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
        summary = row["task_description"]
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
        "search_type": "bm25",
    }
