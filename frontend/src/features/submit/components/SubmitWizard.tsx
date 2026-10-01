"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";

import { msg } from "@/shared/lib/messages";
import { registerTutorialHook } from "@/features/tutorial";

import { useSubmitWizard } from "../hooks/use-submit-wizard";
import { slideVariants, emptyModelConfig } from "../constants";
import { focusField } from "../lib/focus-field";
import { WIZARD_STAGE, stageAt, type WizardStageId } from "../lib/wizard-steps";
import { SubmitStepper } from "./SubmitStepper";
import { SubmitNav } from "./SubmitNav";
import { SubmitSplash } from "./SubmitSplash";
import { WizardSubsteps } from "./WizardSubsteps";
import { ModelConfigModal } from "./ModelConfigModal";
import { BasicsStep } from "./steps/BasicsStep";
import { DatasetStep } from "./steps/DatasetStep";
import { ModelStep } from "./steps/ModelStep";
import { CodeStep } from "./steps/CodeStep";
import { ParamsStep } from "./steps/ParamsStep";
import { SplitSection } from "./steps/SplitSection";
import { SummaryStep } from "./steps/SummaryStep";

const EVALUATION_STEPS = ["dataset", "code", "split"] as const;
const OPTIMIZATION_STEPS = ["parameters", "models"] as const;
const REVIEW_STEPS = ["details", "summary"] as const;
const CODE_FIELDS = new Set([
  "code-editors",
  "signature-editor",
  "metric-editor",
  "react-config",
  "wizard-stage-code",
]);

/** The evaluation substep that holds a field, so a problem opens where it is fixed. */
function evaluationPartFor(field?: string): number | null {
  if (!field) return null;
  if (CODE_FIELDS.has(field)) return 1;
  if (field === "data-splits") return 2;
  return 0;
}

export function SubmitWizard() {
  const w = useSubmitWizard();
  const [evaluationPart, setEvaluationPart] = useState(0);
  const [optimizationPart, setOptimizationPart] = useState(0);
  const [reviewPart, setReviewPart] = useState(0);

  const routeSubstep = useCallback((stage: WizardStageId, field?: string) => {
    if (stage === "evaluation") {
      const part = evaluationPartFor(field);
      if (part != null) setEvaluationPart(part);
    }
    if (stage === "optimization") setOptimizationPart(field === "model-catalog" ? 1 : 0);
    if (stage === "review") setReviewPart(field === "wizard-stage-review" ? 1 : 0);
  }, []);
  useEffect(() => registerTutorialHook("showWizardSubstep", routeSubstep), [routeSubstep]);
  // A reported problem opens the substep that holds its field and lands focus there.
  useEffect(() => {
    if (!w.focusRequest) return;
    routeSubstep(w.focusRequest.stage, w.focusRequest.fieldId);
    focusField(w.focusRequest.fieldId);
  }, [w.focusRequest, routeSubstep]);

  const evaluationPanels: readonly ReactNode[] = [
    <DatasetStep key="dataset" w={w} />,
    <CodeStep key="code" w={w} part="code" />,
    <SplitSection key="split" w={w} />,
  ];
  const optimizationPanels: readonly ReactNode[] = [
    <ParamsStep key="parameters" w={w} />,
    <ModelStep key="models" w={w} />,
  ];

  const stageViews: Record<WizardStageId, ReactNode> = {
    goal: <CodeStep w={w} part="module" />,
    evaluation: (
      <WizardSubsteps
        active={evaluationPart}
        ariaLabel={msg("submit.stage.evaluation")}
        steps={EVALUATION_STEPS}
      >
        {evaluationPanels[evaluationPart]}
      </WizardSubsteps>
    ),
    optimization: (
      <WizardSubsteps
        active={optimizationPart}
        ariaLabel={msg("submit.stage.optimization")}
        steps={OPTIMIZATION_STEPS}
      >
        {optimizationPanels[optimizationPart]}
      </WizardSubsteps>
    ),
    review: (
      <WizardSubsteps
        active={reviewPart}
        ariaLabel={msg("submit.stage.review")}
        steps={REVIEW_STEPS}
      >
        {reviewPart === 0 ? <BasicsStep w={w} /> : <SummaryStep w={w} />}
      </WizardSubsteps>
    ),
  };

  const onBack = () => {
    if (w.step === WIZARD_STAGE.evaluation && evaluationPart > 0) {
      setEvaluationPart((current) => current - 1);
      return;
    }
    if (w.step === WIZARD_STAGE.optimization && optimizationPart > 0) {
      setOptimizationPart((current) => current - 1);
      return;
    }
    if (w.step === WIZARD_STAGE.review && reviewPart > 0) {
      setReviewPart((current) => current - 1);
      return;
    }
    if (w.step === WIZARD_STAGE.review) setOptimizationPart(OPTIMIZATION_STEPS.length - 1);
    w.goPrev();
  };
  const onNext = async () => {
    if (w.step === WIZARD_STAGE.evaluation && evaluationPart < EVALUATION_STEPS.length - 1) {
      setEvaluationPart((current) => current + 1);
      return;
    }
    if (w.step === WIZARD_STAGE.optimization && optimizationPart < OPTIMIZATION_STEPS.length - 1) {
      setOptimizationPart((current) => current + 1);
      return;
    }
    if (w.step === WIZARD_STAGE.review && reviewPart < REVIEW_STEPS.length - 1) {
      setReviewPart((current) => current + 1);
      return;
    }
    await w.handleNext();
  };
  // Submit replaces the nav only on the summary, the last page of the wizard.
  const showSubmit = w.step === WIZARD_STAGE.review && reviewPart === REVIEW_STEPS.length - 1;

  // The code substep widens for its two-pane layout in auto mode; the other
  // substeps keep the regular column.
  const containerWidthClass =
    w.step === WIZARD_STAGE.evaluation && evaluationPart === 1 && w.codeAssistMode === "auto"
      ? "max-w-5xl"
      : "max-w-2xl";

  return (
    <div
      className={`mx-auto w-full min-w-0 space-y-4 pb-6 transition-[max-width] duration-300 md:-mt-4 md:space-y-6 md:pb-8 ${containerWidthClass}`}
    >
      <SubmitStepper w={w} />

      <div className="relative overflow-hidden pt-[10px]" data-tutorial="submit-wizard">
        <AnimatePresence mode="wait" custom={w.direction}>
          <motion.div
            key={w.step}
            custom={w.direction}
            variants={slideVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.1 }}
          >
            {stageViews[stageAt(w.step)]}
          </motion.div>
        </AnimatePresence>
      </div>

      <SubmitNav w={w} onBack={onBack} onNext={onNext} showSubmit={showSubmit} />

      {/* Model config modal — shared by every model chip AND the workflow
          canvas's dry-run "pick a model in place" flow, so it mounts at the
          wizard root rather than inside the model step. */}
      <ModelConfigModal
        open={!!w.editingModel}
        onOpenChange={(open) => {
          if (!open) w.setEditingModel(null);
        }}
        config={w.editingModel?.config ?? emptyModelConfig()}
        onSave={(c) => {
          w.editingModel?.onSave(c);
          w.saveToRecent(c);
          w.setEditingModel(null);
        }}
        roleLabel={w.editingModel?.label ?? msg("model.generation.label")}
        recentConfigs={w.recentConfigs}
        onRemoveRecent={w.removeRecentConfig}
      />

      {/* Submit splash overlay — portal to body so it covers sidebar + header */}
      <SubmitSplash w={w} />
    </div>
  );
}
