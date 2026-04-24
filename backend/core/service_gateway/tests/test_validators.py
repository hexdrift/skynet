"""Tests for the pure service_gateway validators."""

from __future__ import annotations

import pytest

from core.exceptions import ServiceError
from core.models import ColumnMapping
from core.service_gateway.validators import (
    require_mapping_columns_in_dataset,
    require_mapping_matches_signature,
)


def _mapping(inputs: dict[str, str], outputs: dict[str, str]) -> ColumnMapping:
    """Build a ColumnMapping from raw dicts."""
    return ColumnMapping(inputs=inputs, outputs=outputs)


def test_require_mapping_matches_signature_ok() -> None:
    """Mapping that covers all signature fields does not raise."""
    m = _mapping({"question": "q"}, {"answer": "a"})
    require_mapping_matches_signature(m, ["question"], ["answer"])


def test_require_mapping_matches_signature_missing_input() -> None:
    """Missing input field in mapping raises ServiceError naming the field."""
    m = _mapping({"question": "q"}, {"answer": "a"})
    with pytest.raises(ServiceError, match="Missing inputs: \\['context'\\]"):
        require_mapping_matches_signature(m, ["question", "context"], ["answer"])


def test_require_mapping_matches_signature_missing_output() -> None:
    """Missing output field in mapping raises ServiceError naming the field."""
    m = _mapping({"question": "q"}, {"answer": "a"})
    with pytest.raises(ServiceError, match="missing outputs: \\['confidence'\\]"):
        require_mapping_matches_signature(m, ["question"], ["answer", "confidence"])


def test_require_mapping_matches_signature_reports_both() -> None:
    """Both missing inputs and outputs are reported in the same ServiceError."""
    m = _mapping({"q": "q"}, {"a": "a"})
    with pytest.raises(ServiceError) as exc:
        require_mapping_matches_signature(m, ["q", "x"], ["a", "y"])
    assert "Missing inputs: ['x']" in str(exc.value)
    assert "missing outputs: ['y']" in str(exc.value)


def test_require_mapping_columns_in_dataset_ok() -> None:
    """Mapping whose columns all exist in the dataset does not raise."""
    m = _mapping({"question": "q"}, {"answer": "a"})
    require_mapping_columns_in_dataset(m, [{"q": "hi", "a": "hello", "extra": 1}])


def test_require_mapping_columns_in_dataset_missing() -> None:
    """Mapped column absent from dataset raises ServiceError."""
    m = _mapping({"question": "q"}, {"answer": "a"})
    with pytest.raises(ServiceError, match="columns not found in dataset: \\['a'\\]"):
        require_mapping_columns_in_dataset(m, [{"q": "hi"}])


def test_require_mapping_columns_in_dataset_merges_row_keys() -> None:
    """Columns across multiple rows are merged when checking availability."""
    m = _mapping({"question": "q"}, {"answer": "a"})
    # Different rows contribute columns to the available set.
    require_mapping_columns_in_dataset(m, [{"q": "hi"}, {"a": "hello"}])


def test_require_mapping_columns_in_dataset_lists_available() -> None:
    """ServiceError lists available dataset columns to aid debugging."""
    m = _mapping({"question": "missing_col"}, {"answer": "also_missing"})
    with pytest.raises(ServiceError) as exc:
        require_mapping_columns_in_dataset(m, [{"q": "hi", "a": "hello"}])
    assert "Available columns: ['a', 'q']" in str(exc.value)
