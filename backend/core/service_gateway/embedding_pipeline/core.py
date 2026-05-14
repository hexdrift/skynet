"""Per-job embedding pipeline backing the public explore-map scatter.

Pipeline:

1. After a job finishes successfully, the worker fires
   ``embed_finished_job(optimization_id, job_store)`` on a daemon thread.
2. That task: fetches the job payload, asks an LLM for a 2-3 sentence
   task summary, embeds the summary, and upserts the vector + display
   metadata (task / module / optimizer name, baseline / optimized score,
   winning model) into ``job_embeddings``.
3. On backend startup, ``backfill_missing_embeddings`` scans for success
   jobs that lack an embedding row and drains them on a single daemon
   thread so a crashed worker thread or restart still heals the index.

Failures never raise — embedding is best-effort. Missing embedding API
credentials, LLM hiccups, or a flaky pgvector connection all degrade to
"skip this job" and the row is retried on the next startup scan.

Only the ``summary`` aspect is embedded. The code / schema aspects from
the original recommendations design were dropped: the explore map's only
consumer is dashboard.py, which reads ``embedding_summary`` exclusively.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...config import settings
from ...constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    PAYLOAD_OVERVIEW_IS_PRIVATE,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
    PAYLOAD_OVERVIEW_USERNAME,
)
from ...storage.models import JobEmbeddingModel
from .embeddings import get_embedder
from .summarizer import summarize_task

logger = logging.getLogger(__name__)


def _extract_metadata(job: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return ``(winning_model, optimization_type)`` for a finished job.

    For a ``run`` job the winner is the single configured model. For a
    grid search the winner is ``result.best_pair.generation_model``.

    Args:
        job: The job-store record (with ``payload_overview`` and ``result``
            sub-dicts) for a finished optimization.

    Returns:
        A 2-tuple of ``(winning_model, optimization_type)`` where each
        entry may be ``None`` when the corresponding field is absent.
    """
    overview = job.get("payload_overview") or {}
    result = job.get("result") or {}
    job_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE)
    if job_type == OPTIMIZATION_TYPE_GRID_SEARCH:
        best = result.get("best_pair") if isinstance(result, dict) else None
        if isinstance(best, dict):
            return best.get("generation_model"), job_type
        return None, job_type
    return overview.get(PAYLOAD_OVERVIEW_MODEL_NAME), job_type


def _extract_scores(job: dict[str, Any]) -> tuple[float | None, float | None]:
    """Return ``(baseline_metric, optimized_metric)`` for a finished job.

    Run jobs store the pair directly in ``latest_metrics``; grid jobs keep
    the winning pair under ``result.best_pair``. Scale is 0-100 for both.

    Args:
        job: The job-store record for a finished optimization.

    Returns:
        A 2-tuple of ``(baseline_metric, optimized_metric)`` where each
        entry is a 0-100 float or ``None`` when the score is missing.
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


def _extract_display_fields(job: dict[str, Any]) -> dict[str, str | None]:
    """Pull the human-readable labels shown on the explore-map tooltip.

    Args:
        job: The job-store record with ``payload`` and ``payload_overview``
            sub-dicts.

    Returns:
        A dict with ``task_name``, ``module_name``, and ``optimizer_name``
        keys; values may be ``None`` when the field is absent.
    """
    payload = job.get("payload") or {}
    overview = job.get("payload_overview") or {}
    return {
        "task_name": overview.get("name") or payload.get("name"),
        "module_name": payload.get("module_name"),
        "optimizer_name": payload.get("optimizer_name"),
    }


def embed_finished_job(optimization_id: str, *, job_store: Any) -> bool:
    """Compute and upsert the summary embedding for a finished job.

    Called on a daemon thread from the worker and from the startup
    backfill — must never raise.

    Args:
        optimization_id: ID of the finished job whose embedding should be
            (re)computed.
        job_store: Job-store handle used to load the payload and to open
            a SQLAlchemy session for the upsert.

    Returns:
        True when a row was written; False when the pipeline skipped the
        job (disabled, embedder unavailable, job missing, no usable text,
        DB error). The return value drives backfill progress logging.
    """
    if not settings.embeddings_enabled:
        logger.info("Embedding skipped for %s: EMBEDDINGS_ENABLED is false.", optimization_id)
        return False

    embedder = get_embedder()
    if not embedder.available():
        return False

    try:
        job = job_store.get_job(optimization_id)
    except KeyError:
        logger.debug("embed_finished_job: job %s not found", optimization_id)
        return False
    except Exception as exc:
        logger.warning("embed_finished_job: could not fetch job %s: %s", optimization_id, exc)
        return False

    if job.get("status") != "success":
        return False

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

    emb_summary = embedder.encode(summary_text) if summary_text else None
    if emb_summary is None:
        logger.debug("embed_finished_job: no usable summary for %s, skipping", optimization_id)
        return False

    winning_model, optimization_type = _extract_metadata(job)
    baseline, optimized = _extract_scores(job)
    display = _extract_display_fields(job)
    user_id = overview.get(PAYLOAD_OVERVIEW_USERNAME)
    is_private = bool(overview.get(PAYLOAD_OVERVIEW_IS_PRIVATE, False))

    try:
        with Session(job_store.engine) as session:
            existing = (
                session.query(JobEmbeddingModel).filter(JobEmbeddingModel.optimization_id == optimization_id).first()
            )
            fields: dict[str, Any] = {
                "user_id": user_id,
                "optimization_type": optimization_type,
                "winning_model": winning_model,
                "embedding_summary": emb_summary,
                "is_private": is_private,
                "baseline_metric": baseline,
                "optimized_metric": optimized,
                "summary_text": summary_text or None,
                "task_name": display["task_name"],
                "module_name": display["module_name"],
                "optimizer_name": display["optimizer_name"],
                # Persist signature_code so identity dedup on the explore
                # map can collapse repeated submissions of the same task.
                "signature_code": signature_code,
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
    except Exception as exc:
        logger.warning("embed_finished_job upsert failed for %s: %s", optimization_id, exc)
        return False

    logger.info(
        "Embedding indexed for %s (type=%s, winner=%s, baseline=%s, optimized=%s)",
        optimization_id,
        optimization_type,
        winning_model,
        baseline,
        optimized,
    )
    return True


def _fetch_missing_embedding_ids(job_store: Any) -> list[str]:
    """Return success-state job IDs that lack a summary embedding row.

    The scan is a single LEFT JOIN — cheap even at 100k jobs — and runs
    synchronously on startup so the lifespan logger knows the queue size
    before the drain thread starts.

    Args:
        job_store: Job-store handle exposing a SQLAlchemy engine.

    Returns:
        A list of optimization IDs ordered by creation time (oldest
        first) so backfill heals the longest-stale rows before any
        recently-crashed ones.
    """
    try:
        with Session(job_store.engine) as session:
            rows = (
                session.execute(
                    text(
                        "SELECT j.optimization_id "
                        "FROM jobs j "
                        "LEFT JOIN job_embeddings e ON e.optimization_id = j.optimization_id "
                        "WHERE j.status = 'success' "
                        "AND (e.optimization_id IS NULL OR e.embedding_summary IS NULL) "
                        "ORDER BY j.created_at ASC"
                    )
                )
                .mappings()
                .all()
            )
            return [row["optimization_id"] for row in rows]
    except Exception as exc:
        logger.warning("Could not scan for missing embeddings: %s", exc)
        return []


def _drain_backfill_queue(job_store: Any, ids: list[str]) -> None:
    """Embed each pending job sequentially, logging progress per row.

    Sequential (not fan-out) so backfill never thunders the embedding API
    on a cold start. The summary LLM call inside ``embed_finished_job``
    is the slow leg; running it serially also keeps the LM provider's
    rate limiter happy.

    Args:
        job_store: Job-store handle forwarded to ``embed_finished_job``.
        ids: Optimization IDs to embed, in the order returned by
            ``_fetch_missing_embedding_ids``.
    """
    total = len(ids)
    if total == 0:
        return
    logger.info("Embedding backfill: starting drain of %d job(s)", total)
    ok = 0
    for idx, optimization_id in enumerate(ids, start=1):
        try:
            written = embed_finished_job(optimization_id, job_store=job_store)
        except Exception as exc:
            logger.warning("Embedding backfill: %s raised: %s", optimization_id, exc)
            written = False
        if written:
            ok += 1
        logger.info("Embedding backfill: %d/%d processed (%d written)", idx, total, ok)
    logger.info("Embedding backfill: drain complete (%d/%d written)", ok, total)


def backfill_missing_embeddings(job_store: Any) -> int:
    """Scan for jobs missing a summary embedding and queue a drain thread.

    Returns immediately after queueing so the API lifespan does not block
    on the LLM. The drain itself runs on a single daemon thread that logs
    progress every row.

    Args:
        job_store: Job-store handle forwarded to the drain.

    Returns:
        The number of jobs queued (0 when none are missing or the scan
        failed). Logged by the caller for operator visibility.
    """
    if not settings.embeddings_enabled:
        return 0
    ids = _fetch_missing_embedding_ids(job_store)
    if not ids:
        return 0
    thread = threading.Thread(
        target=_drain_backfill_queue,
        args=(job_store, ids),
        name="embed-backfill",
        daemon=True,
    )
    thread.start()
    return len(ids)
