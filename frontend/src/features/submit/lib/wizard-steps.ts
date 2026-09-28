/**
 * Stage model of the submission wizard.
 *
 * The wizard walks four stages: Goal, Evaluation, Optimization, Review. Stage
 * IDs are the identity used by saved drafts, validation destinations, tutorial
 * targets and the stepper; the numeric position is derived from the order for
 * display and the slide direction only.
 */
export type WizardStageId = "goal" | "evaluation" | "optimization" | "review";

export const WIZARD_STAGE_ORDER: readonly WizardStageId[] = [
  "goal",
  "evaluation",
  "optimization",
  "review",
];

export const LAST_WIZARD_STAGE = WIZARD_STAGE_ORDER.length - 1;

/** Position of each stage — the `step` index the hook animates and validates by. */
export const WIZARD_STAGE: Readonly<Record<WizardStageId, number>> = {
  goal: 0,
  evaluation: 1,
  optimization: 2,
  review: 3,
};

export function isWizardStageId(value: unknown): value is WizardStageId {
  return typeof value === "string" && (WIZARD_STAGE_ORDER as readonly string[]).includes(value);
}

function clampIndex(index: number, last: number): number {
  if (!Number.isFinite(index)) return 0;
  return Math.min(Math.max(Math.trunc(index), 0), last);
}

/** Stage at a numeric position; out-of-range positions clamp to the nearest end. */
export function stageAt(index: number): WizardStageId {
  return WIZARD_STAGE_ORDER[clampIndex(index, LAST_WIZARD_STAGE)] ?? "goal";
}

/**
 * The six-step layout the wizard used before the stage model. Kept only so a
 * draft stashed by that layout restores into the stage that now owns its
 * content; nothing renders from it.
 */
export type LegacyWizardStepId = "basics" | "data" | "params" | "code" | "model" | "review";

export const LEGACY_STEP_ORDER: readonly LegacyWizardStepId[] = [
  "basics",
  "data",
  "params",
  "code",
  "model",
  "review",
];

// The old code step also held the module picker; a draft with no module
// chosen is sent back to Goal by the restore walk, not by this table.
export const LEGACY_STEP_STAGE: Readonly<Record<LegacyWizardStepId, WizardStageId>> = {
  basics: "review",
  data: "evaluation",
  params: "optimization",
  code: "evaluation",
  model: "optimization",
  review: "review",
};

/** The stage that now owns the content of a legacy step index. */
export function migrateLegacyStep(index: number): WizardStageId {
  const id = LEGACY_STEP_ORDER[clampIndex(index, LEGACY_STEP_ORDER.length - 1)] ?? "basics";
  return LEGACY_STEP_STAGE[id];
}

/**
 * The furthest stage a legacy draft has earned. Basics moved from the front
 * of the flow to Review, so having seen it unlocks nothing — otherwise every
 * old draft would open with Review reachable.
 */
export function migrateLegacyFurthest(index: number): WizardStageId {
  const reached = LEGACY_STEP_ORDER.slice(
    0,
    clampIndex(index, LEGACY_STEP_ORDER.length - 1) + 1,
  ).filter((id) => id !== "basics");
  const furthest = Math.max(0, ...reached.map((id) => WIZARD_STAGE[LEGACY_STEP_STAGE[id]]));
  return WIZARD_STAGE_ORDER[furthest] ?? "goal";
}

/**
 * Where a restored draft opens. Every stage before the saved furthest one is
 * re-checked: the first incomplete stage caps both the stage that opens and
 * how far the stepper lets the user jump, so a draft never lands past a
 * problem it can no longer see.
 */
export function restoreTarget(
  saved: WizardStageId,
  furthest: WizardStageId,
  isComplete: (index: number) => boolean,
): { open: number; reachable: number } {
  let open = WIZARD_STAGE[saved];
  let reachable = Math.max(WIZARD_STAGE[furthest], open);
  for (let i = 0; i < reachable; i++) {
    if (!isComplete(i)) {
      open = Math.min(open, i);
      reachable = i;
      break;
    }
  }
  return { open, reachable };
}
