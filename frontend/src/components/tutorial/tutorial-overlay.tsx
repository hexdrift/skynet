"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useTutorialContext } from "./tutorial-provider";
import { getTrack } from "@/lib/tutorial-steps";
import { SpotlightMask } from "./spotlight-mask";
import { TutorialPopover } from "./tutorial-popover";
import { AnimatedWordmark } from "@/components/animated-wordmark";
import { DEMO_OPTIMIZATION_ID } from "@/lib/tutorial-demo-data";
import { isTutorialNavigating, registerTutorialHook } from "@/lib/tutorial-bridge";

export function TutorialOverlay() {
  const {
    state,
    currentStep,
    nextStep,
    prevStep,
    exitTutorial,
    completeTrack,
    toggleAutoPlay,
  } = useTutorialContext();

  const [targetRect, setTargetRect] = React.useState<DOMRect | null>(null);
  const [popoverPosition, setPopoverPosition] = React.useState<{
    top: number;
    left: number;
    placement: "top" | "bottom" | "left" | "right";
  } | null>(null);
  const [showSplash, setShowSplash] = React.useState(false);
  const [stepReady, setStepReady] = React.useState(false);
  const router = useRouter();

  // Register splash trigger + client-side navigation with the typed
  // tutorial bridge so steps in lib/tutorial-steps.ts can drive them.
  React.useEffect(() => {
    const unregisterSplash = registerTutorialHook("showTutorialSplash", () => {
      setShowSplash(true);
      // Auto-dismiss: match real submit splash (1.5s) + buffer for navigation
      setTimeout(() => setShowSplash(false), 1500);
    });
    const unregisterPush = registerTutorialHook("routerPush", (path: string) => router.push(path));
    return () => {
      unregisterSplash();
      unregisterPush();
    };
  }, [router]);

  const targetRef = React.useRef<Element | null>(null);
  const rafRef = React.useRef<number>(0);

  const calculatePosition = React.useCallback(
    (rect: DOMRect, placement: "top" | "bottom" | "left" | "right" | "auto") => {
      const pw = 360;
      const ph = 260;
      const gap = 16;
      const vw = window.innerWidth;
      const vh = window.innerHeight;

      let p = placement;
      if (p === "auto") {
        const spaces = [
          { p: "bottom" as const, s: vh - rect.bottom },
          { p: "top" as const, s: rect.top },
          { p: "right" as const, s: vw - rect.right },
          { p: "left" as const, s: rect.left },
        ];
        p = spaces.sort((a, b) => b.s - a.s)[0].p;
      }

      let top = 0, left = 0;
      switch (p) {
        case "top":    top = rect.top - ph - gap; left = rect.left + rect.width / 2 - pw / 2; break;
        case "bottom": top = rect.bottom + gap;   left = rect.left + rect.width / 2 - pw / 2; break;
        case "left":   top = rect.top + rect.height / 2 - ph / 2; left = rect.left - pw - gap; break;
        case "right":  top = rect.top + rect.height / 2 - ph / 2; left = rect.right + gap; break;
      }

      top = Math.max(12, Math.min(top, vh - ph - 12));
      left = Math.max(12, Math.min(left, vw - pw - 12));

      return { top, left, placement: p };
    },
    []
  );

  const updatePositions = React.useCallback(() => {
    if (!currentStep) return;

    const el = document.querySelector(currentStep.target);
    if (!el) {
      setTargetRect(null);
      setPopoverPosition({
        top: window.innerHeight / 2 - 110,
        left: window.innerWidth / 2 - 180,
        placement: "bottom",
      });
      return;
    }

    targetRef.current = el;
    const rect = el.getBoundingClientRect();
    setTargetRect(rect);
    setPopoverPosition(calculatePosition(rect, currentStep.placement || "auto"));
  }, [currentStep, calculatePosition]);

  // Smooth position tracking via rAF
  const trackPosition = React.useCallback(() => {
    updatePositions();
    rafRef.current = requestAnimationFrame(trackPosition);
  }, [updatePositions]);

  React.useEffect(() => {
    if (!state.isVisible || !currentStep) return;
    setStepReady(false);

    const init = async () => {
      if (currentStep.beforeShow) {
        await currentStep.beforeShow();
      }

      // Scroll target into view only if off-screen
      const el = document.querySelector(currentStep.target);
      if (el) {
        const rect = el.getBoundingClientRect();
        const offScreen = rect.top < 0 || rect.bottom > window.innerHeight;
        if (offScreen) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          await new Promise(r => setTimeout(r, 250));
        }
      }
      // Start rAF tracking — handles resize, scroll, layout shifts
      rafRef.current = requestAnimationFrame(trackPosition);
      setStepReady(true);
    };

    init();

    return () => {
      cancelAnimationFrame(rafRef.current);
    };
  }, [state.isVisible, currentStep, trackPosition]);

  // Auto-advance timer when auto-playing
  React.useEffect(() => {
    if (!stepReady || !state.isAutoPlaying || !currentStep) return;
    const track = state.activeTrack ? getTrack(state.activeTrack) : null;
    if (!track) return;

    const isLast = state.currentStepIndex >= track.steps.length - 1;
    const duration = (currentStep.readingTimeSec ?? 10) * 1000;

    const timer = setTimeout(() => {
      if (isLast) completeTrack();
      else nextStep();
    }, duration);

    return () => clearTimeout(timer);
  }, [stepReady, state.isAutoPlaying, state.activeTrack, state.currentStepIndex, currentStep, nextStep, completeTrack]);

  const handleExit = React.useCallback(() => {
    exitTutorial();
    // Navigate away from demo page so user doesn't interact with fake data
    if (window.location.pathname.includes(DEMO_OPTIMIZATION_ID)) {
      router.push("/");
    }
  }, [exitTutorial, router]);

  // Keyboard navigation
  React.useEffect(() => {
    if (!state.isVisible) return;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter" || e.key === "ArrowLeft") { e.preventDefault(); nextStep(); }
      else if (e.key === "ArrowRight" || e.key === "Backspace") { e.preventDefault(); prevStep(); }
      else if (e.key === "Escape") { e.preventDefault(); handleExit(); }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state.isVisible, nextStep, prevStep, handleExit]);

  // Splash must render independently of tutorial visibility
  const splashPortal = showSplash ? createPortal(
    <AnimatePresence>
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
    </AnimatePresence>,
    document.body
  ) : null;

  if (!state.isVisible || !currentStep) return splashPortal;
  if (isTutorialNavigating()) return splashPortal;

  const track = state.activeTrack ? getTrack(state.activeTrack) : null;
  if (!track) return splashPortal;

  const stepNumber = state.currentStepIndex + 1;
  const isFirst = state.currentStepIndex === 0;
  const isLast = state.currentStepIndex === track.steps.length - 1;

  const handleNext = () => {
    if (isLast) completeTrack();
    else nextStep();
  };

  return (
    <>
      {splashPortal}
      {createPortal(
        <div className="fixed inset-0 z-[9998] pointer-events-none">
          <SpotlightMask targetRect={targetRect} padding={8} borderRadius={12} />

          {popoverPosition && (
            <TutorialPopover
              key={currentStep.id}
              step={currentStep}
              stepNumber={stepNumber}
              totalSteps={track.stepCount}
              position={popoverPosition}
              onNext={handleNext}
              onPrev={prevStep}
              onExit={handleExit}
              isFirst={isFirst}
              isLast={isLast}
              isAutoPlaying={state.isAutoPlaying}
              onToggleAutoPlay={toggleAutoPlay}
            />
          )}
        </div>,
        document.body
      )}
    </>
  );
}
