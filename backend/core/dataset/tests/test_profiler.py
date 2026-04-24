"""Tests for ``core.dataset.profiler.profile_dataset``."""

from __future__ import annotations

import pytest

from core.dataset.profiler import profile_dataset
from core.exceptions import ValidationError
from core.models import ColumnMapping, ProfileWarningCode


def _mapping(inputs: dict[str, str] | None = None, outputs: dict[str, str] | None = None) -> ColumnMapping:
    """Build a ColumnMapping from raw dicts with a sensible default shape."""
    return ColumnMapping(
        inputs=inputs or {"question": "q"},
        outputs=outputs or {"answer": "a"},
    )


def _rows(pairs: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Build a list of ``{"q": ..., "a": ...}`` rows from (q, a) tuples."""
    return [{"q": q, "a": a} for q, a in pairs]


def test_profile_dataset_empty_raises() -> None:
    """An empty dataset raises ValidationError."""
    with pytest.raises(ValidationError, match="at least one row"):
        profile_dataset([], _mapping())


def test_profile_dataset_reports_basic_shape() -> None:
    """Row count and column count reflect the input rows."""
    rows = _rows([("q1", "yes"), ("q2", "no"), ("q3", "yes")])
    profile = profile_dataset(rows, _mapping())

    assert profile.row_count == 3
    assert profile.column_count == 2


def test_profile_dataset_detects_categorical_target() -> None:
    """Short low-cardinality target values produce a categorical profile and histogram."""
    rows = _rows([("q1", "yes"), ("q2", "no"), ("q3", "yes"), ("q4", "no"), ("q5", "yes")])
    profile = profile_dataset(rows, _mapping())

    assert profile.target is not None
    assert profile.target.kind == "categorical"
    assert profile.target.class_histogram == {"yes": 3, "no": 2}


def test_profile_dataset_detects_numeric_target() -> None:
    """Pure numeric target values produce a numeric profile with empty histogram."""
    rows = [{"q": f"q{i}", "a": float(i)} for i in range(10)]
    profile = profile_dataset(rows, _mapping())

    assert profile.target is not None
    assert profile.target.kind == "numeric"
    assert profile.target.class_histogram == {}


def test_profile_dataset_detects_freeform_target() -> None:
    """Long-text target values produce a freeform profile."""
    long_text = "a" * 80
    rows = [{"q": f"q{i}", "a": f"{long_text} {i}"} for i in range(10)]
    profile = profile_dataset(rows, _mapping())

    assert profile.target is not None
    assert profile.target.kind == "freeform"


def test_profile_dataset_warns_on_too_small() -> None:
    """Datasets below the recommended minimum surface a too_small warning."""
    rows = _rows([("q1", "yes"), ("q2", "no")])
    profile = profile_dataset(rows, _mapping())

    codes = {w.code for w in profile.warnings}
    assert ProfileWarningCode.too_small in codes


def test_profile_dataset_warns_on_duplicates() -> None:
    """Repeated input rows increment the duplicate count and emit a warning."""
    rows = _rows([("q1", "yes"), ("q1", "no"), ("q2", "yes")])
    profile = profile_dataset(rows, _mapping())

    assert profile.duplicate_count == 1
    assert any(w.code == ProfileWarningCode.duplicates for w in profile.warnings)


def test_profile_dataset_warns_on_rare_class() -> None:
    """A category with fewer than the rare threshold of members triggers a warning."""
    rows = _rows([("q", "majority")] * 30 + [("q2", "rare")])
    profile = profile_dataset(rows, _mapping())

    assert any(w.code == ProfileWarningCode.rare_class for w in profile.warnings)


def test_profile_dataset_warns_on_imbalance() -> None:
    """A 20:1 class ratio triggers a class_imbalance warning."""
    rows = _rows([(f"q{i}", "majority") for i in range(40)] + [("qx", "minority")] * 2)
    profile = profile_dataset(rows, _mapping())

    assert any(w.code == ProfileWarningCode.class_imbalance for w in profile.warnings)


def test_profile_dataset_warns_on_missing_target_values() -> None:
    """Rows with None or empty target values count as missing and emit a warning."""
    rows: list[dict[str, object]] = [
        {"q": "q1", "a": "yes"},
        {"q": "q2", "a": None},
        {"q": "q3", "a": ""},
    ]
    profile = profile_dataset(rows, _mapping())

    assert any(w.code == ProfileWarningCode.missing_target for w in profile.warnings)


def test_profile_dataset_without_output_mapping_has_no_target() -> None:
    """A mapping with no outputs returns profile.target == None."""
    rows = _rows([("q1", "yes"), ("q2", "no")])
    profile = profile_dataset(rows, ColumnMapping(inputs={"question": "q"}))

    assert profile.target is None
    assert profile.targets == []


def test_profile_dataset_adaptive_categorical_above_min_unique() -> None:
    """A column with 25 short labels in 1000 rows is categorical via the ratio rule."""
    # 25 unique short genres × 40 rows each = 1000 rows. Ratio 0.025 ≪ 0.2.
    rows = [
        {"q": f"q{i}", "a": f"genre_{i % 25}"} for i in range(1000)
    ]
    profile = profile_dataset(rows, _mapping())

    assert profile.target is not None
    assert profile.target.kind == "categorical"
    assert profile.target.unique_values == 25


def test_profile_dataset_adaptive_freeform_when_unique_ratio_too_high() -> None:
    """25 unique short labels in only 30 rows is freeform — each class is just a label."""
    rows = [{"q": f"q{i}", "a": f"label_{i % 25}"} for i in range(30)]
    profile = profile_dataset(rows, _mapping())

    assert profile.target is not None
    # 25 / 30 = 0.83 > CATEGORICAL_UNIQUE_RATIO=0.2 → freeform.
    assert profile.target.kind == "freeform"


def test_profile_dataset_freeform_when_unique_count_above_max() -> None:
    """A column with more than CATEGORICAL_MAX_UNIQUE distinct values is never categorical."""
    rows = [{"q": f"q{i}", "a": f"id_{i}"} for i in range(1000)]
    profile = profile_dataset(rows, _mapping())

    assert profile.target is not None
    assert profile.target.kind == "freeform"


def test_profile_dataset_profiles_every_output_column() -> None:
    """A mapping with two outputs produces a TargetColumnProfile for each."""
    rows = [
        {"q": f"q{i}", "label": "yes" if i % 2 == 0 else "no", "tag": f"t{i % 3}"}
        for i in range(30)
    ]
    profile = profile_dataset(
        rows,
        ColumnMapping(
            inputs={"question": "q"},
            outputs={"label": "label", "tag": "tag"},
        ),
    )

    assert len(profile.targets) == 2
    names = {t.name for t in profile.targets}
    assert names == {"label", "tag"}


def test_profile_dataset_primary_target_prefers_categorical() -> None:
    """When outputs mix kinds, the primary target is the smallest-cardinality categorical."""
    rows = [
        {"q": f"q{i}", "label": "yes" if i % 2 == 0 else "no", "summary": "a" * 80}
        for i in range(20)
    ]
    profile = profile_dataset(
        rows,
        ColumnMapping(
            inputs={"question": "q"},
            outputs={"summary": "summary", "label": "label"},
        ),
    )

    assert profile.target is not None
    assert profile.target.name == "label"
    assert profile.target.kind == "categorical"


def test_profile_dataset_warning_carries_target_column_name() -> None:
    """Class-imbalance/rare-class warnings include the originating column name in details."""
    rows = _rows([("q", "majority")] * 30 + [("q2", "rare")])
    profile = profile_dataset(rows, _mapping())

    rare = next(w for w in profile.warnings if w.code == ProfileWarningCode.rare_class)
    assert rare.details.get("target_column") == "a"


def test_profile_dataset_imbalance_warning_attributed_to_correct_column() -> None:
    """When two outputs have warnings, each warning carries its own target_column."""
    rows = [
        {
            "q": f"q{i}",
            "balanced": "yes" if i % 2 == 0 else "no",
            # 49:1 imbalance on the second column
            "skewed": "majority" if i < 49 else "minority",
        }
        for i in range(50)
    ]
    profile = profile_dataset(
        rows,
        ColumnMapping(
            inputs={"question": "q"},
            outputs={"balanced": "balanced", "skewed": "skewed"},
        ),
    )

    imbalance_warnings = [
        w for w in profile.warnings if w.code == ProfileWarningCode.class_imbalance
    ]
    assert len(imbalance_warnings) == 1
    assert imbalance_warnings[0].details.get("target_column") == "skewed"
