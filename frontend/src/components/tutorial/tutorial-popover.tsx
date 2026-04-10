"use client";

import { motion } from "framer-motion";
import * as React from "react";
import { ArrowLeft, ArrowRight, X, Play, Pause } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TutorialStep } from "@/lib/tutorial-steps";

interface TutorialPopoverProps {
  step: TutorialStep;
  stepNumber: number;
  totalSteps: number;
  position: { top: number; left: number; placement: "top" | "bottom" | "left" | "right" };
  onNext: () => void;
  onPrev: () => void;
  onExit: () => void;
  isFirst: boolean;
  isLast: boolean;
  isAutoPlaying: boolean;
  onToggleAutoPlay: () => void;
}

export function TutorialPopover({
  step,
  stepNumber,
  totalSteps,
  position,
  onNext,
  onPrev,
  onExit,
  isFirst,
  isLast,
  isAutoPlaying,
  onToggleAutoPlay,
}: TutorialPopoverProps) {
  const arrowClasses = React.useMemo(() => {
    const base = "absolute w-3 h-3 bg-[#FAF8F5] rotate-45 border-[#E5DDD4]";
    switch (position.placement) {
      case "top":
        return cn(base, "bottom-[-7px] start-1/2 -translate-x-1/2 border-b border-e");
      case "bottom":
        return cn(base, "top-[-7px] start-1/2 -translate-x-1/2 border-t border-s");
      case "left":
        return cn(base, "end-[-7px] top-1/2 -translate-y-1/2 border-t border-e");
      case "right":
        return cn(base, "start-[-7px] top-1/2 -translate-y-1/2 border-b border-s");
      default:
        return base;
    }
  }, [position.placement]);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.12, ease: "easeOut" }}
      className="fixed z-[9999] pointer-events-auto"
      style={{ top: position.top, left: position.left }}
      dir="rtl"
    >
      <div className="relative w-[min(90vw,360px)] rounded-2xl border border-[#E5DDD4] bg-gradient-to-b from-[#FAF8F5] to-[#F5F1EC] shadow-[0_8px_32px_rgba(28,22,18,0.14)] overflow-hidden">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 px-5 pt-4 pb-2">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-bold text-[#3D2E22] leading-tight">{step.title}</h3>
            <div className="flex items-center gap-1.5 mt-0.5">
              <p className="text-[10px] font-medium text-[#8C7A6B]/70 tabular-nums">
                {stepNumber} מתוך {totalSteps}
              </p>
              <button
                type="button"
                onClick={onToggleAutoPlay}
                className="p-0.5 rounded hover:bg-[#E5DDD4]/60 text-[#8C7A6B] hover:text-[#3D2E22] transition-colors cursor-pointer"
                aria-label={isAutoPlaying ? "השהה" : "נגן אוטומטי"}
                title={isAutoPlaying ? "השהה" : "נגן אוטומטי"}
              >
                {isAutoPlaying ? <Pause className="size-2.5" /> : <Play className="size-2.5" />}
              </button>
            </div>
          </div>
          <button
            type="button"
            onClick={onExit}
            className="shrink-0 p-1 rounded-lg hover:bg-[#E5DDD4]/60 text-[#8C7A6B] hover:text-[#3D2E22] transition-colors cursor-pointer"
            aria-label="סגור מדריך"
          >
            <X className="size-3.5" />
          </button>
        </div>

        {/* Description */}
        <div className="px-5 pb-3">
          <p className="text-xs text-[#3D2E22]/75 leading-relaxed">{step.description}</p>
        </div>

        {/* Progress */}
        <div className="px-5 pb-3">
          <div className="h-1 bg-[#E5DDD4]/50 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-[#3D2E22] rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${(stepNumber / totalSteps) * 100}%` }}
              transition={{ duration: 0.35, ease: [0.2, 0.8, 0.2, 1] }}
            />
          </div>
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between gap-2 px-5 pb-4">
          <button
            type="button"
            onClick={onPrev}
            disabled={isFirst}
            className={cn(
              "flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-[#3D2E22] text-[#FAF8F5] hover:bg-[#2C2018] transition-colors cursor-pointer",
              isFirst && "invisible"
            )}
          >
            <ArrowRight className="size-3" />
            הקודם
          </button>

          <button
            type="button"
            onClick={onNext}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-[#3D2E22] text-[#FAF8F5] hover:bg-[#2C2018] transition-colors cursor-pointer"
          >
            {isLast ? "סיום" : "הבא"}
            {!isLast && <ArrowLeft className="size-3" />}
          </button>
        </div>

        {/* Auto-play countdown bar */}
        {isAutoPlaying && (
          <motion.div
            className="absolute bottom-0 inset-x-0 h-[2px] bg-[#3D2E22]/30 origin-right"
            initial={{ scaleX: 1 }}
            animate={{ scaleX: 0 }}
            transition={{ duration: step.readingTimeSec ?? 10, ease: "linear" }}
          />
        )}
      </div>
    </motion.div>
  );
}
