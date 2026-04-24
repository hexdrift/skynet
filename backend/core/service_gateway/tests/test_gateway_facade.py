from __future__ import annotations

import pytest
import dspy

from core.exceptions import ServiceError
from core.models import ColumnMapping, ModelConfig, RunRequest, SplitFractions
from core.registry import ServiceRegistry
from core.service_gateway.core import DspyService


_VALID_SIG = """\
import dspy
class QA(dspy.Signature):
    question: str = dspy.InputField()
    answer: str = dspy.OutputField()
"""

_VALID_METRIC = "def metric(example, prediction, trace=None): return 1.0"

_DATASET = [{"q": "What is 1+1?", "a": "2"}]

_MAPPING = ColumnMapping(inputs={"question": "q"}, outputs={"answer": "a"})

_MODEL_CFG = ModelConfig(name="openai/gpt-4o-mini")


def _service() -> DspyService:
    """Return a DspyService backed by an empty ServiceRegistry."""
    return DspyService(registry=ServiceRegistry())


def _payload(**overrides) -> RunRequest:
    """Build a valid RunRequest, with keyword overrides applied."""
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



def test_validate_payload_valid_request_does_not_raise() -> None:
    """A fully valid payload passes validation without raising."""
    service = _service()
    payload = _payload()

    service.validate_payload(payload)



def test_validate_payload_bad_signature_syntax_raises_service_error() -> None:
    """Malformed signature code raises ServiceError with 'syntax error'."""
    service = _service()
    payload = _payload(signature_code="def bad !!!")

    with pytest.raises(ServiceError, match="syntax error"):
        service.validate_payload(payload)


def test_validate_payload_no_signature_class_raises_service_error() -> None:
    """Code that defines no Signature subclass raises ServiceError."""
    service = _service()
    payload = _payload(signature_code="x = 1")

    with pytest.raises(ServiceError, match="dspy.Signature"):
        service.validate_payload(payload)



def test_validate_payload_missing_input_field_in_mapping_raises_service_error() -> None:
    """Column mapping missing a required signature input field raises ServiceError."""
    service = _service()
    # Signature requires "context" but mapping only provides "question"
    sig_with_context = """\
import dspy
class QA(dspy.Signature):
    question: str = dspy.InputField()
    context: str = dspy.InputField()
    answer: str = dspy.OutputField()
"""
    payload = _payload(
        signature_code=sig_with_context,
        dataset=[{"q": "?", "a": "yes"}],
    )

    with pytest.raises(ServiceError, match="Missing inputs"):
        service.validate_payload(payload)


def test_validate_payload_column_not_in_dataset_raises_service_error() -> None:
    """Mapping column absent from the dataset raises ServiceError."""
    service = _service()
    # mapping references "missing_col" which doesn't exist in the row
    bad_mapping = ColumnMapping(inputs={"question": "missing_col"}, outputs={"answer": "a"})
    payload = _payload(column_mapping=bad_mapping)

    with pytest.raises(ServiceError, match="columns not found in dataset"):
        service.validate_payload(payload)



def test_validate_payload_bad_metric_syntax_raises_service_error() -> None:
    """Malformed metric code raises ServiceError."""
    service = _service()
    payload = _payload(metric_code="def bad !!!")

    with pytest.raises(ServiceError, match="syntax error"):
        service.validate_payload(payload)


def test_validate_payload_metric_not_callable_raises_service_error() -> None:
    """Metric code defining no callable raises ServiceError."""
    service = _service()
    payload = _payload(metric_code="x = 42")

    with pytest.raises(ServiceError, match="must define a callable"):
        service.validate_payload(payload)



def test_validate_payload_unknown_module_raises_service_error() -> None:
    """Unresolvable module name raises ServiceError."""
    service = _service()
    payload = _payload(module_name="totally_unknown_module_xyz")

    with pytest.raises(ServiceError):
        service.validate_payload(payload)


def test_validate_payload_registered_module_resolves_successfully() -> None:
    """Registry-registered module resolves without raising."""
    registry = ServiceRegistry()
    registry.register_module("my_cot", lambda signature: dspy.ChainOfThought(signature))
    service = DspyService(registry=registry)
    payload = _payload(module_name="my_cot")

    service.validate_payload(payload)



def test_validate_payload_unknown_optimizer_raises_service_error() -> None:
    """Unresolvable optimizer name raises ServiceError."""
    service = _service()
    payload = _payload(optimizer_name="totally_unknown_optimizer_xyz")

    with pytest.raises(ServiceError):
        service.validate_payload(payload)


def test_validate_payload_dspy_prefixed_optimizer_resolves_successfully() -> None:
    """dspy-prefixed optimizer name resolves without raising."""
    service = _service()
    payload = _payload(optimizer_name="dspy.BootstrapFewShot")

    service.validate_payload(payload)


def test_validate_payload_optimizer_kwargs_validated_against_signature() -> None:
    """Unsupported optimizer_kwargs key raises ServiceError."""
    service = _service()
    payload = _payload(
        optimizer_name="dspy.BootstrapFewShot",
        optimizer_kwargs={"completely_nonexistent_kwarg_xyz": True},
    )

    with pytest.raises(ServiceError, match="unsupported entries"):
        service.validate_payload(payload)
