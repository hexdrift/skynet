"""Shared helpers used by the domain routers.

Contains the small number of functions, constants, and caches that were
closures inside ``create_app`` but are needed by more than one extracted
router. Kept under a leading underscore to signal "package-internal".
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import pickle
from collections import OrderedDict
from collections.abc import AsyncIterable, AsyncIterator
from datetime import UTC, datetime
from typing import Any

from ...config import settings
from ...constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_COMPILE_KWARGS,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
    PAYLOAD_OVERVIEW_OPTIMIZER_KWARGS,
    PAYLOAD_OVERVIEW_SEED,
    PAYLOAD_OVERVIEW_SHUFFLE,
    PAYLOAD_OVERVIEW_SPLIT_FRACTIONS,
    PAYLOAD_OVERVIEW_TASK_FINGERPRINT,
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
from ..errors import DomainError
from .constants import TERMINAL_STATUSES

logger = logging.getLogger(__name__)

class _BoundedProgramCache(OrderedDict[str, Any]):
    """OrderedDict-backed LRU for deserialized DSPy programs.

    A plain dict here grew without bound — every served optimization pinned
    its compiled module in process memory until the API restarted. This
    bounded variant evicts the least-recently-used entry once
    ``settings.program_cache_max_entries`` is exceeded so a long-lived API
    process can't be DoS'd by serving many distinct optimizations.
    """

    def __init__(self) -> None:
        """Initialise an empty cache; capacity is read lazily from settings."""
        super().__init__()

    @property
    def _max_entries(self) -> int:
        """Resolve the live cache ceiling from application settings.

        Reading on every mutation lets test fixtures override the cap by
        tweaking ``settings.program_cache_max_entries`` between cases without
        re-importing this module.
        """
        return max(int(settings.program_cache_max_entries), 1)

    def __setitem__(self, key: str, value: Any) -> None:
        """Insert ``value`` at most-recently-used and evict if past capacity.

        Args:
            key: Cache key (optimization id or pair-scoped key).
            value: Deserialized DSPy program object.
        """
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        while len(self) > self._max_entries:
            self.popitem(last=False)

    def __getitem__(self, key: str) -> Any:
        """Return the cached program and mark it most-recently-used.

        Args:
            key: Cache key to look up.

        Returns:
            The previously stored program object.

        Raises:
            KeyError: When ``key`` is not present in the cache.
        """
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value


# Cache deserialized programs to avoid repeated pickle loads.
# Keyed by optimization_id (for single runs + grid-search best pair) or
# f"{optimization_id}_pair_{pair_index}" (for per-pair serving). Bounded by
# ``settings.program_cache_max_entries`` to cap process resident memory.
_program_cache: _BoundedProgramCache = _BoundedProgramCache()


def clear_program_cache() -> None:
    """Clear the module-level deserialized-program cache.

    Intended for test teardown; production code should not call this.
    """
    _program_cache.clear()


async def sse_from_events(
    source: AsyncIterable[dict[str, Any]],
) -> AsyncIterator[str]:
    """Serialize an ``{event, data}`` async iterable as Server-Sent Events.

    Every SSE route in this codebase shares the same formatting contract:
    each yielded mapping has an ``event`` name and a ``data`` dict that is
    JSON-encoded (``ensure_ascii=False``) and emitted as
    ``"event: <name>\\ndata: <json>\\n\\n"``. Centralising it here lets
    route handlers stay free of nested ``event_generator`` closures.

    Args:
        source: Async iterable yielding ``{"event": str, "data": dict}`` mappings.

    Yields:
        SSE-formatted strings ready for ``StreamingResponse``.
    """
    async for event in source:
        name = event["event"]
        payload = json.dumps(event["data"], ensure_ascii=False, default=str)
        yield f"event: {name}\ndata: {payload}\n\n"


def strip_api_key(d: dict) -> dict:
    """Return a shallow copy of *d* with ``extra.api_key`` removed.

    Args:
        d: A model-settings dict that may contain an ``extra.api_key`` field.

    Returns:
        A copy of ``d`` with the API key scrubbed from ``extra``.
    """
    result = dict(d)
    extra = result.get("extra")
    if isinstance(extra, dict) and "api_key" in extra:
        result["extra"] = {k: v for k, v in extra.items() if k != "api_key"}
    return result


def stable_seed(optimization_id: str) -> int:
    """Derive a process-stable 31-bit RNG seed from an optimization id.

    Python's built-in :func:`hash` is salted per process via
    ``PYTHONHASHSEED``, so the same id maps to a different int in every
    worker. Read paths (``/dataset``, ``/test-results``,
    ``/pair/{i}/test-results``) recompute the train/val/test split with
    this seed when the payload's stored seed is missing — using
    :func:`hash` there silently desyncs splits across workers and breaks
    UI index remapping. SHA256 truncated to 31 bits keeps the same numeric
    shape but is byte-stable across processes.

    Args:
        optimization_id: Optimization identifier to derive a seed from.

    Returns:
        A non-negative ``int`` strictly less than ``2 ** 31``.
    """
    digest = hashlib.sha256(optimization_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % (2**31)


def compute_task_fingerprint(
    signature_code: str,
    metric_code: str,
    dataset: list[dict[str, Any]],
) -> str:
    """Return a stable SHA256 fingerprint identifying the ML task.

    Two jobs share a fingerprint iff their signature source, metric source,
    and dataset content are byte-identical. Used by the frontend to gate
    apples-to-apples run comparisons.

    Args:
        signature_code: Source code of the user's DSPy signature.
        metric_code: Source code of the user's metric function.
        dataset: The full list of dataset rows used for the optimization.

    Returns:
        A hex-encoded SHA256 digest derived from the three inputs.
    """
    dataset_blob = json.dumps(dataset, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    dataset_hash = hashlib.sha256(dataset_blob.encode("utf-8")).hexdigest()
    task_blob = f"{signature_code}\x00{metric_code}\x00{dataset_hash}"
    return hashlib.sha256(task_blob.encode("utf-8")).hexdigest()


def enforce_user_quota(job_store, username: str) -> None:
    """Raise if ``username`` is at or over their job quota.

    Admins and users with an explicit ``None`` override bypass the check
    entirely.

    Args:
        job_store: The job store used to count the user's existing jobs.
        username: The user whose quota should be enforced.

    Raises:
        DomainError: When the user already has at least ``quota`` jobs (HTTP 409).
    """
    quota = settings.get_user_quota(username)
    if quota is None:
        return
    current = job_store.count_jobs(username=username)
    if current >= quota:
        raise DomainError("quota.reached", status=409, quota=quota)


def build_summary(job_data: dict) -> OptimizationSummaryResponse:
    """Build a compact dashboard-card summary from a raw job dict.

    Handles both single-run and grid-search jobs. For grid search the best pair
    is used as the representative result. Live pair counters fall back to
    ``latest_metrics`` while the sweep is still in progress.

    Args:
        job_data: Raw job row from the job store.

    Returns:
        A populated :class:`OptimizationSummaryResponse` for dashboard rendering.
    """
    created_at = parse_timestamp(job_data.get("created_at")) or datetime.now(UTC)
    started_at = parse_timestamp(job_data.get("started_at"))
    completed_at = parse_timestamp(job_data.get("completed_at"))
    overview = parse_overview(job_data)
    job_status = status_to_job_status(job_data.get("status", "pending"))
    optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)

    est_remaining = None
    if job_status not in TERMINAL_STATUSES:
        est_remaining = extract_estimated_remaining(job_data)

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
        task_fingerprint=overview.get(PAYLOAD_OVERVIEW_TASK_FINGERPRINT),
    )


def load_program(job_store, optimization_id: str) -> tuple[Any, RunResponse, dict]:
    """Load and cache an optimized program from a completed job.

    For grid-search jobs, loads the best pair's program automatically and
    synthesizes a ``RunResponse`` from the grid result envelope.

    Args:
        job_store: The job store to read the job row from.
        optimization_id: The optimization to load.

    Returns:
        A ``(program, RunResponse, overview)`` tuple where ``program`` is the
        deserialized DSPy module, ``RunResponse`` is the synthesized result,
        and ``overview`` is the parsed payload-overview dict.

    Raises:
        DomainError: 404 when the job is unknown; 409 when the job is not in
            a success state, has no result, or lacks a serialized program artifact.
    """
    try:
        job_data = job_store.get_job(optimization_id)
    except KeyError:
        raise DomainError(
            "optimization.not_found",
            status=404,
            optimization_id=optimization_id,
        ) from None

    overview = parse_overview(job_data)
    optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)

    status = status_to_job_status(job_data.get("status", "pending"))
    if status != OptimizationStatus.success:
        raise DomainError(
            "optimization.not_success_status_for_serve",
            status=409,
            params={"status": status.value},
        )

    result_data = job_data.get("result")
    if not result_data or not isinstance(result_data, dict):
        raise DomainError("optimization.no_result", status=409)

    if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
        grid_result = GridSearchResponse.model_validate(result_data)
        if not grid_result.best_pair:
            raise DomainError("grid_search.no_best_pair", status=409)
        artifact = grid_result.best_pair.program_artifact
        if not artifact or not artifact.program_pickle_base64:
            raise DomainError("grid_search.no_best_program_artifact", status=409)
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
        overview[PAYLOAD_OVERVIEW_MODEL_NAME] = grid_result.best_pair.generation_model
    else:
        result = RunResponse.model_validate(result_data)
        artifact = result.program_artifact
        if not artifact or not artifact.program_pickle_base64:
            raise DomainError("optimization.no_program_artifact_scoped", status=409)

    if optimization_id not in _program_cache:
        program_bytes = base64.b64decode(artifact.program_pickle_base64)
        # pickle.loads is RCE if an attacker can write to the jobs table.
        # The artifact bytes are produced by our own worker and never
        # accepted from API input, so today the only attacker who reaches
        # this branch already has DB write — at which point they own the
        # process anyway. Follow-up tracked under "signed payloads": HMAC
        # the pickle at worker-write time and verify here before loading.
        _program_cache[optimization_id] = pickle.loads(program_bytes)

    return _program_cache[optimization_id], result, overview


def load_pair_program(job_store, optimization_id: str, pair_index: int) -> tuple[Any, PairResult, dict]:
    """Load and cache the compiled program for a specific grid-search pair.

    Args:
        job_store: The job store to read the job row from.
        optimization_id: The grid-search optimization to load.
        pair_index: The index of the pair within the grid sweep.

    Returns:
        A ``(program, PairResult, overview)`` tuple where ``program`` is the
        deserialized DSPy module for the pair, ``PairResult`` describes the
        pair's outcome, and ``overview`` is the parsed payload-overview dict.

    Raises:
        DomainError: 404 when the job or pair index is unknown; 409 when the
            job is not a successful grid search, the pair failed, or the
            program artifact is missing.
    """
    try:
        job_data = job_store.get_job(optimization_id)
    except KeyError:
        raise DomainError(
            "optimization.not_found",
            status=404,
            optimization_id=optimization_id,
        ) from None

    overview = parse_overview(job_data)
    optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)

    if optimization_type != OPTIMIZATION_TYPE_GRID_SEARCH:
        raise DomainError("grid_search.pair_submission_grid_only", status=409)

    status = status_to_job_status(job_data.get("status", "pending"))
    if status != OptimizationStatus.success:
        raise DomainError(
            "optimization.not_success_status_for_serve",
            status=409,
            params={"status": status.value},
        )

    result_data = job_data.get("result")
    if not result_data or not isinstance(result_data, dict):
        raise DomainError("optimization.no_result", status=409)

    grid_result = GridSearchResponse.model_validate(result_data)

    pair = None
    for pr in grid_result.pair_results:
        if pr.pair_index == pair_index:
            pair = pr
            break
    if pair is None:
        raise DomainError(
            "grid_search.pair_position_missing",
            status=404,
            pair_index=pair_index,
        )

    if pair.error:
        raise DomainError(
            "grid_search.pair_failed_error",
            status=409,
            pair_index=pair_index,
            error=pair.error,
        )

    artifact = pair.program_artifact
    if not artifact or not artifact.program_pickle_base64:
        raise DomainError(
            "grid_search.pair_no_artifact",
            status=409,
            pair_index=pair_index,
        )

    cache_key = f"{optimization_id}_pair_{pair_index}"
    if cache_key not in _program_cache:
        program_bytes = base64.b64decode(artifact.program_pickle_base64)
        # See ``load_program`` for the full pickle.loads safety story; same
        # signed-payload follow-up applies here.
        _program_cache[cache_key] = pickle.loads(program_bytes)

    return _program_cache[cache_key], pair, overview
