"use client";

import { useEffect, useState } from "react";
import { AnimatedWordmark } from "./animated-wordmark";

/**
 * Splash screen — story.foundation-style preloader.
 * Full-screen warm overlay with a large morphing SKYNET wordmark
 * centered. Plays for ~2s then fades out to reveal the app.
 */

export function SplashScreen() {
  const [phase, setPhase] = useState<"active" | "fading" | "done">("active");

  useEffect(() => {
    const fadeTimer = setTimeout(() => setPhase("fading"), 1000);
    const removeTimer = setTimeout(() => setPhase("done"), 1300);

    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(removeTimer);
    };
  }, []);

  if (phase === "done") return null;

  return (
    <div
      className="fixed inset-0 z-[99999] flex items-center justify-center"
      aria-hidden="true"
      suppressHydrationWarning
      style={
        phase === "fading"
          ? { backgroundColor: "#F0EBE4", opacity: 0, transition: "opacity 300ms cubic-bezier(0.16, 1, 0.3, 1)", pointerEvents: "none" as const }
          : { backgroundColor: "#F0EBE4" }
      }
    >
      <AnimatedWordmark size={64} autoMorph />
    </div>
  );
}
