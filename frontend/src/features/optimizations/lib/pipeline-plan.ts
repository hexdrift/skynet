/**
 * Per-run pipeline plan for the stage tracker.
 *
 * Every run validates, splits, measures a baseline and evaluates the winner,
 * but the middle differs by algorithm: a DSPy compile (MIPROv2,
 * BootstrapFewShot…) or a GEPA reflective search. The plan names that stage
 * and its algorithm so the tracker reads as the run that actually happened.
 */
import type { OptimizationStatusResponse } from "@/shared/types/api";
import { TERMS } from "@/shared/lib/terms";
import { msg } from "@/shared/lib/messages";
import type { PipelineStage } from "../constants";

export interface PlannedStage {
  key: PipelineStage;
  label: string;
  /** The algorithm behind the stage, shown under the label. */
  detail?: string;
}

// Optimizer names arrive as dotted DSPy paths ("dspy.teleprompt.MIPROv2") or
// the bare "gepa" alias; the tracker wants the class name alone.
function optimizerLabel(raw: string): string {
  const name = raw.split(".").pop() ?? raw;
  return name.toLowerCase() === "gepa" ? "GEPA" : name;
}

function optimizingStage(job: OptimizationStatusResponse): PlannedStage {
  const optimizer = job.optimizer_name ?? "";
  const isReact = job.module_name === "react";
  if (isReact || optimizer.toLowerCase() === "gepa") {
    return {
      key: "optimizing",
      label: msg("pipeline.stage.reflectiveSearch"),
      detail: isReact ? "GEPA · ReAct" : "GEPA",
    };
  }
  if (optimizer)
    return { key: "optimizing", label: msg("pipeline.stage.compile"), detail: optimizerLabel(optimizer) };
  return { key: "optimizing", label: TERMS.optimization };
}

export function planPipelineStages(job: OptimizationStatusResponse): PlannedStage[] {
  return [
    { key: "validating", label: msg("auto.features.optimizations.constants.literal.1") },
    { key: "splitting", label: msg("auto.features.optimizations.constants.literal.2") },
    { key: "baseline", label: TERMS.baselineScore },
    optimizingStage(job),
    { key: "evaluating", label: msg("auto.features.optimizations.constants.literal.3") },
  ];
}
