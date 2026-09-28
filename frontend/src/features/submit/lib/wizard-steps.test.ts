import assert from "node:assert/strict";
import { test } from "node:test";

import {
  LAST_WIZARD_STAGE,
  LEGACY_STEP_ORDER,
  LEGACY_STEP_STAGE,
  WIZARD_STAGE,
  WIZARD_STAGE_ORDER,
  isWizardStageId,
  migrateLegacyFurthest,
  migrateLegacyStep,
  restoreTarget,
  stageAt,
} from "./wizard-steps.ts";

test("the four stages run Goal → Evaluation → Optimization → Review", () => {
  assert.deepEqual(WIZARD_STAGE_ORDER, ["goal", "evaluation", "optimization", "review"]);
  assert.equal(LAST_WIZARD_STAGE, 3);
});

test("stage positions round-trip through the order", () => {
  for (const [id, index] of Object.entries(WIZARD_STAGE)) {
    assert.equal(WIZARD_STAGE_ORDER[index], id);
    assert.equal(stageAt(index), id);
  }
});

test("stageAt clamps positions outside the flow", () => {
  assert.equal(stageAt(-1), "goal");
  assert.equal(stageAt(99), "review");
  assert.equal(stageAt(Number.NaN), "goal");
  assert.equal(stageAt(1.7), "evaluation");
});

test("isWizardStageId accepts stage ids only", () => {
  for (const id of WIZARD_STAGE_ORDER) assert.ok(isWizardStageId(id));
  assert.equal(isWizardStageId("basics"), false);
  assert.equal(isWizardStageId(1), false);
  assert.equal(isWizardStageId(undefined), false);
});

test("legacy steps migrate to the stage that owns their content", () => {
  assert.deepEqual(LEGACY_STEP_ORDER, ["basics", "data", "params", "code", "model", "review"]);
  LEGACY_STEP_ORDER.forEach((id, index) => {
    assert.equal(migrateLegacyStep(index), LEGACY_STEP_STAGE[id]);
  });
  assert.equal(migrateLegacyStep(1), "evaluation");
  assert.equal(migrateLegacyStep(3), "evaluation");
  assert.equal(migrateLegacyStep(4), "optimization");
  assert.equal(migrateLegacyStep(-3), LEGACY_STEP_STAGE.basics);
  assert.equal(migrateLegacyStep(42), "review");
});

test("a legacy furthest step never unlocks Review through Basics alone", () => {
  assert.equal(migrateLegacyFurthest(0), "goal");
  assert.equal(migrateLegacyFurthest(1), "evaluation");
  assert.equal(migrateLegacyFurthest(2), "optimization");
  assert.equal(migrateLegacyFurthest(3), "optimization");
  assert.equal(migrateLegacyFurthest(4), "optimization");
  assert.equal(migrateLegacyFurthest(5), "review");
  assert.equal(migrateLegacyFurthest(99), "review");
});

test("a restored draft reopens where it was when every earlier stage still holds", () => {
  assert.deepEqual(
    restoreTarget("optimization", "review", () => true),
    { open: 2, reachable: 3 },
  );
});

test("a restored draft opens on the first stage that no longer holds", () => {
  const incomplete = new Set([1]);
  assert.deepEqual(
    restoreTarget("review", "review", (i) => !incomplete.has(i)),
    { open: 1, reachable: 1 },
  );
  assert.deepEqual(
    restoreTarget("goal", "optimization", (i) => i !== 0),
    { open: 0, reachable: 0 },
  );
});

test("a restore never checks the saved furthest stage itself", () => {
  const checked: number[] = [];
  restoreTarget("evaluation", "optimization", (i) => {
    checked.push(i);
    return true;
  });
  assert.deepEqual(checked, [0, 1]);
});
