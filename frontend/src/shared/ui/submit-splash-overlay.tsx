"use client";

import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";

import { AnimatedWordmark } from "@/shared/ui/animated-wordmark";

/**
 * Hold (ms) the splash stays up before routing to the new optimization.
 * Mirrors the manual wizard submit so the agent-driven submit feels identical.
 */
export const SUBMIT_SPLASH_HOLD_MS = 1500;

/**
 * Full-screen submit splash: the animated wordmark over the warm canvas that
 * plays while an optimization submission settles and the app routes to the new
 * job. Shared by the manual wizard submit (``SubmitSplash``) and the
 * agent-panel auto-submit so both paths render the identical banner.
 */
export function SubmitSplashOverlay({ show }: { show: boolean }) {
  if (typeof document === "undefined") return null;

  return createPortal(
    <AnimatePresence>
      {show && (
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
