"""Routes for the core optimizations resource (list, detail, lifecycle)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import pickle
import random
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import dspy
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.responses import StreamingResponse

from ...constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODEL_SETTINGS,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
    PAYLOAD_OVERVIEW_TOTAL_PAIRS,
    PAYLOAD_OVERVIEW_USERNAME,
)
from ...i18n import CANCELLATION_REASON, CLONE_NAME_PREFIX, RETRY_NAME_PREFIX, t
from ...models import (
    BulkCancelRequest,
    BulkCancelResponse,
    BulkCancelSkipped,
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkDeleteSkipped,
    ColumnMapping,
    GridSearchRequest,
    GridSearchResponse,
    JobCancelResponse,
    JobDeleteResponse,
    JobLogEntry,
    ModelConfig,
    OptimizationCountsResponse,
    OptimizationStatus,
    OptimizationStatusResponse,
    OptimizationSubmissionResponse,
    OptimizationSummaryResponse,
    PaginatedJobsResponse,
    ProgramArtifactResponse,
    RunRequest,
    RunResponse,
    SplitFractions,
)
from ...notifications import notify_job_started
from ...registry import ResolverError, resolve_module_factory
from ...service_gateway.data import load_metric_from_code, load_signature_from_code
from ...service_gateway.language_models import build_language_model
from ...worker import get_worker
from ..converters import (
    compute_elapsed,
    extract_estimated_remaining,
    overview_to_base_fields,
    parse_overview,
    parse_timestamp,
    status_to_job_status,
)
from ..response_limits import AGENT_DEFAULT_LIST, AGENT_MAX_LIST, clamp_limit
from ._helpers import (
    TERMINAL_STATUSES,
    VALID_OPTIMIZATION_TYPES,
    VALID_STATUSES,
    _program_cache,
    build_summary,
    compute_task_fingerprint,
    enforce_user_quota,
    strip_api_key,
)

logger = logging.getLogger(__name__)


class SidebarJobItem(BaseModel):
    """Compact per-optimization entry for the sidebar navigation list."""

    optimization_id: str
    status: str
    name: str | None = None
    module_name: str | None = None
    optimizer_name: str | None = None
    model_name: str | None = None
    username: str | None = None
    created_at: datetime | None = None
    pinned: bool = False
    optimization_type: str | None = None
    total_pairs: int | None = None


class SidebarJobsResponse(BaseModel):
    """Paginated response for the sidebar optimization list."""

    items: list[SidebarJobItem]
    total: int


class CloneJobRequest(BaseModel):
    """Request body for cloning an optimization."""

    count: int = Field(default=1, ge=1, le=5, description="Number of copies to create (1–5).")
    name_prefix: str | None = Field(
        default=None,
        max_length=100,
        description=f"Prefix prepended to each clone's name. Defaults to '{CLONE_NAME_PREFIX}'.",
    )


class CloneJobResponse(BaseModel):
    """List of newly-created clones plus the source id for reference."""

    source_optimization_id: str
    created: list[OptimizationSubmissionResponse]


class CompareJobsRequest(BaseModel):
    """Request body for side-by-side comparison of 2–5 optimizations."""

    optimization_ids: list[str] = Field(min_length=2, max_length=5)


class CompareJobSnapshot(BaseModel):
    """Compact per-optimization snapshot used in comparison responses."""

    optimization_id: str
    status: str
    name: str | None = None
    optimization_type: str | None = None
    module_name: str | None = None
    optimizer_name: str | None = None
    model_name: str | None = None
    dataset_rows: int | None = None
    baseline_test_metric: float | None = None
    optimized_test_metric: float | None = None
    metric_improvement: float | None = None


class CompareJobsResponse(BaseModel):
    """Response for POST /optimizations/compare."""

    jobs: list[CompareJobSnapshot]
    differing_fields: list[str]
    missing_optimization_ids: list[str]


class BulkMetadataRequest(BaseModel):
    """Request body for bulk pin or bulk archive."""

    optimization_ids: list[str] = Field(min_length=1, max_length=100)
    value: bool = Field(description="Target state — true to pin/archive, false to clear.")


class BulkMetadataSkipped(BaseModel):
    optimization_id: str
    reason: str


class BulkMetadataResponse(BaseModel):
    """Response for POST /optimizations/bulk-pin and /bulk-archive."""

    updated: list[str]
    skipped: list[BulkMetadataSkipped]


def create_optimizations_router(*, job_store, get_worker_ref: Callable[[], Any]) -> APIRouter:
    """Build the optimizations' router."""
    router = APIRouter()

    @router.get(
        "/optimizations",
        response_model=PaginatedJobsResponse,
        summary="List optimizations with filtering and pagination",
        tags=["agent"],
    )
    def list_jobs(
        status: str | None = Query(
            default=None,
            description="Exact-match status filter: pending, validating, running, success, failed, cancelled",
        ),
        username: str | None = Query(default=None, description="Only include optimizations submitted by this user"),
        optimization_type: str | None = Query(
            default=None, description="'run' (single optimization) or 'grid_search' (model-pair sweep)"
        ),
        limit: int = Query(
            default=AGENT_DEFAULT_LIST,
            ge=1,
            le=AGENT_MAX_LIST,
            description=(
                f"Page size (default {AGENT_DEFAULT_LIST}, ceiling {AGENT_MAX_LIST}). "
                "Paginate with offset — the agent context stays small that way."
            ),
        ),
        offset: int = Query(
            default=0,
            ge=0,
            description="Number of optimizations to skip before returning; combine with limit for stable pagination",
        ),
    ) -> PaginatedJobsResponse:
        """Return a page of optimizations ordered by ``created_at`` descending.

        Filters combine with AND. ``status`` and ``optimization_type`` are validated
        against closed lists (422 on mismatch). ``total`` reflects the pre-pagination count.
        ``limit`` is clamped to keep agent responses context-safe; UI callers that
        genuinely need larger pages hit the dedicated ``/optimizations/sidebar`` route.
        """
        if status is not None and status not in VALID_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=t("filter.invalid_status", value=status, allowed=sorted(VALID_STATUSES)),
            )
        if optimization_type is not None and optimization_type not in VALID_OPTIMIZATION_TYPES:
            raise HTTPException(
                status_code=422,
                detail=t(
                    "filter.invalid_optimization_type",
                    value=optimization_type,
                    allowed=sorted(VALID_OPTIMIZATION_TYPES),
                ),
            )
        resolved_limit = clamp_limit(limit)
        total = job_store.count_jobs(status=status, username=username, optimization_type=optimization_type)
        rows = job_store.list_jobs(
            status=status,
            username=username,
            optimization_type=optimization_type,
            limit=resolved_limit,
            offset=offset,
        )
        items = [build_summary(job_data) for job_data in rows]
        return PaginatedJobsResponse(items=items, total=total, limit=resolved_limit, offset=offset)

    @router.get(
        "/optimizations/counts",
        response_model=OptimizationCountsResponse,
        summary="Aggregate optimization counts grouped by status",
        tags=["agent"],
    )
    def get_optimization_counts(
        username: str | None = Query(default=None, description="Restrict counts to a single user"),
    ) -> OptimizationCountsResponse:
        """Return backend row counts grouped by status for dashboard stat cards."""
        total = job_store.count_jobs(username=username)
        return OptimizationCountsResponse(
            total=total,
            pending=job_store.count_jobs(status="pending", username=username),
            validating=job_store.count_jobs(status="validating", username=username),
            running=job_store.count_jobs(status="running", username=username),
            success=job_store.count_jobs(status="success", username=username),
            failed=job_store.count_jobs(status="failed", username=username),
            cancelled=job_store.count_jobs(status="cancelled", username=username),
        )

    @router.get(
        "/optimizations/sidebar",
        response_model=SidebarJobsResponse,
        summary="Compact optimization list tuned for sidebar navigation",
    )
    def list_jobs_sidebar(
        username: str | None = Query(default=None, description="Restrict the list to a single user's optimizations"),
        limit: int = Query(
            default=50,
            ge=1,
            le=200,
            description="Page size; capped at 200 because the sidebar only renders a finite slice",
        ),
        offset: int = Query(default=0, ge=0, description="Number of optimizations to skip before the returned slice"),
    ) -> SidebarJobsResponse:
        """Return minimal per-optimization fields for the sidebar (ID, status, name, model, pin state).

        No result payload, metrics, logs, or progress. Newest-first; pin reordering is client-side.
        """
        total = job_store.count_jobs(username=username)
        rows = job_store.list_jobs(username=username, limit=limit, offset=offset)
        items = []
        for row in rows:
            overview = parse_overview(row)
            items.append(
                SidebarJobItem(
                    optimization_id=row["optimization_id"],
                    status=row.get("status", "pending"),
                    name=overview.get(PAYLOAD_OVERVIEW_NAME),
                    module_name=overview.get(PAYLOAD_OVERVIEW_MODULE_NAME),
                    optimizer_name=overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_NAME),
                    model_name=overview.get(PAYLOAD_OVERVIEW_MODEL_NAME),
                    username=overview.get(PAYLOAD_OVERVIEW_USERNAME),
                    created_at=parse_timestamp(row.get("created_at")),
                    pinned=bool(overview.get("pinned", False)),
                    optimization_type=overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE),
                    total_pairs=overview.get(PAYLOAD_OVERVIEW_TOTAL_PAIRS),
                )
            )
        return SidebarJobsResponse(items=items, total=total)

    # NOTE: Must be registered BEFORE /optimizations/{optimization_id} to avoid route shadowing.

    @router.get(
        "/optimizations/stream",
        summary="Stream live dashboard updates (all active optimizations) as SSE",
    )
    async def stream_dashboard():
        """SSE feed of active-optimization snapshots every 3 seconds; closes with ``event: idle`` when the queue drains."""
        loop = asyncio.get_running_loop()

        async def event_generator():
            """Poll active optimizations every 3 seconds and yield SSE snapshots."""
            while True:
                active_rows = []
                for s in ("pending", "validating", "running"):
                    rows = await loop.run_in_executor(None, lambda st=s: job_store.list_jobs(status=st, limit=100))
                    active_rows.extend(rows)

                summaries = []
                for row in active_rows:
                    overview = parse_overview(row)
                    oid = row["optimization_id"]
                    log_count, progress_count = await asyncio.gather(
                        loop.run_in_executor(None, job_store.get_log_count, oid),
                        loop.run_in_executor(None, job_store.get_progress_count, oid),
                    )
                    summaries.append(
                        {
                            "optimization_id": oid,
                            "status": row.get("status", "pending"),
                            "name": overview.get(PAYLOAD_OVERVIEW_NAME),
                            "latest_metrics": row.get("latest_metrics", {}),
                            "log_count": log_count,
                            "progress_count": progress_count,
                        }
                    )

                yield f"data: {json.dumps({'active_jobs': summaries, 'active_count': len(summaries)}, default=str)}\n\n"

                if len(summaries) == 0:
                    yield f"event: idle\ndata: {json.dumps({'active_count': 0})}\n\n"
                    return

                await asyncio.sleep(3)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get(
        "/optimizations/{optimization_id}",
        response_model=OptimizationStatusResponse,
        summary="Full optimization detail with logs, progress, metrics, and result",
    )
    def get_job(optimization_id: str, request: Request) -> OptimizationStatusResponse:
        """Return full optimization detail: status, overview, timing, metrics, logs, progress, and result.

        Supports conditional GET via ``If-None-Match`` / ``ETag`` (304 when unchanged).
        Grid searches include partial ``grid_result`` while still running.
        Corrupted result data is omitted with a warning rather than 500ing.
        """

        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            logger.warning("Optimization status requested for unknown optimization_id=%s", optimization_id)
            raise HTTPException(
                status_code=404, detail=t("optimization.not_found", optimization_id=optimization_id)
            ) from None

        status = status_to_job_status(job_data.get("status", "pending"))

        progress_events = job_store.get_progress_events(optimization_id)
        logs = job_store.get_logs(optimization_id)

        overview = parse_overview(job_data)
        optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)

        result = None
        grid_result = None
        result_data = job_data.get("result")
        if result_data and isinstance(result_data, dict):
            try:
                if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
                    # Always include per-pair results so users can see what
                    # went wrong without a separate /grid-result call.
                    grid_result = GridSearchResponse.model_validate(result_data)
                elif status == OptimizationStatus.success:
                    result = RunResponse.model_validate(result_data)
            except ValidationError:
                logger.warning("Optimization %s has corrupted result data", optimization_id)

        created_at = parse_timestamp(job_data.get("created_at")) or datetime.now(timezone.utc)
        started_at = parse_timestamp(job_data.get("started_at"))
        completed_at = parse_timestamp(job_data.get("completed_at"))

        est_remaining = None
        if status not in TERMINAL_STATUSES:
            est_remaining = extract_estimated_remaining(job_data)

        latest_metrics = job_data.get("latest_metrics", {})
        completed_pairs = None
        failed_pairs = None
        if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
            if grid_result:
                completed_pairs = grid_result.completed_pairs
                failed_pairs = grid_result.failed_pairs
            else:
                live_completed = latest_metrics.get("completed_so_far")
                completed_pairs = live_completed if isinstance(live_completed, int) else 0
                live_failed = latest_metrics.get("failed_so_far")
                failed_pairs = live_failed if isinstance(live_failed, int) else 0

        elapsed_str, elapsed_secs = compute_elapsed(created_at, started_at, completed_at)

        logger.debug("Returning status for optimization_id=%s state=%s", optimization_id, status)
        response_data = OptimizationStatusResponse(
            optimization_id=optimization_id,
            status=status,
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            elapsed=elapsed_str,
            elapsed_seconds=elapsed_secs,
            estimated_remaining=est_remaining,
            **overview_to_base_fields(overview),
            message=job_data.get("message"),
            latest_metrics=latest_metrics,
            completed_pairs=completed_pairs,
            failed_pairs=failed_pairs,
            progress_events=progress_events,
            logs=[JobLogEntry(**log) for log in logs],
            result=result,
            grid_result=grid_result,
        )

        etag_src = f"{status}:{len(logs)}:{len(progress_events)}:{latest_metrics!s}"
        etag = '"' + hashlib.md5(etag_src.encode()).hexdigest()[:12] + '"'
        if_none_match = request.headers.get("if-none-match")
        if if_none_match == etag:
            return JSONResponse(status_code=304, content=None, headers={"ETag": etag})

        headers = {"ETag": etag}
        if status in TERMINAL_STATUSES:
            headers["Cache-Control"] = "private, max-age=60"
        else:
            headers["Cache-Control"] = "private, max-age=1"

        return JSONResponse(
            content=response_data.model_dump(mode="json"),
            headers=headers,
        )

    @router.get(
        "/optimizations/{optimization_id}/summary",
        response_model=OptimizationSummaryResponse,
        summary="Lightweight summary card for one optimization",
        tags=["agent"],
    )
    def get_job_summary(optimization_id: str) -> OptimizationSummaryResponse:
        """Return the compact dashboard-card shape for a single optimization. 404 if unknown."""

        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            logger.warning("Optimization summary requested for unknown optimization_id=%s", optimization_id)
            raise HTTPException(
                status_code=404, detail=t("optimization.not_found", optimization_id=optimization_id)
            ) from None

        job_data["progress_count"] = job_store.get_progress_count(optimization_id)
        job_data["log_count"] = job_store.get_log_count(optimization_id)
        return build_summary(job_data)

    @router.get(
        "/optimizations/{optimization_id}/dataset",
        summary="Reconstruct the train/val/test split used by this optimization",
    )
    def get_job_dataset(optimization_id: str) -> dict:
        """Reconstruct the train/val/test split deterministically from the stored seed.

        Each row includes its global dataset index for UI highlighting.
        404 if the optimization or dataset is missing; 500 on corrupted column mapping.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=t("optimization.not_found", optimization_id=optimization_id)
            ) from None

        payload = job_data.get("payload")
        if not payload or not isinstance(payload, dict):
            raise HTTPException(
                status_code=404,
                detail=t("optimization.payload_unavailable"),
            )

        dataset = payload.get("dataset")
        if not dataset or not isinstance(dataset, list):
            raise HTTPException(
                status_code=404,
                detail=t("optimization.dataset_unavailable"),
            )

        raw_mapping = payload.get("column_mapping", {})
        try:
            column_mapping = ColumnMapping.model_validate(raw_mapping)
        except ValidationError:
            raise HTTPException(
                status_code=500,
                detail=t("optimization.corrupt_column_mapping"),
            ) from None

        raw_fractions = payload.get("split_fractions", {})
        try:
            fractions = SplitFractions.model_validate(raw_fractions)
        except ValidationError:
            fractions = SplitFractions()

        shuffle = payload.get("shuffle", True)
        seed = payload.get("seed")

        # Replicate the split algorithm from service_gateway/data.py
        # When seed is None, derive a stable seed from optimization_id so repeated
        # calls produce the same shuffle (needed for index remapping).
        effective_seed = seed if seed is not None else hash(optimization_id) % (2**31)
        total = len(dataset)
        indices = list(range(total))
        if shuffle:
            rng = random.Random(effective_seed)
            rng.shuffle(indices)

        train_end = int(total * fractions.train)
        val_end = train_end + int(total * fractions.val)
        train_indices = indices[:train_end]
        val_indices = indices[train_end:val_end]
        test_indices = indices[val_end:]

        def _build_rows(idx_list: list[int]) -> list[dict]:
            """Wrap dataset rows with their original indices for UI highlighting."""
            return [{"index": i, "row": dataset[i]} for i in idx_list]

        splits = {
            "train": _build_rows(train_indices),
            "val": _build_rows(val_indices),
            "test": _build_rows(test_indices),
        }

        return {
            "total_rows": total,
            "splits": splits,
            "column_mapping": {
                "inputs": column_mapping.inputs,
                "outputs": column_mapping.outputs,
            },
            "split_counts": {
                "train": len(train_indices),
                "val": len(val_indices),
                "test": len(test_indices),
            },
        }

    @router.post(
        "/optimizations/{optimization_id}/evaluate-examples",
        summary="Run the optimized or baseline program on specific dataset rows",
    )
    def evaluate_examples(optimization_id: str, req: dict) -> dict:
        """Run the stored metric on specific dataset rows and return per-row scores.

        ``program_type``: ``"optimized"`` (default) or ``"baseline"`` (fresh unoptimized module).
        Out-of-range indices are silently skipped. Errors: 404/400/409.
        """
        indices = req.get("indices", [])
        program_type = req.get("program_type", "optimized")

        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=t("optimization.not_found", optimization_id=optimization_id)
            ) from None

        overview = parse_overview(job_data)
        payload = job_data.get("payload")
        if not payload or not isinstance(payload, dict):
            raise HTTPException(status_code=404, detail=t("optimization.no_payload"))

        dataset = payload.get("dataset", [])
        total = len(dataset)
        column_mapping_raw = payload.get("column_mapping", {})
        column_mapping = ColumnMapping.model_validate(column_mapping_raw)

        metric_code = payload.get("metric_code", "")
        if not metric_code:
            raise HTTPException(status_code=400, detail=t("optimization.no_metric_code"))
        metric = load_metric_from_code(metric_code)

        model_settings = payload.get("model_config") or overview.get(PAYLOAD_OVERVIEW_MODEL_SETTINGS, {})
        model_name_str = overview.get(PAYLOAD_OVERVIEW_MODEL_NAME, "")
        if model_settings:
            model_config = ModelConfig.model_validate(model_settings)
        elif model_name_str:
            model_config = ModelConfig(name=model_name_str)
        else:
            raise HTTPException(status_code=400, detail=t("optimization.no_model_config"))

        lm = build_language_model(model_config)

        if program_type == "baseline":
            signature_code = payload.get("signature_code", "")
            signature_cls = load_signature_from_code(signature_code)
            module_name = payload.get("module_name", "predict")
            module_kwargs = dict(payload.get("module_kwargs", {}))

            try:
                module_factory, auto_signature = resolve_module_factory(module_name)
            except ResolverError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if auto_signature or "signature" not in module_kwargs:
                module_kwargs["signature"] = signature_cls
            program = module_factory(**module_kwargs)
        else:
            result_data = job_data.get("result")
            if not result_data:
                raise HTTPException(status_code=409, detail=t("optimization.no_result_for_artifact"))
            result = RunResponse.model_validate(result_data)
            artifact = result.program_artifact
            if not artifact or not artifact.program_pickle_base64:
                raise HTTPException(status_code=409, detail=t("optimization.no_program_artifact"))
            if optimization_id not in _program_cache:
                program_bytes = base64.b64decode(artifact.program_pickle_base64)
                _program_cache[optimization_id] = pickle.loads(program_bytes)
            program = _program_cache[optimization_id]

        results = []
        with dspy.context(lm=lm):
            for idx in indices:
                if idx < 0 or idx >= total:
                    continue
                row = dataset[idx]
                example_dict = {}
                for sig_field, col_name in column_mapping.inputs.items():
                    example_dict[sig_field] = row.get(col_name, "")
                for sig_field, col_name in column_mapping.outputs.items():
                    example_dict[sig_field] = row.get(col_name, "")

                example = dspy.Example(**example_dict).with_inputs(*list(column_mapping.inputs.keys()))

                try:
                    prediction = program(**{k: example_dict[k] for k in column_mapping.inputs})
                    outputs = {}
                    for sig_field in column_mapping.outputs:
                        outputs[sig_field] = getattr(prediction, sig_field, None)

                    try:
                        score = metric(example, prediction)
                        score = float(score) if isinstance(score, (int, float, bool)) else 0.0
                    except Exception:
                        score = 0.0

                    results.append(
                        {
                            "index": idx,
                            "outputs": outputs,
                            "score": score,
                            "pass": score > 0,
                        }
                    )
                except Exception as exc:
                    results.append(
                        {
                            "index": idx,
                            "outputs": {},
                            "score": 0.0,
                            "pass": False,
                            "error": str(exc),
                        }
                    )

        return {"results": results, "program_type": program_type}

    @router.get(
        "/optimizations/{optimization_id}/test-results",
        summary="Per-example baseline and optimized test scores",
    )
    def get_test_results(optimization_id: str) -> dict:
        """Return stored per-example baseline and optimized scores from the test split.

        Sequential test-split indices are remapped to global dataset indices for UI use.
        No inference runs. 404 if unknown; 409 if no result yet.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=t("optimization.not_found", optimization_id=optimization_id)
            ) from None

        result_data = job_data.get("result")
        if not result_data:
            raise HTTPException(status_code=409, detail=t("optimization.no_result_pending"))

        result = RunResponse.model_validate(result_data)

        payload = job_data.get("payload", {})
        dataset = payload.get("dataset", [])
        total = len(dataset)
        fractions_raw = payload.get("split_fractions", {})
        fractions = SplitFractions.model_validate(fractions_raw)
        shuffle = payload.get("shuffle", True)
        seed = payload.get("seed")
        effective_seed = seed if seed is not None else hash(optimization_id) % (2**31)

        ordered = list(range(total))
        if shuffle:
            rng = random.Random(effective_seed)
            rng.shuffle(ordered)
        train_end = int(total * fractions.train)
        val_end = train_end + int(total * fractions.val)
        test_indices = ordered[val_end:]

        def remap(results: list) -> list:
            """Translate sequential test-split indices back to global dataset indices."""
            remapped = []
            for r in results:
                seq_idx = r.get("index", 0)
                global_idx = test_indices[seq_idx] if seq_idx < len(test_indices) else seq_idx
                remapped.append({**r, "index": global_idx})
            return remapped

        return {
            "baseline": remap(result.baseline_test_results),
            "optimized": remap(result.optimized_test_results),
        }

    @router.get(
        "/optimizations/{optimization_id}/artifact",
        response_model=ProgramArtifactResponse,
        summary="Download the compiled DSPy program artifact",
    )
    def get_job_artifact(optimization_id: str) -> ProgramArtifactResponse:
        """Return the pickled program artifact for a successful single-run optimization.

        Grid searches 404 here — use ``/grid-result`` instead (one artifact per pair).
        Errors: 404 (unknown or grid search), 409 (not yet successful), 500 (corrupted result).
        """

        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            logger.warning("Artifact requested for unknown optimization_id=%s", optimization_id)
            raise HTTPException(
                status_code=404, detail=t("optimization.not_found", optimization_id=optimization_id)
            ) from None

        overview = parse_overview(job_data)
        optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)

        if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
            raise HTTPException(
                status_code=404,
                detail=t("grid_search.artifact_per_pair_redirect"),
            )

        status = status_to_job_status(job_data.get("status", "pending"))

        if status in {OptimizationStatus.pending, OptimizationStatus.validating, OptimizationStatus.running}:
            raise HTTPException(status_code=409, detail=t("optimization.not_finished"))

        if status == OptimizationStatus.failed:
            error_msg = job_data.get("message") or "unknown error"
            raise HTTPException(
                status_code=409,
                detail=t("optimization.failed_no_artifact", error=error_msg),
            )

        if status == OptimizationStatus.cancelled:
            raise HTTPException(
                status_code=409,
                detail=t("optimization.cancelled_no_artifact"),
            )

        if status == OptimizationStatus.success:
            result_data = job_data.get("result")
            if result_data and isinstance(result_data, dict):
                try:
                    result = RunResponse.model_validate(result_data)
                except ValidationError:
                    logger.warning("Optimization %s has corrupted result data", optimization_id)
                    raise HTTPException(status_code=500, detail=t("optimization.corrupt_result")) from None
                return ProgramArtifactResponse(
                    program_artifact=result.program_artifact,
                )

        raise HTTPException(status_code=409, detail=t("optimization.no_artifact_generic"))

    @router.get(
        "/optimizations/{optimization_id}/grid-result",
        response_model=GridSearchResponse,
        summary="Retrieve the full grid-search result with per-pair details",
    )
    def get_grid_search_result(optimization_id: str) -> GridSearchResponse:
        """Return all pair results for a finished grid search, including ``best_pair``.

        Only valid after the sweep reaches a terminal status. For live progress use
        ``GET /optimizations/{id}`` (its ``grid_result`` field updates in-flight).
        Errors: 404 (unknown or not a grid search), 409 (running or failed with no result), 500 (corrupted).
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=t("optimization.not_found", optimization_id=optimization_id)
            ) from None

        overview = parse_overview(job_data)
        if overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE) != OPTIMIZATION_TYPE_GRID_SEARCH:
            raise HTTPException(status_code=404, detail=t("grid_search.not_a_grid_search"))

        status = status_to_job_status(job_data.get("status", "pending"))
        if status not in TERMINAL_STATUSES:
            raise HTTPException(status_code=409, detail=t("optimization.not_finished"))

        result_data = job_data.get("result")
        if not result_data or not isinstance(result_data, dict):
            if status == OptimizationStatus.failed:
                error_msg = job_data.get("message") or "unknown error"
                raise HTTPException(
                    status_code=409,
                    detail=t("grid_search.failed_no_result", error=error_msg),
                )
            if status == OptimizationStatus.cancelled:
                raise HTTPException(
                    status_code=409,
                    detail=t("grid_search.cancelled_no_result"),
                )
            raise HTTPException(status_code=404, detail=t("grid_search.no_result_available"))

        try:
            return GridSearchResponse.model_validate(result_data)
        except ValidationError:
            raise HTTPException(status_code=500, detail=t("grid_search.corrupt_result")) from None

    @router.post(
        "/optimizations/{optimization_id}/cancel",
        response_model=JobCancelResponse,
        status_code=200,
        summary="Cancel a pending or running optimization",
        tags=["agent"],
    )
    def cancel_job(optimization_id: str) -> JobCancelResponse:
        """Cooperatively cancel an active optimization.

        Flips status to ``cancelled`` immediately; the worker stops between DSPy calls.
        One-way — no uncancel. 404 if unknown; 409 if already terminal.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=t("optimization.not_found", optimization_id=optimization_id)
            ) from None

        status = status_to_job_status(job_data.get("status", "pending"))
        if status in TERMINAL_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=t("optimization.already_terminal", status=status.value),
            )

        worker = get_worker_ref()
        if worker:
            worker.cancel_job(optimization_id)

        now = datetime.now(timezone.utc).isoformat()
        job_store.update_job(optimization_id, status="cancelled", message=CANCELLATION_REASON, completed_at=now)
        logger.info("Optimization %s (%s) cancelled", optimization_id, status.value)
        return JobCancelResponse(optimization_id=optimization_id, status="cancelled")

    @router.delete(
        "/optimizations/{optimization_id}",
        response_model=JobDeleteResponse,
        status_code=200,
        summary="Permanently delete an optimization and all its data",
        tags=["agent"],
    )
    def delete_job(optimization_id: str) -> JobDeleteResponse:
        """Hard-delete an optimization and all its data (not recoverable).

        Only terminal optimizations can be deleted — cancel first if still active.
        Use ``PATCH /archive`` for soft-hide. 404 if unknown; 409 if non-terminal.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=t("optimization.not_found", optimization_id=optimization_id)
            ) from None

        status = status_to_job_status(job_data.get("status", "pending"))
        if status not in TERMINAL_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=t("optimization.cannot_delete", status=status.value),
            )

        job_store.delete_job(optimization_id)
        logger.info("Optimization %s deleted", optimization_id)
        return JobDeleteResponse(optimization_id=optimization_id, deleted=True)

    @router.delete(
        "/optimizations/{optimization_id}/pair/{pair_index}",
        response_model=GridSearchResponse,
        status_code=200,
        summary="Delete a single pair from a grid-search result",
    )
    def delete_grid_pair(optimization_id: str, pair_index: int) -> GridSearchResponse:
        """Remove one pair from a terminal grid search and return the updated grid result.

        Drops the pair from ``grid_result.pair_results``, clears its cached program,
        and recomputes ``total_pairs`` / ``completed_pairs`` / ``failed_pairs`` / ``best_pair``.
        The stored result JSON is rewritten in place.

        Errors: 404 (unknown optimization, not a grid search, or pair missing),
        409 (grid search is not in a terminal state — cancel it first).
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=t("optimization.not_found", optimization_id=optimization_id)
            ) from None

        overview = parse_overview(job_data)
        if overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE) != OPTIMIZATION_TYPE_GRID_SEARCH:
            raise HTTPException(status_code=404, detail=t("grid_search.not_a_grid_search"))

        status = status_to_job_status(job_data.get("status", "pending"))
        if status not in TERMINAL_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=t("grid_search.cannot_delete_pair", status=status.value),
            )

        result_data = job_data.get("result")
        if not result_data or not isinstance(result_data, dict):
            raise HTTPException(status_code=404, detail=t("grid_search.no_result_to_modify"))

        try:
            grid_result = GridSearchResponse.model_validate(result_data)
        except ValidationError:
            raise HTTPException(status_code=500, detail=t("grid_search.corrupt_result")) from None

        remaining = [pr for pr in grid_result.pair_results if pr.pair_index != pair_index]
        if len(remaining) == len(grid_result.pair_results):
            raise HTTPException(
                status_code=404,
                detail=t("grid_search.pair_position_missing", pair_index=pair_index),
            )

        successful = [pr for pr in remaining if not pr.error and pr.optimized_test_metric is not None]
        failed = [pr for pr in remaining if pr.error]
        best = None
        if successful:
            best = max(successful, key=lambda pr: pr.optimized_test_metric or 0.0)

        updated = grid_result.model_copy(
            update={
                "pair_results": remaining,
                "total_pairs": len(remaining),
                "completed_pairs": len(successful),
                "failed_pairs": len(failed),
                "best_pair": best,
            }
        )

        job_store.update_job(optimization_id, result=updated.model_dump(mode="json"))
        _program_cache.pop(f"{optimization_id}_pair_{pair_index}", None)
        # Invalidate the single-program cache entry too (best pair may have changed).
        _program_cache.pop(optimization_id, None)
        logger.info("Optimization %s pair %d deleted", optimization_id, pair_index)
        return updated

    @router.post(
        "/optimizations/bulk-cancel",
        response_model=BulkCancelResponse,
        status_code=200,
        summary="Cancel many running or pending optimizations in a single request",
        tags=["agent"],
    )
    def bulk_cancel_jobs(body: BulkCancelRequest) -> BulkCancelResponse:
        """Cancel a batch of non-terminal optimizations; returns per-ID skip reasons for non-cancellable IDs.

        Same semantics as single-ID ``POST /optimizations/{id}/cancel``:
        flips status to ``cancelled`` immediately, worker stops between
        DSPy calls, one-way. IDs that don't exist or are already terminal
        are reported in ``skipped`` with the reason.
        """
        cancelled: list[str] = []
        skipped: list[BulkCancelSkipped] = []
        seen: set[str] = set()
        ordered_unique: list[str] = []
        for optimization_id in body.optimization_ids:
            if optimization_id in seen:
                continue
            seen.add(optimization_id)
            ordered_unique.append(optimization_id)

        if not ordered_unique:
            return BulkCancelResponse(cancelled=cancelled, skipped=skipped)

        status_by_id = job_store.get_jobs_status_by_ids(ordered_unique)

        cancellable: list[str] = []
        for optimization_id in ordered_unique:
            raw_status = status_by_id.get(optimization_id)
            if raw_status is None:
                skipped.append(BulkCancelSkipped(optimization_id=optimization_id, reason="not_found"))
                continue
            status = status_to_job_status(raw_status)
            if status in TERMINAL_STATUSES:
                skipped.append(BulkCancelSkipped(optimization_id=optimization_id, reason=status.value))
                continue
            cancellable.append(optimization_id)

        if cancellable:
            worker = get_worker_ref()
            now = datetime.now(timezone.utc).isoformat()
            for optimization_id in cancellable:
                try:
                    if worker:
                        worker.cancel_job(optimization_id)
                    job_store.update_job(
                        optimization_id,
                        status="cancelled",
                        message=CANCELLATION_REASON,
                        completed_at=now,
                    )
                except Exception as exc:
                    logger.exception("Bulk cancel failed for %s", optimization_id)
                    skipped.append(
                        BulkCancelSkipped(
                            optimization_id=optimization_id,
                            reason=f"error: {exc}",
                        )
                    )
                else:
                    cancelled.append(optimization_id)

        logger.info(
            "Bulk cancel: %d cancelled, %d skipped (requested %d)",
            len(cancelled),
            len(skipped),
            len(body.optimization_ids),
        )
        return BulkCancelResponse(cancelled=cancelled, skipped=skipped)

    @router.post(
        "/optimizations/bulk-delete",
        response_model=BulkDeleteResponse,
        status_code=200,
        summary="Delete many optimizations in a single request",
        tags=["agent"],
    )
    def bulk_delete_jobs(body: BulkDeleteRequest) -> BulkDeleteResponse:
        """Delete a batch of terminal optimizations; returns per-ID skip reasons for non-deletable IDs."""
        deleted: list[str] = []
        skipped: list[BulkDeleteSkipped] = []
        seen: set[str] = set()
        ordered_unique: list[str] = []
        for optimization_id in body.optimization_ids:
            if optimization_id in seen:
                continue
            seen.add(optimization_id)
            ordered_unique.append(optimization_id)

        if not ordered_unique:
            return BulkDeleteResponse(deleted=deleted, skipped=skipped)

        status_by_id = job_store.get_jobs_status_by_ids(ordered_unique)

        deletable: list[str] = []
        for optimization_id in ordered_unique:
            raw_status = status_by_id.get(optimization_id)
            if raw_status is None:
                skipped.append(BulkDeleteSkipped(optimization_id=optimization_id, reason="not_found"))
                continue
            status = status_to_job_status(raw_status)
            if status not in TERMINAL_STATUSES:
                skipped.append(BulkDeleteSkipped(optimization_id=optimization_id, reason=status.value))
                continue
            deletable.append(optimization_id)

        if deletable:
            try:
                job_store.delete_jobs(deletable)
            except Exception as exc:
                logger.exception("Bulk delete failed for %d ids", len(deletable))
                for optimization_id in deletable:
                    skipped.append(
                        BulkDeleteSkipped(
                            optimization_id=optimization_id,
                            reason=f"error: {exc}",
                        )
                    )
            else:
                deleted.extend(deletable)

        logger.info(
            "Bulk delete: %d deleted, %d skipped (requested %d)",
            len(deleted),
            len(skipped),
            len(body.optimization_ids),
        )
        return BulkDeleteResponse(deleted=deleted, skipped=skipped)

    @router.get(
        "/optimizations/{optimization_id}/stream",
        summary="Stream one optimization's live status updates as SSE",
    )
    async def stream_job(optimization_id: str):
        """SSE stream for one optimization: status + metrics every 2 s, then ``event: done`` on terminal.

        Pre-flight 404 if the optimization ID is unknown.
        """
        loop = asyncio.get_running_loop()
        try:
            raw = await loop.run_in_executor(None, job_store.get_job, optimization_id)
        except KeyError:
            raw = None
        if raw is None:
            raise HTTPException(
                status_code=404, detail=t("optimization.not_found", optimization_id=optimization_id)
            ) from None

        terminal = {"success", "failed", "cancelled"}

        async def event_generator():
            while True:
                raw = await loop.run_in_executor(None, job_store.get_job, optimization_id)
                if raw is None:
                    yield f"event: error\ndata: {json.dumps({'error': 'Optimization not found'})}\n\n"
                    return

                status = raw.get("status", "pending")
                metrics = raw.get("latest_metrics", {})
                log_count, progress_count = await asyncio.gather(
                    loop.run_in_executor(None, job_store.get_log_count, optimization_id),
                    loop.run_in_executor(None, job_store.get_progress_count, optimization_id),
                )
                payload = {
                    "optimization_id": optimization_id,
                    "status": status,
                    "message": raw.get("message"),
                    "latest_metrics": metrics,
                    "log_count": log_count,
                    "progress_count": progress_count,
                }

                yield f"data: {json.dumps(payload, default=str)}\n\n"

                if status in terminal:
                    yield f"event: done\ndata: {json.dumps({'status': status})}\n\n"
                    return

                await asyncio.sleep(2)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get(
        "/optimizations/{optimization_id}/pair/{pair_index}/test-results",
        summary="Per-example test scores for one grid-search pair",
    )
    def get_pair_test_results(optimization_id: str, pair_index: int) -> dict:
        """Per-pair analogue of ``GET /test-results`` with global-index remapping.

        ``pair_index`` matches ``pair_results[*].pair_index`` from ``/grid-result``.
        Errors: 404 (unknown or pair missing), 409 (not grid search, not success, or no result).
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=t("optimization.not_found", optimization_id=optimization_id)
            ) from None

        overview = parse_overview(job_data)
        optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)

        if optimization_type != OPTIMIZATION_TYPE_GRID_SEARCH:
            raise HTTPException(
                status_code=409,
                detail=t("grid_search.pair_test_results_grid_only"),
            )

        status = status_to_job_status(job_data.get("status", "pending"))
        if status != OptimizationStatus.success:
            raise HTTPException(
                status_code=409,
                detail=t("optimization.not_success_status_for_test_results", status=status.value),
            )

        result_data = job_data.get("result")
        if not result_data or not isinstance(result_data, dict):
            raise HTTPException(status_code=409, detail=t("optimization.no_result"))

        grid_result = GridSearchResponse.model_validate(result_data)

        pair = None
        for pr in grid_result.pair_results:
            if pr.pair_index == pair_index:
                pair = pr
                break
        if pair is None:
            raise HTTPException(
                status_code=404,
                detail=t("grid_search.pair_position_missing", pair_index=pair_index),
            )

        payload = job_data.get("payload", {})
        dataset = payload.get("dataset", [])
        total = len(dataset)
        fractions_raw = payload.get("split_fractions", {})
        fractions = SplitFractions.model_validate(fractions_raw)
        shuffle = payload.get("shuffle", True)
        seed = payload.get("seed")
        effective_seed = seed if seed is not None else hash(optimization_id) % (2**31)

        ordered = list(range(total))
        if shuffle:
            rng = random.Random(effective_seed)
            rng.shuffle(ordered)
        train_end = int(total * fractions.train)
        val_end = train_end + int(total * fractions.val)
        test_indices = ordered[val_end:]

        def remap(results: list) -> list:
            """Translate sequential test-split indices back to global dataset indices."""
            remapped = []
            for r in results:
                seq_idx = r.get("index", 0)
                global_idx = test_indices[seq_idx] if seq_idx < len(test_indices) else seq_idx
                remapped.append({**r, "index": global_idx})
            return remapped

        return {
            "baseline": remap(pair.baseline_test_results),
            "optimized": remap(pair.optimized_test_results),
        }

    def _clone_payload(
        source_payload: dict,
        *,
        optimization_type: str,
        new_name: str | None,
    ) -> tuple[str, Any]:
        """Return ``(new_optimization_id, payload_model)`` from a stored payload dict.

        Re-parses the stored payload into the original Pydantic request model,
        assigns a fresh UUID and seed, and overrides the display name if given.
        """
        copy = dict(source_payload)
        if new_name is not None:
            copy["name"] = new_name
        request_cls = GridSearchRequest if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH else RunRequest
        try:
            payload = request_cls.model_validate(copy)
        except ValidationError as exc:
            raise HTTPException(
                status_code=500,
                detail=t("optimization.cannot_resubmit_payload", error=exc.errors()[0]["msg"]),
            ) from exc
        new_id = str(uuid4())
        payload.seed = hash(new_id) % (2**31)
        return new_id, payload

    def _persist_and_enqueue(new_id: str, payload: Any, *, optimization_type: str) -> OptimizationSubmissionResponse:
        """Shared persistence path for clone and retry.

        Writes the overview dict the same way /run and /grid-search do, then
        hands the payload to the background worker.
        """
        fingerprint = compute_task_fingerprint(payload.signature_code, payload.metric_code, payload.dataset)
        is_grid = optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH

        overview: dict[str, Any] = {
            PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE: optimization_type,
            PAYLOAD_OVERVIEW_NAME: payload.name,
            "description": payload.description,
            PAYLOAD_OVERVIEW_USERNAME: payload.username,
            PAYLOAD_OVERVIEW_MODULE_NAME: payload.module_name,
            "module_kwargs": dict(payload.module_kwargs),
            PAYLOAD_OVERVIEW_OPTIMIZER_NAME: payload.optimizer_name,
            "column_mapping": payload.column_mapping.model_dump(),
            "dataset_rows": len(payload.dataset),
            "dataset_filename": payload.dataset_filename,
            "split_fractions": payload.split_fractions.model_dump(),
            "shuffle": payload.shuffle,
            "seed": payload.seed,
            "optimizer_kwargs": dict(payload.optimizer_kwargs),
            "compile_kwargs": dict(payload.compile_kwargs),
            "task_fingerprint": fingerprint,
        }
        if is_grid:
            overview[PAYLOAD_OVERVIEW_TOTAL_PAIRS] = len(payload.generation_models) * len(payload.reflection_models)
            overview["generation_models"] = [m.model_dump() for m in payload.generation_models]
            overview["reflection_models"] = [m.model_dump() for m in payload.reflection_models]
        else:
            overview[PAYLOAD_OVERVIEW_MODEL_NAME] = payload.model_settings.normalized_identifier()
            overview[PAYLOAD_OVERVIEW_MODEL_SETTINGS] = strip_api_key(payload.model_settings.model_dump())

        job_store.create_job(new_id)
        job_store.set_payload_overview(new_id, overview)

        worker = get_worker(job_store, service=None)
        worker.submit_job(new_id, payload)

        notify_job_started(
            optimization_id=new_id,
            username=payload.username,
            optimization_type=optimization_type,
            optimizer_name=payload.optimizer_name,
            module_name=payload.module_name,
            model_name=(
                t(
                    "optimization.pairs_label",
                    count=overview.get(PAYLOAD_OVERVIEW_TOTAL_PAIRS, 0),
                )
                if is_grid
                else payload.model_settings.normalized_identifier()
            ),
        )
        return OptimizationSubmissionResponse(
            optimization_id=new_id,
            optimization_type=optimization_type,
            status=OptimizationStatus.pending,
            created_at=datetime.now(timezone.utc),
            name=payload.name,
            username=payload.username,
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
        )

    @router.post(
        "/optimizations/{optimization_id}/clone",
        response_model=CloneJobResponse,
        status_code=201,
        summary="Duplicate an optimization and queue N copies",
        tags=["agent"],
    )
    def clone_job(optimization_id: str, req: CloneJobRequest) -> CloneJobResponse:
        """Clone a finished or active optimization into ``count`` fresh runs.

        Reads the stored payload, assigns new ids and seeds, and enqueues each
        copy. Each clone's display name is prefixed with ``name_prefix`` or
        ``CLONE_NAME_PREFIX``. Respects the per-user quota.
        Errors: 404 (unknown), 409 (quota).
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=t("optimization.not_found", optimization_id=optimization_id)
            ) from None

        source_payload = job_data.get("payload")
        if not source_payload or not isinstance(source_payload, dict):
            raise HTTPException(status_code=409, detail=t("optimization.clone_no_payload"))

        overview = parse_overview(job_data)
        optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)
        prefix = (req.name_prefix or CLONE_NAME_PREFIX).strip()
        source_name = overview.get(PAYLOAD_OVERVIEW_NAME) or optimization_id[:8]
        username = source_payload.get("username") or overview.get(PAYLOAD_OVERVIEW_USERNAME)

        enforce_user_quota(job_store, username)

        created: list[OptimizationSubmissionResponse] = []
        for i in range(req.count):
            suffix = f" ({i + 1})" if req.count > 1 else ""
            cloned_name = f"{prefix} {source_name}{suffix}".strip()
            new_id, payload = _clone_payload(
                source_payload,
                optimization_type=optimization_type,
                new_name=cloned_name,
            )
            created.append(_persist_and_enqueue(new_id, payload, optimization_type=optimization_type))

        logger.info("Cloned optimization %s into %d copies", optimization_id, len(created))
        return CloneJobResponse(source_optimization_id=optimization_id, created=created)

    @router.post(
        "/optimizations/{optimization_id}/retry",
        response_model=OptimizationSubmissionResponse,
        status_code=201,
        summary="Re-run a failed or cancelled optimization with the same configuration",
        tags=["agent"],
    )
    def retry_job(optimization_id: str) -> OptimizationSubmissionResponse:
        """Re-run a failed or cancelled optimization using the original payload.

        Only valid when the source optimization is in a terminal non-success state.
        The new run's name is prefixed with ``RETRY_NAME_PREFIX``. Errors:
        404 (unknown), 409 (source still running or succeeded — use clone instead).
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=t("optimization.not_found", optimization_id=optimization_id)
            ) from None

        status = status_to_job_status(job_data.get("status", "pending"))
        if status not in {OptimizationStatus.failed, OptimizationStatus.cancelled}:
            raise HTTPException(
                status_code=409,
                detail=t("optimization.retry_wrong_status", status=status.value),
            )

        source_payload = job_data.get("payload")
        if not source_payload or not isinstance(source_payload, dict):
            raise HTTPException(status_code=409, detail=t("optimization.retry_no_payload"))

        overview = parse_overview(job_data)
        optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)
        username = source_payload.get("username") or overview.get(PAYLOAD_OVERVIEW_USERNAME)
        enforce_user_quota(job_store, username)

        source_name = overview.get(PAYLOAD_OVERVIEW_NAME) or optimization_id[:8]
        retry_name = f"{RETRY_NAME_PREFIX} {source_name}".strip()
        new_id, payload = _clone_payload(source_payload, optimization_type=optimization_type, new_name=retry_name)
        response = _persist_and_enqueue(new_id, payload, optimization_type=optimization_type)
        logger.info("Retried optimization %s as %s", optimization_id, new_id)
        return response

    @router.post(
        "/optimizations/compare",
        response_model=CompareJobsResponse,
        summary="Compare 2–5 optimizations side-by-side",
        tags=["agent"],
    )
    def compare_jobs(req: CompareJobsRequest) -> CompareJobsResponse:
        """Return a compact side-by-side comparison of 2–5 optimizations.

        Reads each optimization's overview and metrics. Also returns ``differing_fields``
        — a list of the config-level fields whose values disagree across the
        optimizations (module, optimizer, model, dataset size). Missing ids are returned
        in ``missing_optimization_ids`` rather than causing a 404.
        """
        snapshots: list[CompareJobSnapshot] = []
        missing: list[str] = []
        seen: set[str] = set()

        for oid in req.optimization_ids:
            if oid in seen:
                continue
            seen.add(oid)
            try:
                job_data = job_store.get_job(oid)
            except KeyError:
                missing.append(oid)
                continue

            overview = parse_overview(job_data)
            status = status_to_job_status(job_data.get("status", "pending"))
            optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)

            baseline: float | None = None
            optimized_metric: float | None = None
            result_data = job_data.get("result")
            if isinstance(result_data, dict):
                if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
                    best_pair = result_data.get("best_pair")
                    if isinstance(best_pair, dict):
                        baseline = best_pair.get("baseline_test_metric")
                        optimized_metric = best_pair.get("optimized_test_metric")
                else:
                    baseline = result_data.get("baseline_test_metric")
                    optimized_metric = result_data.get("optimized_test_metric")

            improvement = None
            if baseline is not None and optimized_metric is not None:
                improvement = round(optimized_metric - baseline, 6)

            snapshots.append(
                CompareJobSnapshot(
                    optimization_id=oid,
                    status=status.value,
                    name=overview.get(PAYLOAD_OVERVIEW_NAME),
                    optimization_type=optimization_type,
                    module_name=overview.get(PAYLOAD_OVERVIEW_MODULE_NAME),
                    optimizer_name=overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_NAME),
                    model_name=overview.get(PAYLOAD_OVERVIEW_MODEL_NAME),
                    dataset_rows=overview.get("dataset_rows"),
                    baseline_test_metric=baseline,
                    optimized_test_metric=optimized_metric,
                    metric_improvement=improvement,
                )
            )

        differing_fields: list[str] = []
        if len(snapshots) >= 2:
            candidate_fields = [
                "module_name",
                "optimizer_name",
                "model_name",
                "optimization_type",
                "dataset_rows",
            ]
            for field in candidate_fields:
                values = {getattr(s, field) for s in snapshots}
                if len(values) > 1:
                    differing_fields.append(field)

        return CompareJobsResponse(
            jobs=snapshots,
            differing_fields=differing_fields,
            missing_optimization_ids=missing,
        )

    def _bulk_set_flag(req: BulkMetadataRequest, *, flag: str) -> BulkMetadataResponse:
        """Shared bulk-metadata update used by /bulk-pin and /bulk-archive."""
        updated: list[str] = []
        skipped: list[BulkMetadataSkipped] = []
        seen: set[str] = set()
        for oid in req.optimization_ids:
            if oid in seen:
                continue
            seen.add(oid)
            try:
                job_data = job_store.get_job(oid)
            except KeyError:
                skipped.append(BulkMetadataSkipped(optimization_id=oid, reason="not_found"))
                continue
            overview = parse_overview(job_data)
            overview[flag] = bool(req.value)
            job_store.set_payload_overview(oid, overview)
            updated.append(oid)
        return BulkMetadataResponse(updated=updated, skipped=skipped)

    @router.post(
        "/optimizations/bulk-pin",
        response_model=BulkMetadataResponse,
        summary="Pin or unpin many optimizations in one call",
        tags=["agent"],
    )
    def bulk_pin_jobs(req: BulkMetadataRequest) -> BulkMetadataResponse:
        """Pin or unpin up to 100 optimizations. Missing ids are returned under ``skipped``."""
        return _bulk_set_flag(req, flag="pinned")

    @router.post(
        "/optimizations/bulk-archive",
        response_model=BulkMetadataResponse,
        summary="Archive or unarchive many optimizations in one call",
        tags=["agent"],
    )
    def bulk_archive_jobs(req: BulkMetadataRequest) -> BulkMetadataResponse:
        """Archive or unarchive up to 100 optimizations. Missing ids are returned under ``skipped``."""
        return _bulk_set_flag(req, flag="archived")

    return router
