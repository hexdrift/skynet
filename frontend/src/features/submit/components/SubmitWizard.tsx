"use client";

import { ChevronLeft } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { TERMS } from "@/shared/lib/terms";
import { msg } from "@/shared/lib/messages";

import { useSubmitWizard } from "../hooks/use-submit-wizard";
import { slideVariants } from "../constants";
import { SubmitStepper } from "./SubmitStepper";
import { SubmitNav } from "./SubmitNav";
import { SubmitSplash } from "./SubmitSplash";
import { WizardRecommendationCard } from "./WizardRecommendationCard";
import { BasicsStep } from "./steps/BasicsStep";
import { DatasetStep } from "./steps/DatasetStep";
import { ModelStep } from "./steps/ModelStep";
import { CodeStep } from "./steps/CodeStep";
import { ParamsStep } from "./steps/ParamsStep";
import { SummaryStep } from "./steps/SummaryStep";

export function SubmitWizard() {
  const w = useSubmitWizard();

  const steps = [
    <BasicsStep key="basics" w={w} />,
    <DatasetStep key="data" w={w} />,
    <ParamsStep key="params" w={w} />,
    <CodeStep key="code" w={w} />,
    <ModelStep key="model" w={w} />,
    <SummaryStep key="review" w={w} />,
  ];

  // Code step (index 3) renders a two-pane layout with an agent side-panel
  // in auto mode, so it needs more horizontal room than the other steps.
  const isCodeStep = w.step === 3;
  const containerWidthClass = isCodeStep && w.codeAssistMode === "auto" ? "max-w-5xl" : "max-w-2xl";

  return (
    <div
      className={`space-y-6 ${containerWidthClass} mx-auto pb-8 transition-[max-width] duration-300`}
    >
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link href="/" className="hover:text-foreground transition-colors">
          {msg("auto.features.submit.components.submitwizard.1")}
        </Link>
        <ChevronLeft className="h-3 w-3" />
        <span className="text-foreground font-medium">{TERMS.notificationNewOpt}</span>
      </div>

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
            {steps[w.step]}
          </motion.div>
        </AnimatePresence>
      </div>

      <SubmitNav w={w} />

      {/* Submit splash overlay — portal to body so it covers sidebar + header */}
      <SubmitSplash w={w} />

      {/* Only renders once the user has drafted a signature in the code step. */}
      <WizardRecommendationCard w={w} />
    </div>
  );
}
