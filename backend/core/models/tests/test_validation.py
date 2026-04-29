"""Tests for ValidateCodeRequest and ValidateCodeResponse models."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from core.models.validation import ValidateCodeRequest, ValidateCodeResponse


def _column_mapping() -> dict[str, Any]:
    """Return a minimal valid column mapping payload for validation tests.

    Returns:
        A column mapping dict with one input and one output binding.
    """
    return {"inputs": {"q": "q"}, "outputs": {"a": "a"}}


def test_validate_code_request_accepts_signature_only() -> None:
    """Verify ValidateCodeRequest accepts signature_code without metric_code."""
    req = ValidateCodeRequest.model_validate({"signature_code": "class S: pass", "column_mapping": _column_mapping()})

    assert req.signature_code == "class S: pass"
    assert req.metric_code is None


def test_validate_code_request_accepts_metric_only() -> None:
    """Verify ValidateCodeRequest accepts metric_code without signature_code."""
    req = ValidateCodeRequest.model_validate(
        {"metric_code": "def m(e, p): return 1.0", "column_mapping": _column_mapping()}
    )

    assert req.metric_code == "def m(e, p): return 1.0"
    assert req.signature_code is None


def test_validate_code_request_accepts_both_blocks() -> None:
    """Verify ValidateCodeRequest accepts both signature_code and metric_code together."""
    req = ValidateCodeRequest.model_validate(
        {
            "signature_code": "class S: pass",
            "metric_code": "def m(e, p): return 1.0",
            "column_mapping": _column_mapping(),
        }
    )

    assert req.signature_code is not None
    assert req.metric_code is not None


def test_validate_code_request_sample_row_defaults_empty() -> None:
    """Verify ValidateCodeRequest defaults sample_row to an empty dict."""
    req = ValidateCodeRequest.model_validate(
        {"signature_code": "class S: pass", "column_mapping": _column_mapping()}
    )

    assert req.sample_row == {}


def test_validate_code_request_optimizer_name_defaults_none() -> None:
    """Verify ValidateCodeRequest defaults optimizer_name to None."""
    req = ValidateCodeRequest.model_validate(
        {"signature_code": "class S: pass", "column_mapping": _column_mapping()}
    )

    assert req.optimizer_name is None


def test_validate_code_request_rejects_invalid_column_mapping() -> None:
    """Verify ValidateCodeRequest rejects a column mapping with no inputs."""
    with pytest.raises(ValidationError, match="At least one input"):
        ValidateCodeRequest.model_validate(
            {"signature_code": "class S: pass", "column_mapping": {"inputs": {}, "outputs": {"a": "a"}}}
        )


def test_validate_code_request_rejects_when_both_code_blocks_missing() -> None:
    """Verify ValidateCodeRequest rejects payloads with neither signature nor metric code."""
    with pytest.raises(ValidationError, match="At least one of signature_code or metric_code"):
        ValidateCodeRequest.model_validate({"column_mapping": _column_mapping()})


def test_validate_code_response_valid_true_defaults() -> None:
    """Verify ValidateCodeResponse with valid=True defaults errors/warnings/signature_fields."""
    r = ValidateCodeResponse(valid=True)

    assert r.errors == []
    assert r.warnings == []
    assert r.signature_fields is None


def test_validate_code_response_valid_false() -> None:
    """Verify ValidateCodeResponse with valid=False stores the provided errors list."""
    r = ValidateCodeResponse(valid=False, errors=["Syntax error on line 1"])

    assert r.valid is False
    assert "Syntax error on line 1" in r.errors


def test_validate_code_response_with_warnings() -> None:
    """Verify ValidateCodeResponse persists the warnings list."""
    r = ValidateCodeResponse(valid=True, warnings=["Metric always returns 1.0"])

    assert r.warnings == ["Metric always returns 1.0"]


def test_validate_code_response_signature_fields_populated() -> None:
    """Verify ValidateCodeResponse stores parsed signature_fields when supplied."""
    r = ValidateCodeResponse(
        valid=True,
        signature_fields={"inputs": ["question"], "outputs": ["answer"]},
    )

    assert r.signature_fields == {"inputs": ["question"], "outputs": ["answer"]}
