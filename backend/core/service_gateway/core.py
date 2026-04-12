import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import dspy

from ..constants import (
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
from ..exceptions import ServiceError
from ..models import (
    GridSearchRequest,
    GridSearchResponse,
    PairResult,
    RunRequest,
    RunResponse,
    SplitCounts,
)
from ..registry import (
    ResolverError,
    ServiceRegistry,
    UnknownRegistrationError,
    resolve_module_factory,
    resolve_optimizer_factory,
)
from .artifacts import persist_program
from .data import (
    extract_signature_fields,
    load_metric_from_code,
    load_signature_from_code,
    rows_to_examples,
    split_examples,
)
from .language_models import build_language_model
from .optimizers import (
    compile_program,
    evaluate_on_test,
    instantiate_optimizer,
    validate_optimizer_kwargs,
    validate_optimizer_signature,
)
from .progress import capture_tqdm
from .validators import (
    require_mapping_columns_in_dataset,
    require_mapping_matches_signature,
)

logger = logging.getLogger(__name__)


class DspyService:
    """High-level coordinator between FastAPI payloads and DSPy runtimes."""

    def __init__(
        self,
        registry: ServiceRegistry,
        default_seed: int | None = None,
    ):
        """Create a new DspyService instance.

        Args:
            registry: ServiceRegistry containing registered modules and optimizers.
            default_seed: Default random seed for reproducibility.
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
        """Execute an optimization workflow for a single request.

        Args:
            payload: RunRequest containing module, optimizer, dataset, and config.
            artifact_id: Optional identifier for the saved artifact.
            progress_callback: Optional callback invoked with progress events.

        Returns:
            RunResponse: Results including metrics and the optimized program artifact.

        Raises:
            ServiceError: If validation fails or optimization errors occur.
        """
        run_start = datetime.now(timezone.utc)
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
            payload.prompt_model_settings,
            payload.task_model_settings,
        )

        examples = rows_to_examples(payload.dataset, payload.column_mapping)
        logger.info("Converted dataset to %d DSPy examples", len(examples))

        splits = split_examples(
            examples,
            payload.split_fractions,
            shuffle=payload.shuffle,
            seed=payload.seed or self.default_seed,
        )
        logger.info(
            "Split dataset -> train=%d val=%d test=%d",
            len(splits.train),
            len(splits.val),
            len(splits.test),
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

        with dspy.context(lm=language_model):
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

            # Return the better program: if optimized is not better than baseline,
            # keep the original unoptimized program.
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

        runtime_seconds = (datetime.now(timezone.utc) - run_start).total_seconds()
        num_lm_calls = len(language_model.history) if hasattr(language_model, "history") else None
        avg_response_time_ms = round((runtime_seconds * 1000) / num_lm_calls, 1) if num_lm_calls else None
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
        """Run GEPA optimization for every (generation, reflection) model pair.

        Iterates over the cartesian product of generation and reflection model
        configs, running a full optimize-and-evaluate cycle for each pair.

        Args:
            payload: GridSearchRequest containing models, module, optimizer, and dataset.
            artifact_id: Optional base identifier for saved artifacts (suffixed per pair).
            progress_callback: Optional callback invoked with per-pair progress events.

        Returns:
            GridSearchResponse with per-pair results and the best-performing pair.
        """
        grid_start = datetime.now(timezone.utc)
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

        examples = rows_to_examples(payload.dataset, payload.column_mapping)
        splits = split_examples(
            examples,
            payload.split_fractions,
            shuffle=payload.shuffle,
            seed=payload.seed or self.default_seed,
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

        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        pair_results: list[PairResult] = [None] * total_pairs  # type: ignore[list-item]
        results_lock = threading.Lock()
        completed_count_ref = [0]
        failed_count_ref = [0]

        def _run_pair(i: int, gen_cfg, ref_cfg) -> PairResult:
            """Execute one grid-search pair end-to-end and return its result.

            Args:
                i: 0-based index of this pair within the sweep.
                gen_cfg: Generation model config for the pair.
                ref_cfg: Reflection model config for the pair.

            Returns:
                PairResult with metrics, runtime, and artifact — or error details
                if the pair failed.
            """
            from ..worker.log_handler import set_current_pair_index

            set_current_pair_index(i)
            pair_label = f"{gen_cfg.name} + {ref_cfg.name}"
            logger.info("Grid pair %d/%d: %s", i + 1, total_pairs, pair_label)
            if progress_callback:
                progress_callback(
                    PROGRESS_GRID_PAIR_STARTED,
                    {
                        "pair_index": i,
                        "total_pairs": total_pairs,
                        "generation_model": gen_cfg.name,
                        "reflection_model": ref_cfg.name,
                    },
                )

            pair_start = datetime.now(timezone.utc)
            try:
                program = module_factory(**module_kwargs)
                language_model = build_language_model(gen_cfg)
                optimizer = instantiate_optimizer(
                    optimizer_factory,
                    payload.optimizer_name,
                    payload.optimizer_kwargs,
                    metric,
                    gen_cfg,
                    ref_cfg,
                    None,
                    None,
                )

                with dspy.context(lm=language_model):
                    baseline = None
                    baseline_test_results: list[dict] = []
                    if splits.test:
                        baseline, baseline_test_results = evaluate_on_test(
                            program,
                            splits.test,
                            metric,
                            collect_per_example=True,
                        )
                        if progress_callback and baseline is not None:
                            progress_callback(
                                PROGRESS_BASELINE,
                                {
                                    DETAIL_BASELINE: baseline,
                                    "pair_index": i,
                                },
                            )

                    with capture_tqdm(progress_callback):
                        compiled = compile_program(
                            optimizer=optimizer,
                            program=program,
                            splits=splits,
                            metric=metric,
                            compile_kwargs=payload.compile_kwargs,
                        )

                    optimized = None
                    optimized_test_results: list[dict] = []
                    if splits.test:
                        optimized, optimized_test_results = evaluate_on_test(
                            compiled,
                            splits.test,
                            metric,
                            collect_per_example=True,
                        )
                        if progress_callback and optimized is not None:
                            progress_callback(
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

                art_id = f"{artifact_id}_pair_{i}" if artifact_id else None
                program_artifact = persist_program(best, art_id)

                improvement = None
                if baseline is not None and optimized is not None:
                    improvement = optimized - baseline

                pair_runtime = (datetime.now(timezone.utc) - pair_start).total_seconds()
                pair_lm_calls = len(language_model.history) if hasattr(language_model, "history") else None
                pair_avg_ms = round((pair_runtime * 1000) / pair_lm_calls, 1) if pair_lm_calls else None
                result = PairResult(
                    pair_index=i,
                    generation_model=gen_cfg.name,
                    reflection_model=ref_cfg.name,
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
                with results_lock:
                    completed_count_ref[0] += 1
                logger.info(
                    "Grid pair %d/%d completed: baseline=%.4f optimized=%.4f (%.1fs)",
                    i + 1,
                    total_pairs,
                    baseline or 0,
                    optimized or 0,
                    pair_runtime,
                )
                if progress_callback:
                    with results_lock:
                        c, f = completed_count_ref[0], failed_count_ref[0]
                    progress_callback(
                        PROGRESS_GRID_PAIR_COMPLETED,
                        {
                            "pair_index": i,
                            "total_pairs": total_pairs,
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
                pair_runtime = (datetime.now(timezone.utc) - pair_start).total_seconds()
                error_msg = str(exc)
                result = PairResult(
                    pair_index=i,
                    generation_model=gen_cfg.name,
                    reflection_model=ref_cfg.name,
                    error=error_msg,
                    runtime_seconds=round(pair_runtime, 2),
                )
                with results_lock:
                    failed_count_ref[0] += 1
                logger.warning(
                    "Grid pair %d/%d failed (%s): %s",
                    i + 1,
                    total_pairs,
                    pair_label,
                    error_msg,
                )
                if progress_callback:
                    with results_lock:
                        c, f = completed_count_ref[0], failed_count_ref[0]
                    progress_callback(
                        PROGRESS_GRID_PAIR_FAILED,
                        {
                            "pair_index": i,
                            "total_pairs": total_pairs,
                            "generation_model": gen_cfg.name,
                            "reflection_model": ref_cfg.name,
                            "error": error_msg,
                            "completed_so_far": c,
                            "failed_so_far": f,
                        },
                    )
                set_current_pair_index(None)
                return result

        max_workers = min(total_pairs, 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_run_pair, i, gen_cfg, ref_cfg): i for i, (gen_cfg, ref_cfg) in enumerate(pairs)}
            for future in as_completed(futures):
                idx = futures[future]
                pair_results[idx] = future.result()

        successful = [p for p in pair_results if p.error is None and p.optimized_test_metric is not None]
        best_pair = max(successful, key=lambda p: p.optimized_test_metric) if successful else None

        grid_runtime = (datetime.now(timezone.utc) - grid_start).total_seconds()
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
        """Validate a grid search request before job submission.

        Args:
            payload: GridSearchRequest to validate.

        Returns:
            None.

        Raises:
            ServiceError: If signature, metric, module, or optimizer validation fails.
        """
        signature_cls = load_signature_from_code(payload.signature_code)
        inputs, outputs = extract_signature_fields(signature_cls)
        require_mapping_matches_signature(payload.column_mapping, inputs, outputs)
        require_mapping_columns_in_dataset(payload.column_mapping, payload.dataset)
        load_metric_from_code(payload.metric_code)
        self._get_module_factory(payload.module_name)
        optimizer_factory = self._get_optimizer_factory(payload.optimizer_name)
        validate_optimizer_signature(optimizer_factory, payload.optimizer_name)
        validate_optimizer_kwargs(
            optimizer_factory,
            payload.optimizer_kwargs,
            payload.optimizer_name,
        )

    def validate_payload(self, payload: RunRequest) -> None:
        """Run additional validations prior to job submission.

        Args:
            payload: RunRequest to validate before execution.

        Returns:
            None.

        Raises:
            ServiceError: If validation fails for signature, metric, module, or optimizer.
        """
        logger.info(
            "Validating payload for module=%s optimizer=%s dataset_rows=%d",
            payload.module_name,
            payload.optimizer_name,
            len(payload.dataset),
        )

        signature_cls = load_signature_from_code(payload.signature_code)
        inputs, outputs = extract_signature_fields(signature_cls)
        require_mapping_matches_signature(payload.column_mapping, inputs, outputs)
        require_mapping_columns_in_dataset(payload.column_mapping, payload.dataset)
        load_metric_from_code(payload.metric_code)
        self._get_module_factory(payload.module_name)
        optimizer_factory = self._get_optimizer_factory(payload.optimizer_name)
        validate_optimizer_signature(optimizer_factory, payload.optimizer_name)
        validate_optimizer_kwargs(optimizer_factory, payload.optimizer_kwargs, payload.optimizer_name)
        logger.info("Payload validation succeeded for module=%s", payload.module_name)

    def _get_module_factory(self, name: str) -> tuple[Callable[..., Any], bool]:
        """Resolve the requested module factory from registry or DSPy.

        Args:
            name: Module name, either registered or a dotted path like 'dspy.ChainOfThought'.

        Returns:
            tuple: (factory_callable, auto_signature_flag) where auto_signature_flag
                indicates whether the signature should be auto-injected.

        Raises:
            ServiceError: If the module cannot be resolved.
        """
        try:
            return self.registry.get_module(name), False
        except UnknownRegistrationError:
            try:
                return resolve_module_factory(name)
            except ResolverError as exc:
                raise ServiceError(str(exc)) from exc

    def _get_optimizer_factory(self, name: str) -> Callable[..., Any]:
        """Resolve the requested optimizer factory from registry or DSPy.

        Args:
            name: Optimizer name, either registered or a dotted path like 'dspy.BootstrapFewShot'.

        Returns:
            Callable: Factory callable that creates the optimizer instance.

        Raises:
            ServiceError: If the optimizer cannot be resolved.
        """
        try:
            return self.registry.get_optimizer(name)
        except UnknownRegistrationError:
            try:
                return resolve_optimizer_factory(name)
            except ResolverError as exc:
                raise ServiceError(str(exc)) from exc
