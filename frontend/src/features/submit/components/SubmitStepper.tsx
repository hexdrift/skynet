"use client";

import { WizardStepper } from "@/shared/ui/wizard-stepper";

import { WIZARD_STAGES } from "../constants";
import type { SubmitWizardContext } from "../hooks/use-submit-wizard";

export function SubmitStepper({ w }: { w: SubmitWizardContext }) {
  const { step, maxReachableStep, validateStep, handleTabClick } = w;

  return (
    <WizardStepper
      steps={WIZARD_STAGES.map((s) => ({ id: s.id, label: s.label() }))}
      step={step}
      maxReachableStep={maxReachableStep}
      validateStep={validateStep}
      onSelect={handleTabClick}
      tutorial="wizard-stepper"
    />
  );
}
