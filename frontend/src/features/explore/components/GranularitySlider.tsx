"use client";

import * as React from "react";
import { formatMsg, msg } from "@/shared/lib/messages";

interface GranularitySliderProps {
  value: number;
  onChange: (next: number) => void;
  // Cluster count at each slider stop, e.g. [2, 4, 8, 16, 32]. Length
  // determines the slider's range.
  levels: number[];
}

export function GranularitySlider({ value, onChange, levels }: GranularitySliderProps) {
  if (levels.length < 2) return null;

  const max = levels.length - 1;
  const clamped = Math.max(0, Math.min(max, value));
  const currentCount = levels[clamped] ?? 0;
  const ariaLabel = formatMsg("explore.granularity.aria", {
    p1: levels[0] ?? 0,
    p2: levels[max] ?? 0,
  });
  const currentText = formatMsg("explore.granularity.value", { p1: currentCount });

  return (
    <div
      dir="rtl"
      className="pointer-events-auto absolute bottom-3 left-1/2 z-20 flex -translate-x-1/2 items-center gap-3 rounded-lg border border-border/70 bg-background/90 px-3 py-2 shadow-sm backdrop-blur-sm"
    >
      <span className="text-[0.6875rem] font-medium text-muted-foreground">
        {msg("explore.granularity.label")}
      </span>
      <input
        type="range"
        min={0}
        max={max}
        step={1}
        value={clamped}
        onChange={(e) => onChange(parseInt(e.target.value, 10))}
        aria-label={ariaLabel}
        aria-valuetext={currentText}
        className="h-2 w-40 cursor-pointer appearance-none rounded-full bg-muted accent-foreground"
        dir="ltr"
      />
      <span
        className="min-w-[3.5rem] text-end text-[0.6875rem] font-mono tabular-nums text-foreground"
        dir="ltr"
      >
        {currentCount}
      </span>
    </div>
  );
}
