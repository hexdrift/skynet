"""Payload validators shared by DspyService.

Pure functions that check that a ``ColumnMapping`` covers every
signature field and references columns actually present in the
dataset. Extracted from ``core.py`` so they can be unit-tested
without constructing a full ``DspyService``.
"""

from typing import Any

from ...exceptions import ServiceError
from ...models import ColumnMapping


def require_mapping_matches_signature(
    mapping: ColumnMapping,
    signature_inputs: list[str],
    signature_outputs: list[str],
) -> None:
    """Raise ServiceError if any signature field is not covered by the column mapping.

    Args:
        mapping: The submitted column mapping for inputs/outputs.
        signature_inputs: Names of inputs declared on the DSPy signature.
        signature_outputs: Names of outputs declared on the DSPy signature.

    Raises:
        ServiceError: When ``mapping`` is missing entries for any
            signature input or output.
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
    dataset: list[dict[str, Any]],
) -> None:
    """Raise ServiceError if any mapped column name is absent from the dataset rows.

    The union of keys across all rows is treated as the set of available
    columns (rows are allowed to be ragged).

    Args:
        mapping: The submitted column mapping whose values reference
            dataset column names.
        dataset: The dataset rows used to compute the available column set.

    Raises:
        ServiceError: When ``mapping`` references columns that are not
            present in any row of ``dataset``.
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
