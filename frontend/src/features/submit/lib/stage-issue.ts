import type { MessageKey } from "@/shared/lib/messages";
import type { WizardStageId } from "./wizard-steps";

/**
 * The first problem that keeps a wizard stage from being complete. The hook
 * resolves `key` into the toast text and moves focus to `fieldId` — a DOM id
 * or a `data-tutorial` handle of the control that fixes it.
 */
export interface WizardIssue {
  stage: WizardStageId;
  fieldId?: string;
  key: MessageKey;
  params?: Record<string, string>;
}

/**
 * Plain snapshot of the wizard state a stage check reads. Server evidence
 * (`*Errors`) is null until the matching check has run at least once.
 */
export interface StageSnapshot {
  username: string;
  jobName: string;
  moduleSelectionRequired: boolean;
  datasetRowCount: number;
  inputColumnCount: number;
  outputColumnCount: number;
  needsTools: boolean;
  mcpUrl: string;
  isWorkflow: boolean;
  /** Problems in the workflow graph, or null when there is no graph yet. */
  workflowIssueCount: number | null;
  signatureCode: string;
  signatureErrors: number | null;
  metricCode: string;
  metricErrors: number | null;
  splitErrors: number | null;
  targetScore: "ok" | "invalid" | "requires_val";
  /** Whether a provider key is saved, or null while the saved keys load. */
  hasApiKey: boolean | null;
  jobType: "run" | "grid_search";
  modelName: string;
  reflectionModelName: string;
  generationModelNames: readonly string[];
  reflectionModelNames: readonly string[];
  imageInputs: readonly string[];
  nonVisionModels: readonly string[];
}

const blank = (value: string) => !value.trim();

function goalIssue(s: StageSnapshot): WizardIssue | null {
  if (s.moduleSelectionRequired) {
    return { stage: "goal", fieldId: "module-selector", key: "submit.validation.module_required" };
  }
  return null;
}

function evaluationIssue(s: StageSnapshot, structureOnly: boolean): WizardIssue | null {
  const issue = (key: MessageKey, fieldId?: string): WizardIssue => ({
    stage: "evaluation",
    fieldId,
    key,
  });
  // The code editors only open once a module is chosen; with none, Evaluation
  // shows the picker in their place.
  if (s.moduleSelectionRequired) return goalIssue(s);
  if (s.datasetRowCount === 0) return issue("submit.validation.dataset_required", "dataset-upload");
  if (s.inputColumnCount === 0) {
    return issue("submit.validation.input_column_required", "column-mapping");
  }
  if (s.outputColumnCount === 0) {
    return issue("submit.validation.output_column_required", "column-mapping");
  }
  if (s.needsTools && blank(s.mcpUrl)) {
    return issue("submit.validation.mcp_url_required", "react-config");
  }
  if (s.isWorkflow) {
    if (s.workflowIssueCount === null || s.workflowIssueCount > 0) {
      return issue("submit.validation.workflow_invalid", "wizard-stage-code");
    }
  } else {
    if (blank(s.signatureCode)) {
      return issue("submit.validation.signature_required", "signature-editor");
    }
    if (!structureOnly && (s.signatureErrors === null || s.signatureErrors > 0)) {
      return issue("submit.validation.code_has_errors", "signature-editor");
    }
  }
  if (blank(s.metricCode)) return issue("submit.validation.metric_required", "metric-editor");
  if (!structureOnly && (s.metricErrors === null || s.metricErrors > 0)) {
    return issue("submit.validation.code_has_errors", "metric-editor");
  }
  if (!structureOnly && s.splitErrors !== null && s.splitErrors > 0) {
    return issue("submit.validation.split_too_small", "data-splits");
  }
  return null;
}

function optimizationIssue(s: StageSnapshot): WizardIssue | null {
  const issue = (key: MessageKey, fieldId?: string): WizardIssue => ({
    stage: "optimization",
    fieldId,
    key,
  });
  if (s.targetScore === "invalid") {
    return issue("submit.validation.target_score_invalid", "target-score");
  }
  if (s.targetScore === "requires_val") {
    return issue("submit.validation.target_score_requires_val", "target-score");
  }
  if (s.hasApiKey === false) return issue("submit.validation.api_key_required", "model-catalog");
  if (s.jobType === "run") {
    if (blank(s.modelName)) return issue("submit.validation.model_required", "model-catalog");
    if (blank(s.reflectionModelName)) {
      return issue("submit.validation.reflection_model_required", "model-catalog");
    }
  } else {
    if (s.generationModelNames.every(blank)) {
      return issue("submit.validation.generation_model_required", "model-catalog");
    }
    if (s.reflectionModelNames.every(blank)) {
      return issue("submit.validation.reflection_models_required", "model-catalog");
    }
  }
  // Mirrors the backend's `submission.vision_required` rejection so the
  // wizard fails fast instead of waiting for a 400 from /run.
  if (s.imageInputs.length > 0 && s.nonVisionModels.length > 0) {
    return {
      ...issue("submit.validation.vision_required", "model-catalog"),
      params: { fields: s.imageInputs.join(", "), model: s.nonVisionModels.join(", ") },
    };
  }
  return null;
}

function reviewIssue(s: StageSnapshot): WizardIssue | null {
  if (blank(s.username)) return { stage: "review", key: "submit.validation.username_required" };
  if (blank(s.jobName)) {
    return { stage: "review", fieldId: "job-name", key: "submit.validation.name_required" };
  }
  return null;
}

/**
 * The first problem on a stage, or null when it is complete. `structureOnly`
 * skips the checks that need server evidence (code and split checks), for
 * holding a forward move while that evidence may still be in flight or stale.
 */
export function stageIssue(
  stage: WizardStageId,
  s: StageSnapshot,
  structureOnly = false,
): WizardIssue | null {
  switch (stage) {
    case "goal":
      return goalIssue(s);
    case "evaluation":
      return evaluationIssue(s, structureOnly);
    case "optimization":
      return optimizationIssue(s);
    case "review":
      return reviewIssue(s);
  }
}
