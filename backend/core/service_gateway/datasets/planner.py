"""Turn a dataset profile into a recommended split plan.

Given a ``DatasetProfile``, pick train/val/test fractions purely from the
example count and assemble a human-readable rationale. The output
``SplitPlan`` is surfaced by ``POST /datasets/profile``; the submit
wizard renders it as the "we'll split it like this" card and the user
either accepts the fractions or overrides them before sending the real
job payload.

The fractions are tuned for DSPy GEPA, which inverts the classical
prompt-optimizer ratio. DSPy's optimization overview explicitly notes
that GEPA "follows the more standard ML convention: maximize the
training set, while keeping the validation set just large enough to
reflect the distribution of the downstream tasks." Trainset (D_feedback)
drives reflective mutation; valset (D_pareto) is a fixed holdout used
to score every candidate against the Pareto frontier. GEPA accepts
val=trainset as a fallback for tiny corpora — formally allowed but
discouraged when more data exists.

The tier thresholds below are anchored to published GEPA tutorials —
the facility-support analyzer ran on 14/10/10, the HF cookbook on
112/22/90, AIME on 33/33/34 — and to DSPy's documented "substantial
value out of 30 examples" floor. We deliberately do not branch on
column type or class balance: GEPA's reflection LM consumes free-form
trajectories and the Pareto frontier scores against an aggregate
metric, so per-class stratified sampling buys nothing here. Pure
size-based splitting is simpler, defensible, and matches every
published GEPA configuration we found.
"""

from __future__ import annotations

import random

from ...i18n import t
from ...models.common import SplitCounts, SplitFractions
from ...models.dataset import DatasetProfile, SplitPlan

TIER_TINY = 30
TIER_SMALL = 80
TIER_MEDIUM = 300

VAL_CAP = 200
TEST_CAP = 500


def recommend_split(profile: DatasetProfile, *, seed: int | None = None) -> SplitPlan:
    """Return a recommended ``SplitPlan`` for the profiled dataset.

    When ``seed`` is omitted a fresh random seed is chosen so the plan is
    still fully specified.

    Args:
        profile: The dataset profile produced by the profiler.
        seed: Optional deterministic seed; when ``None`` a random seed is chosen.

    Returns:
        A fully-populated :class:`SplitPlan` describing fractions, counts,
        seed, and rationale.
    """
    total = profile.row_count
    fractions = _recommend_fractions(total)
    counts = _compute_counts(total, fractions)
    resolved_seed = seed if seed is not None else random.Random().randint(0, 2**31 - 1)

    return SplitPlan(
        fractions=fractions,
        shuffle=True,
        seed=resolved_seed,
        counts=counts,
        rationale=_build_rationale(total, counts),
    )


def _recommend_fractions(total: int) -> SplitFractions:
    """Pick train/val/test fractions sized to GEPA's documented sweet spots.

    Tier policy (research-grounded; see module docstring for citations):

    * ``total < 30``  — all train (val=test=0). GEPA falls back to using
      the trainset as the valset; documented as legal-but-discouraged
      and the only viable option for tutorial-scale corpora.
    * ``30 <= total < 80`` — 80/20/0. Enough to give GEPA a true holdout
      valset for Pareto scoring; a test slice would starve training.
    * ``80 <= total < 300`` — 60/20/20. Standard 3-way split where val
      and test are both large enough (≥16 / ≥16) for stable scoring.
    * ``total >= 300`` — 60/20/20 with val capped at ``VAL_CAP`` and
      test capped at ``TEST_CAP``. DSPy's GEPA notes call out a ~35
      example threshold below which further valset reduction is
      unhelpful; the cap keeps optimizer compute bounded once the
      valset is "large enough to reflect the distribution."

    Args:
        total: Total number of rows in the dataset.

    Returns:
        Recommended train/val/test fractions summing to 1.0.
    """
    if total < TIER_TINY:
        return SplitFractions(train=1.0, val=0.0, test=0.0)
    if total < TIER_SMALL:
        return SplitFractions(train=0.80, val=0.20, test=0.0)
    if total < TIER_MEDIUM:
        return SplitFractions(train=0.60, val=0.20, test=0.20)

    val_fraction = round(min(0.20, VAL_CAP / total), 4)
    test_fraction = round(min(0.20, TEST_CAP / total), 4)
    train_fraction = round(1.0 - val_fraction - test_fraction, 4)
    val_fraction = round(1.0 - train_fraction - test_fraction, 4)
    return SplitFractions(train=train_fraction, val=val_fraction, test=test_fraction)


def _compute_counts(total: int, fractions: SplitFractions) -> SplitCounts:
    """Convert fractional sizes into integer counts that sum to ``total``.

    Rounds train and val down; test absorbs the remainder so the three
    counts always sum exactly to ``total``. No floor logic — the new
    tier policy already guarantees test=0 when the dataset can't
    afford a meaningful holdout.

    Args:
        total: Total number of rows in the dataset.
        fractions: Recommended train/val/test fractions.

    Returns:
        :class:`SplitCounts` with train+val+test == total.
    """
    train = int(total * fractions.train)
    val = int(total * fractions.val)
    if fractions.test == 0:
        train = total - val
        return SplitCounts(train=train, val=val, test=0)
    test = total - train - val
    return SplitCounts(train=train, val=val, test=test)


def _build_rationale(total: int, counts: SplitCounts) -> list[str]:
    """Build short Hebrew rationale bullets explaining the chosen tier.

    Args:
        total: Total dataset size.
        counts: Per-split row counts produced by ``_compute_counts``.

    Returns:
        A list of short Hebrew bullet strings describing the plan.
    """
    if total < TIER_TINY:
        return [t("dataset.split.rationale.tiny", total=total)]
    if total < TIER_SMALL:
        return [t("dataset.split.rationale.small", total=total)]
    if total < TIER_MEDIUM:
        return [t("dataset.split.rationale.medium", total=total)]
    return [
        t(
            "dataset.split.rationale.large",
            total=total,
            val_count=counts.val,
            test_count=counts.test,
        )
    ]
