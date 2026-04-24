"use client";

import { ChevronLeft, ChevronRight, ChevronDown, Loader2 } from "lucide-react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { TERMS } from "@/shared/lib/terms";

import { STEPS } from "../constants";
import type { SubmitWizardContext } from "../hooks/use-submit-wizard";

export function SubmitNav({ w }: { w: SubmitWizardContext }) {
  const { step, goPrev, handleNext, handleSubmit, submitting } = w;

  if (step < STEPS.length - 1) {
    return (
      <div className="flex items-center justify-between">
        <Button variant="outline" onClick={goPrev} disabled={step === 0} className="gap-2">
          <ChevronRight className="h-4 w-4" />
          הקודם
        </Button>
        <span className="text-xs text-muted-foreground tabular-nums">
          {step + 1} / {STEPS.length}
        </span>
        <Button onClick={handleNext} className="gap-2" data-tutorial="wizard-next">
          הבא
          <ChevronLeft className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  return (
    <motion.button
      type="button"
      onClick={handleSubmit}
      disabled={submitting}
      data-tutorial="submit-button"
      animate={{ scale: [1, 1.01, 1] }}
      transition={{ repeat: Infinity, duration: 3, ease: "easeInOut" }}
      className="group relative w-full rounded-2xl bg-primary text-primary-foreground font-semibold text-base pt-5 pb-7 cursor-pointer transition-all duration-300 hover:shadow-[0_0_30px_rgba(61,46,34,0.35)] hover:scale-[1.01] active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
    >
      {submitting ? (
        <span className="flex items-center justify-center gap-2">
          <Loader2 className="size-5 animate-spin" />
          שולח...
        </span>
      ) : (
        <div className="flex flex-col items-center gap-4">
          <span>שלח {TERMS.optimization}</span>
          <div className="flex flex-col items-center -space-y-7 h-0 overflow-visible opacity-70 group-hover:opacity-100 transition-opacity duration-200 [&>svg]:animate-[cascadeDown_1s_ease-in-out_infinite] group-hover:[&>svg]:animate-[cascadeDownHyper_0.5s_ease-out_infinite]">
            <ChevronDown className="size-10 [animation-delay:0s] group-hover:[animation-delay:0s]" />
            <ChevronDown className="size-10 [animation-delay:0.15s] group-hover:[animation-delay:0.08s]" />
            <ChevronDown className="size-10 [animation-delay:0.3s] group-hover:[animation-delay:0.16s]" />
          </div>
        </div>
      )}
    </motion.button>
  );
}
