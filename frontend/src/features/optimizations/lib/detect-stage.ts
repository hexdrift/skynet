/**
 * Pipeline-stage detection for an in-progress optimization.
 *
 * Looks at a job's progress event stream + latest metrics to classify
 * what step of the DSPy pipeline it is currently executing.
 */
import type { OptimizationStatusResponse } from "@/shared/types/api";
import type { PipelineStage } from "../constants";

export function detectStage(job: OptimizationStatusResponse): PipelineStage {
  if (job.status === "validating") return "validating";
  if (job.status === "success") return "done";

  const events = job.progress_events ?? [];
  const eventNames = events.map((e) => e.event);
  const metrics = job.latest_metrics ?? {};

  // Check progress events (works for both single-run and grid search)
  if (eventNames.includes("optimized_evaluated") || eventNames.includes("grid_pair_completed"))
    return "done";
  if (eventNames.includes("optimizer_progress")) return "optimizing";
  if (eventNames.includes("baseline_evaluated")) return "optimizing";
  if (eventNames.includes("grid_pair_started")) return "baseline";
  if (eventNames.includes("dataset_splits_ready")) return "baseline";

  // Fallback: use latest_metrics hints (e.g. tqdm from optimizer)
  if (metrics.tqdm_desc || metrics.tqdm_percent != null) return "optimizing";

  if (job.status === "running") return "splitting";
  return "validating";
}

/**
 * Pair-scoped stage detection for grid_search jobs. Uses events carrying the
 * matching `pair_index` (grid_pair_started/completed/failed, baseline_evaluated,
 * optimized_evaluated); falls back to the job-level stage for events emitted
 * before any pair started (validation, dataset splits).
 */
export function detectPairStage(
  job: OptimizationStatusResponse,
  pairIndex: number,
): PipelineStage {
  // Authoritative signal: if the pair result itself has a final score, an
  // artifact, or an error recorded, the pair is done — regardless of
  // whether the progress-event stream survived (events can be dropped
  // when the job is reloaded from storage without an active worker).
  const pair = job.grid_result?.pair_results?.find((p) => p.pair_index === pairIndex);
  if (pair && (pair.error || pair.optimized_test_metric != null || pair.program_artifact)) {
    return "done";
  }

  const events = job.progress_events ?? [];
  const pairEvents = events.filter((e) => {
    const pi = e.metrics?.pair_index;
    return typeof pi === "number" && pi === pairIndex;
  });
  const pairEventNames = pairEvents.map((e) => e.event);

  if (pairEventNames.includes("grid_pair_failed")) return "done";
  if (pairEventNames.includes("grid_pair_completed")) return "done";
  if (pairEventNames.includes("optimized_evaluated")) return "evaluating";
  if (pairEventNames.includes("baseline_evaluated")) return "optimizing";
  if (pairEventNames.includes("grid_pair_started")) return "baseline";

  // Pair hasn't started yet — reflect the job-level pre-pair stage.
  const eventNames = events.map((e) => e.event);
  if (eventNames.includes("dataset_splits_ready")) return "baseline";
  if (eventNames.includes("validation_passed")) return "splitting";
  if (job.status === "validating") return "validating";
  return "validating";
}
