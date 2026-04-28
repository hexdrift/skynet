import type { GridSearchResult, OptimizationStatusResponse, PairResult } from "@/shared/types/api";

/**
 * Rebuild a partial `GridSearchResult` from `progress_events` when the backend
 * never persisted one — cancelled/failed grid_search jobs return
 * `grid_result = null` because `GridSearchResponse` is only produced after all
 * pairs finish. Per-pair metrics (models, baseline, optimized, improvement,
 * runtime) ride along on the `grid_pair_started/completed/failed` events, so
 * we can rebuild enough of the shape to render overview + per-pair detail.
 *
 * Caveats: `program_artifact` is not in progress events, so pairs rebuilt here
 * are not servable. The Serve tab is separately gated on
 * `job.status === "success"`, so this is fine.
 */
export function reconstructGridResult(job: OptimizationStatusResponse): GridSearchResult | null {
  if (job.optimization_type !== "grid_search") return null;
  const events = job.progress_events ?? [];
  const byIndex = new Map<number, PairResult>();

  const getPi = (m: Record<string, unknown>) =>
    typeof m.pair_index === "number" ? m.pair_index : null;

  for (const ev of events) {
    const pi = getPi(ev.metrics);
    if (pi == null) continue;
    const existing = byIndex.get(pi) ?? {
      pair_index: pi,
      generation_model: "",
      reflection_model: "",
    };
    if (ev.event === "grid_pair_started") {
      byIndex.set(pi, {
        ...existing,
        generation_model: (ev.metrics.generation_model as string) ?? existing.generation_model,
        reflection_model: (ev.metrics.reflection_model as string) ?? existing.reflection_model,
      });
    } else if (ev.event === "grid_pair_completed") {
      byIndex.set(pi, {
        ...existing,
        generation_model: (ev.metrics.generation_model as string) ?? existing.generation_model,
        reflection_model: (ev.metrics.reflection_model as string) ?? existing.reflection_model,
        baseline_test_metric: ev.metrics.baseline_test_metric as number | undefined,
        optimized_test_metric: ev.metrics.optimized_test_metric as number | undefined,
        metric_improvement: ev.metrics.metric_improvement as number | undefined,
        runtime_seconds: ev.metrics.runtime_seconds as number | undefined,
      });
    } else if (ev.event === "grid_pair_failed") {
      byIndex.set(pi, {
        ...existing,
        generation_model: (ev.metrics.generation_model as string) ?? existing.generation_model,
        reflection_model: (ev.metrics.reflection_model as string) ?? existing.reflection_model,
        error: (ev.metrics.error as string) ?? "failed",
      });
    }
  }

  if (byIndex.size === 0) return null;

  const pair_results = [...byIndex.values()].sort((a, b) => a.pair_index - b.pair_index);
  const successful = pair_results.filter((p) => !p.error && p.optimized_test_metric != null);
  const best_pair =
    successful.length > 0
      ? successful.reduce((a, b) =>
          (a.optimized_test_metric ?? 0) >= (b.optimized_test_metric ?? 0) ? a : b,
        )
      : undefined;

  return {
    module_name: job.module_name ?? "",
    optimizer_name: job.optimizer_name ?? "",
    total_pairs: job.total_pairs ?? pair_results.length,
    completed_pairs: successful.length,
    failed_pairs: pair_results.filter((p) => !!p.error).length,
    pair_results,
    best_pair,
  };
}
