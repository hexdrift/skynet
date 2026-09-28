"use client";

import { useCallback, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { useWizardStateOptional } from "@/features/agent-panel";
import { useTutorialContext } from "@/features/tutorial";

import { useWizardDraftController, WizardDraftsProvider } from "../hooks/use-wizard-drafts";
import { SubmitWizard } from "./SubmitWizard";

/**
 * The `/submit` entry: owns the durable draft and remounts the wizard when
 * the user continues a saved setup, so the wizard hydrates once from the
 * chosen snapshot instead of patching a live form.
 */
export function SubmitEntry() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const wizardCtx = useWizardStateOptional();
  const tutorial = useTutorialContext();
  const [wizardKey, setWizardKey] = useState(0);

  const remount = useCallback(() => {
    wizardCtx?.reset();
    setWizardKey((k) => k + 1);
  }, [wizardCtx]);

  const onContinue = useCallback(() => {
    remount();
    // A leftover query (a staged dataset, say) would re-apply over the draft.
    if (searchParams.size > 0) router.replace("/submit");
  }, [remount, router, searchParams]);

  const { api } = useWizardDraftController({
    cloning: Boolean(searchParams.get("clone") || searchParams.get("shareToken")),
    suspended: tutorial.state.isVisible && tutorial.state.activeTrack !== null,
    onContinue,
  });

  return (
    <WizardDraftsProvider api={api}>
      <SubmitWizard key={wizardKey} />
    </WizardDraftsProvider>
  );
}
