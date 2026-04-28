"""Tests for ``DspyService.validate_payload`` (gateway facade contract)."""

from __future__ import annotations

import dspy
import pytest

from core.exceptions import ServiceError
from core.models import ColumnMapping, ModelConfig, RunRequest, SplitFractions
from core.registry import ServiceRegistry
from core.service_gateway.optimization.core import DspyService

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
    """Return a fresh ``DspyService`` backed by a clean registry."""
    return DspyService(registry=ServiceRegistry())


def _payload(**overrides) -> RunRequest:
    """Build a ``RunRequest`` with the standard fixtures and optional overrides."""
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


def test_validate_payload_valid_request_does_not_raise() -> None:
    """A fully valid payload validates without raising."""
    service = _service()
    payload = _payload()

    service.validate_payload(payload)


def test_validate_payload_bad_signature_syntax_raises_service_error() -> None:
    """A signature with invalid Python raises a ``ServiceError``."""
    service = _service()
    payload = _payload(signature_code="def bad !!!")

    with pytest.raises(ServiceError, match="syntax error"):
        service.validate_payload(payload)


def test_validate_payload_no_signature_class_raises_service_error() -> None:
    """Source without a ``dspy.Signature`` subclass raises ``ServiceError``."""
    service = _service()
    payload = _payload(signature_code="x = 1")

    with pytest.raises(ServiceError, match=r"dspy\.Signature"):
        service.validate_payload(payload)


def test_validate_payload_missing_input_field_in_mapping_raises_service_error() -> None:
    """A mapping that omits a required signature input raises ``ServiceError``."""
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
    """A mapping referencing a missing dataset column raises ``ServiceError``."""
    service = _service()
    # mapping references "missing_col" which doesn't exist in the row
    bad_mapping = ColumnMapping(inputs={"question": "missing_col"}, outputs={"answer": "a"})
    payload = _payload(column_mapping=bad_mapping)

    with pytest.raises(ServiceError, match="columns not found in dataset"):
        service.validate_payload(payload)


def test_validate_payload_bad_metric_syntax_raises_service_error() -> None:
    """A metric with invalid Python raises ``ServiceError``."""
    service = _service()
    payload = _payload(metric_code="def bad !!!")

    with pytest.raises(ServiceError, match="syntax error"):
        service.validate_payload(payload)


def test_validate_payload_metric_not_callable_raises_service_error() -> None:
    """Metric source without any callable raises ``ServiceError``."""
    service = _service()
    payload = _payload(metric_code="x = 42")

    with pytest.raises(ServiceError, match="must define a callable"):
        service.validate_payload(payload)


def test_validate_payload_unknown_module_raises_service_error() -> None:
    """An unregistered module name raises ``ServiceError``."""
    service = _service()
    payload = _payload(module_name="totally_unknown_module_xyz")

    with pytest.raises(ServiceError):
        service.validate_payload(payload)


def test_validate_payload_registered_module_resolves_successfully() -> None:
    """A module pre-registered in the registry validates without raising."""
    registry = ServiceRegistry()
    registry.register_module("my_cot", dspy.ChainOfThought)
    service = DspyService(registry=registry)
    payload = _payload(module_name="my_cot")

    service.validate_payload(payload)


def test_validate_payload_unknown_optimizer_raises_service_error() -> None:
    """An unregistered optimizer name raises ``ServiceError``."""
    service = _service()
    payload = _payload(optimizer_name="totally_unknown_optimizer_xyz")

    with pytest.raises(ServiceError):
        service.validate_payload(payload)


def test_validate_payload_dspy_prefixed_optimizer_resolves_successfully() -> None:
    """A ``dspy.``-prefixed optimizer name resolves through the resolver."""
    service = _service()
    payload = _payload(optimizer_name="dspy.BootstrapFewShot")

    service.validate_payload(payload)


def test_validate_payload_optimizer_kwargs_validated_against_signature() -> None:
    """Unsupported optimizer kwargs surface a ``ServiceError``."""
    service = _service()
    payload = _payload(
        optimizer_name="dspy.BootstrapFewShot",
        optimizer_kwargs={"completely_nonexistent_kwarg_xyz": True},
    )

    with pytest.raises(ServiceError, match="unsupported entries"):
        service.validate_payload(payload)
