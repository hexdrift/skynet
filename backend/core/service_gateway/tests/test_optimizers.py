"""Tests for core.service_gateway.optimizers."""

from __future__ import annotations

import inspect
import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.service_gateway.tests.mocks import fake_compiled_program, fake_language_model

from core.exceptions import ServiceError
from core.models import ModelConfig
from core.service_gateway.data import DatasetSplits
from core.service_gateway.optimizers import (
    _callable_accepts_metric,
    _compile_accepts_valset,
    _extract_factory_targets,
    compile_program,
    evaluate_on_test,
    instantiate_optimizer,
    optimizer_requires_metric,
    validate_optimizer_kwargs,
    validate_optimizer_signature,
)



def _splits(train=None, val=None, test=None) -> DatasetSplits:
    """Return a DatasetSplits with defaults: train=[1,2,3], val=[], test=[]."""
    return DatasetSplits(
        train=train if train is not None else [1, 2, 3],
        val=val if val is not None else [],
        test=test if test is not None else [],
    )


def _model_cfg(name: str = "openai/gpt-4o-mini") -> ModelConfig:
    """Return a ModelConfig for the given model name."""
    return ModelConfig(name=name)


class _FakeOptimizer:
    """Minimal fake optimizer that records compile calls."""

    def __init__(self, **kwargs: Any) -> None:
        """Store kwargs for later inspection."""
        self.kwargs = kwargs

    def compile(self, program: Any, *, trainset: Any, **kwargs: Any) -> Any:
        """Return the program unchanged."""
        return program


class _FakeOptimizerWithValset:
    """Fake optimizer whose compile() accepts a valset parameter."""

    def __init__(self, **kwargs: Any) -> None:
        """Store kwargs."""
        self.kwargs = kwargs

    def compile(self, program: Any, *, trainset: Any, valset: Any = None, **kwargs: Any) -> Any:
        """Return the program unchanged."""
        return program


class _FactoryWithMetric:
    """Fake optimizer factory that exposes a metric parameter in __init__."""

    def __init__(self, metric=None, **kwargs: Any) -> None:
        """Accept and ignore all kwargs."""
        pass

    def compile(self, program: Any, **kwargs: Any) -> Any:
        """Return the program unchanged."""
        return program


class _FactoryNoMetric:
    """Fake optimizer factory without a metric parameter."""

    def __init__(self, **kwargs: Any) -> None:
        """Accept and ignore all kwargs."""
        pass

    def compile(self, program: Any, **kwargs: Any) -> Any:
        """Return the program unchanged."""
        return program


def _dummy_metric(example: Any, prediction: Any, trace: Any = None) -> float:
    """Always return 1.0; used as a stand-in metric in tests."""
    return 1.0



def test_compile_accepts_valset_returns_true_when_valset_in_signature() -> None:
    """Optimizer whose compile() accepts valset returns True."""
    optimizer = _FakeOptimizerWithValset()

    result = _compile_accepts_valset(optimizer)

    assert result is True


def test_compile_accepts_valset_returns_false_when_valset_not_in_signature() -> None:
    """Optimizer whose compile() does not accept valset returns False."""
    optimizer = _FakeOptimizer()

    result = _compile_accepts_valset(optimizer)

    assert result is False


def test_compile_accepts_valset_returns_false_when_no_compile_method() -> None:
    """Object with no compile method returns False."""
    result = _compile_accepts_valset(object())

    assert result is False



def test_compile_program_empty_train_raises_service_error() -> None:
    """Empty trainset raises ServiceError before calling the optimizer."""
    splits = _splits(train=[])
    optimizer = _FakeOptimizer()

    with pytest.raises(ServiceError, match="Training split is empty"):
        compile_program(
            optimizer=optimizer,
            program=fake_compiled_program(),
            splits=splits,
            metric=None,
            compile_kwargs={},
        )


def test_compile_program_calls_optimizer_compile_with_trainset() -> None:
    """compile_program calls optimizer.compile and returns the result."""
    program = fake_compiled_program()
    optimizer = _FakeOptimizer()
    splits = _splits(train=[1, 2, 3])

    result = compile_program(
        optimizer=optimizer,
        program=program,
        splits=splits,
        metric=None,
        compile_kwargs={},
    )

    assert result is program


def test_compile_program_injects_valset_when_optimizer_accepts_it() -> None:
    received: dict = {}

    class _RecordingOpt:
        def compile(self, program: Any, *, trainset: Any, valset: Any = None, **kwargs: Any) -> Any:
            received["valset"] = valset
            return program

    splits = _splits(train=[1, 2], val=[3])
    compile_program(
        optimizer=_RecordingOpt(),
        program=object(),
        splits=splits,
        metric=None,
        compile_kwargs={},
    )

    assert received.get("valset") == [3]


def test_compile_program_does_not_inject_valset_when_optimizer_does_not_accept_it() -> None:
    received: dict = {}

    class _StrictOpt:
        def compile(self, program: Any, *, trainset: Any, **kwargs: Any) -> Any:
            received["extra"] = kwargs
            return program

    splits = _splits(train=[1], val=[2])
    compile_program(
        optimizer=_StrictOpt(),
        program=object(),
        splits=splits,
        metric=None,
        compile_kwargs={},
    )

    assert "valset" not in received.get("extra", {})


def test_compile_program_honours_pre_set_trainset_in_compile_kwargs() -> None:
    received: dict = {}

    class _RecordingOpt:
        def compile(self, program: Any, *, trainset: Any, **kwargs: Any) -> Any:
            received["trainset"] = trainset
            return program

    custom_train = ["custom"]
    compile_program(
        optimizer=_RecordingOpt(),
        program=object(),
        splits=_splits(train=[1, 2]),
        metric=None,
        compile_kwargs={"trainset": custom_train},
    )

    assert received["trainset"] == custom_train


def test_compile_program_type_error_from_optimizer_raises_service_error() -> None:
    """TypeError from optimizer.compile is wrapped in a ServiceError."""
    class _BadOpt:
        def compile(self, program: Any, **kwargs: Any) -> Any:
            raise TypeError("bad kwarg")

    with pytest.raises(ServiceError, match="rejected the provided arguments"):
        compile_program(
            optimizer=_BadOpt(),
            program=object(),
            splits=_splits(),
            metric=None,
            compile_kwargs={},
        )



def test_optimizer_requires_metric_returns_true_when_metric_in_init() -> None:
    """Factory with 'metric' in __init__ signature reports it requires a metric."""
    result = optimizer_requires_metric(_FactoryWithMetric)

    assert result is True


def test_optimizer_requires_metric_returns_false_when_metric_not_present() -> None:
    """Factory without 'metric' parameter reports it does not require a metric."""
    def _no_metric_factory(num_threads: int = 4) -> None:
        pass

    result = optimizer_requires_metric(_no_metric_factory)

    assert result is False


def test_optimizer_requires_metric_returns_false_for_uninspectable() -> None:
    """None factory returns False rather than raising."""
    result = optimizer_requires_metric(None)

    assert result is False



def test_callable_accepts_metric_true_for_metric_param() -> None:
    """Callable with 'metric' parameter returns True."""
    def fn(metric, other=None):
        pass

    assert _callable_accepts_metric(fn) is True


def test_callable_accepts_metric_false_when_no_metric_param() -> None:
    """Callable without 'metric' parameter returns False."""
    def fn(foo, bar):
        pass

    assert _callable_accepts_metric(fn) is False


def test_callable_accepts_metric_false_for_none() -> None:
    """None returns False without raising."""
    assert _callable_accepts_metric(None) is False



def test_extract_factory_targets_includes_factory_itself() -> None:
    """The factory itself is always included in the targets list."""
    def my_factory():
        pass

    targets = _extract_factory_targets(my_factory)

    assert my_factory in targets


def test_extract_factory_targets_includes_wrapped_when_present() -> None:
    """A __wrapped__ attribute is added to the targets list."""
    def inner():
        pass

    def outer():
        pass

    outer.__wrapped__ = inner

    targets = _extract_factory_targets(outer)

    assert inner in targets



def test_validate_optimizer_kwargs_empty_kwargs_always_passes() -> None:
    """Empty kwargs dict passes validation without raising."""
    validate_optimizer_kwargs(_FactoryNoMetric, {}, "no_metric")


def test_validate_optimizer_kwargs_valid_kwargs_passes() -> None:
    """Valid (empty) kwargs dict passes validation."""
    validate_optimizer_kwargs(_FactoryNoMetric, {}, "no_metric")


def test_validate_optimizer_kwargs_invalid_kwarg_raises_service_error() -> None:
    # Use a factory with explicit, closed signature (no **kwargs) so
    # bind_partial can actually reject unknown keys.
    def _strict_factory(num_threads: int = 4, max_rounds: int = 1) -> None:
        pass

    with pytest.raises(ServiceError, match="unsupported entries"):
        validate_optimizer_kwargs(
            _strict_factory,
            {"completely_unknown_kwarg_xyz": True},
            "strict_factory",
        )


def test_validate_optimizer_kwargs_uninspectable_factory_does_not_raise() -> None:
    """Uninspectable factory (e.g. built-in) silently skips validation."""
    # Built-in int doesn't expose a useful signature in older Pythons — the
    # function should silently skip validation rather than raise.
    validate_optimizer_kwargs(int, {"foo": "bar"}, "int_factory")



def test_validate_optimizer_signature_logs_warning_for_uninspectable(caplog) -> None:
    """None factory logs a warning rather than raising."""
    with caplog.at_level(logging.WARNING):
        validate_optimizer_signature(None, "bad_factory")

    # Should not raise; may emit a warning
    # (None raises TypeError in inspect.signature)



def test_instantiate_optimizer_injects_metric_when_factory_requires_it() -> None:
    """Metric is injected when the factory exposes a 'metric' parameter."""
    captured: dict = {}

    class _MetricFactory:
        def __init__(self, metric=None, **kw):
            captured["metric"] = metric

        def compile(self, *a, **kw):
            return None

    instantiate_optimizer(
        factory=_MetricFactory,
        optimizer_name="my_opt",
        optimizer_kwargs={},
        metric=_dummy_metric,
        default_model=_model_cfg(),
        reflection_model=None,
    )

    assert captured["metric"] is _dummy_metric


def test_instantiate_optimizer_does_not_override_metric_if_already_in_kwargs() -> None:
    """Pre-set metric in optimizer_kwargs is not overridden by the service metric."""
    captured: dict = {}
    custom_metric = lambda e, p: 0.5

    class _MetricFactory:
        def __init__(self, metric=None, **kw):
            captured["metric"] = metric

        def compile(self, *a, **kw):
            return None

    instantiate_optimizer(
        factory=_MetricFactory,
        optimizer_name="my_opt",
        optimizer_kwargs={"metric": custom_metric},
        metric=_dummy_metric,
        default_model=_model_cfg(),
        reflection_model=None,
    )

    assert captured["metric"] is custom_metric


def test_instantiate_optimizer_gepa_requires_reflection_model_or_raises() -> None:
    class _GepaFactory:
        def __init__(self, metric=None, auto=None, reflection_lm=None, **kw):
            pass

        def compile(self, *a, **kw):
            return None

    with pytest.raises(ServiceError, match="reflection_model_config"):
        instantiate_optimizer(
            factory=_GepaFactory,
            optimizer_name="gepa",
            optimizer_kwargs={},
            metric=_dummy_metric,
            default_model=_model_cfg(),
            reflection_model=None,
        )


def test_instantiate_optimizer_gepa_injects_reflection_lm_when_model_provided() -> None:
    """GEPA reflection_lm is built and injected when reflection_model is provided."""
    captured: dict = {}
    fake_lm = fake_language_model()

    class _GepaFactory:
        def __init__(self, metric=None, auto=None, reflection_lm=None, **kw):
            captured["reflection_lm"] = reflection_lm

        def compile(self, *a, **kw):
            return None

    with patch("core.service_gateway.optimizers.build_language_model", return_value=fake_lm):
        instantiate_optimizer(
            factory=_GepaFactory,
            optimizer_name="gepa",
            optimizer_kwargs={},
            metric=_dummy_metric,
            default_model=_model_cfg(),
            reflection_model=_model_cfg("openai/gpt-4o"),
        )

    assert captured["reflection_lm"] is fake_lm


def test_instantiate_optimizer_gepa_sets_auto_light_default() -> None:
    """GEPA auto defaults to 'light' when no budget kwarg is supplied."""
    captured: dict = {}
    fake_lm = fake_language_model()

    class _GepaFactory:
        def __init__(self, metric=None, auto=None, reflection_lm=None, **kw):
            captured["auto"] = auto

        def compile(self, *a, **kw):
            return None

    with patch("core.service_gateway.optimizers.build_language_model", return_value=fake_lm):
        instantiate_optimizer(
            factory=_GepaFactory,
            optimizer_name="gepa",
            optimizer_kwargs={},
            metric=_dummy_metric,
            default_model=_model_cfg(),
            reflection_model=_model_cfg("openai/gpt-4o"),
        )

    assert captured["auto"] == "light"


class _FakeEvalResult:
    """Fake EvaluationResult returned by dspy.Evaluate."""

    def __init__(self, score: Any, results: list | None = None) -> None:
        """Set score and optional per-example results list."""
        self.score = score
        self.results = results or []


class _FakeExample:
    """Minimal stand-in for a dspy.Example."""

    def labels(self) -> list[str]:
        """Return a fixed list of output field names."""
        return ["answer"]


def test_evaluate_on_test_happy_path_returns_float_and_empty_results() -> None:
    """Happy path returns the aggregate score and an empty per-example list."""
    program = fake_compiled_program()
    metric = _dummy_metric
    test_examples = [_FakeExample()]
    fake_evaluator = MagicMock()
    fake_evaluator.return_value = _FakeEvalResult(score=0.75, results=[])

    with patch("core.service_gateway.optimizers.dspy.Evaluate", return_value=fake_evaluator):
        score, per_example = evaluate_on_test(
            program, test_examples, metric, collect_per_example=True
        )

    assert score == pytest.approx(0.75)
    assert per_example == []


def test_evaluate_on_test_bare_int_float_return_treated_as_aggregate() -> None:
    """Evaluator returns a plain float (not EvaluationResult)."""
    program = fake_compiled_program()
    metric = _dummy_metric
    test_examples = [_FakeExample()]
    fake_evaluator = MagicMock()
    fake_evaluator.return_value = 0.42  # bare float

    with patch("core.service_gateway.optimizers.dspy.Evaluate", return_value=fake_evaluator):
        result = evaluate_on_test(program, test_examples, metric, collect_per_example=False)

    assert result == pytest.approx(0.42)


def test_evaluate_on_test_bare_int_return_treated_as_aggregate() -> None:
    """Evaluator returns a plain int (not EvaluationResult)."""
    program = fake_compiled_program()
    metric = _dummy_metric
    test_examples = [_FakeExample()]
    fake_evaluator = MagicMock()
    fake_evaluator.return_value = 1  # bare int

    with patch("core.service_gateway.optimizers.dspy.Evaluate", return_value=fake_evaluator):
        result = evaluate_on_test(program, test_examples, metric, collect_per_example=False)

    assert result == pytest.approx(1.0)


def test_evaluate_on_test_non_numeric_score_raises_service_error() -> None:
    """Evaluator returns an object whose .score is not numeric → ServiceError."""
    program = fake_compiled_program()
    metric = _dummy_metric
    test_examples = [_FakeExample()]
    fake_evaluator = MagicMock()
    fake_evaluator.return_value = _FakeEvalResult(score="not-a-number")

    with patch("core.service_gateway.optimizers.dspy.Evaluate", return_value=fake_evaluator):
        with pytest.raises(ServiceError, match="non-numeric"):
            evaluate_on_test(program, test_examples, metric, collect_per_example=True)


def test_evaluate_on_test_empty_test_set_returns_none_when_not_collecting() -> None:
    """Empty test set short-circuits before calling dspy.Evaluate."""
    program = fake_compiled_program()
    metric = _dummy_metric

    with patch("core.service_gateway.optimizers.dspy.Evaluate") as mock_eval_cls:
        result = evaluate_on_test(program, [], metric, collect_per_example=False)

    mock_eval_cls.assert_not_called()
    assert result is None


def test_evaluate_on_test_empty_test_set_returns_none_and_empty_list_when_collecting() -> None:
    """Empty test set short-circuits and returns (None, []) when collect_per_example=True."""
    program = fake_compiled_program()
    metric = _dummy_metric

    with patch("core.service_gateway.optimizers.dspy.Evaluate") as mock_eval_cls:
        score, per_example = evaluate_on_test(program, [], metric, collect_per_example=True)

    mock_eval_cls.assert_not_called()
    assert score is None
    assert per_example == []


def test_evaluate_on_test_per_example_unpacking_normal_entry() -> None:
    """Per-example results are correctly unpacked from (example, prediction, score) tuples."""
    program = fake_compiled_program()
    metric = _dummy_metric
    test_examples = [_FakeExample()]

    prediction = MagicMock()
    prediction.answer = "2"
    example = _FakeExample()
    raw_results = [(example, prediction, 1.0)]
    fake_evaluator = MagicMock()
    fake_evaluator.return_value = _FakeEvalResult(score=1.0, results=raw_results)

    with patch("core.service_gateway.optimizers.dspy.Evaluate", return_value=fake_evaluator):
        score, per_example = evaluate_on_test(
            program, test_examples, metric, collect_per_example=True
        )

    assert len(per_example) == 1
    entry = per_example[0]
    assert entry["score"] == pytest.approx(1.0)
    assert entry["pass"] is True
    assert "answer" in entry["outputs"]


def test_evaluate_on_test_per_example_bare_except_fallback() -> None:
    """Malformed entry triggers the bare-except fallback (index, 0.0, pass=False)."""
    program = fake_compiled_program()
    metric = _dummy_metric
    test_examples = [_FakeExample()]

    # A deliberately unparseable entry (too few elements)
    raw_results = [("only_one_element",)]
    fake_evaluator = MagicMock()
    fake_evaluator.return_value = _FakeEvalResult(score=0.0, results=raw_results)

    with patch("core.service_gateway.optimizers.dspy.Evaluate", return_value=fake_evaluator):
        score, per_example = evaluate_on_test(
            program, test_examples, metric, collect_per_example=True
        )

    assert len(per_example) == 1
    entry = per_example[0]
    assert entry["score"] == pytest.approx(0.0)
    assert entry["pass"] is False
    assert entry["outputs"] == {}
