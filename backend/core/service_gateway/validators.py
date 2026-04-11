"""Payload validators shared by DspyService.

Pure functions that check that a ``ColumnMapping`` covers every
signature field and references columns actually present in the
dataset. Extracted from ``core.py`` so they can be unit-tested
without constructing a full ``DspyService``.
"""

from typing import Any, Dict, List

from ..exceptions import ServiceError
from ..models import ColumnMapping


def require_mapping_matches_signature(
    mapping: ColumnMapping,
    signature_inputs: List[str],
    signature_outputs: List[str],
) -> None:
    """Ensure the column mapping covers every signature field exactly once.

    Args:
        mapping: ColumnMapping specifying input/output column mappings.
        signature_inputs: List of input field names from the DSPy signature.
        signature_outputs: List of output field names from the DSPy signature.

    Returns:
        None.

    Raises:
        ServiceError: If any signature fields are missing from the mapping.
    """
    missing_inputs = set(signature_inputs) - set(mapping.inputs.keys())
    missing_outputs = set(signature_outputs) - set(mapping.outputs.keys())
    if missing_inputs or missing_outputs:
        raise ServiceError(
            "column_mapping must include every signature field. "
            f"Missing inputs: {sorted(missing_inputs)}; "
            f"missing outputs: {sorted(missing_outputs)}"
        )


def require_mapping_columns_in_dataset(
    mapping: ColumnMapping,
    dataset: List[Dict[str, Any]],
) -> None:
    """Ensure every mapped column name exists in the dataset rows.

    Args:
        mapping: ColumnMapping specifying input/output column mappings.
        dataset: Non-empty list of row dicts from the request.

    Returns:
        None.

    Raises:
        ServiceError: If mapped columns are not found in dataset keys.
    """
    dataset_columns: set[str] = set()
    for row in dataset:
        dataset_columns.update(row.keys())
    mapped_columns = set(mapping.inputs.values()) | set(mapping.outputs.values())
    missing = mapped_columns - dataset_columns
    if missing:
        raise ServiceError(
            f"column_mapping references columns not found in dataset: {sorted(missing)}. "
            f"Available columns: {sorted(dataset_columns)}"
        )
