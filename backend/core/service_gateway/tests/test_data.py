from __future__ import annotations

import dspy
import pytest

from core.exceptions import ServiceError
from core.models import ColumnMapping, SplitFractions
from core.service_gateway.data import (
    DatasetSplits,
    _is_signature_field,
    extract_signature_fields,
    extract_stratify_values,
    load_metric_from_code,
    load_signature_from_code,
    rows_to_examples,
    split_examples,
)


def _fractions(train: float, val: float, test: float) -> SplitFractions:
    """Build a SplitFractions from positional floats."""
    return SplitFractions(train=train, val=val, test=test)


def _items(n: int) -> list[int]:
    """Return a stable list of ints as stand-in examples."""
    return list(range(n))



@pytest.mark.parametrize(
    "n, train_f, val_f, test_f, exp_train, exp_val, exp_test",
    [
        (10, 0.7, 0.15, 0.15, 7, 1, 2),
        (100, 0.7, 0.15, 0.15, 70, 15, 15),
        (1, 1.0, 0.0, 0.0, 1, 0, 0),
        (10, 0.8, 0.1, 0.1, 8, 1, 1),
        (10, 0.5, 0.5, 0.0, 5, 5, 0),
    ],
    ids=["10-std", "100-std", "1-all-train", "10-80-10-10", "10-50-50-0"],
)
def test_split_examples_counts(n, train_f, val_f, test_f, exp_train, exp_val, exp_test) -> None:
    """Parametrized check that split sizes match expected counts for various fraction combos."""
    items = _items(n)
    fractions = _fractions(train_f, val_f, test_f)

    result = split_examples(items, fractions, shuffle=False, seed=None)

    assert len(result.train) == exp_train
    assert len(result.val) == exp_val
    assert len(result.test) == exp_test


def test_split_examples_too_small_for_nonzero_val_raises() -> None:
    """Dataset too small for a non-zero val fraction raises ServiceError."""
    items = _items(3)
    fractions = _fractions(0.7, 0.15, 0.15)

    with pytest.raises(ServiceError, match="too small for a val split"):
        split_examples(items, fractions, shuffle=False, seed=None)


def test_split_examples_empty_dataset_returns_empty_splits() -> None:
    """Empty dataset returns three empty lists without raising."""
    result = split_examples([], _fractions(0.7, 0.15, 0.15), shuffle=False, seed=None)

    assert result.train == []
    assert result.val == []
    assert result.test == []


def test_split_examples_all_items_accounted_for() -> None:
    """No examples are lost or duplicated across the three splits."""
    items = _items(20)
    fractions = _fractions(0.7, 0.15, 0.15)

    result = split_examples(items, fractions, shuffle=False, seed=None)

    assert len(result.train) + len(result.val) + len(result.test) == len(items)


def test_split_examples_no_shuffle_preserves_order() -> None:
    """shuffle=False keeps the original item order across concatenated splits."""
    items = _items(10)
    fractions = _fractions(0.7, 0.15, 0.15)

    result = split_examples(items, fractions, shuffle=False, seed=None)

    combined = result.train + result.val + result.test
    assert combined == items



def test_split_examples_shuffle_changes_order() -> None:
    """shuffle=True reorders items while preserving the full set."""
    items = _items(20)
    fractions = _fractions(0.7, 0.15, 0.15)

    result = split_examples(items, fractions, shuffle=True, seed=42)
    combined = result.train + result.val + result.test

    assert sorted(combined) == items
    assert combined != items


def test_split_examples_same_seed_is_deterministic() -> None:
    """Same seed produces identical splits on repeated calls."""
    items = _items(30)
    fractions = _fractions(0.7, 0.15, 0.15)

    r1 = split_examples(items, fractions, shuffle=True, seed=99)
    r2 = split_examples(items, fractions, shuffle=True, seed=99)

    assert r1.train == r2.train
    assert r1.val == r2.val
    assert r1.test == r2.test


def test_split_examples_different_seeds_differ() -> None:
    """Different seeds produce different orderings (statistically guaranteed)."""
    items = _items(30)
    fractions = _fractions(0.7, 0.15, 0.15)

    r1 = split_examples(items, fractions, shuffle=True, seed=1)
    r2 = split_examples(items, fractions, shuffle=True, seed=2)

    # It would be astronomically unlikely for both orderings to match.
    assert r1.train != r2.train


def test_split_examples_shuffle_does_not_mutate_input() -> None:
    """split_examples does not mutate the input list even when shuffling."""
    items = _items(20)
    original = list(items)
    fractions = _fractions(0.7, 0.15, 0.15)

    split_examples(items, fractions, shuffle=True, seed=7)

    assert items == original


def test_split_examples_stratified_preserves_class_proportions() -> None:
    """Stratified split keeps each class's per-slice ratio close to the global one."""
    # 100 items: 80 of class "a", 20 of class "b" (4:1 imbalance).
    items = _items(100)
    labels = ["a"] * 80 + ["b"] * 20
    fractions = _fractions(0.6, 0.2, 0.2)

    result = split_examples(
        items, fractions, shuffle=True, seed=42, stratify_values=labels
    )

    train_a = sum(1 for i in result.train if labels[i] == "a")
    train_b = sum(1 for i in result.train if labels[i] == "b")
    val_a = sum(1 for i in result.val if labels[i] == "a")
    val_b = sum(1 for i in result.val if labels[i] == "b")
    test_a = sum(1 for i in result.test if labels[i] == "a")
    test_b = sum(1 for i in result.test if labels[i] == "b")

    # Each class is split 60/20/20 independently.
    assert train_a == 48 and train_b == 12
    assert val_a == 16 and val_b == 4
    assert test_a == 16 and test_b == 4


def test_split_examples_stratified_keeps_rare_class_in_every_slice() -> None:
    """A rare class (5 examples) ends up with at least one row in every slice."""
    items = _items(105)
    labels = ["majority"] * 100 + ["rare"] * 5
    fractions = _fractions(0.6, 0.2, 0.2)

    result = split_examples(
        items, fractions, shuffle=True, seed=7, stratify_values=labels
    )

    assert any(labels[i] == "rare" for i in result.train)
    assert any(labels[i] == "rare" for i in result.val)
    assert any(labels[i] == "rare" for i in result.test)


def test_split_examples_stratified_all_items_accounted_for() -> None:
    """Stratified split partitions every item exactly once with no duplicates."""
    items = _items(50)
    labels = ["a"] * 25 + ["b"] * 25
    fractions = _fractions(0.7, 0.15, 0.15)

    result = split_examples(
        items, fractions, shuffle=True, seed=1, stratify_values=labels
    )
    combined = result.train + result.val + result.test

    assert sorted(combined) == items
    assert len(combined) == len(set(combined))


def test_split_examples_stratified_is_deterministic_with_same_seed() -> None:
    """Same seed produces identical stratified splits on repeated calls."""
    items = _items(60)
    labels = (["a"] * 40) + (["b"] * 20)
    fractions = _fractions(0.7, 0.15, 0.15)

    r1 = split_examples(items, fractions, shuffle=True, seed=99, stratify_values=labels)
    r2 = split_examples(items, fractions, shuffle=True, seed=99, stratify_values=labels)

    assert r1.train == r2.train
    assert r1.val == r2.val
    assert r1.test == r2.test


def test_split_examples_stratified_length_mismatch_raises() -> None:
    """Mismatched stratify_values length raises ServiceError."""
    items = _items(10)
    fractions = _fractions(0.7, 0.15, 0.15)

    with pytest.raises(ServiceError, match="stratify_values length"):
        split_examples(
            items, fractions, shuffle=True, seed=1, stratify_values=["a"] * 9
        )


def test_extract_stratify_values_reads_first_output_column() -> None:
    """extract_stratify_values pulls the first output field from each example."""
    mapping = ColumnMapping(inputs={"q": "q"}, outputs={"label": "label"})
    rows = [{"q": "x", "label": "cat"}, {"q": "y", "label": "dog"}]
    examples = rows_to_examples(rows, mapping)

    values = extract_stratify_values(examples, mapping)

    assert values == ["cat", "dog"]


def test_extract_stratify_values_coerces_non_string_values() -> None:
    """Numeric labels are coerced to strings for hashing into class buckets."""
    mapping = ColumnMapping(inputs={"q": "q"}, outputs={"label": "label"})
    rows = [{"q": "x", "label": 1}, {"q": "y", "label": 2}]
    examples = rows_to_examples(rows, mapping)

    values = extract_stratify_values(examples, mapping)

    assert values == ["1", "2"]


def test_extract_stratify_values_reads_explicit_column_when_multiple_outputs() -> None:
    """An explicit column kwarg picks that output instead of the first one."""
    mapping = ColumnMapping(
        inputs={"q": "q"},
        outputs={"primary": "primary", "secondary": "secondary"},
    )
    rows = [
        {"q": "x", "primary": "a", "secondary": "X"},
        {"q": "y", "primary": "b", "secondary": "Y"},
    ]
    examples = rows_to_examples(rows, mapping)

    values = extract_stratify_values(examples, mapping, column="secondary")

    assert values == ["X", "Y"]


def test_extract_stratify_values_accepts_signature_field_or_dataset_column() -> None:
    """The column kwarg may be either a dataset column or the signature field name."""
    mapping = ColumnMapping(
        inputs={"q": "q"},
        outputs={"sig_field": "raw_col"},
    )
    rows = [{"q": "x", "raw_col": "a"}, {"q": "y", "raw_col": "b"}]
    examples = rows_to_examples(rows, mapping)

    by_dataset = extract_stratify_values(examples, mapping, column="raw_col")
    by_signature = extract_stratify_values(examples, mapping, column="sig_field")

    assert by_dataset == by_signature == ["a", "b"]


def test_extract_stratify_values_unknown_column_raises() -> None:
    """Asking for a column that isn't in the mapping raises ServiceError."""
    mapping = ColumnMapping(inputs={"q": "q"}, outputs={"label": "label"})
    rows = [{"q": "x", "label": "a"}]
    examples = rows_to_examples(rows, mapping)

    with pytest.raises(ServiceError, match="not present in column_mapping outputs"):
        extract_stratify_values(examples, mapping, column="ghost")


def test_extract_stratify_values_no_outputs_raises() -> None:
    """A mapping with no outputs cannot be used for stratification."""
    mapping = ColumnMapping(inputs={"q": "q"})

    with pytest.raises(ServiceError, match="no output columns"):
        extract_stratify_values([], mapping)


_VALID_SIG = """
import dspy
class QA(dspy.Signature):
    question: str = dspy.InputField()
    answer: str = dspy.OutputField()
"""

def test_load_signature_from_code_returns_signature_class() -> None:
    """Valid signature code returns a dspy.Signature subclass."""
    sig = load_signature_from_code(_VALID_SIG)

    assert issubclass(sig, dspy.Signature)


def test_load_signature_from_code_syntax_error_raises_service_error() -> None:
    """Syntax error in signature code raises ServiceError."""
    with pytest.raises(ServiceError, match="syntax error"):
        load_signature_from_code("def bad syntax !!!")


def test_load_signature_from_code_no_signature_raises_service_error() -> None:
    """Code defining no Signature subclass raises ServiceError."""
    with pytest.raises(ServiceError, match="must define a dspy.Signature"):
        load_signature_from_code("x = 1")


def test_load_signature_from_code_multiple_signatures_raises_service_error() -> None:
    """Code defining more than one Signature subclass raises ServiceError."""
    code = """
import dspy
class A(dspy.Signature):
    q: str = dspy.InputField()
    a: str = dspy.OutputField()
class B(dspy.Signature):
    q: str = dspy.InputField()
    a: str = dspy.OutputField()
"""
    with pytest.raises(ServiceError, match="exactly one"):
        load_signature_from_code(code)



def test_load_metric_from_code_returns_callable() -> None:
    """Valid metric code returns a callable."""
    code = "def metric(example, prediction, trace=None): return 1.0"

    result = load_metric_from_code(code)

    assert callable(result)


def test_load_metric_from_code_named_metric_preferred() -> None:
    """When multiple callables exist, the one named 'metric' is selected."""
    code = """
def helper(): pass
def metric(example, prediction, trace=None): return 1.0
"""
    result = load_metric_from_code(code)

    assert result.__name__ == "metric"


def test_load_metric_from_code_no_callable_raises_service_error() -> None:
    """Code with no callable raises ServiceError."""
    with pytest.raises(ServiceError, match="must define a callable"):
        load_metric_from_code("x = 42")


def test_load_metric_from_code_syntax_error_raises_service_error() -> None:
    """Syntax error in metric code raises ServiceError."""
    with pytest.raises(ServiceError, match="syntax error"):
        load_metric_from_code("def !!!")



_SIMPLE_MAPPING = ColumnMapping(inputs={"question": "q"}, outputs={"answer": "a"})

_SIMPLE_ROWS = [
    {"q": "What is 1+1?", "a": "2"},
    {"q": "What is 2+2?", "a": "4"},
]


def test_rows_to_examples_happy_path_returns_correct_count() -> None:
    """Happy path produces one Example per input row."""
    examples = rows_to_examples(_SIMPLE_ROWS, _SIMPLE_MAPPING)

    assert len(examples) == 2


def test_rows_to_examples_example_has_expected_input_value() -> None:
    """Input column value is accessible via the signature field name on the Example."""
    examples = rows_to_examples(_SIMPLE_ROWS, _SIMPLE_MAPPING)

    assert examples[0].question == "What is 1+1?"


def test_rows_to_examples_example_has_expected_output_value() -> None:
    """Output column value is accessible via the signature field name on the Example."""
    examples = rows_to_examples(_SIMPLE_ROWS, _SIMPLE_MAPPING)

    assert examples[0].answer == "2"


def test_rows_to_examples_column_mapping_fanout_multi_rename() -> None:
    """Multiple input columns are all remapped to their signature field names."""
    mapping = ColumnMapping(inputs={"q1": "col_a", "q2": "col_b"}, outputs={"ans": "col_c"})
    rows = [{"col_a": "hello", "col_b": "world", "col_c": "hi"}]

    examples = rows_to_examples(rows, mapping)

    assert examples[0].q1 == "hello"
    assert examples[0].q2 == "world"
    assert examples[0].ans == "hi"


def test_rows_to_examples_missing_input_column_raises_service_error() -> None:
    """Missing mapped input column raises ServiceError."""
    rows = [{"wrong_col": "value", "a": "2"}]

    with pytest.raises(ServiceError, match="Missing input column"):
        rows_to_examples(rows, _SIMPLE_MAPPING)


def test_rows_to_examples_missing_output_column_raises_service_error() -> None:
    """Missing mapped output column raises ServiceError."""
    rows = [{"q": "value", "wrong_col": "2"}]

    with pytest.raises(ServiceError, match="Missing output column"):
        rows_to_examples(rows, _SIMPLE_MAPPING)


def test_rows_to_examples_non_dict_row_raises_service_error() -> None:
    """Non-dict row raises ServiceError."""
    rows = ["not-a-dict"]  # type: ignore[list-item]

    with pytest.raises(ServiceError, match="not a mapping"):
        rows_to_examples(rows, _SIMPLE_MAPPING)  # type: ignore[arg-type]


def test_rows_to_examples_empty_dataset_returns_empty_list() -> None:
    """Empty dataset returns an empty list without raising."""
    examples = rows_to_examples([], _SIMPLE_MAPPING)

    assert examples == []



_SIG_CODE = """\
import dspy
class QA(dspy.Signature):
    question: str = dspy.InputField()
    context: str = dspy.InputField()
    answer: str = dspy.OutputField()
"""


def test_extract_signature_fields_returns_correct_inputs() -> None:
    """Input field names are correctly extracted from a signature class."""
    sig_cls = load_signature_from_code(_SIG_CODE)

    inputs, _ = extract_signature_fields(sig_cls)

    assert "question" in inputs
    assert "context" in inputs


def test_extract_signature_fields_returns_correct_outputs() -> None:
    """Output field names are correctly extracted from a signature class."""
    sig_cls = load_signature_from_code(_SIG_CODE)

    _, outputs = extract_signature_fields(sig_cls)

    assert "answer" in outputs


def test_extract_signature_fields_returns_two_element_tuple() -> None:
    """extract_signature_fields returns a 2-tuple of (inputs, outputs) lists."""
    sig_cls = load_signature_from_code(_SIG_CODE)

    result = extract_signature_fields(sig_cls)

    assert len(result) == 2


def test_extract_signature_fields_raises_when_no_inputs() -> None:
    """Signature with no InputFields raises ServiceError."""
    code = """\
import dspy
class NoIn(dspy.Signature):
    answer: str = dspy.OutputField()
"""
    sig_cls = load_signature_from_code(code)

    with pytest.raises(ServiceError, match="at least one input"):
        extract_signature_fields(sig_cls)


def test_extract_signature_fields_raises_when_no_outputs() -> None:
    """Signature with no OutputFields raises ServiceError."""
    code = """\
import dspy
class NoOut(dspy.Signature):
    question: str = dspy.InputField()
"""
    sig_cls = load_signature_from_code(code)

    with pytest.raises(ServiceError, match="at least one"):
        extract_signature_fields(sig_cls)



def test_is_signature_field_returns_false_for_plain_string() -> None:
    """Plain string is not a signature field."""
    assert _is_signature_field("not-a-field", field_type="input") is False


def test_is_signature_field_returns_false_for_none() -> None:
    """None is not a signature field."""
    assert _is_signature_field(None, field_type="output") is False


def test_is_signature_field_returns_false_for_plain_int() -> None:
    """Plain integer is not a signature field."""
    assert _is_signature_field(42, field_type="input") is False


def test_is_signature_field_returns_true_for_dspy_input_field() -> None:
    """dspy.InputField() is recognised as an input field."""
    field = dspy.InputField()

    assert _is_signature_field(field, field_type="input") is True


def test_is_signature_field_returns_false_for_dspy_input_field_when_querying_output() -> None:
    """dspy.InputField() is not recognised as an output field."""
    field = dspy.InputField()

    assert _is_signature_field(field, field_type="output") is False


def test_is_signature_field_returns_true_for_dspy_output_field() -> None:
    """dspy.OutputField() is recognised as an output field."""
    field = dspy.OutputField()

    assert _is_signature_field(field, field_type="output") is True


def test_is_signature_field_detects_via_dspy_field_type_marker() -> None:
    """Object with __dspy_field_type marker is recognised even without isinstance match."""
    # Must use setattr to avoid Python's name-mangling of double-underscore names
    obj = object.__new__(type("_FakeField", (), {}))
    setattr(obj, "__dspy_field_type", "input")

    assert _is_signature_field(obj, field_type="input") is True


def test_is_signature_field_detects_via_json_schema_extra() -> None:
    """Object using json_schema_extra dict is recognised as the correct type."""

    class _SchemaField:
        json_schema_extra = {"__dspy_field_type": "output"}

    assert _is_signature_field(_SchemaField(), field_type="output") is True
