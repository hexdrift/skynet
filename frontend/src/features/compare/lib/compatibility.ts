import type { OptimizationStatusResponse } from "@/shared/types/api";

// Gate row-by-row comparison on ``compare_fingerprint``, not ``task_fingerprint``.
// Two jobs with matching ``task_fingerprint`` may still evaluate on different
// train/val/test splits (e.g., legacy jobs with no stored seed each derive their
// own from ``stable_seed(optimization_id)``). Only matching ``compare_fingerprint``
// guarantees identical test rows.
export function compareCompatibilityKey(job: OptimizationStatusResponse): string | null {
  const fp = job.compare_fingerprint;
  return typeof fp === "string" && fp.length > 0 ? fp : null;
}

export function canCompareKeys(keys: Array<string | null>): boolean {
  if (keys.length < 2) return false;
  const [first] = keys;
  if (!first) return false;
  return keys.every((key) => key === first);
}
