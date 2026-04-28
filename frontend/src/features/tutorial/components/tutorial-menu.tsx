"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, GraduationCap } from "lucide-react";
import { useTutorialContext } from "./tutorial-provider";
import { msg } from "@/shared/lib/messages";

export function TutorialMenu() {
  const { state, startTrack, closeMenu } = useTutorialContext();

  if (!state.isMenuOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4" dir="rtl">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="absolute inset-0 bg-[#1C1612]/50 backdrop-blur-sm"
          onClick={closeMenu}
        />

        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 12 }}
          transition={{ duration: 0.25, ease: [0.2, 0.8, 0.2, 1] }}
          className="relative w-full max-w-xs rounded-2xl border border-[#E5DDD4] bg-gradient-to-b from-[#FAF8F5] to-[#F5F1EC] shadow-[0_16px_48px_rgba(28,22,18,0.18)] overflow-hidden"
        >
          <button
            type="button"
            onClick={closeMenu}
            className="absolute top-3.5 end-3.5 z-10 p-1.5 rounded-lg hover:bg-[#E5DDD4]/60 text-[#8C7A6B] hover:text-[#3D2E22] transition-colors cursor-pointer"
            aria-label={msg("auto.features.tutorial.components.tutorial.menu.literal.1")}
          >
            <X className="size-4" />
          </button>

          <div className="flex flex-col items-center px-6 pt-7 pb-6 text-center">
            <div className="size-12 rounded-xl bg-[#F0EBE4] flex items-center justify-center mb-4">
              <GraduationCap className="size-6 text-[#8C7A6B]" />
            </div>
            <h2 className="text-lg font-bold text-[#3D2E22] mb-1">
              {msg("auto.features.tutorial.components.tutorial.menu.1")}
            </h2>
            <p className="text-xs text-[#8C7A6B] leading-relaxed mb-5">
              {msg("auto.features.tutorial.components.tutorial.menu.2")}
            </p>
            <button
              type="button"
              onClick={() => startTrack("deep-dive")}
              className="w-full px-5 py-2.5 rounded-xl text-sm font-semibold bg-[#3D2E22] text-[#FAF8F5] hover:bg-[#2C2018] transition-colors cursor-pointer"
            >
              {msg("auto.features.tutorial.components.tutorial.menu.3")}
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
