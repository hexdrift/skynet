"""Tests for ``DspyService.validate_payload`` (gateway facade contract)."""

from __future__ import annotations

import dspy
import pytest

from core.exceptions import ServiceError
from core.models import ColumnMapping, ModelConfig, RunRequest, SplitFractions, ToolSource
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


def test_validate_payload_gepa_rejects_short_metric_arity() -> None:
    """GEPA payloads with a 2-3 arg metric raise before enqueue.

    Regression: the generalist agent (and any direct ``POST /run`` caller)
    could previously submit a ``def metric(example, prediction, trace=None)``
    metric with ``optimizer_name=gepa``. GEPA's reflection step calls the
    metric with 5 positional args, so every iteration failed silently and
    the run completed "successfully" with no improvement.
    """
    service = _service()
    payload = _payload(
        optimizer_name="gepa",
        metric_code="def metric(example, prediction, trace=None): return 1.0",
        reflection_model_config=_MODEL_CFG,
    )

    with pytest.raises(ServiceError, match="GEPA metric must accept 5 arguments"):
        service.validate_payload(payload)


def test_validate_payload_gepa_accepts_five_arg_metric() -> None:
    """GEPA payloads with a 5-arg metric returning ``dspy.Prediction`` pass validation."""
    service = _service()
    five_arg_metric = (
        "import dspy\n"
        "def metric(gold, pred, trace, pred_name, pred_trace):\n"
        "    return dspy.Prediction(score=1.0, feedback='ok')\n"
    )
    payload = _payload(
        optimizer_name="gepa",
        metric_code=five_arg_metric,
        reflection_model_config=_MODEL_CFG,
    )

    service.validate_payload(payload)


_REACT_DATASET = [{"q": "hi", "a": "yo"}]

_TOOL_SOURCE = ToolSource(kind="live_mcp", mcp_url="http://localhost:9000/mcp")

# React is generic: rollouts are scored with the same standard 5-arg GEPA metric
# the predict/cot path uses, so the arity gate applies identically.
_REACT_METRIC = (
    "import dspy\n"
    "def metric(gold, pred, trace, pred_name, pred_trace):\n"
    "    return dspy.Prediction(score=1.0, feedback='ok')\n"
)


def _react_payload(**overrides) -> RunRequest:
    """Build a react ``RunRequest`` backed by a standard 5-arg GEPA metric."""
    base: dict = {
        "username": "tester",
        "module_name": "react",
        "signature_code": _VALID_SIG,
        "metric_code": _REACT_METRIC,
        "optimizer_name": "gepa",
        "dataset": _REACT_DATASET,
        "column_mapping": _MAPPING,
        "split_fractions": SplitFractions(train=1.0, val=0.0, test=0.0),
        "model_config": _MODEL_CFG,
        "reflection_model_config": _MODEL_CFG,
        "tool_source": _TOOL_SOURCE,
    }
    base.update(overrides)
    return RunRequest(**base)


def test_validate_payload_react_passes() -> None:
    """A react run with a tool_source and a standard 5-arg metric validates."""
    service = _service()
    payload = _react_payload()

    service.validate_payload(payload)


def test_validate_payload_react_requires_tool_source() -> None:
    """A react run missing ``tool_source`` raises ``ServiceError``."""
    service = _service()
    payload = _react_payload(tool_source=None)

    with pytest.raises(ServiceError, match="require tool_source"):
        service.validate_payload(payload)


def test_validate_payload_react_rejects_short_metric_arity() -> None:
    """A react run applies the same 5-arg GEPA arity gate as predict/cot.

    React is now a generic GEPA module — its rollouts are scored with the
    standard ``(gold, pred, trace, pred_name, pred_trace)`` metric, so a 2-3 arg
    metric is rejected before enqueue exactly as it is for any other GEPA run.
    """
    service = _service()
    payload = _react_payload(
        metric_code="def metric(example, prediction, trace=None): return 1.0",
    )

    with pytest.raises(ServiceError, match="GEPA metric must accept 5 arguments"):
        service.validate_payload(payload)
