/**
 * Pipeline-stage detection for an in-progress optimization.
 *
 * Looks at a job's progress event stream + latest metrics to classify
 * what step of the DSPy pipeline it is currently executing.
 */
import type { OptimizationStatusResponse } from "@/lib/types";
import type { PipelineStage } from "../constants";

export function detectStage(job: OptimizationStatusResponse): PipelineStage {
  if (job.status === "validating") return "validating";
  if (job.status === "success") return "done";

  const events = job.progress_events ?? [];
  const eventNames = events.map((e) => e.event);
  const metrics = job.latest_metrics ?? {};

  // Check progress events (works for both single-run and grid search)
  if (eventNames.includes("optimized_evaluated") || eventNames.includes("grid_pair_completed")) return "done";
  if (eventNames.includes("optimizer_progress")) return "optimizing";
  if (eventNames.includes("baseline_evaluated")) return "optimizing";
  if (eventNames.includes("grid_pair_started")) return "baseline";
  if (eventNames.includes("dataset_splits_ready")) return "baseline";

  // Fallback: use latest_metrics hints (e.g. tqdm from optimizer)
  if (metrics.tqdm_desc || metrics.tqdm_percent != null) return "optimizing";

  if (job.status === "running") return "splitting";
  return "validating";
}
