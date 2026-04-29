"use client";

import { useEffect, useState } from "react";
import { AnimatedWordmark } from "@/shared/ui/animated-wordmark";

export function SplashScreen() {
  const [phase, setPhase] = useState<"active" | "fading" | "done">("active");

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const fadeDelay = reduceMotion ? 0 : 1000;
    const doneDelay = reduceMotion ? 0 : 1300;
    const fadeTimer = setTimeout(() => setPhase("fading"), fadeDelay);
    const removeTimer = setTimeout(() => setPhase("done"), doneDelay);

    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(removeTimer);
    };
  }, []);

  if (phase === "done") return null;

  return (
    <div
      className="fixed inset-0 z-[99999] flex items-center justify-center bg-background"
      aria-hidden="true"
      style={
        phase === "fading"
          ? {
              opacity: 0,
              transition: "opacity 300ms cubic-bezier(0.16, 1, 0.3, 1)",
              pointerEvents: "none" as const,
            }
          : undefined
      }
    >
      <AnimatedWordmark size={64} autoMorph />
    </div>
  );
}
