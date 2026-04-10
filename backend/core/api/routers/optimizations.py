"""Routes for the core optimizations resource (list, detail, lifecycle)."""
from __future__ import annotations

import hashlib
import logging
import random
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from starlette.responses import StreamingResponse

from ...constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_JOB_TYPE,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODEL_SETTINGS,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
    PAYLOAD_OVERVIEW_TOTAL_PAIRS,
    PAYLOAD_OVERVIEW_USERNAME,
)
from ...models import (
    ColumnMapping,
    GridSearchResponse,
    JobCancelResponse,
    JobDeleteResponse,
    JobLogEntry,
    ModelConfig,
    OptimizationStatus,
    OptimizationStatusResponse,
    OptimizationSummaryResponse,
    PaginatedJobsResponse,
    ProgramArtifactResponse,
    RunResponse,
    SplitFractions,
)
from ..converters import (
    compute_elapsed,
    extract_estimated_remaining,
    overview_to_base_fields,
    parse_overview,
    parse_timestamp,
    status_to_job_status,
)
from ._helpers import (
    _TERMINAL_STATUSES,
    _VALID_JOB_TYPES,
    _VALID_STATUSES,
    _program_cache,
    build_summary,
)

logger = logging.getLogger(__name__)


class SidebarJobItem(BaseModel):
    optimization_id: str
    status: str
    name: Optional[str] = None
    module_name: Optional[str] = None
    optimizer_name: Optional[str] = None
    model_name: Optional[str] = None
    username: Optional[str] = None
    created_at: Optional[datetime] = None
    pinned: bool = False
    optimization_type: Optional[str] = None
    total_pairs: Optional[int] = None


class SidebarJobsResponse(BaseModel):
    items: list[SidebarJobItem]
    total: int


def create_optimizations_router(*, job_store, get_worker_ref: Callable[[], Any]) -> APIRouter:
    """Build the optimizations router.

    Args:
        job_store: Active job store instance.
        get_worker_ref: Callable returning the current BackgroundWorker (or None).
            Used by the cancel endpoint, which needs the live worker populated
            by the app lifespan — can't be captured eagerly.

    Returns:
        APIRouter: Router with all ``/optimizations/*`` core routes.
    """
    router = APIRouter()

    @router.get("/optimizations", response_model=PaginatedJobsResponse)
    def list_jobs(
        status: Optional[str] = Query(default=None, description="Filter by job status"),
        username: Optional[str] = Query(default=None, description="Filter by username"),
        optimization_type: Optional[str] = Query(default=None, description="Filter by job type (run or grid_search)"),
        limit: int = Query(default=50, ge=1, le=500, description="Max results"),
        offset: int = Query(default=0, ge=0, description="Skip N results"),
    ) -> PaginatedJobsResponse:
        """List all jobs with optional filtering and pagination.

        Args:
            status: Optional status filter.
            username: Optional username filter.
            optimization_type: Optional job type filter ('run' or 'grid_search').
            limit: Maximum number of jobs to return.
            offset: Number of jobs to skip.

        Returns:
            PaginatedJobsResponse: Paginated jobs ordered by creation time (newest first).
        """
        if status is not None and status not in _VALID_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status filter '{status}'. Valid values: {sorted(_VALID_STATUSES)}",
            )
        if optimization_type is not None and optimization_type not in _VALID_JOB_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid optimization_type filter '{optimization_type}'. Valid values: {sorted(_VALID_JOB_TYPES)}",
            )
        total = job_store.count_jobs(status=status, username=username, optimization_type=optimization_type)
        rows = job_store.list_jobs(status=status, username=username, optimization_type=optimization_type, limit=limit, offset=offset)
        items = [build_summary(job_data) for job_data in rows]
        return PaginatedJobsResponse(items=items, total=total, limit=limit, offset=offset)

    @router.get("/optimizations/sidebar", response_model=SidebarJobsResponse)
    def list_jobs_sidebar(
        username: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> SidebarJobsResponse:
        """Lightweight job listing for sidebar navigation.

        Returns only the minimal fields needed for the sidebar (no result
        data, metrics, or logs). Much faster than the full /jobs endpoint.
        """
        total = job_store.count_jobs(username=username)
        rows = job_store.list_jobs(username=username, limit=limit, offset=offset)
        items = []
        for row in rows:
            overview = parse_overview(row)
            items.append(SidebarJobItem(
                optimization_id=row["optimization_id"],
                status=row.get("status", "pending"),
                name=overview.get(PAYLOAD_OVERVIEW_NAME),
                module_name=overview.get(PAYLOAD_OVERVIEW_MODULE_NAME),
                optimizer_name=overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_NAME),
                model_name=overview.get(PAYLOAD_OVERVIEW_MODEL_NAME),
                username=overview.get(PAYLOAD_OVERVIEW_USERNAME),
                created_at=parse_timestamp(row.get("created_at")),
                pinned=bool(overview.get("pinned", False)),
                optimization_type=overview.get(PAYLOAD_OVERVIEW_JOB_TYPE),
                total_pairs=overview.get(PAYLOAD_OVERVIEW_TOTAL_PAIRS),
            ))
        return SidebarJobsResponse(items=items, total=total)

    # ── Server-Sent Events (SSE) for real-time dashboard streaming ──
    # NOTE: Must be registered BEFORE /optimizations/{optimization_id} to avoid route shadowing.

    @router.get("/optimizations/stream")
    async def stream_dashboard():
        """Stream dashboard-level updates via Server-Sent Events.

        Sends a JSON event every 3 seconds with a summary of all active jobs.
        Sends an 'idle' event and closes when no active jobs remain.
        """
        import asyncio
        import json

        async def event_generator():
            while True:
                active_rows = []
                for s in ("pending", "validating", "running"):
                    active_rows.extend(
                        job_store.list_jobs(status=s, limit=100)
                    )

                summaries = []
                for row in active_rows:
                    overview = parse_overview(row)
                    summaries.append({
                        "optimization_id": row["optimization_id"],
                        "status": row.get("status", "pending"),
                        "name": overview.get(PAYLOAD_OVERVIEW_NAME),
                        "latest_metrics": row.get("latest_metrics", {}),
                        "log_count": job_store.get_log_count(row["optimization_id"]),
                        "progress_count": job_store.get_progress_count(row["optimization_id"]),
                    })

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

    @router.get("/optimizations/{optimization_id}", response_model=OptimizationStatusResponse)
    def get_job(optimization_id: str, request: Request) -> OptimizationStatusResponse:
        """Return the status of a queued or running job.

        Supports conditional GET via ETag/If-None-Match for caching.

        Args:
            optimization_id: Identifier returned during submission.

        Returns:
            OptimizationStatusResponse: Current job metadata and latest metrics.

        Raises:
            HTTPException: If the job is not found.
        """

        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            logger.warning("Optimization status requested for unknown optimization_id=%s", optimization_id)
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.")

        status = status_to_job_status(job_data.get("status", "pending"))

        progress_events = job_store.get_progress_events(optimization_id)
        logs = job_store.get_logs(optimization_id)

        overview = parse_overview(job_data)
        optimization_type = overview.get(PAYLOAD_OVERVIEW_JOB_TYPE, OPTIMIZATION_TYPE_RUN)

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

        # Only show estimated_remaining for active jobs
        est_remaining = None
        if status not in _TERMINAL_STATUSES:
            est_remaining = extract_estimated_remaining(job_data)

        # Pair counters for grid search jobs
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

        # ETag based on status + metrics hash for conditional GET
        etag_src = f"{status}:{len(logs)}:{len(progress_events)}:{str(latest_metrics)}"
        etag = '"' + hashlib.md5(etag_src.encode()).hexdigest()[:12] + '"'
        if_none_match = request.headers.get("if-none-match")
        if if_none_match == etag:
            return JSONResponse(status_code=304, content=None, headers={"ETag": etag})

        # For terminal jobs, allow longer caching
        headers = {"ETag": etag}
        if status in _TERMINAL_STATUSES:
            headers["Cache-Control"] = "private, max-age=60"
        else:
            headers["Cache-Control"] = "private, max-age=1"

        return JSONResponse(
            content=response_data.model_dump(mode="json"),
            headers=headers,
        )

    @router.get("/optimizations/{optimization_id}/summary", response_model=OptimizationSummaryResponse)
    def get_job_summary(optimization_id: str) -> OptimizationSummaryResponse:
        """Return a coarse summary of job progress and metadata.

        Args:
            optimization_id: Identifier for the job returned during submission.

        Returns:
            OptimizationSummaryResponse: Aggregated job metadata and timing information.
        """

        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            logger.warning("Optimization summary requested for unknown optimization_id=%s", optimization_id)
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.")

        job_data["progress_count"] = job_store.get_progress_count(optimization_id)
        job_data["log_count"] = job_store.get_log_count(optimization_id)
        return build_summary(job_data)

    @router.get("/optimizations/{optimization_id}/dataset")
    def get_job_dataset(optimization_id: str) -> dict:
        """Return the dataset rows grouped by split (train/val/test).

        Args:
            optimization_id: Identifier for the job returned during submission.

        Returns:
            dict: Dataset rows partitioned into splits with metadata.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.")

        payload = job_data.get("payload")
        if not payload or not isinstance(payload, dict):
            raise HTTPException(
                status_code=404,
                detail="Payload not available for this job.",
            )

        dataset = payload.get("dataset")
        if not dataset or not isinstance(dataset, list):
            raise HTTPException(
                status_code=404,
                detail="Dataset not available for this job.",
            )

        # Parse column mapping
        raw_mapping = payload.get("column_mapping", {})
        try:
            column_mapping = ColumnMapping.model_validate(raw_mapping)
        except ValidationError:
            raise HTTPException(
                status_code=500,
                detail="Stored column mapping is invalid.",
            )

        # Parse split fractions (fall back to defaults)
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

    @router.post("/optimizations/{optimization_id}/evaluate-examples")
    def evaluate_examples(optimization_id: str, req: dict) -> dict:
        """Evaluate examples using the actual metric function.

        Body: { "indices": [0,1,...], "program_type": "optimized"|"baseline" }
        Returns per-example results with predictions and metric scores.
        """
        import base64
        import pickle

        import dspy

        from ...service_gateway.data import (
            load_metric_from_code,
            load_signature_from_code,
        )
        from ...service_gateway.language_models import build_language_model

        indices = req.get("indices", [])
        program_type = req.get("program_type", "optimized")

        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.")

        overview = parse_overview(job_data)
        payload = job_data.get("payload")
        if not payload or not isinstance(payload, dict):
            raise HTTPException(status_code=404, detail="Optimization has no payload.")

        dataset = payload.get("dataset", [])
        column_mapping_raw = payload.get("column_mapping", {})
        column_mapping = ColumnMapping.model_validate(column_mapping_raw)
        fractions_raw = payload.get("split_fractions", {})
        fractions = SplitFractions.model_validate(fractions_raw)
        shuffle = payload.get("shuffle", True)
        seed = payload.get("seed")

        # Reconstruct splits to identify test rows
        total = len(dataset)
        ordered = list(range(total))
        if shuffle:
            rng = random.Random(seed)
            rng.shuffle(ordered)
        train_end = int(total * fractions.train)
        val_end = train_end + int(total * fractions.val)
        test_indices_set = set(ordered[val_end:])

        # Load metric
        metric_code = payload.get("metric_code", "")
        if not metric_code:
            raise HTTPException(status_code=400, detail="Optimization has no metric code.")
        metric = load_metric_from_code(metric_code)

        # Load model config
        model_settings = payload.get("model_config") or overview.get(PAYLOAD_OVERVIEW_MODEL_SETTINGS, {})
        model_name_str = overview.get(PAYLOAD_OVERVIEW_MODEL_NAME, "")
        if model_settings:
            model_config = ModelConfig.model_validate(model_settings)
        elif model_name_str:
            model_config = ModelConfig(name=model_name_str)
        else:
            raise HTTPException(status_code=400, detail="No model config found.")

        lm = build_language_model(model_config)

        # Build program
        if program_type == "baseline":
            signature_code = payload.get("signature_code", "")
            signature_cls = load_signature_from_code(signature_code)
            module_name = payload.get("module_name", "predict")
            module_kwargs = dict(payload.get("module_kwargs", {}))

            from ...service_gateway import DspyService
            module_factory, auto_signature = DspyService._get_module_factory(None, module_name)
            if auto_signature or "signature" not in module_kwargs:
                module_kwargs["signature"] = signature_cls
            program = module_factory(**module_kwargs)
        else:
            # Load optimized program
            result_data = job_data.get("result")
            if not result_data:
                raise HTTPException(status_code=409, detail="Optimization has no result.")
            result = RunResponse.model_validate(result_data)
            artifact = result.program_artifact
            if not artifact or not artifact.program_pickle_base64:
                raise HTTPException(status_code=409, detail="No program artifact.")
            if optimization_id not in _program_cache:
                program_bytes = base64.b64decode(artifact.program_pickle_base64)
                _program_cache[optimization_id] = pickle.loads(program_bytes)  # noqa: S301
            program = _program_cache[optimization_id]

        # Convert requested rows to DSPy examples and evaluate
        results = []
        with dspy.context(lm=lm):
            for idx in indices:
                if idx < 0 or idx >= total:
                    continue
                row = dataset[idx]
                # Build example
                example_dict = {}
                for sig_field, col_name in column_mapping.inputs.items():
                    example_dict[sig_field] = row.get(col_name, "")
                for sig_field, col_name in column_mapping.outputs.items():
                    example_dict[sig_field] = row.get(col_name, "")

                example = dspy.Example(**example_dict).with_inputs(
                    *list(column_mapping.inputs.keys())
                )

                try:
                    prediction = program(**{k: example_dict[k] for k in column_mapping.inputs})
                    outputs = {}
                    for sig_field in column_mapping.outputs:
                        outputs[sig_field] = getattr(prediction, sig_field, None)

                    # Run metric
                    try:
                        score = metric(example, prediction)
                        score = float(score) if isinstance(score, (int, float, bool)) else 0.0
                    except Exception:
                        score = 0.0

                    results.append({
                        "index": idx,
                        "outputs": outputs,
                        "score": score,
                        "pass": score > 0,
                    })
                except Exception as exc:
                    results.append({
                        "index": idx,
                        "outputs": {},
                        "score": 0.0,
                        "pass": False,
                        "error": str(exc),
                    })

        return {"results": results, "program_type": program_type}

    @router.get("/optimizations/{optimization_id}/test-results")
    def get_test_results(optimization_id: str) -> dict:
        """Return per-example test results stored during optimization.

        The stored results use sequential indices within the test split.
        This endpoint remaps them to global dataset indices so the frontend
        can match results to dataset rows.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.")

        result_data = job_data.get("result")
        if not result_data:
            raise HTTPException(status_code=409, detail="Optimization has no result yet.")

        result = RunResponse.model_validate(result_data)

        # Reconstruct global test indices for remapping
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

    @router.get("/optimizations/{optimization_id}/artifact", response_model=ProgramArtifactResponse)
    def get_job_artifact(optimization_id: str) -> ProgramArtifactResponse:
        """Return the serialized artifact once the job succeeds.

        Args:
            optimization_id: Identifier for the job returned during submission.

        Returns:
            ProgramArtifactResponse: Serialized program artifact payload.
        """

        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            logger.warning("Artifact requested for unknown optimization_id=%s", optimization_id)
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.")

        overview = parse_overview(job_data)
        optimization_type = overview.get(PAYLOAD_OVERVIEW_JOB_TYPE, OPTIMIZATION_TYPE_RUN)

        if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
            raise HTTPException(
                status_code=404,
                detail="Grid search jobs produce per-pair artifacts. Use GET /optimizations/{optimization_id}/grid-result instead.",
            )

        status = status_to_job_status(job_data.get("status", "pending"))

        if status in {OptimizationStatus.pending, OptimizationStatus.validating, OptimizationStatus.running}:
            raise HTTPException(status_code=409, detail="Optimization has not finished yet.")

        if status == OptimizationStatus.failed:
            error_msg = job_data.get("message") or "unknown error"
            raise HTTPException(
                status_code=409,
                detail=f"Optimization failed and did not produce an artifact. Error: {error_msg}",
            )

        if status == OptimizationStatus.cancelled:
            raise HTTPException(
                status_code=409,
                detail="Optimization was cancelled and did not produce an artifact.",
            )

        if status == OptimizationStatus.success:
            result_data = job_data.get("result")
            if result_data and isinstance(result_data, dict):
                try:
                    result = RunResponse.model_validate(result_data)
                except ValidationError:
                    logger.warning("Optimization %s has corrupted result data", optimization_id)
                    raise HTTPException(status_code=500, detail="Optimization result data is corrupted.")
                return ProgramArtifactResponse(
                    program_artifact=result.program_artifact,
                )

        raise HTTPException(status_code=409, detail="Optimization did not produce an artifact.")

    @router.get("/optimizations/{optimization_id}/grid-result", response_model=GridSearchResponse)
    def get_grid_search_result(optimization_id: str) -> GridSearchResponse:
        """Return the full grid search result once the job completes."""
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.")

        overview = parse_overview(job_data)
        if overview.get(PAYLOAD_OVERVIEW_JOB_TYPE) != OPTIMIZATION_TYPE_GRID_SEARCH:
            raise HTTPException(status_code=404, detail="Optimization is not a grid search.")

        status = status_to_job_status(job_data.get("status", "pending"))
        if status not in _TERMINAL_STATUSES:
            raise HTTPException(status_code=409, detail="Optimization has not finished yet.")

        result_data = job_data.get("result")
        if not result_data or not isinstance(result_data, dict):
            if status == OptimizationStatus.failed:
                error_msg = job_data.get("message") or "unknown error"
                raise HTTPException(
                    status_code=409,
                    detail=f"Grid search failed and produced no result. Error: {error_msg}",
                )
            if status == OptimizationStatus.cancelled:
                raise HTTPException(
                    status_code=409,
                    detail="Grid search was cancelled and produced no result.",
                )
            raise HTTPException(status_code=404, detail="No grid search result available.")

        try:
            return GridSearchResponse.model_validate(result_data)
        except ValidationError:
            raise HTTPException(status_code=500, detail="Grid search result data is corrupted.")

    @router.post("/optimizations/{optimization_id}/cancel", response_model=JobCancelResponse, status_code=200)
    def cancel_job(optimization_id: str) -> JobCancelResponse:
        """Cancel a pending or running job.

        Args:
            optimization_id: Identifier for the job to cancel.

        Returns:
            dict: Confirmation with optimization_id and new status.

        Raises:
            HTTPException: If the job is not found or already in a terminal state.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.")

        status = status_to_job_status(job_data.get("status", "pending"))
        if status in _TERMINAL_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=f"Optimization is already in terminal state '{status.value}'.",
            )

        worker = get_worker_ref()
        if worker:
            worker.cancel_job(optimization_id)

        now = datetime.now(timezone.utc).isoformat()
        job_store.update_job(optimization_id, status="cancelled", message="בוטל על ידי המשתמש", completed_at=now)
        logger.info("Optimization %s (%s) cancelled", optimization_id, status.value)
        return JobCancelResponse(optimization_id=optimization_id, status="cancelled")

    @router.delete("/optimizations/{optimization_id}", response_model=JobDeleteResponse, status_code=200)
    def delete_job(optimization_id: str) -> JobDeleteResponse:
        """Delete a completed, failed, or cancelled job and all its data.

        Args:
            optimization_id: Identifier for the job to delete.

        Returns:
            dict: Confirmation with deleted optimization_id.

        Raises:
            HTTPException: If the job is not found or still active.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.")

        status = status_to_job_status(job_data.get("status", "pending"))
        if status not in _TERMINAL_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete job in '{status.value}' state. Cancel it first.",
            )

        job_store.delete_job(optimization_id)
        logger.info("Optimization %s deleted", optimization_id)
        return JobDeleteResponse(optimization_id=optimization_id, deleted=True)

    # ── Server-Sent Events (SSE) for real-time job streaming ──

    @router.get("/optimizations/{optimization_id}/stream")
    async def stream_job(optimization_id: str):
        """Stream job status updates via Server-Sent Events.

        Sends a JSON event every 2 seconds with the current job state.
        Stops when the job reaches a terminal status. Returns 404 for
        nonexistent jobs before opening the stream.

        Args:
            optimization_id: The optimization identifier to stream.

        Returns:
            StreamingResponse: SSE stream of job status updates.

        Raises:
            HTTPException: 404 if the job does not exist.
        """
        import asyncio
        import json

        # Check job exists before opening stream
        try:
            raw = job_store.get_job(optimization_id)
        except KeyError:
            raw = None
        if raw is None:
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.")

        terminal = {"success", "failed", "cancelled"}

        async def event_generator():
            """Yield SSE events until job completes."""
            while True:
                raw = job_store.get_job(optimization_id)
                if raw is None:
                    yield f"event: error\ndata: {json.dumps({'error': 'Optimization not found'})}\n\n"
                    return

                # Build a lightweight status payload
                status = raw.get("status", "pending")
                metrics = raw.get("latest_metrics", {})
                payload = {
                    "optimization_id": optimization_id,
                    "status": status,
                    "message": raw.get("message"),
                    "latest_metrics": metrics,
                    "log_count": job_store.get_log_count(optimization_id),
                    "progress_count": job_store.get_progress_count(optimization_id),
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

    @router.get("/optimizations/{optimization_id}/pair/{pair_index}/test-results")
    def get_pair_test_results(optimization_id: str, pair_index: int) -> dict:
        """Return per-example test results for a specific grid search pair.

        Applies the same index remapping as the main test-results endpoint.
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
                detail="Per-pair test results are only available for grid search jobs.",
            )

        status = status_to_job_status(job_data.get("status", "pending"))
        if status != OptimizationStatus.success:
            raise HTTPException(
                status_code=409,
                detail=f"Optimization is '{status.value}' — only successful optimizations have test results.",
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

        # Reconstruct global test indices for remapping
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

    return router
