import type { OptimizationDatasetResponse, OptimizationPayloadResponse } from "@/shared/types/api";

export function compareCompatibilityKey(
  payload: OptimizationPayloadResponse,
  dataset: OptimizationDatasetResponse,
): string | null {
  const metricCode = payload.payload.metric_code;
  if (typeof metricCode !== "string" || metricCode.trim() === "") return null;
  return JSON.stringify({
    metric_code: metricCode,
    test_indices: dataset.splits.test.map((row) => row.index),
  });
}

export function canCompareKeys(keys: Array<string | null>): boolean {
  if (keys.length < 2) return false;
  const [first] = keys;
  if (!first) return false;
  return keys.every((key) => key === first);
}
