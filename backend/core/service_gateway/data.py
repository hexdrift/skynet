import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import dspy

from ..exceptions import ServiceError
from ..models import ColumnMapping, SplitFractions


@dataclass
class DatasetSplits:
    """Container for train/validation/test partitions."""

    train: list[Any]
    val: list[Any]
    test: list[Any]


def extract_signature_fields(signature_cls: type[dspy.Signature]) -> tuple[list[str], list[str]]:
    """Inspect a DSPy signature class and return (input_field_names, output_field_names).

    Args:
        signature_cls: A DSPy Signature subclass to introspect.

    Returns:
        A 2-tuple of (input_field_names, output_field_names).

    Raises:
        ServiceError: If the signature has no input or no output fields.
    """

    inputs: list[str] = []
    outputs: list[str] = []

    fields_mapping = getattr(signature_cls, "model_fields", None) or getattr(signature_cls, "__pydantic_fields__", None)
    if fields_mapping:
        for field_name, field_info in fields_mapping.items():
            if _is_signature_field(field_info, field_type="input"):
                inputs.append(field_name)
            elif _is_signature_field(field_info, field_type="output"):
                outputs.append(field_name)
    else:
        for attr_name, attr_value in signature_cls.__dict__.items():
            if _is_signature_field(attr_value, field_type="input"):
                inputs.append(attr_name)
            elif _is_signature_field(attr_value, field_type="output"):
                outputs.append(attr_name)
    if not inputs or not outputs:
        raise ServiceError("Signature must declare at least one input and one output field.")
    return inputs, outputs


def rows_to_examples(dataset: list[dict[str, Any]], mapping: ColumnMapping) -> list[Any]:
    """Convert dataset rows into DSPy Example instances using the column mapping.

    Args:
        dataset: List of raw row dicts from the uploaded dataset.
        mapping: Column mapping that translates dataset column names to signature field names.

    Returns:
        A list of ``dspy.Example`` objects with inputs and outputs marked.

    Raises:
        ServiceError: If a row is not a dict or a mapped column is missing.
    """

    examples: list[Any] = []
    for row_idx, row in enumerate(dataset):
        if not isinstance(row, dict):
            raise ServiceError(f"Row {row_idx} is not a mapping: {row!r}")
        payload: dict[str, Any] = {}
        for signature_field, column_name in mapping.inputs.items():
            try:
                payload[signature_field] = row[column_name]
            except KeyError as exc:
                raise ServiceError(f"Missing input column '{column_name}' for row {row_idx}") from exc
        for signature_field, column_name in mapping.outputs.items():
            try:
                payload[signature_field] = row[column_name]
            except KeyError as exc:
                raise ServiceError(f"Missing output column '{column_name}' for row {row_idx}") from exc

        example = dspy.Example(**payload)
        if hasattr(example, "with_inputs"):
            example = example.with_inputs(*mapping.inputs.keys())
        if mapping.outputs:
            if hasattr(example, "with_outputs"):
                example = example.with_outputs(*mapping.outputs.keys())
            elif hasattr(example, "with_targets"):
                example = example.with_targets(*mapping.outputs.keys())
        examples.append(example)

    return examples


def load_signature_from_code(code: str) -> type[dspy.Signature]:
    """Execute user-provided code and return the single DSPy signature class it defines.

    Args:
        code: Python source code string that must define exactly one ``dspy.Signature`` subclass.

    Returns:
        The ``dspy.Signature`` subclass defined in ``code``.

    Raises:
        ServiceError: If the code has a syntax error, defines no Signature subclass,
            or defines more than one.
    """

    namespace: dict[str, Any] = {"dspy": dspy}
    try:
        exec(code, namespace)
    except SyntaxError as exc:
        raise ServiceError(f"signature_code has a syntax error: {exc}") from exc
    signature_classes = [
        obj
        for obj in namespace.values()
        if isinstance(obj, type) and issubclass(obj, dspy.Signature) and obj is not dspy.Signature
    ]
    if not signature_classes:
        raise ServiceError("signature_code must define a dspy.Signature subclass.")
    if len(signature_classes) > 1:
        raise ServiceError("signature_code must define exactly one dspy.Signature subclass.")
    return signature_classes[0]


def load_metric_from_code(code: str) -> Callable[..., Any]:
    """Execute user-provided code and return the metric callable it defines.

    Args:
        code: Python source code string defining a callable, preferably named ``metric``.

    Returns:
        The metric callable extracted from ``code``.

    Raises:
        ServiceError: If the code has a syntax error or defines no callable.
    """

    namespace: dict[str, Any] = {"dspy": dspy}
    try:
        exec(code, namespace)
    except SyntaxError as exc:
        raise ServiceError(f"metric_code has a syntax error: {exc}") from exc
    metric = namespace.get("metric")
    if not callable(metric):
        callables = [obj for obj in namespace.values() if callable(obj)]
        if len(callables) == 1:
            metric = callables[0]
    if not callable(metric):
        raise ServiceError("metric_code must define a callable named 'metric'.")
    return metric


def extract_stratify_values(
    examples: list[Any],
    mapping: ColumnMapping,
    *,
    column: str | None = None,
) -> list[str]:
    """Pull the stratify label for each example from a target column.

    Args:
        examples: The full list of DSPy examples.
        mapping: The column mapping used to build those examples — needed
            to translate dataset column names back to signature field names.
        column: Optional dataset column name to read. When omitted, falls
            back to the first declared output column.

    Returns:
        One string per example, suitable for grouping in a stratified split.

    Raises:
        ServiceError: When the mapping has no outputs, or when ``column``
            is provided but does not match any mapped output column.
    """

    if not mapping.outputs:
        raise ServiceError("Cannot stratify split: column_mapping has no output columns.")

    if column is None:
        field_name = next(iter(mapping.outputs.keys()))
    else:
        field_name = _signature_field_for_column(mapping, column)
        if field_name is None:
            raise ServiceError(
                f"stratify column '{column}' is not present in column_mapping outputs."
            )

    values: list[str] = []
    for example in examples:
        raw = getattr(example, field_name, None)
        if raw is None:
            values.append("")
        elif isinstance(raw, str):
            values.append(raw.strip())
        else:
            values.append(str(raw))
    return values


def _signature_field_for_column(mapping: ColumnMapping, column: str) -> str | None:
    """Return the signature field name whose mapped output is ``column``.

    Accepts either the dataset column name (the value side of
    ``mapping.outputs``) or the signature field name itself (the key
    side), since the planner emits the dataset column name but callers
    may already be using signature field names.
    """
    for sig_field, col_name in mapping.outputs.items():
        if col_name == column or sig_field == column:
            return sig_field
    return None


def split_examples(
    examples: list[Any],
    fractions: SplitFractions,
    *,
    shuffle: bool,
    seed: int | None,
    stratify_values: list[str] | None = None,
) -> DatasetSplits:
    """Split examples into train/val/test partitions.

    Args:
        examples: Full list of DSPy examples to partition.
        fractions: Desired fractional sizes for train, val, and test splits.
        shuffle: When True, shuffle ``examples`` before splitting.
        seed: RNG seed used when ``shuffle`` is True; pass ``None`` for a random seed.
        stratify_values: Optional per-example class label. When provided, the
            split is stratified — each class is partitioned into
            train/val/test independently and proportionally, so rare classes
            survive in every slice. Must be the same length as ``examples``.

    Returns:
        A ``DatasetSplits`` containing the three partitioned lists.

    Raises:
        ServiceError: If the dataset is too small to produce the requested val
            split, or if ``stratify_values`` length does not match ``examples``.
    """

    total = len(examples)
    if total == 0:
        return DatasetSplits(train=[], val=[], test=[])

    if stratify_values is not None:
        if len(stratify_values) != total:
            raise ServiceError(
                f"stratify_values length ({len(stratify_values)}) does not match "
                f"examples length ({total})."
            )
        splits = _stratified_split(examples, stratify_values, fractions, seed=seed)
    else:
        splits = _simple_split(examples, fractions, shuffle=shuffle, seed=seed)

    if fractions.val > 0 and len(splits.val) == 0:
        raise ServiceError(
            f"Dataset has {total} examples — too small for a val split of "
            f"{fractions.val:.0%}. Add more data or set val fraction to 0."
        )

    return splits


def _simple_split(
    examples: list[Any],
    fractions: SplitFractions,
    *,
    shuffle: bool,
    seed: int | None,
) -> DatasetSplits:
    """Random (non-stratified) split into train/val/test."""

    total = len(examples)
    ordered = list(examples)
    if shuffle:
        rng = random.Random(seed)
        rng.shuffle(ordered)

    train_count = int(total * fractions.train)
    val_count = int(total * fractions.val)
    val_end = train_count + val_count
    return DatasetSplits(
        train=ordered[:train_count],
        val=ordered[train_count:val_end],
        test=ordered[val_end:],
    )


def _stratified_split(
    examples: list[Any],
    stratify_values: list[str],
    fractions: SplitFractions,
    *,
    seed: int | None,
) -> DatasetSplits:
    """Per-class proportional split.

    Groups example indices by their stratify value, splits each group
    independently using the same fractions, then re-shuffles the resulting
    train/val/test lists so a single class doesn't appear contiguously
    inside a slice. Always shuffles per-class indices before slicing —
    stratification without shuffle would defeat the purpose for any
    dataset whose rows are sorted by class.
    """

    rng = random.Random(seed)
    groups: dict[str, list[int]] = {}
    for idx, value in enumerate(stratify_values):
        groups.setdefault(value, []).append(idx)

    train_idx: list[int] = []
    val_idx: list[int] = []
    test_idx: list[int] = []

    for class_indices in groups.values():
        shuffled = list(class_indices)
        rng.shuffle(shuffled)
        n = len(shuffled)
        n_train = int(n * fractions.train)
        n_val = int(n * fractions.val)
        train_idx.extend(shuffled[:n_train])
        val_idx.extend(shuffled[n_train : n_train + n_val])
        test_idx.extend(shuffled[n_train + n_val :])

    rng.shuffle(train_idx)
    rng.shuffle(val_idx)
    rng.shuffle(test_idx)

    return DatasetSplits(
        train=[examples[i] for i in train_idx],
        val=[examples[i] for i in val_idx],
        test=[examples[i] for i in test_idx],
    )


def _is_signature_field(value: Any, *, field_type: str) -> bool:
    """Return True when a signature attribute represents the requested field type.

    Args:
        value: The attribute value to inspect.
        field_type: Either ``"input"`` or ``"output"``.

    Returns:
        True if ``value`` matches the requested field type, False otherwise.
    """

    type_attr = getattr(dspy, "InputField" if field_type == "input" else "OutputField", None)
    if type_attr is not None:
        try:
            if isinstance(value, type_attr):
                return True
        except TypeError:
            pass

    marker = getattr(value, "__dspy_field_type", None)
    if marker == field_type:
        return True

    extra = getattr(value, "json_schema_extra", None)
    return bool(isinstance(extra, dict) and extra.get("__dspy_field_type") == field_type)
