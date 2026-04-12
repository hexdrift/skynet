"""Routes for the core optimizations resource (list, detail, lifecycle)."""

from __future__ import annotations

import hashlib
import logging
import random
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

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
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkDeleteSkipped,
    ColumnMapping,
    GridSearchResponse,
    JobCancelResponse,
    JobDeleteResponse,
    JobLogEntry,
    ModelConfig,
    OptimizationCountsResponse,
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

    @router.get(
        "/optimizations",
        response_model=PaginatedJobsResponse,
        summary="List optimization jobs with filtering and pagination",
    )
    def list_jobs(
        status: str | None = Query(
            default=None,
            description="Exact-match status filter: pending, validating, running, success, failed, cancelled",
        ),
        username: str | None = Query(default=None, description="Only include jobs submitted by this user"),
        optimization_type: str | None = Query(
            default=None, description="'run' (single optimization) or 'grid_search' (model-pair sweep)"
        ),
        limit: int = Query(
            default=50,
            ge=1,
            le=500,
            description="Page size; the per-user quota keeps total job counts bounded in practice",
        ),
        offset: int = Query(
            default=0,
            ge=0,
            description="Number of jobs to skip before returning; combine with limit for stable pagination",
        ),
    ) -> PaginatedJobsResponse:
        """Return a page of optimization jobs ordered by ``created_at`` descending.

        This is the primary dashboard endpoint. Every job summary in the
        response is a compact card (status, module, optimizer, model,
        timing, latest metrics) built by ``build_summary``, not the full
        result/artifact blob.

        Filter semantics:
            - ``status``, ``username``, ``optimization_type`` combine with AND.
            - ``status`` and ``optimization_type`` are validated server-side
              against closed lists and return HTTP 422 with the allowed
              values on mismatch.
            - ``username`` is an exact string match — no wildcards.

        Pagination: ``total`` in the response is the full count before
        ``limit``/``offset`` are applied, so clients can render "showing 50
        of 312" indicators. Ordering is stable as long as no new jobs are
        inserted between pages; new submissions can push the window.

        Response caching: a brief private cache is applied by the
        app-level middleware when no status filter is set, since the
        unfiltered dashboard view is the hottest path.

        Args:
            status: Exact-match job status filter.
            username: Only include jobs submitted by this user.
            optimization_type: Filter by ``run`` or ``grid_search``.
            limit: Maximum number of jobs returned in this page.
            offset: Number of jobs to skip before the returned slice.

        Returns:
            PaginatedJobsResponse with one compact card per job.

        Raises:
            HTTPException: 422 if ``status`` or ``optimization_type`` is invalid.
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
        rows = job_store.list_jobs(
            status=status, username=username, optimization_type=optimization_type, limit=limit, offset=offset
        )
        items = [build_summary(job_data) for job_data in rows]
        return PaginatedJobsResponse(items=items, total=total, limit=limit, offset=offset)

    @router.get(
        "/optimizations/counts",
        response_model=OptimizationCountsResponse,
        summary="Aggregate job counts grouped by status",
    )
    def get_optimization_counts(
        username: str | None = Query(default=None, description="Restrict counts to a single user"),
    ) -> OptimizationCountsResponse:
        """Return the full backend row counts grouped by status.

        The dashboard pulls job pages incrementally via infinite scroll,
        so summing locally-loaded items would under-report the true
        totals displayed in the stat cards. This endpoint issues one
        ``COUNT`` per status (plus a grand total) so the dashboard can
        render "סה״כ", "נכשלו", "הצליחו" etc. against the full dataset
        without loading every row.

        Args:
            username: Restrict counts to jobs owned by this user.

        Returns:
            OptimizationCountsResponse with totals per status.
        """
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
        summary="Compact job list tuned for sidebar navigation",
    )
    def list_jobs_sidebar(
        username: str | None = Query(default=None, description="Restrict the list to a single user's jobs"),
        limit: int = Query(
            default=50,
            ge=1,
            le=200,
            description="Page size; capped at 200 because the sidebar only renders a finite slice",
        ),
        offset: int = Query(default=0, ge=0, description="Number of jobs to skip before the returned slice"),
    ) -> SidebarJobsResponse:
        """Return a minimal per-job summary optimized for the left sidebar.

        Trimmed counterpart to ``GET /optimizations``: each item contains
        only what the sidebar card needs to render — ID, status, display
        name, optimizer, model, username, creation time, pin state, and
        (for grid searches) total pair count.

        No result payload, no metrics, no logs, no progress events. This
        endpoint is safe to poll aggressively because the database query
        hits the same table but avoids materializing the full summary
        shape, and the response stays small regardless of how many jobs
        the user has.

        Ordering is newest-first. Pinned jobs are *not* reordered by this
        endpoint — the UI handles the "pinned on top" sort client-side.

        Args:
            username: Restrict the list to a single user's jobs.
            limit: Maximum page size.
            offset: Number of jobs to skip before the returned slice.

        Returns:
            SidebarJobsResponse with minimal per-job entries for the sidebar.
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
                    optimization_type=overview.get(PAYLOAD_OVERVIEW_JOB_TYPE),
                    total_pairs=overview.get(PAYLOAD_OVERVIEW_TOTAL_PAIRS),
                )
            )
        return SidebarJobsResponse(items=items, total=total)

    # NOTE: Must be registered BEFORE /optimizations/{optimization_id} to avoid route shadowing.

    @router.get(
        "/optimizations/stream",
        summary="Stream live dashboard updates (all active jobs) as SSE",
    )
    async def stream_dashboard():
        """Server-Sent Events feed that pushes a snapshot of every currently
        active optimization every 3 seconds.

        "Active" = in ``pending``, ``validating``, or ``running`` status.
        Each snapshot includes a compact record per active job: ID,
        status, display name, latest metrics, log count, and progress
        count. The client uses this to animate dashboard cards in real
        time without polling ``/optimizations`` repeatedly.

        Event stream shape:
            - ``data: {"active_jobs": [...], "active_count": N}``
              Sent every 3 seconds while at least one job is active.
            - ``event: idle`` → ``{"active_count": 0}``
              Sent once when the last active job transitions to terminal,
              after which the server closes the connection.

        Because the response auto-closes on idle, long-running SPAs need
        to reconnect whenever they transition from "some jobs running"
        back to "jobs running again". The frontend hides this behind a
        reconnecting EventSource wrapper.

        Returns:
            StreamingResponse yielding ``text/event-stream`` snapshots.
        """
        import asyncio
        import json

        async def event_generator():
            """Yield active-job snapshots as SSE payloads until the queue drains.

            Yields:
                SSE-formatted strings describing the active job set, ending with
                an ``event: idle`` payload once no jobs remain.
            """
            while True:
                active_rows = []
                for s in ("pending", "validating", "running"):
                    active_rows.extend(job_store.list_jobs(status=s, limit=100))

                summaries = []
                for row in active_rows:
                    overview = parse_overview(row)
                    summaries.append(
                        {
                            "optimization_id": row["optimization_id"],
                            "status": row.get("status", "pending"),
                            "name": overview.get(PAYLOAD_OVERVIEW_NAME),
                            "latest_metrics": row.get("latest_metrics", {}),
                            "log_count": job_store.get_log_count(row["optimization_id"]),
                            "progress_count": job_store.get_progress_count(row["optimization_id"]),
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
        summary="Full job detail with logs, progress, metrics, and result",
    )
    def get_job(optimization_id: str, request: Request) -> OptimizationStatusResponse:
        """Return the complete state of a single optimization.

        This is the richest endpoint for a specific job — it aggregates
        status, overview fields (module, optimizer, model, mapping,
        dataset metadata), timing (created/started/completed), elapsed
        and estimated-remaining, latest metrics, all captured logs, all
        progress events, and the final result (for run jobs) or grid
        result (for grid-search jobs). The "Overview" tab of the job
        detail view is built almost entirely from this response.

        Conditional GET:
            The response includes an ``ETag`` derived from the job's
            current status and the counts of logs, progress events, and
            metrics. Clients can send ``If-None-Match`` with the last
            ETag they saw; if nothing changed, the server returns HTTP
            304 with no body. Terminal jobs are cached for 60 seconds;
            active jobs for 1 second so the UI stays responsive.

        Grid-search handling:
            For grid searches, the ``grid_result`` field is populated
            even while the job is still running, so partial per-pair
            output is visible before the whole sweep finishes. This is
            different from ``result``, which is only set once a single
            run has reached ``success``.

        Errors: HTTP 404 if the optimization ID is unknown. Corrupted
        result data is tolerated — the endpoint logs a warning and
        omits the offending section rather than 500ing.

        Args:
            optimization_id: Identifier of the optimization job to fetch.
            request: Incoming HTTP request used for conditional ``If-None-Match``.

        Returns:
            OptimizationStatusResponse with the full job detail, or a 304 response
            when the client's ETag matches the current job state.

        Raises:
            HTTPException: 404 when the optimization ID is unknown.
        """

        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            logger.warning("Optimization status requested for unknown optimization_id=%s", optimization_id)
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.") from None

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
        etag_src = f"{status}:{len(logs)}:{len(progress_events)}:{latest_metrics!s}"
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

    @router.get(
        "/optimizations/{optimization_id}/summary",
        response_model=OptimizationSummaryResponse,
        summary="Lightweight summary card for one optimization",
    )
    def get_job_summary(optimization_id: str) -> OptimizationSummaryResponse:
        """Return the same compact card shape used by ``GET /optimizations``
        but for a single specific ID.

        Useful when a client already has the ID (e.g. just submitted a
        job) and wants the dashboard-row representation without paying
        for the full logs/progress/result payload returned by
        ``GET /optimizations/{id}``.

        The returned summary includes counts for logs and progress events
        (``log_count``, ``progress_count``) but not the events themselves —
        clients who need to render logs should still call
        ``/optimizations/{id}/logs``.

        Returns HTTP 404 if the optimization doesn't exist.

        Args:
            optimization_id: Identifier of the optimization job to summarize.

        Returns:
            OptimizationSummaryResponse with the compact card shape.

        Raises:
            HTTPException: 404 when the optimization ID is unknown.
        """

        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            logger.warning("Optimization summary requested for unknown optimization_id=%s", optimization_id)
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.") from None

        job_data["progress_count"] = job_store.get_progress_count(optimization_id)
        job_data["log_count"] = job_store.get_log_count(optimization_id)
        return build_summary(job_data)

    @router.get(
        "/optimizations/{optimization_id}/dataset",
        summary="Reconstruct the train/val/test split used by this optimization",
    )
    def get_job_dataset(optimization_id: str) -> dict:
        """Return the dataset exactly as it was split into train, validation,
        and test partitions when the job ran.

        The server does not store the splits directly — they're
        reconstructed on demand by replaying the same algorithm
        ``service_gateway.data`` uses: optional shuffle with a
        deterministic seed, then slice by ``split_fractions.train`` /
        ``.val`` / ``.test``. Passing ``shuffle=True`` with no seed at
        submission time falls back to a seed derived from the
        optimization ID, guaranteeing the splits are reproducible
        regardless of when this endpoint is called.

        Response shape:
            ``{"total_rows": N, "splits": {"train": [{"index": i, "row": {...}}],
            "val": [...], "test": [...]}, "column_mapping": {...},
            "split_counts": {...}}``

        Each row carries its global ``index`` into the original dataset
        so the UI can highlight which rows ended up in which split.
        ``column_mapping`` is echoed to save the client a second fetch.

        Errors:
            - 404 if the optimization doesn't exist, or if it was
              submitted without a dataset (very old jobs).
            - 500 if the stored ``column_mapping`` fails validation —
              this indicates data corruption.

        Args:
            optimization_id: Identifier of the optimization job whose dataset is fetched.

        Returns:
            Dict with total rows, per-split rows, column mapping, and split counts.

        Raises:
            HTTPException: 404 (missing job or dataset) or 500 (invalid mapping).
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.") from None

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

        raw_mapping = payload.get("column_mapping", {})
        try:
            column_mapping = ColumnMapping.model_validate(raw_mapping)
        except ValidationError:
            raise HTTPException(
                status_code=500,
                detail="Stored column mapping is invalid.",
            ) from None

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
            """Build row dicts with original indices for a split.

            Args:
                idx_list: Global dataset indices belonging to a single split.

            Returns:
                List of ``{"index", "row"}`` dicts in the same order as ``idx_list``.
            """
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
        """Ad-hoc evaluation against arbitrary dataset rows using the stored
        metric and program.

        Users can pick any row indices from the submitted dataset and get
        back per-row predictions + metric scores, without having to
        re-submit a whole optimization. This powers the "Try it on this
        example" workflow in the job detail view.

        Request body:
            ``{"indices": [int, ...], "program_type": "optimized" | "baseline"}``

            - ``indices``: global indices into the original dataset
              (same numbering as ``GET /optimizations/{id}/dataset``).
              Out-of-range indices are silently skipped rather than
              erroring.
            - ``program_type``: ``"optimized"`` (default) loads the
              compiled program from the successful run. ``"baseline"``
              re-constructs a fresh, unoptimized module from the stored
              signature and module kwargs — useful for before/after
              comparisons on the same examples.

        Response:
            ``{"results": [{"index": i, "outputs": {...}, "score": float,
            "pass": bool, "error"?: str}, ...], "program_type": "..."}``

            The metric score is always normalized to a float; ``pass``
            is ``score > 0``. Rows where the program itself raises
            include the exception message in ``error`` but still appear
            in the list so UIs can render them.

        Errors: 404 (optimization missing), 400 (no metric code stored,
        no model config), 409 (no optimized program when
        ``program_type="optimized"``).

        Args:
            optimization_id: Identifier of the optimization job to run against.
            req: Request body with ``indices`` and ``program_type`` keys.

        Returns:
            Dict with ``results`` (list of per-example outputs) and ``program_type``.

        Raises:
            HTTPException: 404/400/409 depending on missing dependencies.
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
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.") from None

        overview = parse_overview(job_data)
        payload = job_data.get("payload")
        if not payload or not isinstance(payload, dict):
            raise HTTPException(status_code=404, detail="Optimization has no payload.")

        dataset = payload.get("dataset", [])
        total = len(dataset)
        column_mapping_raw = payload.get("column_mapping", {})
        column_mapping = ColumnMapping.model_validate(column_mapping_raw)

        metric_code = payload.get("metric_code", "")
        if not metric_code:
            raise HTTPException(status_code=400, detail="Optimization has no metric code.")
        metric = load_metric_from_code(metric_code)

        model_settings = payload.get("model_config") or overview.get(PAYLOAD_OVERVIEW_MODEL_SETTINGS, {})
        model_name_str = overview.get(PAYLOAD_OVERVIEW_MODEL_NAME, "")
        if model_settings:
            model_config = ModelConfig.model_validate(model_settings)
        elif model_name_str:
            model_config = ModelConfig(name=model_name_str)
        else:
            raise HTTPException(status_code=400, detail="No model config found.")

        lm = build_language_model(model_config)

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
            result_data = job_data.get("result")
            if not result_data:
                raise HTTPException(status_code=409, detail="Optimization has no result.")
            result = RunResponse.model_validate(result_data)
            artifact = result.program_artifact
            if not artifact or not artifact.program_pickle_base64:
                raise HTTPException(status_code=409, detail="No program artifact.")
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
        """Return the test-set evaluation captured during optimization, split
        into baseline and optimized rows for side-by-side comparison.

        The worker evaluates both the baseline (unoptimized) and
        optimized programs against every example in the test split and
        stores the results on the job's ``result`` blob. This endpoint
        just exposes them — no inference runs again, so it's cheap.

        Index remapping:
            Internally the stored results use sequential indices
            within the test split (0, 1, 2, ...) because that's how the
            evaluator walked them. Those are remapped here to **global**
            dataset indices so the frontend can highlight the same
            rows on the Dataset tab without a second lookup. The
            remapping replays the split algorithm deterministically
            using the job's seed.

        Response:
            ``{"baseline": [{"index": i, "outputs": {...}, "score": float,
            "pass": bool, ...}, ...], "optimized": [...]}``

            Both arrays have the same length (one row per test example).
            The ``score`` comes straight from the metric function used
            during optimization.

        Errors: 404 (unknown job), 409 (no result yet — run still in
        progress or failed before evaluation completed).

        Args:
            optimization_id: Identifier of the optimization job to inspect.

        Returns:
            Dict with ``baseline`` and ``optimized`` per-example result arrays.

        Raises:
            HTTPException: 404 (unknown job) or 409 (no result yet).
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.") from None

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
            """Rewrite sequential test indices to global dataset indices.

            Args:
                results: Per-example result dicts keyed by sequential test index.

            Returns:
                New list of result dicts with ``index`` remapped to the global dataset.
            """
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
        """Return the serialized program artifact produced by a successful
        single-run optimization.

        The artifact contains the base64-encoded pickled program plus
        the extracted ``optimized_prompt`` (instructions, input/output
        fields, and few-shot demos). Downstream code uses this to
        either round-trip the program back into DSPy via pickle, or to
        re-render the prompt outside the service.

        This endpoint is only valid for single-run jobs that finished
        successfully:
            - HTTP 404 if the optimization ID is unknown.
            - HTTP 404 (with explanatory detail) if the job is a grid
              search; use ``/optimizations/{id}/grid-result`` instead,
              since grid searches produce one artifact per pair.
            - HTTP 409 if the job is still ``pending``, ``validating``,
              or ``running``.
            - HTTP 409 if the job is in ``failed`` or ``cancelled``
              status — the detail includes the failure message so the
              caller can surface it.
            - HTTP 500 if the stored result data fails schema
              validation (indicates upstream corruption).

        Args:
            optimization_id: Identifier of the optimization whose artifact is fetched.

        Returns:
            ProgramArtifactResponse containing the serialized program artifact.

        Raises:
            HTTPException: 404, 409, or 500 depending on the failure mode described above.
        """

        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            logger.warning("Artifact requested for unknown optimization_id=%s", optimization_id)
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.") from None

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
                    raise HTTPException(status_code=500, detail="Optimization result data is corrupted.") from None
                return ProgramArtifactResponse(
                    program_artifact=result.program_artifact,
                )

        raise HTTPException(status_code=409, detail="Optimization did not produce an artifact.")

    @router.get(
        "/optimizations/{optimization_id}/grid-result",
        response_model=GridSearchResponse,
        summary="Retrieve the full grid-search result with per-pair details",
    )
    def get_grid_search_result(optimization_id: str) -> GridSearchResponse:
        """Return the complete outcome of a grid-search sweep.

        Unlike ``/artifact`` (which is single-run only), this endpoint
        surfaces every pair's individual result: baseline and optimized
        test metrics, runtime, compiled program, status, and any
        per-pair error. The ``best_pair`` field identifies which
        ``(generation_model, reflection_model)`` combination won by
        optimized test metric.

        Only valid for grid-search jobs in a terminal status:
            - HTTP 404 if the optimization ID is unknown or if the job
              is not a grid search.
            - HTTP 409 if the grid search is still running (wait for a
              terminal status before calling).
            - HTTP 409 with the failure message if the grid search
              failed or was cancelled before producing any result.
            - HTTP 500 on result-data corruption.

        For live per-pair progress during a running grid search, call
        ``GET /optimizations/{id}`` — its ``grid_result`` field is
        populated from the same underlying data while the sweep is in
        progress.

        Args:
            optimization_id: Identifier of the grid-search job.

        Returns:
            GridSearchResponse with per-pair metrics, artifacts, and the best pair.

        Raises:
            HTTPException: 404, 409, or 500 depending on the failure described above.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.") from None

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
            raise HTTPException(status_code=500, detail="Grid search result data is corrupted.") from None

    @router.post(
        "/optimizations/{optimization_id}/cancel",
        response_model=JobCancelResponse,
        status_code=200,
        summary="Cancel a pending or running optimization",
    )
    def cancel_job(optimization_id: str) -> JobCancelResponse:
        """Request cancellation of an active optimization.

        What happens:
            1. The job's status is flipped to ``cancelled`` in the store
               with a Hebrew "cancelled by user" message and a
               ``completed_at`` timestamp.
            2. The live worker is asked to stop executing the job. This
               is a *cooperative* cancellation — the worker checks for
               the cancel flag between DSPy calls. If a single LLM call
               is in flight it will finish before the worker observes
               the cancel, so the actual stop can take a few seconds.
            3. For grid searches, cancellation stops the entire sweep;
               remaining pairs will not start.

        Cancellation is only valid for non-terminal statuses. Attempting
        to cancel a job that already finished returns HTTP 409. Unknown
        IDs return HTTP 404.

        This endpoint is a one-way trip — there is no "uncancel". If
        the cancel lands before the worker has started the job it
        simply disappears from the queue; otherwise the partial
        progress remains on the job (logs, progress events) but
        ``result`` will be unset.

        Args:
            optimization_id: Identifier of the optimization to cancel.

        Returns:
            JobCancelResponse confirming the cancellation.

        Raises:
            HTTPException: 404 (unknown job) or 409 (already terminal).
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.") from None

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

    @router.delete(
        "/optimizations/{optimization_id}",
        response_model=JobDeleteResponse,
        status_code=200,
        summary="Permanently delete an optimization and all its data",
    )
    def delete_job(optimization_id: str) -> JobDeleteResponse:
        """Hard-delete an optimization from the store.

        Removes the job row, its stored payload, its result, its
        progress events, and its logs. This is **not** a soft delete —
        there is no tombstone or recovery. Use
        ``PATCH /optimizations/{id}/archive`` if you want to hide a job
        from the dashboard without losing it.

        Safety rails:
            - Only jobs in a terminal status (``success``, ``failed``,
              ``cancelled``) can be deleted. Attempting to delete an
              active job returns HTTP 409 with guidance to cancel first.
            - HTTP 404 if the optimization doesn't exist. Deleting an
              already-deleted job returns 404 rather than silently
              succeeding, which catches double-deletes from the UI.

        Returns ``{"optimization_id": ..., "deleted": true}`` on
        success. The deletion is immediate and not recoverable.

        Args:
            optimization_id: Identifier of the optimization to delete.

        Returns:
            JobDeleteResponse confirming the delete succeeded.

        Raises:
            HTTPException: 404 (unknown job) or 409 (still active).
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.") from None

        status = status_to_job_status(job_data.get("status", "pending"))
        if status not in _TERMINAL_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete job in '{status.value}' state. Cancel it first.",
            )

        job_store.delete_job(optimization_id)
        logger.info("Optimization %s deleted", optimization_id)
        return JobDeleteResponse(optimization_id=optimization_id, deleted=True)

    @router.post(
        "/optimizations/bulk-delete",
        response_model=BulkDeleteResponse,
        status_code=200,
        summary="Delete many optimizations in a single request",
    )
    def bulk_delete_jobs(body: BulkDeleteRequest) -> BulkDeleteResponse:
        """Hard-delete a batch of optimizations in one call.

        Accepts ``{"optimization_ids": [...]}`` and deletes every job
        that exists and is in a terminal status (``success``, ``failed``,
        ``cancelled``). This endpoint never raises 404 or 409 for
        individual IDs — instead it returns per-id results so the caller
        can report partial failures:

            {
              "deleted": ["opt_a", "opt_b"],
              "skipped": [
                {"optimization_id": "opt_c", "reason": "not_found"},
                {"optimization_id": "opt_d", "reason": "running"}
              ]
            }

        Duplicate IDs in the request are deduplicated. The request as
        a whole only fails if the body is malformed.

        Performance: validation and deletion run in two bulk queries
        regardless of batch size — one ``SELECT ... WHERE id IN (...)``
        to fetch existing statuses and one batched ``DELETE`` on the
        terminal subset (plus the associated logs/progress rows).

        Args:
            body: Request payload containing the ``optimization_ids`` to delete.

        Returns:
            BulkDeleteResponse with the IDs deleted and per-ID skip reasons.
        """
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
            if status not in _TERMINAL_STATUSES:
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
        summary="Stream one job's live status updates as SSE",
    )
    async def stream_job(optimization_id: str):
        """Per-job Server-Sent Events stream, complementary to
        ``/optimizations/stream`` (which covers every active job).

        Every 2 seconds the server emits a compact status event for the
        target job: current status, latest worker message, latest
        metrics, log count, and progress event count. The job detail
        page uses this to animate metric charts and log counters
        without polling.

        Event sequence:
            1. ``data: {"optimization_id": ..., "status": ..., "message": ...,
               "latest_metrics": {...}, "log_count": N, "progress_count": M}``
               Emitted every 2 seconds while the job is non-terminal.
            2. Once the job reaches ``success``, ``failed``, or
               ``cancelled``, a final ``data:`` event is sent followed
               by ``event: done`` → ``{"status": ...}`` and the server
               closes the connection.
            3. If the job vanishes mid-stream (e.g. deleted), an
               ``event: error`` → ``{"error": "Optimization not found"}``
               is sent and the stream ends.

        Pre-flight check: the endpoint returns HTTP 404 *before* opening
        the stream if the optimization ID is unknown, so clients don't
        have to handle missing-job errors as SSE messages on first
        connect.

        Args:
            optimization_id: Identifier of the optimization to stream.

        Returns:
            StreamingResponse yielding ``text/event-stream`` events until completion.

        Raises:
            HTTPException: 404 if the optimization ID is unknown.
        """
        import asyncio
        import json

        try:
            raw = job_store.get_job(optimization_id)
        except KeyError:
            raw = None
        if raw is None:
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.") from None

        terminal = {"success", "failed", "cancelled"}

        async def event_generator():
            """Yield SSE events until job completes.

            Yields:
                SSE-formatted strings with the job's latest status, ending with a
                ``done`` event on terminal status or an ``error`` event if the job vanishes.
            """
            while True:
                raw = job_store.get_job(optimization_id)
                if raw is None:
                    yield f"event: error\ndata: {json.dumps({'error': 'Optimization not found'})}\n\n"
                    return

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

    @router.get(
        "/optimizations/{optimization_id}/pair/{pair_index}/test-results",
        summary="Per-example test scores for one grid-search pair",
    )
    def get_pair_test_results(optimization_id: str, pair_index: int) -> dict:
        """Per-pair analogue of
        ``GET /optimizations/{id}/test-results``.

        For grid searches, each ``(generation_model, reflection_model)``
        pair evaluates its own baseline and optimized programs against
        the test split. This endpoint exposes a single pair's results,
        with the same global-index remapping applied as the single-run
        variant so results can be matched to dataset rows.

        ``pair_index`` is 0-based and matches the
        ``pair_results[*].pair_index`` field in
        ``/optimizations/{id}/grid-result``.

        Response shape is identical to the single-run test-results
        endpoint: ``{"baseline": [...], "optimized": [...]}``.

        Errors:
            - HTTP 404: optimization missing, or pair index doesn't
              exist in the grid result.
            - HTTP 409: the optimization is not a grid search, or
              hasn't reached ``success``, or stored no result data.

        Args:
            optimization_id: Identifier of the grid-search job.
            pair_index: 0-based index of the pair within the grid-search sweep.

        Returns:
            Dict with ``baseline`` and ``optimized`` per-example result arrays.

        Raises:
            HTTPException: 404 or 409 as described above.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{optimization_id}'.") from None

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
            """Rewrite per-pair sequential test indices to global dataset indices.

            Args:
                results: Per-example result dicts keyed by sequential test index.

            Returns:
                New list of result dicts with ``index`` remapped to the global dataset.
            """
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
