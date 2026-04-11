"use client";

import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { AnimatedWordmark } from "@/shared/ui/animated-wordmark";

import type { SubmitWizardContext } from "../hooks/use-submit-wizard";

export function SubmitSplash({ w }: { w: SubmitWizardContext }) {
  if (typeof document === "undefined") return null;

  return createPortal(
    <AnimatePresence>
      {(w.submitPhase === "splash" || w.submitPhase === "done") && (
        <motion.div
          className="fixed inset-0 z-[99999] flex items-center justify-center"
          style={{ backgroundColor: "#F0EBE4" }}
          initial={{ y: "-100%" }}
          animate={{ y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        >
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.3, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          >
            <AnimatedWordmark size={64} autoMorph morphSpeed={120} />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
