"""Tests for ``DspyService.run`` and ``DspyService.run_grid_search``."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.constants import PROGRESS_GRID_PAIR_FAILED, PROGRESS_SPLITS_READY
from core.exceptions import ServiceError
from core.models import ColumnMapping, ModelConfig, RunRequest, RunResponse, SplitFractions
from core.models.results import GridSearchResponse
from core.models.submissions import GridSearchRequest
from core.registry import ServiceRegistry
from core.service_gateway.optimization.core import DspyService
from core.service_gateway.tests.mocks import (
    fake_compiled_program,
    fake_language_model,
    fake_language_model_no_history,
    fake_original_program,
    patch_core_dependencies,
)

_VALID_SIG = """\
import dspy
class QA(dspy.Signature):
    question: str = dspy.InputField()
    answer: str = dspy.OutputField()
"""

_VALID_METRIC = "def metric(example, prediction, trace=None): return 1.0"

_DATASET = [{"q": "What is 1+1?", "a": "2"}, {"q": "What is 2+2?", "a": "4"}]

_MAPPING = ColumnMapping(inputs={"question": "q"}, outputs={"answer": "a"})

_MODEL_CFG = ModelConfig(name="openai/gpt-4o-mini")


def _service() -> DspyService:
    """Return a fresh ``DspyService`` backed by a clean registry."""
    return DspyService(registry=ServiceRegistry())


def _run_request(**overrides) -> RunRequest:
    """Build a ``RunRequest`` with all-train fractions and optional overrides."""
    base: dict = {
        "username": "tester",
        "module_name": "cot",
        "signature_code": _VALID_SIG,
        "metric_code": _VALID_METRIC,
        "optimizer_name": "dspy.BootstrapFewShot",
        "dataset": _DATASET,
        "column_mapping": _MAPPING,
        "split_fractions": SplitFractions(train=1.0, val=0.0, test=0.0),
        "model_config": _MODEL_CFG,
    }
    base.update(overrides)
    return RunRequest(**base)


def _run_request_with_test(**overrides) -> RunRequest:
    """Build a ``RunRequest`` with a 70/0/30 train/test split."""
    base: dict = {
        "username": "tester",
        "module_name": "cot",
        "signature_code": _VALID_SIG,
        "metric_code": _VALID_METRIC,
        "optimizer_name": "dspy.BootstrapFewShot",
        "dataset": _DATASET * 10,  # 20 rows for splits
        "column_mapping": _MAPPING,
        "split_fractions": SplitFractions(train=0.7, val=0.0, test=0.3),
        "model_config": _MODEL_CFG,
        "shuffle": False,
    }
    base.update(overrides)
    return RunRequest(**base)


def _grid_request(**overrides) -> GridSearchRequest:
    """Build a ``GridSearchRequest`` with two generation models and one reflection model."""
    base: dict = {
        "username": "tester",
        "module_name": "cot",
        "signature_code": _VALID_SIG,
        "metric_code": _VALID_METRIC,
        "optimizer_name": "dspy.BootstrapFewShot",
        "dataset": _DATASET * 10,
        "column_mapping": _MAPPING,
        "split_fractions": SplitFractions(train=0.7, val=0.0, test=0.3),
        "shuffle": False,
        "generation_models": [ModelConfig(name="openai/gpt-4o-mini"), ModelConfig(name="openai/gpt-4o")],
        "reflection_models": [ModelConfig(name="openai/gpt-4o-mini")],
    }
    base.update(overrides)
    return GridSearchRequest(**base)


def test_run_happy_path_returns_run_response() -> None:
    """A valid run returns a ``RunResponse`` with module/optimizer fields set."""
    service = _service()
    payload = _run_request()

    with patch_core_dependencies(fake_lm=fake_language_model()):
        result = service.run(payload)

    assert isinstance(result, RunResponse)
    assert result.module_name == "cot"
    assert result.optimizer_name == "dspy.BootstrapFewShot"


def test_run_happy_path_no_test_split_no_metrics() -> None:
    """An all-train run leaves test metrics ``None``."""
    service = _service()
    payload = _run_request()  # all-train, no test split

    with patch_core_dependencies():
        result = service.run(payload)

    assert result.baseline_test_metric is None
    assert result.optimized_test_metric is None
    assert result.metric_improvement is None


def test_run_calls_progress_callback_for_splits_ready() -> None:
    """The progress callback receives a ``PROGRESS_SPLITS_READY`` event."""
    service = _service()
    payload = _run_request()
    events: list[str] = []

    def _cb(event: str, data: dict) -> None:
        events.append(event)

    with patch_core_dependencies():
        service.run(payload, progress_callback=_cb)

    assert PROGRESS_SPLITS_READY in events


def test_run_returns_baseline_program_when_optimized_worse() -> None:
    """When the optimized program scores worse, the service keeps the baseline."""
    service = _service()
    payload = _run_request_with_test()

    original_program = fake_original_program()
    compiled_program = fake_compiled_program()

    # Baseline score = 0.9, optimized score = 0.5 → service should keep baseline
    def _eval_side_effect(program, test_examples, metric, collect_per_example=False):
        if program is original_program:
            return (0.9, [])
        return (0.5, [])

    with (
        patch_core_dependencies(fake_lm=fake_language_model(), compiled_program=compiled_program),
        patch("core.service_gateway.optimization.core.evaluate_on_test", side_effect=_eval_side_effect),
        patch.object(service, "_get_module_factory", return_value=(lambda **kw: original_program, True)),
    ):
        result = service.run(payload)

    assert result.optimized_test_metric == pytest.approx(0.9)
    assert result.metric_improvement == pytest.approx(0.0)


def test_run_keeps_compiled_program_when_optimized_better() -> None:
    """When the optimized program scores better, that score is reported."""
    service = _service()
    payload = _run_request_with_test()

    original_program = fake_original_program()
    compiled_program = fake_compiled_program()

    def _eval_side_effect(program, test_examples, metric, collect_per_example=False):
        if program is original_program:
            return (0.5, [])
        return (0.9, [])

    with (
        patch_core_dependencies(fake_lm=fake_language_model(), compiled_program=compiled_program),
        patch("core.service_gateway.optimization.core.evaluate_on_test", side_effect=_eval_side_effect),
        patch.object(service, "_get_module_factory", return_value=(lambda **kw: original_program, True)),
    ):
        result = service.run(payload)

    assert result.optimized_test_metric == pytest.approx(0.9)
    assert result.metric_improvement == pytest.approx(0.4)


def test_run_avg_response_time_is_none_when_lm_has_no_history() -> None:
    """An LM lacking ``history`` reports ``num_lm_calls`` and ``avg_response_time_ms`` as ``None``."""
    service = _service()
    payload = _run_request()

    with patch_core_dependencies(fake_lm=fake_language_model_no_history()):
        result = service.run(payload)

    assert result.num_lm_calls is None
    assert result.avg_response_time_ms is None


def test_run_avg_response_time_is_none_when_no_real_lm_calls() -> None:
    """avg_response_time_ms is None when no actual dspy.LM __call__ fires.

    Mocks replace compile/evaluate, so the LM is never invoked through dspy —
    the timing callback records zero calls and avg_response_time_ms stays None
    even though language_model.history is pre-populated.
    """
    service = _service()
    payload = _run_request()

    # history_len=4 is intentional: the test asserts num_lm_calls == 4 exactly
    with patch_core_dependencies(fake_lm=fake_language_model(history_len=4)):
        result = service.run(payload)

    assert result.num_lm_calls == 4
    assert result.avg_response_time_ms is None


def test_run_grid_search_happy_path_returns_two_pair_results() -> None:
    """A 2-gen × 1-ref grid produces 2 completed pair results."""
    service = _service()
    payload = _grid_request()  # 2 gen models × 1 ref model = 2 pairs

    def _eval_side_effect(program, test_examples, metric, collect_per_example=False):
        return (0.8, [])

    with (
        patch_core_dependencies(),
        patch("core.service_gateway.optimization.core.evaluate_on_test", side_effect=_eval_side_effect),
        patch("core.worker.log_handler.set_current_pair_index"),
    ):
        result = service.run_grid_search(payload)

    assert isinstance(result, GridSearchResponse)
    assert result.total_pairs == 2
    assert len(result.pair_results) == 2
    assert result.completed_pairs == 2
    assert result.failed_pairs == 0


def test_run_grid_search_best_pair_has_highest_score() -> None:
    """``best_pair`` is selected by the highest optimized metric across pairs."""
    service = _service()
    payload = _grid_request()

    call_count = [0]

    def _eval_side_effect(program, test_examples, metric, collect_per_example=False):
        # baseline always 0.5; optimized alternates 0.6 and 0.9
        call_count[0] += 1
        if call_count[0] % 2 == 1:
            return (0.5, [])  # baseline
        return (0.6 if call_count[0] <= 4 else 0.9, [])  # optimized

    with (
        patch_core_dependencies(),
        patch("core.service_gateway.optimization.core.evaluate_on_test", side_effect=_eval_side_effect),
        patch("core.worker.log_handler.set_current_pair_index"),
    ):
        result = service.run_grid_search(payload)

    assert result.best_pair is not None
    assert result.best_pair.optimized_test_metric is not None


def test_run_grid_search_per_pair_swaps_when_optimized_worse() -> None:
    """Per-pair selection keeps the baseline when the optimized score is worse."""
    service = _service()
    # 1 gen × 1 ref = 1 pair to keep things simple
    payload = _grid_request(
        generation_models=[ModelConfig(name="openai/gpt-4o-mini")],
        reflection_models=[ModelConfig(name="openai/gpt-4o-mini")],
    )

    original_program = fake_original_program()
    compiled_program = fake_compiled_program()

    def _eval_side_effect(program, test_examples, metric, collect_per_example=False):
        # baseline > optimized to trigger swap
        if program is original_program:
            return (0.9, [])
        return (0.3, [])

    with (
        patch_core_dependencies(fake_lm=fake_language_model(), compiled_program=compiled_program),
        patch("core.service_gateway.optimization.core.evaluate_on_test", side_effect=_eval_side_effect),
        patch("core.worker.log_handler.set_current_pair_index"),
        patch.object(service, "_get_module_factory", return_value=(lambda **kw: original_program, True)),
    ):
        result = service.run_grid_search(payload)

    pair = result.pair_results[0]
    assert pair.error is None
    assert pair.optimized_test_metric == pytest.approx(0.9)


def test_run_grid_search_pair_exception_fires_failed_callback_and_increments_count() -> None:
    """A pair exception fires ``PROGRESS_GRID_PAIR_FAILED`` and bumps ``failed_pairs``."""
    service = _service()
    payload = _grid_request()  # 2 pairs

    events: list[str] = []

    def _cb(event: str, data: dict) -> None:
        events.append(event)

    surviving_program = fake_compiled_program()
    compile_call_count = [0]

    def _failing_compile(**kwargs):
        compile_call_count[0] += 1
        if compile_call_count[0] == 1:
            raise RuntimeError("optimizer blew up")
        return surviving_program

    def _eval_side_effect(program, test_examples, metric, collect_per_example=False):
        return (0.8, [])

    with (
        patch_core_dependencies(fake_lm=fake_language_model()),
        patch("core.service_gateway.optimization.core.compile_program", side_effect=_failing_compile),
        patch("core.service_gateway.optimization.core.evaluate_on_test", side_effect=_eval_side_effect),
        patch("core.worker.log_handler.set_current_pair_index"),
    ):
        result = service.run_grid_search(payload, progress_callback=_cb)

    assert PROGRESS_GRID_PAIR_FAILED in events
    assert result.failed_pairs >= 1
    assert result.completed_pairs >= 1


def test_run_grid_search_pair_exception_sets_error_field_on_pair_result() -> None:
    """A pair exception is captured in the pair result's ``error`` field."""
    service = _service()
    payload = _grid_request(
        generation_models=[ModelConfig(name="openai/gpt-4o-mini")],
        reflection_models=[ModelConfig(name="openai/gpt-4o-mini")],
    )

    def _failing_compile(**kwargs):
        raise RuntimeError("boom")

    with (
        patch_core_dependencies(fake_lm=fake_language_model()),
        patch("core.service_gateway.optimization.core.compile_program", side_effect=_failing_compile),
        patch("core.worker.log_handler.set_current_pair_index"),
    ):
        result = service.run_grid_search(payload)

    pair = result.pair_results[0]
    assert pair.error is not None
    assert "boom" in pair.error


def test_run_grid_search_best_pair_is_none_when_all_pairs_fail() -> None:
    """When every pair fails, ``best_pair`` stays ``None``."""
    service = _service()
    payload = _grid_request()  # 2 pairs — both will fail

    def _always_fail(**kwargs):
        raise RuntimeError("total failure")

    with (
        patch_core_dependencies(fake_lm=fake_language_model()),
        patch("core.service_gateway.optimization.core.compile_program", side_effect=_always_fail),
        patch("core.worker.log_handler.set_current_pair_index"),
    ):
        result = service.run_grid_search(payload)

    assert result.best_pair is None
    assert result.failed_pairs == 2
    assert result.completed_pairs == 0


def test_get_module_factory_resolver_error_raises_service_error() -> None:
    """An unresolvable module name raises ``ServiceError``."""
    service = _service()

    with pytest.raises(ServiceError):
        service._get_module_factory("totally_unknown_module_xyz_abc")


def test_get_optimizer_factory_resolver_error_raises_service_error() -> None:
    """An unresolvable optimizer name raises ``ServiceError``."""
    service = _service()

    with pytest.raises(ServiceError):
        service._get_optimizer_factory("totally_unknown_optimizer_xyz_abc")


def test_get_module_factory_registry_lookup_succeeds_before_resolver() -> None:
    """Registry lookups precede the resolver fallback."""
    registry = ServiceRegistry()
    sentinel = MagicMock(name="my_cot_factory")
    registry.register_module("my_cot", sentinel)
    service = DspyService(registry=registry)

    factory, auto_sig = service._get_module_factory("my_cot")

    assert factory is sentinel
    assert auto_sig is False


def test_run_raises_service_error_when_module_factory_unavailable() -> None:
    """``run`` raises ``ServiceError`` when the module factory is unavailable."""
    service = _service()
    payload = _run_request(module_name="completely_nonexistent_module_xyz")

    with pytest.raises(ServiceError):
        service.run(payload)
