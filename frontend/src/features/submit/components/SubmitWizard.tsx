"use client";

import { ChevronLeft } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

import { useSubmitWizard } from "../hooks/use-submit-wizard";
import { slideVariants } from "../constants";
import { SubmitStepper } from "./SubmitStepper";
import { SubmitNav } from "./SubmitNav";
import { SubmitSplash } from "./SubmitSplash";
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
    <ModelStep key="model" w={w} />,
    <CodeStep key="code" w={w} />,
    <ParamsStep key="params" w={w} />,
    <SummaryStep key="review" w={w} />,
  ];

  return (
    <div className="space-y-6 max-w-2xl mx-auto pb-8">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <a href="/" className="hover:text-foreground transition-colors">
          לוח בקרה
        </a>
        <ChevronLeft className="h-3 w-3" />
        <span className="text-foreground font-medium">אופטימיזציה חדשה</span>
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
    </div>
  );
}
