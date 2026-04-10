"""Shared helpers used by the domain routers.

Contains the small number of functions, constants, and caches that were
closures inside ``create_app`` but are needed by more than one extracted
router. Kept under a leading underscore to signal "package-internal".
"""
from __future__ import annotations

import base64
import logging
import pickle
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from ...constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_JOB_TYPE,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_SEED,
    PAYLOAD_OVERVIEW_SHUFFLE,
    PAYLOAD_OVERVIEW_SPLIT_FRACTIONS,
    PAYLOAD_OVERVIEW_OPTIMIZER_KWARGS,
    PAYLOAD_OVERVIEW_COMPILE_KWARGS,
)
from ...models import (
    GridSearchResponse,
    OptimizationStatus,
    OptimizationSummaryResponse,
    PairResult,
    RunResponse,
)
from ..converters import (
    compute_elapsed,
    extract_estimated_remaining,
    overview_to_base_fields,
    parse_overview,
    parse_timestamp,
    status_to_job_status,
)

logger = logging.getLogger(__name__)

# Terminal job states that cannot be cancelled or restarted
_TERMINAL_STATUSES = {OptimizationStatus.success, OptimizationStatus.failed, OptimizationStatus.cancelled}

_VALID_STATUSES = {s.value for s in OptimizationStatus}
_VALID_JOB_TYPES = {OPTIMIZATION_TYPE_RUN, OPTIMIZATION_TYPE_GRID_SEARCH}

# Cache deserialized programs to avoid repeated pickle loads.
# Keyed by optimization_id (for single runs + grid-search best pair) or
# f"{optimization_id}_pair_{pair_index}" (for per-pair serving).
_program_cache: dict[str, Any] = {}


def strip_api_key(d: dict) -> dict:
    """Remove api_key from a model settings dict before persisting."""
    result = dict(d)
    extra = result.get("extra")
    if isinstance(extra, dict) and "api_key" in extra:
        result["extra"] = {k: v for k, v in extra.items() if k != "api_key"}
    return result


def build_summary(job_data: dict) -> OptimizationSummaryResponse:
    """Build a OptimizationSummaryResponse from a raw job store dict."""
    created_at = parse_timestamp(job_data.get("created_at")) or datetime.now(timezone.utc)
    started_at = parse_timestamp(job_data.get("started_at"))
    completed_at = parse_timestamp(job_data.get("completed_at"))
    overview = parse_overview(job_data)
    job_status = status_to_job_status(job_data.get("status", "pending"))
    optimization_type = overview.get(PAYLOAD_OVERVIEW_JOB_TYPE, OPTIMIZATION_TYPE_RUN)

    # Only show estimated_remaining for active jobs
    est_remaining = None
    if job_status not in _TERMINAL_STATUSES:
        est_remaining = extract_estimated_remaining(job_data)

    # Extract result metrics
    result_data = job_data.get("result")
    latest_metrics = job_data.get("latest_metrics", {})
    baseline = None
    optimized = None
    completed_pairs = None
    failed_pairs = None
    best_pair_label = None

    if isinstance(result_data, dict):
        if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
            best_pair = result_data.get("best_pair")
            if isinstance(best_pair, dict):
                baseline = best_pair.get("baseline_test_metric")
                optimized = best_pair.get("optimized_test_metric")
                gen = best_pair.get("generation_model", "")
                ref = best_pair.get("reflection_model", "")
                best_pair_label = f"{gen} + {ref}"
            completed_pairs = result_data.get("completed_pairs")
            failed_pairs = result_data.get("failed_pairs")
        else:
            baseline = result_data.get("baseline_test_metric")
            optimized = result_data.get("optimized_test_metric")

    # For grid search, pull live counters from latest_metrics if result not yet available
    if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
        if completed_pairs is None:
            live_completed = latest_metrics.get("completed_so_far")
            completed_pairs = live_completed if isinstance(live_completed, int) else 0
        if failed_pairs is None:
            live_failed = latest_metrics.get("failed_so_far")
            failed_pairs = live_failed if isinstance(live_failed, int) else 0

    # Compute metric improvement
    metric_improvement = None
    if baseline is not None and optimized is not None:
        metric_improvement = round(optimized - baseline, 6)

    elapsed_str, elapsed_secs = compute_elapsed(created_at, started_at, completed_at)

    return OptimizationSummaryResponse(
        optimization_id=job_data["optimization_id"],
        status=job_status,
        message=job_data.get("message"),
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        elapsed=elapsed_str,
        elapsed_seconds=elapsed_secs,
        estimated_remaining=est_remaining,
        **overview_to_base_fields(overview),
        split_fractions=overview.get(PAYLOAD_OVERVIEW_SPLIT_FRACTIONS),
        shuffle=overview.get(PAYLOAD_OVERVIEW_SHUFFLE),
        seed=overview.get(PAYLOAD_OVERVIEW_SEED),
        optimizer_kwargs=overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_KWARGS, {}),
        compile_kwargs=overview.get(PAYLOAD_OVERVIEW_COMPILE_KWARGS, {}),
        latest_metrics=latest_metrics,
        progress_count=job_data.get("progress_count", 0),
        log_count=job_data.get("log_count", 0),
        baseline_test_metric=baseline,
        optimized_test_metric=optimized,
        metric_improvement=metric_improvement,
        completed_pairs=completed_pairs,
        failed_pairs=failed_pairs,
        best_pair_label=best_pair_label,
    )


def load_program(job_store, optimization_id: str) -> tuple[Any, RunResponse, dict]:
    """Load and cache an optimized program from a completed job.

    For grid search jobs, loads the best pair's program automatically.

    Args:
        optimization_id: The optimization identifier.

    Returns:
        Tuple of (compiled_program, run_response, payload_overview).

    Raises:
        HTTPException: If job not found, not finished, or has no artifact.
    """
    try:
        job_data = job_store.get_job(optimization_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.")

    overview = parse_overview(job_data)
    optimization_type = overview.get(PAYLOAD_OVERVIEW_JOB_TYPE, OPTIMIZATION_TYPE_RUN)

    status = status_to_job_status(job_data.get("status", "pending"))
    if status != OptimizationStatus.success:
        raise HTTPException(
            status_code=409,
            detail=f"Optimization is '{status.value}' — only successful optimizations can be served.",
        )

    result_data = job_data.get("result")
    if not result_data or not isinstance(result_data, dict):
        raise HTTPException(status_code=409, detail="Optimization has no result data.")

    if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
        grid_result = GridSearchResponse.model_validate(result_data)
        if not grid_result.best_pair:
            raise HTTPException(status_code=409, detail="Grid search has no successful pair.")
        artifact = grid_result.best_pair.program_artifact
        if not artifact or not artifact.program_pickle_base64:
            raise HTTPException(status_code=409, detail="Best pair has no program artifact.")
        # Build a synthetic RunResponse so callers get consistent data
        result = RunResponse(
            module_name=grid_result.module_name,
            optimizer_name=grid_result.optimizer_name,
            metric_name=grid_result.metric_name,
            split_counts=grid_result.split_counts,
            baseline_test_metric=grid_result.best_pair.baseline_test_metric,
            optimized_test_metric=grid_result.best_pair.optimized_test_metric,
            metric_improvement=grid_result.best_pair.metric_improvement,
            program_artifact=artifact,
        )
        # Use the best pair's generation model as the default model name
        overview[PAYLOAD_OVERVIEW_MODEL_NAME] = grid_result.best_pair.generation_model
    else:
        result = RunResponse.model_validate(result_data)
        artifact = result.program_artifact
        if not artifact or not artifact.program_pickle_base64:
            raise HTTPException(status_code=409, detail="Optimization has no program artifact.")

    if optimization_id not in _program_cache:
        program_bytes = base64.b64decode(artifact.program_pickle_base64)
        _program_cache[optimization_id] = pickle.loads(program_bytes)  # noqa: S301

    return _program_cache[optimization_id], result, overview


def load_pair_program(job_store, optimization_id: str, pair_index: int) -> tuple[Any, PairResult, dict]:
    """Load and cache an optimized program from a specific grid search pair.

    Args:
        optimization_id: The optimization identifier.
        pair_index: Index of the pair within the grid search results.

    Returns:
        Tuple of (compiled_program, pair_result, payload_overview).

    Raises:
        HTTPException: If job not found, not grid_search, or pair invalid.
    """
    try:
        job_data = job_store.get_job(optimization_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.")

    overview = parse_overview(job_data)
    optimization_type = overview.get(PAYLOAD_OVERVIEW_JOB_TYPE, OPTIMIZATION_TYPE_RUN)

    if optimization_type != OPTIMIZATION_TYPE_GRID_SEARCH:
        raise HTTPException(
            status_code=409,
            detail="Per-pair serving is only available for grid search jobs.",
        )

    status = status_to_job_status(job_data.get("status", "pending"))
    if status != OptimizationStatus.success:
        raise HTTPException(
            status_code=409,
            detail=f"Optimization is '{status.value}' — only successful optimizations can be served.",
        )

    result_data = job_data.get("result")
    if not result_data or not isinstance(result_data, dict):
        raise HTTPException(status_code=409, detail="Optimization has no result data.")

    grid_result = GridSearchResponse.model_validate(result_data)

    pair = None
    for pr in grid_result.pair_results:
        if pr.pair_index == pair_index:
            pair = pr
            break
    if pair is None:
        raise HTTPException(
            status_code=404,
            detail=f"No pair with index {pair_index} in grid search results.",
        )

    if pair.error:
        raise HTTPException(
            status_code=409,
            detail=f"Pair {pair_index} failed: {pair.error}",
        )

    artifact = pair.program_artifact
    if not artifact or not artifact.program_pickle_base64:
        raise HTTPException(
            status_code=409,
            detail=f"Pair {pair_index} has no program artifact.",
        )

    cache_key = f"{optimization_id}_pair_{pair_index}"
    if cache_key not in _program_cache:
        program_bytes = base64.b64decode(artifact.program_pickle_base64)
        _program_cache[cache_key] = pickle.loads(program_bytes)  # noqa: S301

    return _program_cache[cache_key], pair, overview
