"""Turn a dataset profile into a recommended split plan.

Given a ``DatasetProfile``, pick train/val/test fractions, compute
concrete per-split example counts, and assemble a human-readable
rationale tuned to the dataset's size tier. The output ``SplitPlan`` is
surfaced by ``POST /datasets/profile``; the submit wizard renders it as
the "we'll split it like this" card and the user either accepts the
fractions or overrides them before sending the real job payload.

The fractions are tuned for DSPy's optimization paradigm where the val
set acts as the optimizer's search surface (every trial is scored on
val), not just a held-out hyperparameter dial. That makes val cheaper
than train at small dataset sizes, so the small-dataset tiers invert
the classical 80/10/10 in favour of more val. Train still matters as
the demo pool, but DSPy only samples a handful of demos from it
regardless of pool size.
"""

from __future__ import annotations

import random

from ...i18n import t
from ...models.common import SplitCounts, SplitFractions
from ...models.dataset import (
    DatasetProfile,
    ProfileWarningCode,
    SplitPlan,
)

TIER_SMALL = 200
TIER_MEDIUM = 2_000
TIER_LARGE = 20_000

MAX_VAL_COUNT = 4_000
MAX_TEST_COUNT = 2_000

# Floor for the test slice — fewer than this gives confidence intervals
# too wide to compare runs meaningfully.
MIN_TEST_COUNT = 30
# Don't promote test to the floor if doing so would leave fewer than
# this many examples for train+val combined.
MIN_REMAINDER_AFTER_FLOOR = 30


def recommend_split(profile: DatasetProfile, *, seed: int | None = None) -> SplitPlan:
    """Return a recommended ``SplitPlan`` for the profiled dataset.

    When ``seed`` is omitted a fresh random seed is chosen so the plan is
    still fully specified.

    Args:
        profile: The dataset profile produced by the profiler.
        seed: Optional deterministic seed; when ``None`` a random seed is chosen.

    Returns:
        A fully-populated :class:`SplitPlan` describing fractions, counts,
        stratification, seed, and rationale.
    """
    total = profile.row_count
    fractions = _recommend_fractions(total)
    counts, floor_applied = _compute_counts(total, fractions)
    stratify, stratify_column = _should_stratify(profile)
    resolved_seed = seed if seed is not None else random.Random().randint(0, 2**31 - 1)

    return SplitPlan(
        fractions=fractions,
        shuffle=True,
        seed=resolved_seed,
        counts=counts,
        stratify=stratify,
        stratify_column=stratify_column,
        rationale=_build_rationale(
            profile,
            counts,
            total,
            stratify=stratify,
            stratify_column=stratify_column,
            floor_applied=floor_applied,
        ),
    )


def _recommend_fractions(total: int) -> SplitFractions:
    """Pick train/val/test fractions tuned for DSPy optimization.

    Small datasets give the optimizer's val search surface most of the
    data; medium and large datasets shift gradually toward train as the
    demo pool starts to matter more; very large datasets cap val and
    test at fixed absolute counts so optimizer compute stays bounded.

    Args:
        total: Total number of rows in the dataset.

    Returns:
        Recommended train/val/test fractions summing to 1.0.
    """
    if total < TIER_SMALL:
        return SplitFractions(train=0.30, val=0.50, test=0.20)
    if total < TIER_MEDIUM:
        return SplitFractions(train=0.40, val=0.45, test=0.15)
    if total < TIER_LARGE:
        return SplitFractions(train=0.60, val=0.30, test=0.10)

    val_fraction = round(MAX_VAL_COUNT / total, 4)
    test_fraction = round(MAX_TEST_COUNT / total, 4)
    train_fraction = round(1.0 - val_fraction - test_fraction, 4)
    # Recompute val last to absorb rounding drift so the three fractions
    # sum to exactly 1.0 (SplitFractions enforces that invariant).
    val_fraction = round(1.0 - train_fraction - test_fraction, 4)
    return SplitFractions(train=train_fraction, val=val_fraction, test=test_fraction)


def _compute_counts(total: int, fractions: SplitFractions) -> tuple[SplitCounts, bool]:
    """Convert fractional sizes into integer counts, enforcing a test floor.

    Rounds train and val down; test absorbs the remainder so the three
    counts always sum to ``total``. When the resulting test slice would
    fall below ``MIN_TEST_COUNT`` (and the dataset is large enough to
    spare them), promote the test slice to the floor by reducing train
    and val proportionally to their original ratio. The returned
    ``floor_applied`` flag is True when the floor was applied.

    Args:
        total: Total number of rows in the dataset.
        fractions: Recommended train/val/test fractions.

    Returns:
        A tuple ``(SplitCounts, floor_applied)`` where ``floor_applied``
        indicates whether the test floor was enforced.
    """
    train = int(total * fractions.train)
    val = int(total * fractions.val)
    test = total - train - val

    floor_applied = False
    if test < MIN_TEST_COUNT and total - MIN_TEST_COUNT >= MIN_REMAINDER_AFTER_FLOOR and fractions.test > 0:
        floor_applied = True
        test = MIN_TEST_COUNT
        remaining = total - test
        non_test_fraction = fractions.train + fractions.val
        if non_test_fraction > 0:
            train = int(remaining * fractions.train / non_test_fraction)
            val = remaining - train
        else:
            train = remaining
            val = 0

    return SplitCounts(train=train, val=val, test=test), floor_applied


def _should_stratify(profile: DatasetProfile) -> tuple[bool, str | None]:
    """Pick a column to stratify on, if any output needs it.

    Walks every profiled output column and returns the first categorical
    one whose warnings include ``class_imbalance`` or ``rare_class``.
    Random sampling on imbalanced data risks dropping a class entirely
    from val or test; stratified sampling preserves the per-class ratio
    across all three slices.

    Args:
        profile: The dataset profile to inspect.

    Returns:
        A tuple ``(stratify, column_name)`` where ``stratify`` is True when
        a stratification column was found and ``column_name`` names it
        (or ``None`` when stratification is unnecessary).
    """
    relevant_codes = {
        ProfileWarningCode.class_imbalance,
        ProfileWarningCode.rare_class,
    }
    targets = profile.targets or ([profile.target] if profile.target else [])
    for target in targets:
        if target is None or target.kind != "categorical":
            continue
        for warning in profile.warnings:
            if warning.code not in relevant_codes:
                continue
            if warning.details.get("target_column") == target.name:
                return True, target.name
    return False, None


def _build_rationale(
    profile: DatasetProfile,
    counts: SplitCounts,
    total: int,
    *,
    stratify: bool,
    stratify_column: str | None,
    floor_applied: bool,
) -> list[str]:
    """Build short Hebrew rationale bullets explaining each decision.

    Args:
        profile: The dataset profile being summarised.
        counts: Per-split row counts produced by ``_compute_counts``.
        total: Total dataset size.
        stratify: Whether stratified splitting was applied.
        stratify_column: Column name used for stratification, if any.
        floor_applied: Whether the minimum-test floor was enforced.

    Returns:
        A list of short Hebrew bullet strings describing the plan.
    """
    lines: list[str] = []

    if total < TIER_SMALL:
        if total < MIN_TEST_COUNT:
            lines.append(t("dataset.split.rationale.micro", total=total))
        else:
            lines.append(t("dataset.split.rationale.small", total=total))
    elif total < TIER_MEDIUM:
        lines.append(t("dataset.split.rationale.medium", total=total))
    elif total < TIER_LARGE:
        lines.append(t("dataset.split.rationale.large", total=total))
    else:
        lines.append(
            t(
                "dataset.split.rationale.huge",
                total=total,
                val_count=counts.val,
                test_count=counts.test,
            )
        )

    if floor_applied:
        lines.append(t("dataset.split.rationale.test_floor", minimum=MIN_TEST_COUNT))

    if stratify and stratify_column:
        lines.append(t("dataset.split.rationale.stratify", stratify_column=stratify_column))

    categorical_targets = [
        t
        for t in (profile.targets or ([profile.target] if profile.target else []))
        if t and t.kind == "categorical" and len(t.class_histogram) >= 2
    ]
    for target in categorical_targets[:2]:
        preview = ", ".join(f"{name}={count}" for name, count in list(target.class_histogram.items())[:5])
        lines.append(
            t(
                "dataset.split.rationale.categorical_target",
                target_name=target.name,
                preview=preview,
            )
        )

    return lines
