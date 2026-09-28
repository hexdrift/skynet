import assert from "node:assert/strict";
import { test } from "node:test";

import { stageIssue, type StageSnapshot } from "./stage-issue.ts";
import { restoreTarget, stageAt } from "./wizard-steps.ts";

const complete: StageSnapshot = {
  username: "dana",
  jobName: "classifier",
  moduleSelectionRequired: false,
  datasetRowCount: 40,
  inputColumnCount: 1,
  outputColumnCount: 1,
  needsTools: false,
  mcpUrl: "",
  isWorkflow: false,
  workflowIssueCount: null,
  signatureCode: "class S(dspy.Signature): ...",
  signatureErrors: 0,
  metricCode: "def metric(example, pred): ...",
  metricErrors: 0,
  splitErrors: 0,
  targetScore: "ok",
  hasApiKey: true,
  jobType: "run",
  modelName: "gen",
  reflectionModelName: "reflect",
  generationModelNames: [],
  reflectionModelNames: [],
  imageInputs: [],
  nonVisionModels: [],
};

const snap = (patch: Partial<StageSnapshot>): StageSnapshot => ({ ...complete, ...patch });

test("a complete wizard has no issue on any stage", () => {
  for (const stage of ["goal", "evaluation", "optimization", "review"] as const) {
    assert.equal(stageIssue(stage, complete), null);
  }
});

test("Goal holds until a module is chosen", () => {
  const issue = stageIssue("goal", snap({ moduleSelectionRequired: true }));
  assert.equal(issue?.key, "submit.validation.module_required");
  assert.equal(issue?.stage, "goal");
});

test("Evaluation sends an unpicked module back to the picker", () => {
  const issue = stageIssue("evaluation", snap({ moduleSelectionRequired: true, datasetRowCount: 0 }));
  assert.equal(issue?.key, "submit.validation.module_required");
  assert.equal(issue?.fieldId, "module-selector");
});

test("Evaluation reports the dataset before the columns and the code", () => {
  const issue = stageIssue(
    "evaluation",
    snap({ datasetRowCount: 0, inputColumnCount: 0, signatureCode: "" }),
  );
  assert.deepEqual(issue, {
    stage: "evaluation",
    fieldId: "dataset-upload",
    key: "submit.validation.dataset_required",
  });
  assert.equal(
    stageIssue("evaluation", snap({ outputColumnCount: 0 }))?.key,
    "submit.validation.output_column_required",
  );
});

test("Evaluation asks for a tool endpoint only when the run uses tools", () => {
  assert.equal(stageIssue("evaluation", snap({ mcpUrl: "" })), null);
  assert.equal(
    stageIssue("evaluation", snap({ needsTools: true, mcpUrl: "  " }))?.fieldId,
    "react-config",
  );
});

test("a workflow run needs a clean graph instead of a signature", () => {
  const workflow = { isWorkflow: true, signatureCode: "" };
  assert.equal(stageIssue("evaluation", snap({ ...workflow, workflowIssueCount: 0 })), null);
  for (const workflowIssueCount of [null, 2]) {
    assert.equal(
      stageIssue("evaluation", snap({ ...workflow, workflowIssueCount }))?.key,
      "submit.validation.workflow_invalid",
    );
  }
});

test("structure-only checks skip server evidence but not missing code", () => {
  const unchecked = snap({ signatureErrors: null, metricErrors: 1, splitErrors: 3 });
  assert.equal(stageIssue("evaluation", unchecked)?.fieldId, "signature-editor");
  assert.equal(stageIssue("evaluation", unchecked, true), null);
  assert.equal(
    stageIssue("evaluation", snap({ metricCode: "" }), true)?.key,
    "submit.validation.metric_required",
  );
  assert.equal(
    stageIssue("evaluation", snap({ splitErrors: 2 }))?.key,
    "submit.validation.split_too_small",
  );
});

test("saved keys still loading do not hold Optimization", () => {
  assert.equal(stageIssue("optimization", snap({ hasApiKey: null })), null);
  assert.equal(
    stageIssue("optimization", snap({ hasApiKey: null, modelName: "" }))?.key,
    "submit.validation.model_required",
  );
});

test("a clone restored before the saved keys load opens on Review", () => {
  const cloned = snap({ hasApiKey: null, signatureErrors: null, metricErrors: null });
  assert.deepEqual(
    restoreTarget("review", "review", (i) => stageIssue(stageAt(i), cloned, true) === null),
    { open: 3, reachable: 3 },
  );
});

test("Optimization checks the target score, keys, models and vision in order", () => {
  assert.equal(
    stageIssue("optimization", snap({ targetScore: "requires_val", hasApiKey: false }))?.key,
    "submit.validation.target_score_requires_val",
  );
  assert.equal(
    stageIssue("optimization", snap({ hasApiKey: false, modelName: "" }))?.key,
    "submit.validation.api_key_required",
  );
  assert.equal(
    stageIssue("optimization", snap({ reflectionModelName: " " }))?.key,
    "submit.validation.reflection_model_required",
  );
  assert.equal(
    stageIssue(
      "optimization",
      snap({ jobType: "grid_search", generationModelNames: ["a"], reflectionModelNames: [""] }),
    )?.key,
    "submit.validation.reflection_models_required",
  );
  const vision = stageIssue(
    "optimization",
    snap({ imageInputs: ["photo"], nonVisionModels: ["gen"] }),
    true,
  );
  assert.equal(vision?.key, "submit.validation.vision_required");
  assert.deepEqual(vision?.params, { fields: "photo", model: "gen" });
});

test("Review holds on the optimization name and points at its field", () => {
  assert.deepEqual(stageIssue("review", snap({ jobName: "" })), {
    stage: "review",
    fieldId: "job-name",
    key: "submit.validation.name_required",
  });
  assert.equal(
    stageIssue("review", snap({ username: "" }))?.key,
    "submit.validation.username_required",
  );
});
