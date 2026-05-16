"""Optimizer compile/evaluate/instantiate helpers for :class:`DspyService`.

Per-strategy plumbing around DSPy's optimizers: detecting whether the
factory accepts ``valset`` / ``metric`` kwargs, validating user-supplied
``optimizer_kwargs`` against the factory signature, evaluating compiled
programs on the test split, and injecting reflection LMs for GEPA.
"""

import inspect
import logging
from collections.abc import Callable
from typing import Any, Literal, overload

import dspy

from ...constants import (
    COMPILE_TRAINSET_KEY,
    COMPILE_VALSET_KEY,
    OPTIMIZER_METRIC_KEY,
    OPTIMIZER_NAME_GEPA,
    OPTIMIZER_REFLECTION_LM_KEY,
)
from ...exceptions import ServiceError
from ...models import ModelConfig
from ..language_models import build_language_model
from .data import DatasetSplits

logger = logging.getLogger(__name__)


def compile_program(
    *,
    optimizer: Any,
    program: Any,
    splits: DatasetSplits,
    metric: Any | None,
    compile_kwargs: dict[str, Any],
) -> Any:
    """Run optimizer.compile() with the derived trainset/valset.

    Passes ``valset`` only when the optimizer's compile signature accepts it,
    preventing TypeError on optimizers like BootstrapFewShot that do not.

    Args:
        optimizer: An instantiated DSPy optimizer.
        program: The DSPy program to compile.
        splits: Train/val/test partitions.
        metric: Optional metric callable (already wired into the optimizer).
        compile_kwargs: User-supplied kwargs forwarded to ``optimizer.compile``.

    Returns:
        The compiled DSPy program returned by ``optimizer.compile``.

    Raises:
        ServiceError: If ``splits.train`` is empty or the optimizer rejects
            the kwargs.
    """

    if not splits.train:
        raise ServiceError("Training split is empty; increase the train fraction or provide more data.")

    kwargs = dict(compile_kwargs or {})
    if COMPILE_TRAINSET_KEY not in kwargs:
        kwargs[COMPILE_TRAINSET_KEY] = splits.train

    if splits.val and _compile_accepts_valset(optimizer):
        kwargs.setdefault(COMPILE_VALSET_KEY, splits.val)

    try:
        return optimizer.compile(program, **kwargs)
    except TypeError as exc:
        raise ServiceError(f"Optimizer.compile rejected the provided arguments; update compile_kwargs: {exc}") from exc


def _compile_accepts_valset(optimizer: Any) -> bool:
    """Return True if the optimizer's compile() method accepts a valset parameter.

    Args:
        optimizer: An instantiated DSPy optimizer.

    Returns:
        True when ``optimizer.compile`` exposes a ``valset`` parameter.
    """
    compile_method = getattr(optimizer, "compile", None)
    if compile_method is None:
        return False
    try:
        sig = inspect.signature(compile_method)
        return COMPILE_VALSET_KEY in sig.parameters
    except (ValueError, TypeError):
        return False


@overload
def evaluate_on_test(
    program: Any,
    test_examples: list[Any],
    metric: Any,
    *,
    collect_per_example: Literal[True],
) -> tuple[float | None, list[dict]]: ...


@overload
def evaluate_on_test(
    program: Any,
    test_examples: list[Any],
    metric: Any,
    *,
    collect_per_example: Literal[False] = ...,
) -> float | None: ...


def evaluate_on_test(
    program: Any,
    test_examples: list[Any],
    metric: Any,
    *,
    collect_per_example: bool = False,
) -> tuple[float | None, list[dict]] | float | None:
    """Evaluate a compiled program on the test split using dspy.Evaluate.

    Args:
        program: The compiled DSPy program to evaluate.
        test_examples: Held-out examples to score.
        metric: The DSPy-compatible scoring callable.
        collect_per_example: When True, also return the per-row breakdown.

    Returns:
        The aggregate score as a float (or ``None`` when ``test_examples``
        is empty). When ``collect_per_example=True``, returns
        ``(score, list[dict])`` where each dict contains ``index``,
        ``outputs``, ``score``, and ``pass``.

    Raises:
        ServiceError: If the evaluator returns a non-numeric score.
    """

    if not test_examples:
        return (None, []) if collect_per_example else None

    evaluator = dspy.Evaluate(
        devset=test_examples,
        metric=metric,
        display_progress=True,
    )
    eval_result = evaluator(program)

    raw_results: list[Any]
    if isinstance(eval_result, (int, float)):
        aggregate = float(eval_result)
        raw_results = []
    else:
        score = getattr(eval_result, "score", None)
        if isinstance(score, (int, float)):
            aggregate = float(score)
        else:
            raise ServiceError("Evaluator returned a non-numeric result; ensure the metric's score is a float.")
        raw_results = getattr(eval_result, "results", []) or []

    if not collect_per_example:
        return aggregate

    # Each EvaluationResult.results entry is (example, prediction, score).
    per_example: list[dict] = []
    for i, entry in enumerate(raw_results):
        try:
            example, prediction, ex_score = entry
            # Metric may return a dspy.Prediction with a .score attribute
            if hasattr(ex_score, "score"):
                ex_score = ex_score.score
            ex_score = float(ex_score) if isinstance(ex_score, (int, float, bool)) else 0.0
            outputs = {}
            for k in example.labels():
                outputs[k] = getattr(prediction, k, None) if prediction else None
            per_example.append({"index": i, "outputs": outputs, "score": ex_score, "pass": ex_score > 0})
        except Exception:
            per_example.append({"index": i, "outputs": {}, "score": 0.0, "pass": False})

    return aggregate, per_example


def optimizer_requires_metric(factory: Callable[..., Any]) -> bool:
    """Return True if the optimizer factory (or any wrapped target) accepts a ``metric`` parameter.

    Wrapped callables (``__wrapped__``) and closure cells are also inspected
    so decorated factories report accurately.

    Args:
        factory: The optimizer factory callable.

    Returns:
        True when the factory or one of its wrapped targets accepts ``metric``.
    """

    try:
        sig = inspect.signature(factory)
    except (ValueError, TypeError):
        return False
    if "metric" in sig.parameters:
        return True

    if _callable_accepts_metric(factory):
        return True
    return any(_callable_accepts_metric(target) for target in _extract_factory_targets(factory))


def validate_optimizer_signature(factory: Callable[..., Any], name: str) -> None:
    """Warn if the optimizer factory is not introspectable.

    Args:
        factory: The optimizer factory callable.
        name: The optimizer's registered name (used in log output).
    """

    try:
        inspect.signature(factory)
    except (ValueError, TypeError):
        logger.warning("Unable to introspect optimizer '%s' signature.", name)


def validate_optimizer_kwargs(factory: Callable[..., Any], kwargs: dict[str, Any], name: str) -> None:
    """Validate user-supplied kwargs against the optimizer factory signature.

    Args:
        factory: The optimizer factory callable.
        kwargs: User-supplied keyword arguments.
        name: The optimizer's registered name (used in error messages).

    Raises:
        ServiceError: When ``kwargs`` cannot be bound to the factory signature.
    """

    if not kwargs:
        return
    try:
        sig = inspect.signature(factory)
    except (ValueError, TypeError):
        return
    try:
        sig.bind_partial(**kwargs)
    except TypeError as exc:
        raise ServiceError(f"optimizer_kwargs contain unsupported entries for '{name}': {exc}") from exc
    # bind_partial is too permissive when the factory accepts **kwargs — every
    # key matches the wildcard. Flag kwargs that aren't in the named params so
    # typos surface instead of silently passing.
    has_var_kw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    if has_var_kw:
        named = {k for k, p in sig.parameters.items() if p.kind is not inspect.Parameter.VAR_KEYWORD}
        unknown = sorted(k for k in kwargs if k not in named)
        if unknown:
            logger.warning(
                "Optimizer '%s' received kwargs %s not in named parameters — forwarded via **kwargs; verify spelling.",
                name,
                unknown,
            )


def instantiate_optimizer(
    factory: Callable[..., Any],
    optimizer_name: str,
    optimizer_kwargs: dict[str, Any],
    metric: Callable[..., Any],
    default_model: ModelConfig,
    reflection_model: ModelConfig | None,
    *,
    reflection_lm: Any | None = None,
) -> Any:
    """Instantiate an optimizer, injecting language models and metrics as needed.

    Per-optimizer injection rules:
    - All optimizers that expose a ``metric`` parameter receive it automatically.
    - GEPA additionally requires ``reflection_lm`` (built from ``reflection_model``)
      and defaults ``auto`` to ``"light"`` when no budget kwarg is supplied.

    Args:
        factory: The optimizer factory callable to invoke.
        optimizer_name: The optimizer's registered name.
        optimizer_kwargs: User-supplied factory kwargs.
        metric: The DSPy-compatible metric callable to inject when needed.
        default_model: Configuration for the generation model (currently
            informational; reserved for future per-optimizer wiring).
        reflection_model: Configuration for the reflection model (required
            when ``optimizer_name`` is GEPA and no ``reflection_lm`` is
            already provided).
        reflection_lm: Optional pre-built reflection LM instance. When
            supplied (e.g. so the caller can attach a timing callback
            bound to its identity), it bypasses construction from
            ``reflection_model``.

    Returns:
        An instantiated optimizer ready for ``compile``.

    Raises:
        ServiceError: When GEPA is requested without a reflection model.
    """

    optimizer_key = optimizer_name.lower()
    reflection_required_optimizers = {OPTIMIZER_NAME_GEPA}
    requires_metric = optimizer_requires_metric(factory)
    if not requires_metric and optimizer_key == OPTIMIZER_NAME_GEPA:
        requires_metric = True

    kwargs = dict(optimizer_kwargs or {})
    if requires_metric and OPTIMIZER_METRIC_KEY not in kwargs:
        kwargs[OPTIMIZER_METRIC_KEY] = metric
    # GEPA requires one of auto/max_full_evals/max_metric_calls — default to "light"
    if optimizer_key == OPTIMIZER_NAME_GEPA and not any(
        k in kwargs for k in ("auto", "max_full_evals", "max_metric_calls")
    ):
        kwargs["auto"] = "light"
    needs_reflection = optimizer_key in reflection_required_optimizers
    if OPTIMIZER_REFLECTION_LM_KEY not in kwargs:
        if reflection_lm is not None and needs_reflection:
            kwargs[OPTIMIZER_REFLECTION_LM_KEY] = reflection_lm
        elif reflection_model and needs_reflection:
            # Caching stays ON: this reflection LM runs inside GEPA's
            # training/eval region, and forcing cache off there suppresses
            # GEPA's recognized tqdm bar (regression from #23/#24).
            kwargs[OPTIMIZER_REFLECTION_LM_KEY] = build_language_model(reflection_model)
        elif needs_reflection:
            raise ServiceError(
                f"Optimizer '{optimizer_name}' requires reflection_model_config "
                "or a preconfigured 'reflection_lm' in optimizer_kwargs."
            )
    logger.debug("Creating optimizer %s with kwargs keys=%s", optimizer_name, list(kwargs.keys()))
    return factory(**kwargs)


def _callable_accepts_metric(target: Any) -> bool:
    """Return True when the callable exposes a ``metric`` parameter.

    Args:
        target: A callable to introspect.

    Returns:
        True when ``target`` has a ``metric`` parameter.
    """

    if target is None:
        return False
    try:
        sig = inspect.signature(target)
    except (ValueError, TypeError):
        return False
    return "metric" in sig.parameters


def _extract_factory_targets(factory: Callable[..., Any]) -> list[Any]:
    """Collect potential callable targets from wrappers/closures for metric-detection.

    Args:
        factory: The factory callable to deconstruct.

    Returns:
        A list of inner callables (``__wrapped__`` target, closure cell
        contents, and the factory itself) suitable for metric-detection.
    """

    targets: list[Any] = []
    wrapped = getattr(factory, "__wrapped__", None)
    if wrapped is not None:
        targets.append(wrapped)
    closure_cells = getattr(factory, "__closure__", None)
    if closure_cells:
        targets.extend(cell.cell_contents for cell in closure_cells)
    if callable(factory):
        targets.append(factory)
    return targets
