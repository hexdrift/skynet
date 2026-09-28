"use client";

import { motion } from "framer-motion";
import { useCallback, useMemo, useRef, useState } from "react";
import { getActiveDir } from "@/shared/lib/runtime-locale";
import { cn } from "@/shared/lib/utils";

export interface TimelineScrubberProps {
  // Last step on the track; steps run from 0 to this value.
  max: number;
  // Step the view is filtered to, or null for the live end of the track.
  value: number | null;
  onChange: (next: number | null) => void;
  isLive: boolean;
  label: string;
  // Spoken name of a step, and of the live end of the track.
  stepText: (step: number) => string;
  liveText: string;
}

/**
 * A slider over the steps of a run (GEPA's generations) that filters the view
 * below it to the steps up to the knob. The far end is live: everything so
 * far, pulsing while the run still grows.
 */
export function TimelineScrubber({
  max,
  value,
  onChange,
  isLive,
  label,
  stepText,
  liveText,
}: TimelineScrubberProps) {
  const current = value ?? max;
  const isAtLive = value === null;
  const isRtl = getActiveDir() === "rtl";
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [dragging, setDragging] = useState(false);

  const stepFromClientX = useCallback(
    (clientX: number) => {
      const el = trackRef.current;
      if (el === null) return current;
      const rect = el.getBoundingClientRect();
      // Step 0 sits at the inline-start edge — the track's right in RTL, its
      // left in LTR — so measure the drag from that edge in either direction.
      const offset = isRtl ? rect.right - clientX : clientX - rect.left;
      const pct = Math.max(0, Math.min(1, offset / rect.width));
      return Math.round(pct * max);
    },
    [current, max, isRtl],
  );

  const applyValue = useCallback(
    (next: number) => {
      onChange(next >= max ? null : next);
    },
    [onChange, max],
  );

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      (e.currentTarget as Element).setPointerCapture(e.pointerId);
      setDragging(true);
      applyValue(stepFromClientX(e.clientX));
    },
    [applyValue, stepFromClientX],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!dragging) return;
      applyValue(stepFromClientX(e.clientX));
    },
    [dragging, applyValue, stepFromClientX],
  );

  const onPointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    (e.currentTarget as Element).releasePointerCapture?.(e.pointerId);
    setDragging(false);
  }, []);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      // Later steps sit toward the inline-end edge — visually left in RTL,
      // right in LTR — so the arrow pointing that way means "forward in time".
      const forwardKey = isRtl ? "ArrowLeft" : "ArrowRight";
      const backKey = isRtl ? "ArrowRight" : "ArrowLeft";
      if (e.key === forwardKey) {
        e.preventDefault();
        applyValue(Math.min(max, current + 1));
      } else if (e.key === backKey) {
        e.preventDefault();
        applyValue(Math.max(0, current - 1));
      } else if (e.key === "Home") {
        e.preventDefault();
        applyValue(0);
      } else if (e.key === "End") {
        e.preventDefault();
        applyValue(max);
      }
    },
    [applyValue, current, max, isRtl],
  );

  const filledPct = max === 0 ? 100 : (current / max) * 100;
  const steps = useMemo(() => Array.from({ length: max + 1 }, (_, i) => i), [max]);

  return (
    <div
      className="rounded-xl border border-border/40 bg-background/70 px-4 pt-3 pb-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]"
      dir={isRtl ? "rtl" : "ltr"}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
      </div>

      <div
        ref={trackRef}
        role="slider"
        tabIndex={0}
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={current}
        aria-valuetext={isAtLive ? liveText : stepText(current)}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onKeyDown={onKeyDown}
        className="relative h-9 cursor-pointer touch-none select-none rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/60"
      >
        <div
          className="absolute inset-x-0 top-1/2 h-[2px] -translate-y-1/2 rounded-full"
          style={{ background: "rgba(28, 22, 18, 0.10)" }}
        />
        <div
          className="absolute top-1/2 h-[2px] -translate-y-1/2 rounded-full bg-[#7C6350]"
          style={{ ...(isRtl ? { right: 0 } : { left: 0 }), width: `${filledPct}%` }}
        />

        {steps.map((step) => {
          const pct = max === 0 ? 0 : (step / max) * 100;
          const isPast = step <= current;
          const isActive = step === current;
          if (isActive) return null;
          return (
            <span
              key={`tick-${step}`}
              className="pointer-events-none absolute top-1/2 inline-flex items-center justify-center rounded-sm bg-background/95 px-1 text-[10px] tabular-nums font-semibold leading-none"
              style={{
                ...(isRtl ? { right: `${pct}%` } : { left: `${pct}%` }),
                transform: isRtl ? "translate(50%, -50%)" : "translate(-50%, -50%)",
                color: isPast ? "#7C6350" : "rgba(28, 22, 18, 0.42)",
              }}
              aria-hidden="true"
            >
              {step}
            </span>
          );
        })}

        <div
          className="pointer-events-none absolute top-1/2 z-10"
          style={{
            ...(isRtl ? { right: `${filledPct}%` } : { left: `${filledPct}%` }),
            transform: isRtl ? "translate(50%, -50%)" : "translate(-50%, -50%)",
          }}
        >
          {isAtLive && isLive ? (
            <motion.span
              className="absolute left-1/2 top-1/2 block h-8 w-8 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#7C8B5A]/30"
              animate={{ scale: [1, 1.7, 1], opacity: [0.55, 0, 0.55] }}
              transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }}
              aria-hidden="true"
            />
          ) : null}
          <div
            className={cn(
              "relative block h-4 w-4 rounded-full border-[1.5px] shadow-[0_1px_2px_rgba(28,22,18,0.18)] transition-transform",
              isAtLive ? "border-[#1c1612] bg-[#1c1612]" : "border-[#1c1612] bg-[#fbf8f3]",
              dragging && "scale-110",
            )}
          />
        </div>
      </div>
    </div>
  );
}
