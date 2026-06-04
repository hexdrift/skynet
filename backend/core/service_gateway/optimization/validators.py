"""Payload validators shared by DspyService.

Pure functions that check that a ``ColumnMapping`` covers every
signature field and references columns actually present in the
dataset. Extracted from ``core.py`` so they can be unit-tested
without constructing a full ``DspyService``.
"""

from typing import Any

from ...exceptions import ServiceError
from ...models import ColumnMapping, ReplayMapping


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


def require_replay_mapping_valid(
    replay_mapping: ReplayMapping,
    dataset: list[dict[str, Any]] | None,
) -> None:
    """Raise ServiceError if a replay role names a column absent from the dataset.

    React replay rollouts read recorded tool-call steps, the allowed-tool
    roster, and per-tool schema hashes off dataset columns named by
    ``replay_mapping``. Every required role (``steps``, ``allowed_tools``,
    ``tool_schema_hashes``) must reference a column that exists in the
    dataset. Optional roles (state/chat-history) are checked too when set.
    Validation is skipped entirely when no inline dataset is supplied (the
    rows live in a staged copy resolved later).

    Args:
        replay_mapping: The submitted replay mapping whose role values name
            dataset column names.
        dataset: The inline dataset rows, or ``None`` when the rows are
            staged and not yet resolved.

    Raises:
        ServiceError: When a replay role references a column that is not
            present in any row of ``dataset``.
    """
    if not dataset:
        return
    dataset_columns: set[str] = set()
    for row in dataset:
        dataset_columns.update(row.keys())
    required = {
        "steps": replay_mapping.steps,
        "allowed_tools": replay_mapping.allowed_tools,
        "tool_schema_hashes": replay_mapping.tool_schema_hashes,
    }
    optional = {
        "state_before": replay_mapping.state_before,
        "state_after": replay_mapping.state_after,
        "chat_history": replay_mapping.chat_history,
    }
    roles = {**required, **{role: col for role, col in optional.items() if col is not None}}
    missing = {role: col for role, col in roles.items() if col not in dataset_columns}
    if missing:
        offending = sorted(f"{role}={col!r}" for role, col in missing.items())
        raise ServiceError(
            f"replay_mapping references columns not found in dataset: {offending}. "
            f"Available columns: {sorted(dataset_columns)}"
        )
