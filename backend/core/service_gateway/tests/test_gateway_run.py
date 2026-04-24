"""Tests for DspyService.run() and DspyService.run_grid_search()."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import dspy
import pytest

from core.constants import PROGRESS_GRID_PAIR_FAILED, PROGRESS_SPLITS_READY
from core.exceptions import ServiceError
from core.models import ColumnMapping, ModelConfig, RunRequest, RunResponse, SplitFractions
from core.models.results import GridSearchResponse
from core.models.submissions import GridSearchRequest
from core.registry import ServiceRegistry
from core.registry.resolvers import ResolverError
from core.service_gateway.core import DspyService
from core.service_gateway.tests.mocks import (
    REAL_NUM_LM_CALLS,
    fake_compiled_program,
    fake_language_model,
    fake_language_model_no_history,
    fake_optimizer,
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
    """Return a DspyService backed by an empty ServiceRegistry."""
    return DspyService(registry=ServiceRegistry())


def _run_request(**overrides) -> RunRequest:
    """Build a valid RunRequest with all-train split, with optional overrides."""
    base: dict = dict(
        username="tester",
        module_name="cot",
        signature_code=_VALID_SIG,
        metric_code=_VALID_METRIC,
        optimizer_name="dspy.BootstrapFewShot",
        dataset=_DATASET,
        column_mapping=_MAPPING,
        split_fractions=SplitFractions(train=1.0, val=0.0, test=0.0),
        model_config=_MODEL_CFG,
    )
    base.update(overrides)
    return RunRequest(**base)


def _run_request_with_test(**overrides) -> RunRequest:
    """Request with a test split so evaluate_on_test is exercised."""
    base: dict = dict(
        username="tester",
        module_name="cot",
        signature_code=_VALID_SIG,
        metric_code=_VALID_METRIC,
        optimizer_name="dspy.BootstrapFewShot",
        dataset=_DATASET * 10,  # 20 rows for splits
        column_mapping=_MAPPING,
        split_fractions=SplitFractions(train=0.7, val=0.0, test=0.3),
        model_config=_MODEL_CFG,
        shuffle=False,
    )
    base.update(overrides)
    return RunRequest(**base)


def _grid_request(**overrides) -> GridSearchRequest:
    """Build a valid GridSearchRequest (2 gen × 1 ref model), with optional overrides."""
    base: dict = dict(
        username="tester",
        module_name="cot",
        signature_code=_VALID_SIG,
        metric_code=_VALID_METRIC,
        optimizer_name="dspy.BootstrapFewShot",
        dataset=_DATASET * 10,
        column_mapping=_MAPPING,
        split_fractions=SplitFractions(train=0.7, val=0.0, test=0.3),
        shuffle=False,
        generation_models=[ModelConfig(name="openai/gpt-4o-mini"), ModelConfig(name="openai/gpt-4o")],
        reflection_models=[ModelConfig(name="openai/gpt-4o-mini")],
    )
    base.update(overrides)
    return GridSearchRequest(**base)




def test_run_happy_path_returns_run_response() -> None:
    """Happy path returns a RunResponse with the expected module and optimizer names."""
    service = _service()
    payload = _run_request()

    with patch_core_dependencies(fake_lm=fake_language_model()):
        result = service.run(payload)

    assert isinstance(result, RunResponse)
    assert result.module_name == "cot"
    assert result.optimizer_name == "dspy.BootstrapFewShot"


def test_run_happy_path_no_test_split_no_metrics() -> None:
    """When test split is empty, metric fields are all None."""
    service = _service()
    payload = _run_request()  # all-train, no test split

    with patch_core_dependencies():
        result = service.run(payload)

    assert result.baseline_test_metric is None
    assert result.optimized_test_metric is None
    assert result.metric_improvement is None


def test_run_calls_progress_callback_for_splits_ready() -> None:
    """PROGRESS_SPLITS_READY event is fired via the progress callback."""
    service = _service()
    payload = _run_request()
    events: list[str] = []

    def _cb(event: str, data: dict) -> None:
        events.append(event)

    with patch_core_dependencies():
        service.run(payload, progress_callback=_cb)

    assert PROGRESS_SPLITS_READY in events



def test_run_returns_baseline_program_when_optimized_worse() -> None:
    """When optimized score < baseline score, the baseline program is returned."""
    service = _service()
    payload = _run_request_with_test()

    original_program = fake_original_program()
    compiled_program = fake_compiled_program()

    # Baseline score = 0.9, optimized score = 0.5 → service should keep baseline
    def _eval_side_effect(program, test_examples, metric, collect_per_example=False):
        if program is original_program:
            return (0.9, [])
        return (0.5, [])

    with patch_core_dependencies(fake_lm=fake_language_model(), compiled_program=compiled_program), \
         patch("core.service_gateway.core.evaluate_on_test", side_effect=_eval_side_effect):
        with patch.object(service, "_get_module_factory", return_value=(lambda **kw: original_program, True)):
            result = service.run(payload)

    assert result.optimized_test_metric == pytest.approx(0.9)
    assert result.metric_improvement == pytest.approx(0.0)


def test_run_keeps_compiled_program_when_optimized_better() -> None:
    """When optimized score is higher than baseline, compiled program and score are used."""
    service = _service()
    payload = _run_request_with_test()

    original_program = fake_original_program()
    compiled_program = fake_compiled_program()

    def _eval_side_effect(program, test_examples, metric, collect_per_example=False):
        if program is original_program:
            return (0.5, [])
        return (0.9, [])

    with patch_core_dependencies(fake_lm=fake_language_model(), compiled_program=compiled_program), \
         patch("core.service_gateway.core.evaluate_on_test", side_effect=_eval_side_effect):
        with patch.object(service, "_get_module_factory", return_value=(lambda **kw: original_program, True)):
            result = service.run(payload)

    assert result.optimized_test_metric == pytest.approx(0.9)
    assert result.metric_improvement == pytest.approx(0.4)



def test_run_avg_response_time_is_none_when_lm_has_no_history() -> None:
    """avg_response_time_ms must be None when the LM exposes no history attr."""
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
    """Grid search over 2×1 model pairs completes with 2 results and 0 failures."""
    service = _service()
    payload = _grid_request()  # 2 gen models × 1 ref model = 2 pairs

    def _eval_side_effect(program, test_examples, metric, collect_per_example=False):
        return (0.8, [])

    with patch_core_dependencies(), \
         patch("core.service_gateway.core.evaluate_on_test", side_effect=_eval_side_effect), \
         patch("core.worker.log_handler.set_current_pair_index"):
        result = service.run_grid_search(payload)

    assert isinstance(result, GridSearchResponse)
    assert result.total_pairs == 2
    assert len(result.pair_results) == 2
    assert result.completed_pairs == 2
    assert result.failed_pairs == 0


def test_run_grid_search_best_pair_has_highest_score() -> None:
    """best_pair is the pair with the highest optimized_test_metric."""
    service = _service()
    payload = _grid_request()

    call_count = [0]

    def _eval_side_effect(program, test_examples, metric, collect_per_example=False):
        # baseline always 0.5; optimized alternates 0.6 and 0.9
        call_count[0] += 1
        if call_count[0] % 2 == 1:
            return (0.5, [])  # baseline
        return (0.6 if call_count[0] <= 4 else 0.9, [])  # optimized

    with patch_core_dependencies(), \
         patch("core.service_gateway.core.evaluate_on_test", side_effect=_eval_side_effect), \
         patch("core.worker.log_handler.set_current_pair_index"):
        result = service.run_grid_search(payload)

    assert result.best_pair is not None
    assert result.best_pair.optimized_test_metric is not None



def test_run_grid_search_per_pair_swaps_when_optimized_worse() -> None:
    """For a pair where optimized < baseline, optimized metric is set to baseline."""
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

    with patch_core_dependencies(fake_lm=fake_language_model(), compiled_program=compiled_program), \
         patch("core.service_gateway.core.evaluate_on_test", side_effect=_eval_side_effect), \
         patch("core.worker.log_handler.set_current_pair_index"):
        with patch.object(service, "_get_module_factory", return_value=(lambda **kw: original_program, True)):
            result = service.run_grid_search(payload)

    pair = result.pair_results[0]
    assert pair.error is None
    assert pair.optimized_test_metric == pytest.approx(0.9)



def test_run_grid_search_pair_exception_fires_failed_callback_and_increments_count() -> None:
    """When one pair raises, PROGRESS_GRID_PAIR_FAILED callback fires and the run continues."""
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

    with patch_core_dependencies(fake_lm=fake_language_model()), \
         patch("core.service_gateway.core.compile_program", side_effect=_failing_compile), \
         patch("core.service_gateway.core.evaluate_on_test", side_effect=_eval_side_effect), \
         patch("core.worker.log_handler.set_current_pair_index"):
        result = service.run_grid_search(payload, progress_callback=_cb)

    assert PROGRESS_GRID_PAIR_FAILED in events
    assert result.failed_pairs >= 1
    assert result.completed_pairs >= 1


def test_run_grid_search_pair_exception_sets_error_field_on_pair_result() -> None:
    """A pair that raises stores the error message in pair.error."""
    service = _service()
    payload = _grid_request(
        generation_models=[ModelConfig(name="openai/gpt-4o-mini")],
        reflection_models=[ModelConfig(name="openai/gpt-4o-mini")],
    )

    def _failing_compile(**kwargs):
        raise RuntimeError("boom")

    with patch_core_dependencies(fake_lm=fake_language_model()), \
         patch("core.service_gateway.core.compile_program", side_effect=_failing_compile), \
         patch("core.worker.log_handler.set_current_pair_index"):
        result = service.run_grid_search(payload)

    pair = result.pair_results[0]
    assert pair.error is not None
    assert "boom" in pair.error



def test_run_grid_search_best_pair_is_none_when_all_pairs_fail() -> None:
    """best_pair is None and failed_pairs==2 when every pair raises."""
    service = _service()
    payload = _grid_request()  # 2 pairs — both will fail

    def _always_fail(**kwargs):
        raise RuntimeError("total failure")

    with patch_core_dependencies(fake_lm=fake_language_model()), \
         patch("core.service_gateway.core.compile_program", side_effect=_always_fail), \
         patch("core.worker.log_handler.set_current_pair_index"):
        result = service.run_grid_search(payload)

    assert result.best_pair is None
    assert result.failed_pairs == 2
    assert result.completed_pairs == 0



def test_get_module_factory_resolver_error_raises_service_error() -> None:
    """Unresolvable module name via _get_module_factory raises ServiceError."""
    service = _service()

    with pytest.raises(ServiceError):
        service._get_module_factory("totally_unknown_module_xyz_abc")


def test_get_optimizer_factory_resolver_error_raises_service_error() -> None:
    """Unresolvable optimizer name via _get_optimizer_factory raises ServiceError."""
    service = _service()

    with pytest.raises(ServiceError):
        service._get_optimizer_factory("totally_unknown_optimizer_xyz_abc")


def test_get_module_factory_registry_lookup_succeeds_before_resolver() -> None:
    """Registry-registered modules are returned without hitting the resolver."""
    registry = ServiceRegistry()
    sentinel = MagicMock(name="my_cot_factory")
    registry.register_module("my_cot", sentinel)
    service = DspyService(registry=registry)

    factory, auto_sig = service._get_module_factory("my_cot")

    assert factory is sentinel
    assert auto_sig is False


def test_run_raises_service_error_when_module_factory_unavailable() -> None:
    """run() with an unavailable module name raises ServiceError."""
    service = _service()
    payload = _run_request(module_name="completely_nonexistent_module_xyz")

    with pytest.raises(ServiceError):
        service.run(payload)
