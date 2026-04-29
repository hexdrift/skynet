"""Embedding + similarity service for the recommendations feature (PER-11).

Pipeline:

1. After a job finishes successfully, the worker fires
   ``embed_finished_job(optimization_id, job_store)`` on a daemon
   thread.
2. That task: fetches the job payload, asks an LLM for a 2-3 sentence
   task summary, builds a dataset-schema digest, then calls the Jina
   encoder three times (summary, code, schema). The three vectors +
   metadata (user_id, optimization_type, winning_model, winning_rank)
   are upserted into ``job_embeddings``.
3. ``search_similar`` embeds the caller's query (code from
   ``signature_code + metric_code``, schema from
   ``dataset_schema``) and runs a single weighted-fusion SQL query
   against pgvector's cosine operator.

Failures never raise — the recommendation feature is best-effort.
Missing embedder / LLM / pgvector extension all degrade to "skip this
step" and, ultimately, to an empty result list that the endpoint
happily returns.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...config import settings
from ...constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
    PAYLOAD_OVERVIEW_USERNAME,
)
from ...storage.models import JobEmbeddingModel
from .embeddings import get_embedder
from .summarizer import summarize_task

logger = logging.getLogger(__name__)

_WEIGHTS = {"summary": 0.5, "code": 0.3, "schema": 0.2}


def _build_code_text(signature_code: str | None, metric_code: str | None) -> str:
    """Concatenate signature + metric into a single chunk for the 'code' embedding.

    Args:
        signature_code: Source code of the user's DSPy signature.
        metric_code: Source code of the user's metric function.

    Returns:
        A single text block prefixed with section headers, suitable for
        passing to the embedder. May be empty when both inputs are blank.
    """
    parts = []
    if signature_code and signature_code.strip():
        parts.append(f"# Signature\n{signature_code.strip()}")
    if metric_code and metric_code.strip():
        parts.append(f"# Metric\n{metric_code.strip()}")
    return "\n\n".join(parts)


def _build_schema_text(dataset: list[dict[str, Any]] | None, column_mapping: dict[str, Any] | None) -> str:
    """Produce a compact text description of dataset columns + their roles.

    Sampling a handful of rows (not the full dataset) keeps the embedding
    signal focused on structure rather than content drift. The role
    annotation (input / output) lets similar tasks match even when column
    names differ.

    Args:
        dataset: Submitted dataset rows; only the first row is sampled.
        column_mapping: Optional ``{"inputs": ..., "outputs": ...}`` map
            used to label each column with its role.

    Returns:
        A multi-line text block describing each column's role, type, and
        a short value preview, or an empty string when no rows are
        provided.
    """
    if not dataset:
        return ""
    inputs = (column_mapping or {}).get("inputs", {}) or {}
    outputs = (column_mapping or {}).get("outputs", {}) or {}
    inputs_set = set(inputs.values()) if isinstance(inputs, dict) else set()
    outputs_set = set(outputs.values()) if isinstance(outputs, dict) else set()
    sample = dataset[0] if dataset else {}
    lines: list[str] = []
    for col in sample:
        role = "input" if col in inputs_set else "output" if col in outputs_set else "ignore"
        value = sample.get(col)
        type_name = type(value).__name__ if value is not None else "null"
        preview = repr(value)[:40] if value is not None else ""
        lines.append(f"{col} ({role}, {type_name}): {preview}")
    return "\n".join(lines)


def _extract_metadata(job: dict[str, Any]) -> tuple[str | None, int | None, str | None]:
    """Return ``(winning_model, winning_rank, optimization_type)`` for a finished job.

    For a ``run`` job the winner is the single configured model (rank=1).
    For a grid search the winner is ``result.best_pair.generation_model``.

    Args:
        job: The job-store record (with ``payload_overview`` and ``result``
            sub-dicts) for a finished optimization.

    Returns:
        A 3-tuple of ``(winning_model, winning_rank, optimization_type)``
        where each entry may be ``None`` when the corresponding field is
        absent from the job record.
    """
    overview = job.get("payload_overview") or {}
    result = job.get("result") or {}
    job_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE)
    if job_type == OPTIMIZATION_TYPE_GRID_SEARCH:
        best = result.get("best_pair") if isinstance(result, dict) else None
        if isinstance(best, dict):
            return best.get("generation_model"), 1, job_type
        return None, None, job_type
    return overview.get(PAYLOAD_OVERVIEW_MODEL_NAME), 1, job_type


def _extract_scores(job: dict[str, Any]) -> tuple[float | None, float | None]:
    """Return ``(baseline_metric, optimized_metric)`` for a finished job.

    Run jobs store the pair directly in ``latest_metrics``; grid jobs keep
    the winning pair under ``result.best_pair``. Scale is 0-100 for both.

    Args:
        job: The job-store record for a finished optimization.

    Returns:
        A 2-tuple of ``(baseline_metric, optimized_metric)`` where each
        entry is a 0-100 float or ``None`` when the score is missing or
        cannot be coerced to ``float``.
    """
    overview = job.get("payload_overview") or {}
    job_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE)
    metrics = job.get("latest_metrics") or {}
    baseline = metrics.get("baseline_test_metric")
    optimized = metrics.get("optimized_test_metric")
    if job_type == OPTIMIZATION_TYPE_GRID_SEARCH:
        result = job.get("result") or {}
        best = result.get("best_pair") if isinstance(result, dict) else None
        if isinstance(best, dict):
            baseline = best.get("baseline_test_metric", baseline)
            optimized = best.get("optimized_test_metric", optimized)
    try:
        baseline_f = float(baseline) if baseline is not None else None
    except (TypeError, ValueError):
        baseline_f = None
    try:
        optimized_f = float(optimized) if optimized is not None else None
    except (TypeError, ValueError):
        optimized_f = None
    return baseline_f, optimized_f


def _evaluate_quality(baseline: float | None, optimized: float | None) -> bool:
    """Return True when a job clears the 'good enough to recommend' bar.

    Gate: optimized beats an absolute floor AND the gain clears both an
    absolute and a relative threshold (max of the two — whichever is
    larger — so low-baseline tasks aren't penalised for small raw lifts).
    Metrics live on the 0-100 scale the worker produces.

    Args:
        baseline: The pre-optimization score on a 0-100 scale, or ``None``.
        optimized: The post-optimization score on a 0-100 scale, or ``None``.

    Returns:
        True when the optimized score is recommendable; False when either
        score is missing, the optimized score is below the floor, or the
        gain is below the absolute / relative threshold.
    """
    if baseline is None or optimized is None:
        return False
    if optimized < settings.recommendations_quality_min_absolute:
        return False
    lift = optimized - baseline
    if lift <= 0:
        return False
    floor_abs = settings.recommendations_quality_min_gain_absolute
    floor_rel = settings.recommendations_quality_min_gain_relative * max(baseline, 1e-6)
    required = max(floor_abs, floor_rel)
    return lift >= required


def _extract_applyable_config(job: dict[str, Any]) -> dict[str, Any]:
    """Extract the model/optimizer/module config needed for one-click apply.

    The wizard stores these shapes on the submission payload; we persist
    them so the frontend can prefill the form without a second round-trip
    to the original job.

    Args:
        job: The job-store record with ``payload`` and ``payload_overview``
            sub-dicts.

    Returns:
        A dict with ``optimizer_name``, ``optimizer_kwargs``,
        ``module_name``, ``metric_name`` and ``task_name`` keys; values
        may be ``None`` when the field is absent on the job payload.
    """
    payload = job.get("payload") or {}
    overview = job.get("payload_overview") or {}
    return {
        "optimizer_name": payload.get("optimizer_name"),
        "optimizer_kwargs": payload.get("optimizer_kwargs") or {},
        "module_name": payload.get("module_name"),
        "metric_name": payload.get("metric_name"),
        "task_name": overview.get("name") or payload.get("name"),
    }


def embed_finished_job(optimization_id: str, *, job_store: Any) -> None:
    """Compute and upsert the three-aspect embedding for a finished job.

    Called on a daemon thread from the worker — must never raise.
    Skips silently when the embedder is unavailable or when the job's
    payload is too incomplete to derive meaningful text.

    Args:
        optimization_id: ID of the finished job whose embeddings should
            be (re)computed.
        job_store: Job-store handle used to load the payload and to open
            a SQLAlchemy session for the upsert.
    """
    if not settings.recommendations_enabled:
        return

    embedder = get_embedder()
    if not embedder.available():
        return

    try:
        job = job_store.get_job(optimization_id)
    except KeyError:
        logger.debug("embed_finished_job: job %s not found", optimization_id)
        return
    except Exception as exc:
        logger.warning("embed_finished_job: could not fetch job %s: %s", optimization_id, exc)
        return

    if job.get("status") != "success":
        return

    payload = job.get("payload") or {}
    overview = job.get("payload_overview") or {}
    signature_code = payload.get("signature_code")
    metric_code = payload.get("metric_code")
    column_mapping = payload.get("column_mapping")
    dataset = payload.get("dataset") or []

    summary_text = summarize_task(
        signature_code=signature_code,
        metric_code=metric_code,
        column_mapping=column_mapping,
        dataset_sample=dataset,
    )
    code_text = _build_code_text(signature_code, metric_code)
    schema_text = _build_schema_text(dataset, column_mapping)

    emb_summary = embedder.encode(summary_text) if summary_text else None
    emb_code = embedder.encode(code_text) if code_text else None
    emb_schema = embedder.encode(schema_text) if schema_text else None

    if emb_summary is None and emb_code is None and emb_schema is None:
        logger.debug("embed_finished_job: no usable text for %s, skipping", optimization_id)
        return

    winning_model, winning_rank, optimization_type = _extract_metadata(job)
    baseline, optimized = _extract_scores(job)
    is_recommendable = _evaluate_quality(baseline, optimized)
    applyable = _extract_applyable_config(job)
    user_id = overview.get(PAYLOAD_OVERVIEW_USERNAME)

    try:
        with Session(job_store.engine) as session:
            existing = (
                session.query(JobEmbeddingModel).filter(JobEmbeddingModel.optimization_id == optimization_id).first()
            )
            fields: dict[str, Any] = {
                "user_id": user_id,
                "optimization_type": optimization_type,
                "winning_model": winning_model,
                "winning_rank": winning_rank,
                "embedding_summary": emb_summary,
                "embedding_code": emb_code,
                "embedding_schema": emb_schema,
                "is_recommendable": is_recommendable,
                "baseline_metric": baseline,
                "optimized_metric": optimized,
                "summary_text": summary_text or None,
                "signature_code": signature_code,
                "metric_name": applyable["metric_name"],
                "optimizer_name": applyable["optimizer_name"],
                "optimizer_kwargs": applyable["optimizer_kwargs"],
                "module_name": applyable["module_name"],
                "task_name": applyable["task_name"],
            }
            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
            else:
                session.add(
                    JobEmbeddingModel(
                        optimization_id=optimization_id,
                        created_at=datetime.now(UTC),
                        **fields,
                    )
                )
            session.commit()
        logger.info(
            "Recommendations: indexed %s (type=%s, winner=%s, recommendable=%s, gain=%s→%s)",
            optimization_id,
            optimization_type,
            winning_model,
            is_recommendable,
            baseline,
            optimized,
        )
    except Exception as exc:
        logger.warning("embed_finished_job upsert failed for %s: %s", optimization_id, exc)


def _weighted_fusion_sql(
    *,
    has_summary: bool,
    has_code: bool,
    has_schema: bool,
    filter_type: bool,
) -> str:
    """Compose the weighted-cosine-similarity SQL.

    pgvector's ``<=>`` operator returns cosine *distance* (0 = identical,
    2 = opposite). We convert to similarity with ``1 - distance`` and
    weight each aspect. NULL embeddings are treated as 0 contribution.
    Only rows with ``is_recommendable = TRUE`` are eligible — the quality
    gate is enforced at query time so the ingest pipeline can keep
    embedding every successful job (the dashboard needs the full set).

    Args:
        has_summary: Whether the caller is supplying a summary embedding.
        has_code: Whether the caller is supplying a code embedding.
        has_schema: Whether the caller is supplying a schema embedding.
        filter_type: When True, the SQL adds an ``optimization_type``
            filter bound to the ``:filter_type`` parameter.

    Returns:
        A SQL string ready to bind named parameters (``:q_summary``,
        ``:q_code``, ``:q_schema``, ``:filter_type``, ``:top_k``) and
        execute against pgvector.
    """
    terms: list[str] = []
    if has_summary:
        terms.append(f"COALESCE(({_WEIGHTS['summary']} * (1 - (embedding_summary <=> CAST(:q_summary AS vector)))), 0)")
    if has_code:
        terms.append(f"COALESCE(({_WEIGHTS['code']} * (1 - (embedding_code <=> CAST(:q_code AS vector)))), 0)")
    if has_schema:
        terms.append(f"COALESCE(({_WEIGHTS['schema']} * (1 - (embedding_schema <=> CAST(:q_schema AS vector)))), 0)")
    score_expr = " + ".join(terms) if terms else "0"
    where_clauses = [
        "is_recommendable = TRUE",
        "(embedding_summary IS NOT NULL OR embedding_code IS NOT NULL OR embedding_schema IS NOT NULL)",
    ]
    if filter_type:
        where_clauses.append("optimization_type = :filter_type")
    where = " AND ".join(where_clauses)
    return (
        f"SELECT optimization_id, optimization_type, winning_model, winning_rank, "
        f"baseline_metric, optimized_metric, summary_text, signature_code, "
        f"metric_name, optimizer_name, optimizer_kwargs, module_name, task_name, "
        f"({score_expr}) AS score "
        f"FROM job_embeddings "
        f"WHERE {where} "
        f"ORDER BY score DESC "
        f"LIMIT :top_k"
    )


def _encode_vector_literal(vec: list[float] | None) -> str | None:
    """Format a numeric vector as pgvector's ``'[0.1,0.2,...]'`` SQL literal.

    Args:
        vec: The vector to encode; pass-through for ``None``.

    Returns:
        The pgvector literal string, or ``None`` when ``vec`` is ``None``.
    """
    if vec is None:
        return None
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def search_similar(
    *,
    job_store: Any,
    signature_code: str | None,
    metric_code: str | None,
    dataset_schema: dict[str, Any] | None,
    optimization_type: str | None,
    user_id: str | None,
    top_k: int,
) -> list[dict[str, Any]]:
    """Return up to ``top_k`` past jobs ranked by weighted vector similarity.

    ``dataset_schema`` is the column → dtype/role map; we turn it into
    the same compact text form the ingest pipeline uses. ``user_id`` is
    reserved for future cross-user scoping (e.g. personalisation); today
    it's accepted but not used in the query.

    Args:
        job_store: Job-store handle used to open a SQLAlchemy session.
        signature_code: Submitted DSPy signature source code (may be empty).
        metric_code: Submitted metric source code (may be empty).
        dataset_schema: Submitted column → role/dtype map (may be empty).
        optimization_type: Optional ``run`` / ``grid_search`` filter.
        user_id: Caller's user id (currently unused; reserved for scoping).
        top_k: Maximum number of recommendations to return.

    Returns:
        A list of recommendation dicts ordered by descending similarity
        score. Empty when recommendations are disabled, the embedder is
        unavailable, no usable text could be derived, or the SQL query
        fails.
    """
    if not settings.recommendations_enabled:
        return []

    embedder = get_embedder()
    if not embedder.available():
        return []

    code_text = _build_code_text(signature_code, metric_code)
    schema_text = _build_schema_from_query_schema(dataset_schema)
    if not code_text and not schema_text:
        return []
    summary_text = summarize_task(
        signature_code=signature_code,
        metric_code=metric_code,
        column_mapping=dataset_schema,
        dataset_sample=None,
    )

    q_code = embedder.encode(code_text) if code_text else None
    q_schema = embedder.encode(schema_text) if schema_text else None
    q_summary = embedder.encode(summary_text) if summary_text else None

    if q_code is None and q_schema is None and q_summary is None:
        return []

    sql = _weighted_fusion_sql(
        has_summary=q_summary is not None,
        has_code=q_code is not None,
        has_schema=q_schema is not None,
        filter_type=bool(optimization_type),
    )
    params: dict[str, Any] = {"top_k": int(top_k)}
    if q_summary is not None:
        params["q_summary"] = _encode_vector_literal(q_summary)
    if q_code is not None:
        params["q_code"] = _encode_vector_literal(q_code)
    if q_schema is not None:
        params["q_schema"] = _encode_vector_literal(q_schema)
    if optimization_type:
        params["filter_type"] = optimization_type

    try:
        with Session(job_store.engine) as session:
            rows = session.execute(text(sql), params).mappings().all()
    except Exception as exc:
        logger.warning("search_similar SQL failed: %s", exc)
        return []

    return [
        {
            "optimization_id": row["optimization_id"],
            "optimization_type": row["optimization_type"],
            "winning_model": row["winning_model"],
            "winning_rank": row["winning_rank"],
            "score": float(row["score"] or 0.0),
            "baseline_metric": _as_float(row.get("baseline_metric")),
            "optimized_metric": _as_float(row.get("optimized_metric")),
            "summary_text": row.get("summary_text"),
            "signature_code": row.get("signature_code"),
            "metric_name": row.get("metric_name"),
            "optimizer_name": row.get("optimizer_name"),
            "optimizer_kwargs": row.get("optimizer_kwargs") or {},
            "module_name": row.get("module_name"),
            "task_name": row.get("task_name"),
        }
        for row in rows
    ]


def _as_float(value: Any) -> float | None:
    """Coerce SQL numerics (Decimal, int, float, None) to plain float or None.

    Args:
        value: A SQL numeric value returned from the driver.

    Returns:
        The value as a ``float``, or ``None`` when ``value`` is ``None``
        or cannot be coerced.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_schema_from_query_schema(schema: dict[str, Any] | None) -> str:
    """Format a submission-time column schema like the ingest digest.

    Frontend sends ``{"columns": [{"name": "...", "role": "...", "dtype": "..."}]}``
    or similar. We accept a permissive shape and fall back gracefully.

    Args:
        schema: A submission-time column schema dict, or ``None``.

    Returns:
        A multi-line ``name (role, dtype)`` block when ``columns`` is a
        list, a JSON dump (truncated to 1000 chars) when not, or an
        empty string when ``schema`` is empty or non-serialisable.
    """
    if not schema:
        return ""
    columns = schema.get("columns") if isinstance(schema, dict) else None
    if isinstance(columns, list):
        lines = []
        for col in columns:
            if not isinstance(col, dict):
                continue
            name = col.get("name") or ""
            role = col.get("role") or "ignore"
            dtype = col.get("dtype") or col.get("type") or "unknown"
            lines.append(f"{name} ({role}, {dtype})")
        return "\n".join(lines)
    try:
        rendered = json.dumps(schema, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return ""
    if len(rendered) > 1000:
        logger.debug("schema digest truncated from %d chars to 1000", len(rendered))
        return rendered[:1000] + "…"
    return rendered
