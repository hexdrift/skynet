"""Single-optimization read routes and evaluate-examples. [MIXED]

Public dev surface (in ``_SCALAR_PUBLIC_PATHS``):
- ``GET /optimizations/{id}`` — full job state.
- ``GET /optimizations/{id}/summary`` — compact metrics summary.
- ``GET /optimizations/{id}/artifact`` — download the trained program.
- ``GET /optimizations/{id}/grid-result`` — per-pair grid-search results.

Internal (frontend-only, hidden from public docs):
- ``GET /optimizations/{id}/dataset`` — dataset reshuffle for the UI.
- ``POST /optimizations/{id}/evaluate-examples`` — per-user playground.
- ``GET /optimizations/{id}/test-results``
- ``GET /optimizations/{id}/pair/{idx}/test-results``
"""

from __future__ import annotations

import hashlib
import logging
import random
from datetime import UTC, datetime
from typing import Annotated

import dspy
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ....constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODEL_SETTINGS,
    PAYLOAD_OVERVIEW_MODULE_KWARGS,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
    PAYLOAD_OVERVIEW_SIGNATURE_CODE,
)
from ....models import (
    ColumnMapping,
    GridSearchResponse,
    JobLogEntry,
    ModelConfig,
    OptimizationStatus,
    OptimizationStatusResponse,
    OptimizationSummaryResponse,
    ProgramArtifactResponse,
    RunResponse,
    SplitFractions,
)
from ....registry import ResolverError, resolve_module_factory
from ....service_gateway.language_models import build_language_model
from ....service_gateway.optimization.data import load_metric_from_code, load_signature_from_code
from ...auth import AuthenticatedUser, get_authenticated_user
from ...converters import (
    compute_elapsed,
    extract_estimated_remaining,
    overview_to_base_fields,
    parse_overview,
    parse_timestamp,
    status_to_job_status,
)
from ...errors import DomainError
from .._helpers import (
    _artifact_has_payload,
    _materialize_program,
    _program_cache,
    build_summary,
    compute_compare_fingerprint,
    load_job_for_user,
    stable_seed,
)
from ..constants import TERMINAL_STATUSES
from ._local import remap_test_indices

logger = logging.getLogger(__name__)

AuthenticatedUserDep = Annotated[AuthenticatedUser, Depends(get_authenticated_user)]

# Bumped whenever the GET /optimizations/{id} response shape changes in a way
# that adds, removes, or renames fields. Mixed into the ETag so cached 304s
# can't serve a pre-change body that's missing the new fields. Last bump:
# task_fingerprint moved onto _JobResponseBase (compare-gate fix).
_RESPONSE_SCHEMA_VERSION = "v3"


def register_detail_routes(router: APIRouter, *, job_store) -> None:
    """Register single-optimization read routes on ``router``.

    Args:
        router: The router to attach the detail routes to.
        job_store: Job-store the routes read from.
    """

    # ``response_model`` is kept for the OpenAPI schema, but the handler
    # returns ``JSONResponse`` directly so it can emit a 304 path and attach
    # ETag / Cache-Control headers. FastAPI skips response_model validation
    # whenever the handler returns a Response instance, so the model class is
    # documentation-only here — every code path still constructs an
    # ``OptimizationStatusResponse`` before serialising.
    @router.get(
        "/optimizations/{optimization_id}",
        response_model=OptimizationStatusResponse,
        summary="Full optimization detail with logs, progress, metrics, and result",
    )
    def get_job(optimization_id: str, request: Request, current_user: AuthenticatedUserDep) -> JSONResponse:
        """Return full optimization detail with logs, progress, metrics, and result.

        Supports conditional GET via ``If-None-Match`` / ``ETag`` (304 when
        unchanged). Grid searches include partial ``grid_result`` while still
        running. Corrupted result data is omitted with a warning rather than
        raising 500. 404 if the optimization id is unknown or the caller
        doesn't own it (non-admins).

        Args:
            optimization_id: The id of the optimization to fetch.
            request: Starlette request used to check ``If-None-Match``.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            A :class:`fastapi.responses.JSONResponse` whose body is a
            serialized :class:`OptimizationStatusResponse` (or a bare 304
            with no body when ``If-None-Match`` matches the current ETag).

        Raises:
            DomainError: 404 when the optimization id is unknown or
                inaccessible to the caller.
        """

        job_data = load_job_for_user(job_store, optimization_id, current_user)

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
                    grid_result = GridSearchResponse.model_validate(result_data)
                elif status == OptimizationStatus.success:
                    result = RunResponse.model_validate(result_data)
            except ValidationError:
                logger.warning("Optimization %s has corrupted result data", optimization_id)

        created_at = parse_timestamp(job_data.get("created_at")) or datetime.now(UTC)
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
            compare_fingerprint=compute_compare_fingerprint(optimization_id, overview),
            message=job_data.get("message"),
            latest_metrics=latest_metrics,
            completed_pairs=completed_pairs,
            failed_pairs=failed_pairs,
            progress_events=progress_events,
            logs=[JobLogEntry(**log) for log in logs],
            result=result,
            grid_result=grid_result,
        )

        etag_src = f"{_RESPONSE_SCHEMA_VERSION}:{status}:{len(logs)}:{len(progress_events)}:{latest_metrics!s}"
        etag = '"' + hashlib.md5(etag_src.encode()).hexdigest()[:12] + '"'
        if_none_match = request.headers.get("if-none-match")
        if if_none_match == etag:
            return JSONResponse(status_code=304, content=None, headers={"ETag": etag})

        headers = {"ETag": etag}
        # ``no-cache`` (not ``no-store``) tells the browser to revalidate via
        # If-None-Match every time, so a schema bump in ``_RESPONSE_SCHEMA_VERSION``
        # invalidates terminal-job bodies immediately instead of being shadowed
        # by ``max-age`` until the next deploy + N seconds pass.
        if status in TERMINAL_STATUSES:
            headers["Cache-Control"] = "private, no-cache"
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
    def get_job_summary(optimization_id: str, current_user: AuthenticatedUserDep) -> OptimizationSummaryResponse:
        """Return the compact dashboard-card shape for a single optimization.

        Args:
            optimization_id: Optimization id to summarise.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            An ``OptimizationSummaryResponse`` for dashboard display.

        Raises:
            DomainError: 404 if the optimization is unknown or inaccessible
                to the caller.
        """

        job_data = load_job_for_user(job_store, optimization_id, current_user)

        job_data["progress_count"] = job_store.get_progress_count(optimization_id)
        job_data["log_count"] = job_store.get_log_count(optimization_id)
        return build_summary(job_data)

    @router.get(
        "/optimizations/{optimization_id}/dataset",
        summary="Reconstruct the train/val/test split used by this optimization",
    )
    def get_job_dataset(optimization_id: str, current_user: AuthenticatedUserDep) -> dict:
        """Reconstruct the train/val/test split deterministically from the stored seed.

        Each row includes its global dataset index for UI highlighting.

        Args:
            optimization_id: Optimization id whose dataset should be returned.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            A dict with ``total_rows``, ``splits``, ``column_mapping``, and
            ``split_counts``.

        Raises:
            DomainError: 404 (optimization unknown / payload/dataset
                missing / inaccessible), 500 (corrupt mapping).
        """
        job_data = load_job_for_user(job_store, optimization_id, current_user)

        payload = job_data.get("payload")
        if not payload or not isinstance(payload, dict):
            raise DomainError("optimization.payload_unavailable", status=404)

        dataset = payload.get("dataset")
        if not dataset or not isinstance(dataset, list):
            raise DomainError("optimization.dataset_unavailable", status=404)

        raw_mapping = payload.get("column_mapping", {})
        try:
            column_mapping = ColumnMapping.model_validate(raw_mapping)
        except ValidationError:
            raise DomainError("optimization.corrupt_column_mapping", status=500) from None

        raw_fractions = payload.get("split_fractions", {})
        try:
            fractions = SplitFractions.model_validate(raw_fractions)
        except ValidationError:
            fractions = SplitFractions()

        shuffle = payload.get("shuffle", True)
        seed = payload.get("seed")

        # Replicates the service_gateway/data.py split algorithm. When seed
        # is None, derive a stable seed from optimization_id so repeated
        # calls produce the same shuffle (needed for index remapping).
        effective_seed = seed if seed is not None else stable_seed(optimization_id)
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

        splits = {
            "train": [{"index": i, "row": dataset[i]} for i in train_indices],
            "val": [{"index": i, "row": dataset[i]} for i in val_indices],
            "test": [{"index": i, "row": dataset[i]} for i in test_indices],
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
    def evaluate_examples(optimization_id: str, req: dict, current_user: AuthenticatedUserDep) -> dict:
        """Run the optimized or baseline program on specific dataset rows.

        Out-of-range indices are silently skipped.

        Args:
            optimization_id: Optimization id whose program should run.
            req: Request body with ``indices`` and ``program_type`` keys.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            ``{"results": [...], "program_type": ...}`` with one entry per
            evaluated row.

        Raises:
            DomainError: 404 (missing/inaccessible optimization or payload),
                400 (no metric/model/module), 409 (no result available for
                the optimized program).
        """
        indices = req.get("indices", [])
        program_type = req.get("program_type", "optimized")

        job_data = load_job_for_user(job_store, optimization_id, current_user)

        overview = parse_overview(job_data)
        payload = job_data.get("payload")
        if not payload or not isinstance(payload, dict):
            raise DomainError("optimization.no_payload", status=404)

        dataset = payload.get("dataset", [])
        total = len(dataset)
        column_mapping_raw = payload.get("column_mapping", {})
        column_mapping = ColumnMapping.model_validate(column_mapping_raw)

        metric_code = payload.get("metric_code", "")
        if not metric_code:
            raise DomainError("optimization.no_metric_code", status=400)
        # exec() isolation gap: runs user code in the API process. Same Phase B
        # story as ``/probe-models`` — evaluate-examples calls the metric once
        # per requested row, so ``safe_exec.probe_metric_on_sample`` would
        # spawn a subprocess per row. The payload here was already validated
        # through the subprocess boundary when the job was submitted.
        metric = load_metric_from_code(metric_code)

        model_settings = payload.get("model_config") or overview.get(PAYLOAD_OVERVIEW_MODEL_SETTINGS, {})
        model_name_str = overview.get(PAYLOAD_OVERVIEW_MODEL_NAME, "")
        if model_settings:
            model_config = ModelConfig.model_validate(model_settings)
        elif model_name_str:
            model_config = ModelConfig(name=model_name_str)
        else:
            raise DomainError("optimization.no_model_config", status=400)

        lm = build_language_model(model_config)

        if program_type == "baseline":
            signature_code = payload.get("signature_code", "")
            signature_cls = load_signature_from_code(signature_code)
            module_name = payload.get("module_name", "predict")
            module_kwargs = dict(payload.get("module_kwargs", {}))

            try:
                module_factory, auto_signature = resolve_module_factory(module_name)
            except ResolverError as exc:
                raise DomainError("submission.module_resolve_failed", status=400, error=str(exc)) from exc
            if auto_signature or "signature" not in module_kwargs:
                module_kwargs["signature"] = signature_cls
            program = module_factory(**module_kwargs)
        else:
            result_data = job_data.get("result")
            if not result_data:
                raise DomainError("optimization.no_result_for_artifact", status=409)
            result = RunResponse.model_validate(result_data)
            artifact = result.program_artifact
            if not _artifact_has_payload(artifact):
                raise DomainError("optimization.no_program_artifact", status=409)
            if optimization_id not in _program_cache:
                # Pre-migration jobs may not have signature_code in their
                # ``payload_overview``, but the original ``payload`` row
                # always carries it — fall back to that so legacy runs can
                # still be reconstructed.
                effective_overview = {
                    **overview,
                    PAYLOAD_OVERVIEW_SIGNATURE_CODE: (
                        overview.get(PAYLOAD_OVERVIEW_SIGNATURE_CODE)
                        or payload.get("signature_code")
                    ),
                    PAYLOAD_OVERVIEW_MODULE_NAME: (
                        overview.get(PAYLOAD_OVERVIEW_MODULE_NAME)
                        or payload.get("module_name")
                    ),
                    PAYLOAD_OVERVIEW_MODULE_KWARGS: (
                        overview.get(PAYLOAD_OVERVIEW_MODULE_KWARGS)
                        or payload.get("module_kwargs", {})
                    ),
                }
                _program_cache[optimization_id] = _materialize_program(artifact, effective_overview)
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
    def get_test_results(optimization_id: str, current_user: AuthenticatedUserDep) -> dict:
        """Return stored per-example baseline and optimized test scores.

        Sequential test-split indices are remapped to global dataset indices for
        UI use. No inference is executed.

        Args:
            optimization_id: Optimization id whose test results should be returned.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            ``{"baseline": [...], "optimized": [...]}`` with global indices.

        Raises:
            DomainError: 404 if unknown or inaccessible, 409 if no result yet.
        """
        job_data = load_job_for_user(job_store, optimization_id, current_user)

        result_data = job_data.get("result")
        if not result_data:
            raise DomainError("optimization.no_result_pending", status=409)

        result = RunResponse.model_validate(result_data)

        payload = job_data.get("payload", {})
        dataset = payload.get("dataset", [])
        total = len(dataset)
        fractions_raw = payload.get("split_fractions", {})
        fractions = SplitFractions.model_validate(fractions_raw)
        shuffle = payload.get("shuffle", True)
        seed = payload.get("seed")
        effective_seed = seed if seed is not None else stable_seed(optimization_id)

        ordered = list(range(total))
        if shuffle:
            rng = random.Random(effective_seed)
            rng.shuffle(ordered)
        train_end = int(total * fractions.train)
        val_end = train_end + int(total * fractions.val)
        test_indices = ordered[val_end:]

        return {
            "baseline": remap_test_indices(result.baseline_test_results, test_indices),
            "optimized": remap_test_indices(result.optimized_test_results, test_indices),
        }

    @router.get(
        "/optimizations/{optimization_id}/artifact",
        response_model=ProgramArtifactResponse,
        summary="Download the compiled DSPy program artifact",
    )
    def get_job_artifact(optimization_id: str, current_user: AuthenticatedUserDep) -> ProgramArtifactResponse:
        """Return the pickled program artifact for a successful single-run optimization.

        Grid searches 404 here — use ``/grid-result`` instead (one artifact per pair).

        Args:
            optimization_id: Optimization id whose artifact should be returned.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            A ``ProgramArtifactResponse`` carrying the pickled program.

        Raises:
            DomainError: 404 (unknown / inaccessible / grid), 409 (not
                success), 500 (corrupt result).
        """

        job_data = load_job_for_user(job_store, optimization_id, current_user)

        overview = parse_overview(job_data)
        optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)

        if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
            raise DomainError("grid_search.artifact_per_pair_redirect", status=404)

        status = status_to_job_status(job_data.get("status", "pending"))

        if status in {OptimizationStatus.pending, OptimizationStatus.validating, OptimizationStatus.running}:
            raise DomainError("optimization.not_finished", status=409)

        if status == OptimizationStatus.failed:
            error_msg = job_data.get("message") or "unknown error"
            raise DomainError("optimization.failed_no_artifact", status=409, error=error_msg)

        if status == OptimizationStatus.cancelled:
            raise DomainError("optimization.cancelled_no_artifact", status=409)

        if status == OptimizationStatus.success:
            result_data = job_data.get("result")
            if result_data and isinstance(result_data, dict):
                try:
                    result = RunResponse.model_validate(result_data)
                except ValidationError:
                    logger.warning("Optimization %s has corrupted result data", optimization_id)
                    raise DomainError("optimization.corrupt_result", status=500) from None
                return ProgramArtifactResponse(
                    program_artifact=result.program_artifact,
                )

        raise DomainError("optimization.no_artifact_generic", status=409)

    @router.get(
        "/optimizations/{optimization_id}/grid-result",
        response_model=GridSearchResponse,
        summary="Retrieve the full grid-search result with per-pair details",
    )
    def get_grid_search_result(optimization_id: str, current_user: AuthenticatedUserDep) -> GridSearchResponse:
        """Return all pair results for a finished grid search, including ``best_pair``.

        Only valid after the sweep reaches a terminal status. For live progress
        use ``GET /optimizations/{id}`` whose ``grid_result`` field updates
        in-flight.

        Args:
            optimization_id: Grid-search optimization id.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            The full ``GridSearchResponse`` including every pair.

        Raises:
            DomainError: 404 (unknown / inaccessible / not grid / no
                result), 409 (still running / failed without result), 500
                (corrupt result).
        """
        job_data = load_job_for_user(job_store, optimization_id, current_user)

        overview = parse_overview(job_data)
        if overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE) != OPTIMIZATION_TYPE_GRID_SEARCH:
            raise DomainError("grid_search.not_a_grid_search", status=404)

        status = status_to_job_status(job_data.get("status", "pending"))
        if status not in TERMINAL_STATUSES:
            raise DomainError("optimization.not_finished", status=409)

        result_data = job_data.get("result")
        if not result_data or not isinstance(result_data, dict):
            if status == OptimizationStatus.failed:
                error_msg = job_data.get("message") or "unknown error"
                raise DomainError("grid_search.failed_no_result", status=409, error=error_msg)
            if status == OptimizationStatus.cancelled:
                raise DomainError("grid_search.cancelled_no_result", status=409)
            raise DomainError("grid_search.no_result_available", status=404)

        try:
            return GridSearchResponse.model_validate(result_data)
        except ValidationError:
            raise DomainError("grid_search.corrupt_result", status=500) from None

    @router.get(
        "/optimizations/{optimization_id}/pair/{pair_index}/test-results",
        summary="Per-example test scores for one grid-search pair",
    )
    def get_pair_test_results(
        optimization_id: str, pair_index: int, current_user: AuthenticatedUserDep
    ) -> dict:
        """Per-pair analogue of ``GET /test-results`` with global-index remapping.

        Args:
            optimization_id: Grid-search optimization id.
            pair_index: Index of the pair to score.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            ``{"baseline": [...], "optimized": [...]}`` with global indices.

        Raises:
            DomainError: 404 (unknown / inaccessible / pair missing), 409
                (not a grid search, not success, or no stored result).
        """
        job_data = load_job_for_user(job_store, optimization_id, current_user)

        overview = parse_overview(job_data)
        optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)

        if optimization_type != OPTIMIZATION_TYPE_GRID_SEARCH:
            raise DomainError("grid_search.pair_test_results_grid_only", status=409)

        status = status_to_job_status(job_data.get("status", "pending"))
        if status != OptimizationStatus.success:
            raise DomainError(
                "optimization.not_success_status_for_test_results",
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

        payload = job_data.get("payload", {})
        dataset = payload.get("dataset", [])
        total = len(dataset)
        fractions_raw = payload.get("split_fractions", {})
        fractions = SplitFractions.model_validate(fractions_raw)
        shuffle = payload.get("shuffle", True)
        seed = payload.get("seed")
        effective_seed = seed if seed is not None else stable_seed(optimization_id)

        ordered = list(range(total))
        if shuffle:
            rng = random.Random(effective_seed)
            rng.shuffle(ordered)
        train_end = int(total * fractions.train)
        val_end = train_end + int(total * fractions.val)
        test_indices = ordered[val_end:]

        return {
            "baseline": remap_test_indices(pair.baseline_test_results, test_indices),
            "optimized": remap_test_indices(pair.optimized_test_results, test_indices),
        }
