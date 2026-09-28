"use client";

import type { ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";

import { msg } from "@/shared/lib/messages";

import { useSubmitWizard } from "../hooks/use-submit-wizard";
import { slideVariants, emptyModelConfig } from "../constants";
import { WIZARD_STAGE, stageAt, type WizardStageId } from "../lib/wizard-steps";
import { SubmitStepper } from "./SubmitStepper";
import { SubmitNav } from "./SubmitNav";
import { SubmitSplash } from "./SubmitSplash";
import { ModelConfigModal } from "./ModelConfigModal";
import { BasicsStep } from "./steps/BasicsStep";
import { DatasetStep } from "./steps/DatasetStep";
import { ModelStep } from "./steps/ModelStep";
import { CodeStep } from "./steps/CodeStep";
import { ParamsStep } from "./steps/ParamsStep";
import { SplitSection } from "./steps/SplitSection";
import { SummaryStep } from "./steps/SummaryStep";

export function SubmitWizard() {
  const w = useSubmitWizard();

  // The Evaluation stage widens for the two-pane code section in auto mode;
  // its other sections keep the regular column so they don't stretch with it.
  const stageViews: Record<WizardStageId, ReactNode> = {
    goal: <CodeStep w={w} part="module" />,
    evaluation: (
      <div className="space-y-4 md:space-y-6">
        <div className="mx-auto w-full max-w-2xl">
          <DatasetStep w={w} />
        </div>
        <CodeStep w={w} part="code" />
        <div className="mx-auto w-full max-w-2xl">
          <SplitSection w={w} />
        </div>
      </div>
    ),
    optimization: (
      <div className="space-y-4 md:space-y-6">
        <ParamsStep w={w} />
        <ModelStep w={w} />
      </div>
    ),
    review: (
      <div className="space-y-4 md:space-y-6">
        <BasicsStep w={w} />
        <SummaryStep w={w} />
      </div>
    ),
  };

  const containerWidthClass =
    w.step === WIZARD_STAGE.evaluation && w.codeAssistMode === "auto" ? "max-w-5xl" : "max-w-2xl";

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

      <SubmitNav w={w} />

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
