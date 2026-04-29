"""High-level :class:`DspyService` facade for running optimization jobs.

Glues together signature/metric loading, dataset splitting, optimizer
instantiation, baseline-vs-optimized evaluation, artifact persistence,
and progress callbacks for both single-run and grid-search payloads.
The companion modules in this package handle the individual concerns;
this file orchestrates them.
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import dspy

from ...constants import (
    DETAIL_BASELINE,
    DETAIL_OPTIMIZED,
    DETAIL_TEST,
    DETAIL_TRAIN,
    DETAIL_VAL,
    META_COMPILE_KWARGS,
    META_MODEL_IDENTIFIER,
    META_MODULE_KWARGS,
    META_OPTIMIZER,
    META_OPTIMIZER_KWARGS,
    PROGRESS_BASELINE,
    PROGRESS_GRID_PAIR_COMPLETED,
    PROGRESS_GRID_PAIR_FAILED,
    PROGRESS_GRID_PAIR_STARTED,
    PROGRESS_OPTIMIZED,
    PROGRESS_SPLITS_READY,
)
from ...exceptions import ServiceError
from ...models import (
    GridSearchRequest,
    GridSearchResponse,
    PairResult,
    RunRequest,
    RunResponse,
    SplitCounts,
)
from ...registry import (
    ResolverError,
    ServiceRegistry,
    UnknownRegistrationError,
    resolve_module_factory,
    resolve_optimizer_factory,
)
from ...worker.log_handler import set_current_pair_index
from ..language_models import build_language_model
from ..safe_exec import validate_metric_code, validate_signature_code
from .artifacts import persist_program
from .data import (
    extract_signature_fields,
    extract_stratify_values,
    image_input_field_names,
    load_metric_from_code,
    load_signature_from_code,
    rows_to_examples,
    split_examples,
)
from .optimizers import (
    compile_program,
    evaluate_on_test,
    instantiate_optimizer,
    validate_optimizer_kwargs,
    validate_optimizer_signature,
)
from .progress import capture_tqdm
from .timing import GenLMTimingCallback
from .validators import (
    require_mapping_columns_in_dataset,
    require_mapping_matches_signature,
)

logger = logging.getLogger(__name__)


@dataclass
class _GridPairContext:
    """Shared state threaded through grid-search pair workers.

    Groups every value a pair worker previously pulled from the
    ``run_grid_search`` closure so the worker can live at module scope.
    Counters are mutated through ``results_lock`` (never directly); pair
    workers read the snapshot inside the lock so progress callbacks see a
    consistent view.
    """

    total_pairs: int
    module_factory: Any
    module_kwargs: dict[str, Any]
    payload: GridSearchRequest
    optimizer_factory: Any
    metric: Any
    splits: Any
    artifact_id: str | None
    progress_callback: Callable[[str, dict[str, Any]], None] | None
    results_lock: threading.Lock = field(default_factory=threading.Lock)
    completed: int = 0
    failed: int = 0


def _run_grid_pair(
    ctx: _GridPairContext,
    i: int,
    gen_cfg: Any,
    ref_cfg: Any,
) -> PairResult:
    """Execute one (generation_model, reflection_model) pair and return its ``PairResult``.

    Mirrors the per-pair flow of ``run_grid_search``: compiles the module,
    evaluates baseline and optimized programs on the test split, persists
    the better program, and emits progress events through
    ``ctx.progress_callback``. On failure returns a ``PairResult`` carrying
    the stringified exception rather than propagating — the caller treats
    unsuccessful pairs as soft failures.

    Args:
        ctx: Shared grid-pair context with payload, factories, and counters.
        i: Zero-based pair index for this worker.
        gen_cfg: Generation-model config for this pair.
        ref_cfg: Reflection-model config for this pair.

    Returns:
        The :class:`PairResult` for this pair (carrying an ``error`` string
        when execution failed).
    """
    set_current_pair_index(i)
    pair_label = f"{gen_cfg.name} + {ref_cfg.name}"
    logger.info("Grid pair %d/%d: %s", i + 1, ctx.total_pairs, pair_label)
    if ctx.progress_callback:
        ctx.progress_callback(
            PROGRESS_GRID_PAIR_STARTED,
            {
                "pair_index": i,
                "total_pairs": ctx.total_pairs,
                "generation_model": gen_cfg.name,
                "reflection_model": ref_cfg.name,
            },
        )

    pair_start = datetime.now(UTC)
    try:
        program = ctx.module_factory(**dict(ctx.module_kwargs))
        language_model = build_language_model(gen_cfg)
        gen_timing = GenLMTimingCallback(language_model)

        with dspy.context(lm=language_model, callbacks=[gen_timing]):
            optimizer = instantiate_optimizer(
                ctx.optimizer_factory,
                ctx.payload.optimizer_name,
                ctx.payload.optimizer_kwargs,
                ctx.metric,
                gen_cfg,
                ref_cfg,
            )
            baseline = None
            baseline_test_results: list[dict] = []
            if ctx.splits.test:
                baseline, baseline_test_results = evaluate_on_test(
                    program,
                    ctx.splits.test,
                    ctx.metric,
                    collect_per_example=True,
                )
                if ctx.progress_callback and baseline is not None:
                    ctx.progress_callback(
                        PROGRESS_BASELINE,
                        {
                            DETAIL_BASELINE: baseline,
                            "pair_index": i,
                        },
                    )

            with capture_tqdm(ctx.progress_callback):
                compiled = compile_program(
                    optimizer=optimizer,
                    program=program,
                    splits=ctx.splits,
                    metric=ctx.metric,
                    compile_kwargs=ctx.payload.compile_kwargs,
                )

            optimized = None
            optimized_test_results: list[dict] = []
            if ctx.splits.test:
                optimized, optimized_test_results = evaluate_on_test(
                    compiled,
                    ctx.splits.test,
                    ctx.metric,
                    collect_per_example=True,
                )
                if ctx.progress_callback and optimized is not None:
                    ctx.progress_callback(
                        PROGRESS_OPTIMIZED,
                        {
                            DETAIL_OPTIMIZED: optimized,
                            "pair_index": i,
                        },
                    )

        best = compiled
        if baseline is not None and optimized is not None and optimized < baseline:
            logger.warning(
                "Grid pair %d: optimized (%.4f) worse than baseline (%.4f) — keeping baseline",
                i,
                optimized,
                baseline,
            )
            best = program
            optimized = baseline

        art_id = f"{ctx.artifact_id}_pair_{i}" if ctx.artifact_id else None
        program_artifact = persist_program(best, art_id)

        improvement = None
        if baseline is not None and optimized is not None:
            improvement = optimized - baseline

        pair_runtime = (datetime.now(UTC) - pair_start).total_seconds()
        pair_lm_calls = len(language_model.history) if hasattr(language_model, "history") else None
        _, pair_avg_ms = gen_timing.summary()
        result = PairResult(
            pair_index=i,
            generation_model=gen_cfg.name,
            reflection_model=ref_cfg.name,
            generation_reasoning_effort=gen_cfg.extra.get("reasoning_effort"),
            reflection_reasoning_effort=ref_cfg.extra.get("reasoning_effort"),
            baseline_test_metric=baseline,
            optimized_test_metric=optimized,
            metric_improvement=improvement,
            runtime_seconds=round(pair_runtime, 2),
            num_lm_calls=pair_lm_calls,
            avg_response_time_ms=pair_avg_ms,
            program_artifact=program_artifact,
            baseline_test_results=baseline_test_results,
            optimized_test_results=optimized_test_results,
        )
        with ctx.results_lock:
            ctx.completed += 1
        logger.info(
            "Grid pair %d/%d completed: baseline=%.4f optimized=%.4f (%.1fs)",
            i + 1,
            ctx.total_pairs,
            baseline if baseline is not None else float("nan"),
            optimized if optimized is not None else float("nan"),
            pair_runtime,
        )
        if ctx.progress_callback:
            with ctx.results_lock:
                c, f = ctx.completed, ctx.failed
            ctx.progress_callback(
                PROGRESS_GRID_PAIR_COMPLETED,
                {
                    "pair_index": i,
                    "total_pairs": ctx.total_pairs,
                    "generation_model": gen_cfg.name,
                    "reflection_model": ref_cfg.name,
                    "baseline_test_metric": baseline,
                    "optimized_test_metric": optimized,
                    "metric_improvement": improvement,
                    "runtime_seconds": round(pair_runtime, 2),
                    "completed_so_far": c,
                    "failed_so_far": f,
                },
            )
        set_current_pair_index(None)
        return result

    except Exception as exc:
        pair_runtime = (datetime.now(UTC) - pair_start).total_seconds()
        error_msg = str(exc)
        result = PairResult(
            pair_index=i,
            generation_model=gen_cfg.name,
            reflection_model=ref_cfg.name,
            generation_reasoning_effort=gen_cfg.extra.get("reasoning_effort"),
            reflection_reasoning_effort=ref_cfg.extra.get("reasoning_effort"),
            error=error_msg,
            runtime_seconds=round(pair_runtime, 2),
        )
        with ctx.results_lock:
            ctx.failed += 1
        logger.warning(
            "Grid pair %d/%d failed (%s): %s",
            i + 1,
            ctx.total_pairs,
            pair_label,
            error_msg,
        )
        if ctx.progress_callback:
            with ctx.results_lock:
                c, f = ctx.completed, ctx.failed
            ctx.progress_callback(
                PROGRESS_GRID_PAIR_FAILED,
                {
                    "pair_index": i,
                    "total_pairs": ctx.total_pairs,
                    "generation_model": gen_cfg.name,
                    "reflection_model": ref_cfg.name,
                    "error": error_msg,
                    "completed_so_far": c,
                    "failed_so_far": f,
                },
            )
        set_current_pair_index(None)
        return result


class DspyService:
    """High-level coordinator between FastAPI payloads and DSPy runtimes."""

    def __init__(
        self,
        registry: ServiceRegistry,
        default_seed: int | None = None,
    ):
        """Initialize DspyService with a module/optimizer registry and optional default seed.

        Args:
            registry: Module/optimizer registry used to resolve named factories.
            default_seed: Optional default split seed when a payload omits one.
        """
        self.registry = registry
        self.default_seed = default_seed

    def run(
        self,
        payload: RunRequest,
        *,
        artifact_id: str | None = None,
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> RunResponse:
        """Execute a single DSPy optimization run and return a structured response.

        Loads the signature, module, metric, and optimizer from the payload,
        splits the dataset, runs baseline evaluation, compiles the program, then
        evaluates the optimized result.  If the optimized program scores lower than
        the baseline on the test set, the baseline program is returned instead and
        the reported optimized metric is swapped to the baseline value.

        Args:
            payload: The validated run request to execute.
            artifact_id: Optional identifier carried into artifact storage.
            progress_callback: Optional callback receiving ``(event, detail)`` updates.

        Returns:
            A populated :class:`RunResponse` summarising the run.
        """
        run_start = datetime.now(UTC)
        logger.info(
            "Starting DSPy run: module=%s optimizer=%s dataset_rows=%d",
            payload.module_name,
            payload.optimizer_name,
            len(payload.dataset),
        )

        signature_cls = load_signature_from_code(payload.signature_code)
        signature_inputs, signature_outputs = extract_signature_fields(signature_cls)
        logger.debug(
            "Loaded signature %s with inputs=%s outputs=%s",
            signature_cls.__name__,
            signature_inputs,
            signature_outputs,
        )
        require_mapping_matches_signature(payload.column_mapping, signature_inputs, signature_outputs)
        module_factory, auto_signature = self._get_module_factory(payload.module_name)
        module_kwargs = dict(payload.module_kwargs)
        if auto_signature or "signature" not in module_kwargs:
            module_kwargs["signature"] = signature_cls
        program = module_factory(**module_kwargs)

        metric = load_metric_from_code(payload.metric_code)
        metric_identifier = getattr(metric, "__name__", "inline_metric")

        language_model = build_language_model(payload.model_settings)
        optimizer_factory = self._get_optimizer_factory(payload.optimizer_name)
        optimizer = instantiate_optimizer(
            optimizer_factory,
            payload.optimizer_name,
            payload.optimizer_kwargs,
            metric,
            payload.model_settings,
            payload.reflection_model_settings,
        )

        examples = rows_to_examples(
            payload.dataset,
            payload.column_mapping,
            image_input_fields=image_input_field_names(signature_cls),
        )
        logger.info("Converted dataset to %d DSPy examples", len(examples))

        stratify_values = (
            extract_stratify_values(
                examples,
                payload.column_mapping,
                column=payload.stratify_column,
            )
            if payload.stratify
            else None
        )
        splits = split_examples(
            examples,
            payload.split_fractions,
            shuffle=payload.shuffle,
            seed=payload.seed or self.default_seed,
            stratify_values=stratify_values,
        )
        logger.info(
            "Split dataset -> train=%d val=%d test=%d (stratify=%s)",
            len(splits.train),
            len(splits.val),
            len(splits.test),
            payload.stratify,
        )
        if progress_callback:
            progress_callback(
                PROGRESS_SPLITS_READY,
                {
                    DETAIL_TRAIN: len(splits.train),
                    DETAIL_VAL: len(splits.val),
                    DETAIL_TEST: len(splits.test),
                },
            )

        gen_timing = GenLMTimingCallback(language_model)
        with dspy.context(lm=language_model, callbacks=[gen_timing]):
            baseline_test_metric = None
            baseline_test_results: list[dict] = []
            if splits.test:
                baseline_test_metric, baseline_test_results = evaluate_on_test(
                    program,
                    splits.test,
                    metric,
                    collect_per_example=True,
                )
                logger.info("Baseline test metric: %s", baseline_test_metric)
                if progress_callback and baseline_test_metric is not None:
                    progress_callback(
                        PROGRESS_BASELINE,
                        {DETAIL_BASELINE: baseline_test_metric},
                    )

            logger.info("Compiling program via optimizer=%s", payload.optimizer_name)
            with capture_tqdm(progress_callback):
                compiled_program = compile_program(
                    optimizer=optimizer,
                    program=program,
                    splits=splits,
                    metric=metric,
                    compile_kwargs=payload.compile_kwargs,
                )
            logger.info("Optimizer compile completed successfully")

            optimized_test_metric = None
            optimized_test_results: list[dict] = []
            if splits.test:
                optimized_test_metric, optimized_test_results = evaluate_on_test(
                    compiled_program,
                    splits.test,
                    metric,
                    collect_per_example=True,
                )
                logger.info("Optimized test metric: %s", optimized_test_metric)
                if progress_callback and optimized_test_metric is not None:
                    progress_callback(
                        PROGRESS_OPTIMIZED,
                        {DETAIL_OPTIMIZED: optimized_test_metric},
                    )

            best_program = compiled_program
            if (
                baseline_test_metric is not None
                and optimized_test_metric is not None
                and optimized_test_metric < baseline_test_metric
            ):
                logger.warning(
                    "Optimized program (%.4f) is worse than baseline (%.4f) — returning baseline program",
                    optimized_test_metric,
                    baseline_test_metric,
                )
                best_program = program
                # Swap so the "optimized" metric reflects what we're actually returning
                optimized_test_metric = baseline_test_metric

        program_artifact = persist_program(best_program, artifact_id)
        if program_artifact:
            logger.info("Program artifact created with base64 payload")

        split_counts = SplitCounts(train=len(splits.train), val=len(splits.val), test=len(splits.test))

        details: dict[str, Any] = {
            DETAIL_TRAIN: split_counts.train,
            DETAIL_VAL: split_counts.val,
            DETAIL_TEST: split_counts.test,
            DETAIL_BASELINE: baseline_test_metric,
            DETAIL_OPTIMIZED: optimized_test_metric,
        }

        optimization_metadata = {
            META_OPTIMIZER: payload.optimizer_name,
            META_OPTIMIZER_KWARGS: payload.optimizer_kwargs,
            META_COMPILE_KWARGS: payload.compile_kwargs,
            META_MODULE_KWARGS: payload.module_kwargs,
            META_MODEL_IDENTIFIER: payload.model_settings.normalized_identifier(),
        }

        metric_improvement = None
        if baseline_test_metric is not None and optimized_test_metric is not None:
            metric_improvement = optimized_test_metric - baseline_test_metric

        runtime_seconds = (datetime.now(UTC) - run_start).total_seconds()
        # num_lm_calls comes from LM history (preserves counting for mocked LMs);
        # avg is wall-clock time spent inside the generation LM only, via the callback.
        num_lm_calls = len(language_model.history) if hasattr(language_model, "history") else None
        _, avg_response_time_ms = gen_timing.summary()
        response = RunResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name=metric_identifier,
            split_counts=split_counts,
            baseline_test_metric=baseline_test_metric,
            optimized_test_metric=optimized_test_metric,
            metric_improvement=metric_improvement,
            optimization_metadata=optimization_metadata,
            details=details,
            program_artifact_path=program_artifact.path if program_artifact else None,
            program_artifact=program_artifact,
            runtime_seconds=runtime_seconds,
            num_lm_calls=num_lm_calls,
            avg_response_time_ms=avg_response_time_ms,
            baseline_test_results=baseline_test_results,
            optimized_test_results=optimized_test_results,
        )

        logger.info(
            "DSPy run finished: module=%s optimizer=%s status=success",
            payload.module_name,
            payload.optimizer_name,
        )
        return response

    def run_grid_search(
        self,
        payload: GridSearchRequest,
        *,
        artifact_id: str | None = None,
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> GridSearchResponse:
        """Run one optimization per (generation_model, reflection_model) pair and return all results.

        Pairs are executed concurrently (up to 4 threads).  Each pair follows the
        same baseline-vs-optimized fallback logic as ``run()``.  Failed pairs are
        recorded with their error message rather than aborting the whole search.

        Args:
            payload: The validated grid-search request to execute.
            artifact_id: Optional identifier carried into per-pair artifacts.
            progress_callback: Optional callback receiving ``(event, detail)`` updates.

        Returns:
            A populated :class:`GridSearchResponse` with per-pair results
            and the best overall pair.
        """
        grid_start = datetime.now(UTC)
        pairs = [(gen_cfg, ref_cfg) for gen_cfg in payload.generation_models for ref_cfg in payload.reflection_models]
        total_pairs = len(pairs)
        logger.info(
            "Starting grid search: %d pairs, module=%s optimizer=%s",
            total_pairs,
            payload.module_name,
            payload.optimizer_name,
        )

        signature_cls = load_signature_from_code(payload.signature_code)
        signature_inputs, signature_outputs = extract_signature_fields(signature_cls)
        require_mapping_matches_signature(
            payload.column_mapping,
            signature_inputs,
            signature_outputs,
        )
        module_factory, auto_signature = self._get_module_factory(payload.module_name)
        module_kwargs = dict(payload.module_kwargs)
        if auto_signature or "signature" not in module_kwargs:
            module_kwargs["signature"] = signature_cls

        metric = load_metric_from_code(payload.metric_code)
        metric_identifier = getattr(metric, "__name__", "inline_metric")
        optimizer_factory = self._get_optimizer_factory(payload.optimizer_name)

        examples = rows_to_examples(
            payload.dataset,
            payload.column_mapping,
            image_input_fields=image_input_field_names(signature_cls),
        )
        stratify_values = (
            extract_stratify_values(
                examples,
                payload.column_mapping,
                column=payload.stratify_column,
            )
            if payload.stratify
            else None
        )
        splits = split_examples(
            examples,
            payload.split_fractions,
            shuffle=payload.shuffle,
            seed=payload.seed or self.default_seed,
            stratify_values=stratify_values,
        )
        split_counts = SplitCounts(
            train=len(splits.train),
            val=len(splits.val),
            test=len(splits.test),
        )
        if progress_callback:
            progress_callback(
                PROGRESS_SPLITS_READY,
                {
                    DETAIL_TRAIN: split_counts.train,
                    DETAIL_VAL: split_counts.val,
                    DETAIL_TEST: split_counts.test,
                    "total_pairs": total_pairs,
                },
            )

        pair_results: list[PairResult] = [None] * total_pairs  # type: ignore[list-item]
        grid_ctx = _GridPairContext(
            total_pairs=total_pairs,
            module_factory=module_factory,
            module_kwargs=module_kwargs,
            payload=payload,
            optimizer_factory=optimizer_factory,
            metric=metric,
            splits=splits,
            artifact_id=artifact_id,
            progress_callback=progress_callback,
        )

        max_workers = min(total_pairs, 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_run_grid_pair, grid_ctx, i, gen_cfg, ref_cfg): i
                for i, (gen_cfg, ref_cfg) in enumerate(pairs)
            }
            for future in as_completed(futures):
                idx = futures[future]
                pair_results[idx] = future.result()

        successful = [p for p in pair_results if p.error is None and p.optimized_test_metric is not None]
        best_pair = (
            max(successful, key=lambda p: p.optimized_test_metric if p.optimized_test_metric is not None else float("-inf"))
            if successful
            else None
        )

        grid_runtime = (datetime.now(UTC) - grid_start).total_seconds()
        completed_count = len([p for p in pair_results if p.error is None])
        failed_count = len([p for p in pair_results if p.error is not None])

        logger.info(
            "Grid search finished: %d/%d completed, %d failed, best=%s (%.1fs total)",
            completed_count,
            total_pairs,
            failed_count,
            f"{best_pair.generation_model}+{best_pair.reflection_model}" if best_pair else "none",
            grid_runtime,
        )

        return GridSearchResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name=metric_identifier,
            split_counts=split_counts,
            total_pairs=total_pairs,
            completed_pairs=completed_count,
            failed_pairs=failed_count,
            pair_results=pair_results,
            best_pair=best_pair,
            runtime_seconds=round(grid_runtime, 2),
        )

    def validate_grid_search_payload(self, payload: GridSearchRequest) -> None:
        """Validate a GridSearchRequest without executing any optimization.

        User-authored signature and metric code is exec'd inside isolated
        subprocesses via ``safe_exec`` — this runs in the API/worker-engine
        process, so we cannot trust the exec to live here.

        Args:
            payload: The grid-search request to validate.

        Raises:
            ServiceError: When any field fails validation (mapping mismatch,
                unknown module/optimizer, malformed kwargs, etc.).
        """
        intro = validate_signature_code(payload.signature_code)
        require_mapping_matches_signature(payload.column_mapping, intro.input_fields, intro.output_fields)
        require_mapping_columns_in_dataset(payload.column_mapping, payload.dataset)
        validate_metric_code(payload.metric_code)
        self._get_module_factory(payload.module_name)
        optimizer_factory = self._get_optimizer_factory(payload.optimizer_name)
        validate_optimizer_signature(optimizer_factory, payload.optimizer_name)
        validate_optimizer_kwargs(
            optimizer_factory,
            payload.optimizer_kwargs,
            payload.optimizer_name,
        )

    def validate_payload(self, payload: RunRequest) -> None:
        """Validate a RunRequest without executing any optimization.

        User-authored signature and metric code is exec'd inside isolated
        subprocesses via ``safe_exec`` — this runs in the API/worker-engine
        process, so we cannot trust the exec to live here.

        Args:
            payload: The run request to validate.

        Raises:
            ServiceError: When any field fails validation (mapping mismatch,
                unknown module/optimizer, malformed kwargs, etc.).
        """
        logger.info(
            "Validating payload for module=%s optimizer=%s dataset_rows=%d",
            payload.module_name,
            payload.optimizer_name,
            len(payload.dataset),
        )

        intro = validate_signature_code(payload.signature_code)
        require_mapping_matches_signature(payload.column_mapping, intro.input_fields, intro.output_fields)
        require_mapping_columns_in_dataset(payload.column_mapping, payload.dataset)
        validate_metric_code(payload.metric_code)
        self._get_module_factory(payload.module_name)
        optimizer_factory = self._get_optimizer_factory(payload.optimizer_name)
        validate_optimizer_signature(optimizer_factory, payload.optimizer_name)
        validate_optimizer_kwargs(optimizer_factory, payload.optimizer_kwargs, payload.optimizer_name)
        logger.info("Payload validation succeeded for module=%s", payload.module_name)

    def _get_module_factory(self, name: str) -> tuple[Callable[..., Any], bool]:
        """Resolve a module factory by name from registry or built-in resolver.

        Args:
            name: The module factory name to resolve.

        Returns:
            A tuple ``(factory, auto_signature)`` where ``auto_signature``
            is False for registry entries and True for resolver-provided ones.

        Raises:
            ServiceError: When ``name`` cannot be resolved.
        """
        try:
            return self.registry.get_module(name), False
        except UnknownRegistrationError:
            try:
                return resolve_module_factory(name)
            except ResolverError as exc:
                raise ServiceError(str(exc)) from exc

    def _get_optimizer_factory(self, name: str) -> Callable[..., Any]:
        """Resolve an optimizer factory by name from registry or built-in resolver.

        Args:
            name: The optimizer factory name to resolve.

        Returns:
            The resolved optimizer factory callable.

        Raises:
            ServiceError: When ``name`` cannot be resolved.
        """
        try:
            return self.registry.get_optimizer(name)
        except UnknownRegistrationError:
            try:
                return resolve_optimizer_factory(name)
            except ResolverError as exc:
                raise ServiceError(str(exc)) from exc
