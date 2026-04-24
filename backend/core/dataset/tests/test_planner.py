"""Tests for ``core.dataset.planner.recommend_split``."""

from __future__ import annotations

from core.dataset.planner import MIN_TEST_COUNT, recommend_split
from core.models import DatasetProfile
from core.models.dataset import (
    ProfileWarning,
    ProfileWarningCode,
    TargetColumnProfile,
)


def _profile(row_count: int) -> DatasetProfile:
    """Build a bare DatasetProfile with only the row count set."""
    return DatasetProfile(row_count=row_count, column_count=2)


def _categorical_profile(
    row_count: int,
    histogram: dict[str, int],
    *,
    warnings: list[ProfileWarning] | None = None,
) -> DatasetProfile:
    """Build a DatasetProfile with a categorical target and optional warnings."""
    return DatasetProfile(
        row_count=row_count,
        column_count=2,
        target=TargetColumnProfile(
            name="label",
            kind="categorical",
            unique_values=len(histogram),
            class_histogram=histogram,
        ),
        warnings=warnings or [],
    )


def test_recommend_split_small_tier_tilts_val_for_dspy() -> None:
    """Small datasets (<200 rows) lean toward val as the optimizer search surface."""
    plan = recommend_split(_profile(150), seed=42)

    assert plan.fractions.train == 0.30
    assert plan.fractions.val == 0.50
    assert plan.fractions.test == 0.20


def test_recommend_split_medium_tier_balances_train_and_val() -> None:
    """Medium datasets (200-2k rows) balance train and val with a 15% test slice."""
    plan = recommend_split(_profile(1_000), seed=42)

    assert plan.fractions.train == 0.40
    assert plan.fractions.val == 0.45
    assert plan.fractions.test == 0.15


def test_recommend_split_large_tier_gives_train_majority() -> None:
    """Large datasets (2k-20k rows) shift the majority of data to train."""
    plan = recommend_split(_profile(5_000), seed=42)

    assert plan.fractions.train == 0.60
    assert plan.fractions.val == 0.30
    assert plan.fractions.test == 0.10


def test_recommend_split_huge_tier_caps_held_out_absolute_size() -> None:
    """Datasets above 20k rows cap val near 4k and test near 2k."""
    plan = recommend_split(_profile(100_000), seed=42)

    assert 3_900 <= plan.counts.val <= 4_100
    assert 1_900 <= plan.counts.test <= 2_100
    assert plan.counts.train >= 93_000


def test_recommend_split_counts_sum_to_total() -> None:
    """Train/val/test counts always sum to the profile row count."""
    for total in (37, 150, 999, 4_321, 25_000):
        plan = recommend_split(_profile(total), seed=7)
        assert plan.counts.train + plan.counts.val + plan.counts.test == total


def test_recommend_split_fractions_sum_to_one() -> None:
    """Recommended fractions always sum to exactly 1.0 (SplitFractions invariant)."""
    for total in (50, 500, 5_000, 50_000):
        plan = recommend_split(_profile(total), seed=0)
        total_frac = plan.fractions.train + plan.fractions.val + plan.fractions.test
        assert abs(total_frac - 1.0) < 1e-6


def test_recommend_split_honors_provided_seed() -> None:
    """When a seed is provided it is returned verbatim in the plan."""
    plan = recommend_split(_profile(500), seed=12345)

    assert plan.seed == 12345


def test_recommend_split_generates_seed_when_none() -> None:
    """An omitted seed is replaced with a non-negative integer."""
    plan = recommend_split(_profile(500))

    assert plan.seed >= 0


def test_recommend_split_rationale_mentions_counts() -> None:
    """The rationale always includes a split-counts bullet."""
    plan = recommend_split(_profile(1_000), seed=42)

    combined = " ".join(plan.rationale)
    assert "אימון" in combined
    assert "אימות" in combined
    assert "בדיקה" in combined


def test_recommend_split_micro_dataset_flags_noise_in_rationale() -> None:
    """Datasets below the MIN_TEST_COUNT floor get an explicit 'noisy scores' note."""
    plan = recommend_split(_profile(10), seed=42)

    assert any("רועשים" in line for line in plan.rationale)


def test_recommend_split_shuffle_is_true_by_default() -> None:
    """The v1 planner always recommends shuffling before the slice."""
    plan = recommend_split(_profile(500), seed=42)

    assert plan.shuffle is True


def test_recommend_split_enforces_test_floor_when_dataset_allows_it() -> None:
    """A 100-row tier-1 dataset hits the test floor: test promoted to MIN_TEST_COUNT."""
    plan = recommend_split(_profile(100), seed=42)

    assert plan.counts.test == MIN_TEST_COUNT
    assert plan.counts.train + plan.counts.val + plan.counts.test == 100
    assert any("הבדיקה" in line for line in plan.rationale)


def test_recommend_split_floor_preserves_train_val_ratio_after_promotion() -> None:
    """After promoting test to the floor, train and val keep their original ratio."""
    plan = recommend_split(_profile(100), seed=42)

    # Tier 1 fractions are 30/50/20 — train:val ratio is 3:5 (= 0.375 train share).
    non_test = plan.counts.train + plan.counts.val
    assert plan.counts.train == int(non_test * 0.30 / 0.80)


def test_recommend_split_skips_test_floor_for_tiny_datasets() -> None:
    """A 50-row dataset is too small to spare 30 for test — floor is skipped."""
    plan = recommend_split(_profile(50), seed=42)

    assert plan.counts.test < MIN_TEST_COUNT
    assert plan.counts.train + plan.counts.val + plan.counts.test == 50


def test_recommend_split_recommends_stratify_for_class_imbalance() -> None:
    """A categorical target with class_imbalance warning gets stratify=True."""
    profile = _categorical_profile(
        row_count=500,
        histogram={"a": 450, "b": 50},
        warnings=[
            ProfileWarning(
                code=ProfileWarningCode.class_imbalance,
                message="...",
                details={"majority": 450, "minority": 50, "target_column": "label"},
            )
        ],
    )
    plan = recommend_split(profile, seed=42)

    assert plan.stratify is True
    assert plan.stratify_column == "label"
    assert any("יחס הקטגוריות" in line for line in plan.rationale)


def test_recommend_split_recommends_stratify_for_rare_class() -> None:
    """A categorical target with rare_class warning gets stratify=True."""
    profile = _categorical_profile(
        row_count=500,
        histogram={"a": 250, "b": 247, "c": 3},
        warnings=[
            ProfileWarning(
                code=ProfileWarningCode.rare_class,
                message="...",
                details={"rare_classes": {"c": 3}, "target_column": "label"},
            )
        ],
    )
    plan = recommend_split(profile, seed=42)

    assert plan.stratify is True
    assert plan.stratify_column == "label"


def test_recommend_split_skips_stratify_for_balanced_categorical() -> None:
    """A balanced categorical target with no warnings does not request stratify."""
    profile = _categorical_profile(
        row_count=500,
        histogram={"a": 250, "b": 250},
        warnings=[],
    )
    plan = recommend_split(profile, seed=42)

    assert plan.stratify is False


def test_recommend_split_skips_stratify_when_no_warnings() -> None:
    """No warnings means stratify=False and stratify_column=None."""
    profile = _categorical_profile(
        row_count=500,
        histogram={"a": 250, "b": 250},
        warnings=[],
    )
    plan = recommend_split(profile, seed=42)

    assert plan.stratify is False
    assert plan.stratify_column is None


def test_recommend_split_picks_imbalanced_column_among_multiple_targets() -> None:
    """When two categorical targets exist, the planner picks the one with the imbalance warning."""
    profile = DatasetProfile(
        row_count=500,
        column_count=3,
        targets=[
            TargetColumnProfile(
                name="balanced",
                kind="categorical",
                unique_values=2,
                class_histogram={"x": 250, "y": 250},
            ),
            TargetColumnProfile(
                name="imbalanced",
                kind="categorical",
                unique_values=2,
                class_histogram={"a": 480, "b": 20},
            ),
        ],
        warnings=[
            ProfileWarning(
                code=ProfileWarningCode.class_imbalance,
                message="...",
                details={"majority": 480, "minority": 20, "target_column": "imbalanced"},
            )
        ],
    )
    plan = recommend_split(profile, seed=42)

    assert plan.stratify is True
    assert plan.stratify_column == "imbalanced"


def test_recommend_split_rationale_names_stratify_column() -> None:
    """Rationale bullet for stratification mentions the chosen column name."""
    profile = _categorical_profile(
        row_count=500,
        histogram={"a": 450, "b": 50},
        warnings=[
            ProfileWarning(
                code=ProfileWarningCode.class_imbalance,
                message="...",
                details={"majority": 450, "minority": 50, "target_column": "label"},
            )
        ],
    )
    plan = recommend_split(profile, seed=42)

    assert any("'label'" in line for line in plan.rationale)


def test_recommend_split_skips_stratify_when_warning_targets_freeform_column() -> None:
    """A warning attached to a freeform column never triggers stratify."""
    profile = DatasetProfile(
        row_count=500,
        column_count=3,
        targets=[
            TargetColumnProfile(
                name="text",
                kind="freeform",
                unique_values=500,
            ),
        ],
        warnings=[
            ProfileWarning(
                code=ProfileWarningCode.class_imbalance,
                message="...",
                details={"target_column": "text"},
            )
        ],
    )
    plan = recommend_split(profile, seed=42)

    assert plan.stratify is False
    assert plan.stratify_column is None


def test_recommend_split_skips_stratify_for_freeform_target() -> None:
    """Freeform/numeric targets never request stratify even with warnings."""
    profile = DatasetProfile(
        row_count=500,
        column_count=2,
        target=TargetColumnProfile(
            name="text",
            kind="freeform",
            unique_values=500,
        ),
        warnings=[
            ProfileWarning(
                code=ProfileWarningCode.class_imbalance,
                message="...",
                details={},
            )
        ],
    )
    plan = recommend_split(profile, seed=42)

    assert plan.stratify is False
