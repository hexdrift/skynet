"use client";

import { SubmitSplashOverlay } from "@/shared/ui/submit-splash-overlay";

import type { SubmitWizardContext } from "../hooks/use-submit-wizard";

export function SubmitSplash({ w }: { w: SubmitWizardContext }) {
  return <SubmitSplashOverlay show={w.submitPhase === "splash" || w.submitPhase === "done"} />;
}
