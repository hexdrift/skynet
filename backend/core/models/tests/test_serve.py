from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.models.serve import ServeRequest, ServeInfoResponse, ServeResponse



def test_serve_request_accepts_non_empty_inputs() -> None:
    """Verify ServeRequest accepts a non-empty inputs dict."""
    req = ServeRequest(inputs={"question": "What is 2+2?"})

    assert req.inputs == {"question": "What is 2+2?"}
    assert req.model_config_override is None


def test_serve_request_rejects_empty_inputs() -> None:
    """Verify ServeRequest rejects an empty inputs dict."""
    with pytest.raises(ValidationError, match="At least one input"):
        ServeRequest(inputs={})


def test_serve_request_accepts_model_config_override() -> None:
    """Verify ServeRequest stores a model_config_override when provided."""
    req = ServeRequest(
        inputs={"q": "hi"},
        model_config_override={"name": "gpt-4o"},
    )

    assert req.model_config_override is not None
    assert req.model_config_override.name == "gpt-4o"


def test_serve_request_model_config_override_defaults_none() -> None:
    """Verify ServeRequest defaults model_config_override to None."""
    req = ServeRequest(inputs={"q": "hi"})

    assert req.model_config_override is None


def test_serve_request_multiple_inputs_accepted() -> None:
    """Verify ServeRequest accepts multiple input fields."""
    req = ServeRequest(inputs={"q": "hi", "context": "some text"})

    assert len(req.inputs) == 2



def test_serve_response_stores_all_fields() -> None:
    """Verify ServeResponse stores all required fields."""
    resp = ServeResponse(
        optimization_id="abc123",
        outputs={"answer": "4"},
        input_fields=["question"],
        output_fields=["answer"],
        model_used="gpt-4o-mini",
    )

    assert resp.optimization_id == "abc123"
    assert resp.outputs == {"answer": "4"}
    assert resp.model_used == "gpt-4o-mini"



def test_serve_info_response_demo_count_defaults_zero() -> None:
    """Verify ServeInfoResponse defaults demo_count to 0 and instructions to None."""
    info = ServeInfoResponse(
        optimization_id="abc123",
        module_name="predict",
        optimizer_name="gepa",
        model_name="gpt-4o-mini",
        input_fields=["question"],
        output_fields=["answer"],
    )

    assert info.demo_count == 0
    assert info.instructions is None
