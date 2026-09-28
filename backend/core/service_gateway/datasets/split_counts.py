"""Turn split fractions into whole-example counts that use every row.

Fractions rarely divide a dataset evenly. The counts come from the
largest-remainder method: each split takes the whole examples its fraction
covers, and the rows left over go to the splits whose fractions were cut
the most, so the three counts always add up to the dataset. Two rules sit
on top: a split with a non-zero fraction always gets at least one example,
taken from the largest split if need be, and a split with a zero fraction
never gets any.

Runs submitted before this allocator existed truncated train and val and
left test the remainder. Their stored payloads carry no ``split_version``,
and :func:`split_counts_for_version` keeps slicing them the legacy way so a
resumed run, and the dataset and test-result views of a finished one, see
the partition the run was actually built on.
"""

from __future__ import annotations

import math

from ...models.common import SplitCounts, SplitFractions

SPLIT_VERSION_LEGACY = 1
SPLIT_VERSION_LARGEST_REMAINDER = 2
CURRENT_SPLIT_VERSION = SPLIT_VERSION_LARGEST_REMAINDER


def split_counts(total: int, fractions: SplitFractions) -> SplitCounts:
    """Allocate ``total`` examples across train, val and test.

    Args:
        total: Number of examples in the dataset.
        fractions: Train/val/test fractions summing to 1.0.

    Returns:
        Whole-example counts that add up to ``total``. When the dataset has
        fewer examples than there are non-zero fractions, the smallest
        fractions go without.
    """
    counts = _allocate(max(total, 0), (fractions.train, fractions.val, fractions.test))
    return SplitCounts(train=counts[0], val=counts[1], test=counts[2])


def legacy_split_counts(total: int, fractions: SplitFractions) -> SplitCounts:
    """Allocate ``total`` examples the way runs did before ``split_version`` existed.

    Args:
        total: Number of examples in the dataset.
        fractions: Train/val/test fractions summing to 1.0.

    Returns:
        Train and val truncated to whole examples, with test taking the rest.
    """
    total = max(total, 0)
    train = int(total * fractions.train)
    val = int(total * fractions.val)
    return SplitCounts(train=train, val=val, test=total - train - val)


def split_counts_for_version(total: int, fractions: SplitFractions, split_version: int | None) -> SplitCounts:
    """Allocate ``total`` examples with the allocator a run was submitted under.

    Args:
        total: Number of examples in the dataset.
        fractions: Train/val/test fractions summing to 1.0.
        split_version: The payload's stamped ``split_version``; ``None`` for
            payloads stored before the stamp existed.

    Returns:
        The counts the run's own split used.
    """
    if split_version is None or split_version < SPLIT_VERSION_LARGEST_REMAINDER:
        return legacy_split_counts(total, fractions)
    return split_counts(total, fractions)


def _allocate(total: int, shares: tuple[float, ...]) -> list[int]:
    """Apportion ``total`` across ``shares`` by largest remainder with a floor of one.

    Args:
        total: Number of examples to hand out.
        shares: Fractions summing to 1.0, in split order.

    Returns:
        One count per share, adding up to ``total``.
    """
    exact = [total * share for share in shares]
    counts = [max(math.floor(value), 1) if share > 0 else 0 for value, share in zip(exact, shares, strict=True)]
    held = [index for index, share in enumerate(shares) if share > 0]
    shortfall = total - sum(counts)
    while shortfall > 0:
        counts[max(held, key=lambda index: exact[index] - counts[index])] += 1
        shortfall -= 1
    # The one-example floors can overdraw a tiny dataset: the largest split
    # gives one back, and once every split is down to one the smallest shares
    # go without, later splits first. ``max`` keeps the first of tied entries.
    while shortfall < 0:
        above_floor = [index for index, count in enumerate(counts) if count > 1]
        if above_floor:
            counts[max(above_floor, key=lambda index: counts[index])] -= 1
        else:
            holding = [index for index in reversed(range(len(counts))) if counts[index] > 0]
            counts[max(holding, key=lambda index: -shares[index])] -= 1
        shortfall += 1
    return counts
