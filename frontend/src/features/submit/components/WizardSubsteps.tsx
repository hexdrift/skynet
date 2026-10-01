"use client";

import type { ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

interface WizardSubstepsProps {
  active: number;
  ariaLabel: string;
  children: ReactNode;
  /** Substep ids in order; the panel re-enters when the active one changes. */
  steps: readonly string[];
}

/**
 * Present one compact decision at a time inside a top-level wizard stage.
 * Back and Continue are the only way between substeps, so the panel gets the
 * stage's whole width with nothing above it.
 */
export function WizardSubsteps({ active, ariaLabel, children, steps }: WizardSubstepsProps) {
  const reducedMotion = useReducedMotion();
  const current = steps[active] ?? steps[0] ?? "current";

  return (
    <section aria-label={ariaLabel}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={current}
          className="scroll-mt-24 outline-none"
          initial={reducedMotion ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reducedMotion ? undefined : { opacity: 0, y: -4 }}
          transition={{ duration: reducedMotion ? 0 : 0.14 }}
        >
          {children}
        </motion.div>
      </AnimatePresence>
    </section>
  );
}
