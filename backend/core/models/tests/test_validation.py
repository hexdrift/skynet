from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.models.validation import ValidateCodeRequest, ValidateCodeResponse
from core.models.common import ColumnMapping


def _column_mapping() -> dict:
    """Return a minimal valid ColumnMapping dict for test fixtures."""
    return {"inputs": {"q": "q"}, "outputs": {"a": "a"}}



def test_validate_code_request_accepts_signature_only() -> None:
    """Verify ValidateCodeRequest accepts a payload with only signature_code."""
    req = ValidateCodeRequest.model_validate(
        {"signature_code": "class S: pass", "column_mapping": _column_mapping()}
    )

    assert req.signature_code == "class S: pass"
    assert req.metric_code is None


def test_validate_code_request_accepts_metric_only() -> None:
    """Verify ValidateCodeRequest accepts a payload with only metric_code."""
    req = ValidateCodeRequest.model_validate(
        {"metric_code": "def m(e, p): return 1.0", "column_mapping": _column_mapping()}
    )

    assert req.metric_code == "def m(e, p): return 1.0"
    assert req.signature_code is None


def test_validate_code_request_accepts_both_blocks() -> None:
    """Verify ValidateCodeRequest accepts a payload providing both code blocks."""
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
        {"column_mapping": _column_mapping()}
    )

    assert req.sample_row == {}


def test_validate_code_request_optimizer_name_defaults_none() -> None:
    """Verify ValidateCodeRequest defaults optimizer_name to None."""
    req = ValidateCodeRequest.model_validate(
        {"column_mapping": _column_mapping()}
    )

    assert req.optimizer_name is None


def test_validate_code_request_rejects_invalid_column_mapping() -> None:
    """Verify ValidateCodeRequest propagates ColumnMapping validation errors."""
    with pytest.raises(ValidationError, match="At least one input"):
        ValidateCodeRequest.model_validate(
            {"column_mapping": {"inputs": {}, "outputs": {"a": "a"}}}
        )



def test_validate_code_response_valid_true_defaults() -> None:
    """Verify ValidateCodeResponse defaults errors, warnings, and signature_fields to empty/None."""
    r = ValidateCodeResponse(valid=True)

    assert r.errors == []
    assert r.warnings == []
    assert r.signature_fields is None


def test_validate_code_response_valid_false() -> None:
    """Verify ValidateCodeResponse stores errors when valid is False."""
    r = ValidateCodeResponse(valid=False, errors=["Syntax error on line 1"])

    assert r.valid is False
    assert "Syntax error on line 1" in r.errors


def test_validate_code_response_with_warnings() -> None:
    """Verify ValidateCodeResponse stores warnings list when provided."""
    r = ValidateCodeResponse(valid=True, warnings=["Metric always returns 1.0"])

    assert r.warnings == ["Metric always returns 1.0"]


def test_validate_code_response_signature_fields_populated() -> None:
    """Verify ValidateCodeResponse stores signature_fields when provided."""
    r = ValidateCodeResponse(
        valid=True,
        signature_fields={"inputs": ["question"], "outputs": ["answer"]},
    )

    assert r.signature_fields == {"inputs": ["question"], "outputs": ["answer"]}
