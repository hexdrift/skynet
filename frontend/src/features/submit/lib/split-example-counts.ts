import type { SplitFractions } from "@/shared/types/api";

/**
 * Whole-example counts for a split, the way the backend slices it
 * (`datasets/split_counts.py`): each split takes the examples its fraction
 * covers, the rows left over go to the splits whose fractions were cut the
 * most, a non-zero fraction always gets at least one example and a zero
 * fraction none. While an edit leaves the fractions short of one, each field
 * previews its own share with the same one-example floor.
 */
export function splitExampleCounts(total: number, split: SplitFractions): SplitFractions {
  const shares = [split.train, split.val, split.test];
  const valid = Math.abs(split.train + split.val + split.test - 1) < 0.0001;
  const [train = 0, val = 0, test = 0] = valid
    ? allocate(total, shares)
    : shares.map((share) =>
        share > 0 ? Math.min(total, Math.max(1, Math.floor(total * share))) : 0,
      );
  return { train, val, test };
}

type Slot = { share: number; exact: number; count: number };

function allocate(total: number, shares: number[]): number[] {
  const slots: Slot[] = shares.map((share) => ({
    share,
    exact: total * share,
    count: share > 0 ? Math.max(1, Math.floor(total * share)) : 0,
  }));
  const held = slots.filter((slot) => slot.share > 0);
  let shortfall = total - slots.reduce((sum, slot) => sum + slot.count, 0);
  for (; shortfall > 0; shortfall -= 1) {
    largest(held, (slot) => slot.exact - slot.count).count += 1;
  }
  // The one-example floors can overdraw a tiny dataset: the largest split gives
  // one back, and once every split is down to one the smallest shares go
  // without, later splits first.
  for (; shortfall < 0; shortfall += 1) {
    const aboveFloor = slots.filter((slot) => slot.count > 1);
    const from = aboveFloor.length
      ? largest(aboveFloor, (slot) => slot.count)
      : largest(slots.filter((slot) => slot.count > 0).reverse(), (slot) => -slot.share);
    from.count -= 1;
  }
  return slots.map((slot) => slot.count);
}

/** The item with the largest key; ties go to the first listed. */
function largest<T>(items: T[], key: (item: T) => number): T {
  return items.reduce((best, item) => (key(item) > key(best) ? item : best));
}
