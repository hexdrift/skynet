"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { useRouter, usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useTutorialContext } from "./tutorial-provider";
import { getTrack } from "../lib/steps";
import { SpotlightMask } from "./spotlight-mask";
import { TutorialPopover } from "./tutorial-popover";
import { AnimatedWordmark } from "@/shared/ui/animated-wordmark";
import { isTutorialNavigating, registerTutorialHook } from "../lib/bridge";

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
  const pathname = usePathname();

  const [targetRect, setTargetRect] = React.useState<DOMRect | null>(null);
  const [popoverPosition, setPopoverPosition] = React.useState<{
    top: number;
    left: number;
    placement: "top" | "bottom" | "left" | "right";
  } | null>(null);
  const [showSplash, setShowSplash] = React.useState(false);
  const [stepReady, setStepReady] = React.useState(false);
  const stepPathRef = React.useRef<string | null>(null);
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
  const lastRectRef = React.useRef<{ x: number; y: number; w: number; h: number } | null>(null);
  const autoPlayTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const calculatePosition = React.useCallback(
    (rect: DOMRect, placement: "top" | "bottom" | "left" | "right" | "auto") => {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const pw = Math.min(360, vw * 0.9 - 16);
      const ph = 260;
      const gap = 16;

      let p = placement;
      if (p === "auto") {
        const spaces = [
          { p: "bottom" as const, s: vh - rect.bottom },
          { p: "top" as const, s: rect.top },
          { p: "right" as const, s: vw - rect.right },
          { p: "left" as const, s: rect.left },
        ];
        p = spaces.sort((a, b) => b.s - a.s)[0]!.p;
      }

      let top = 0,
        left = 0;
      switch (p) {
        case "top":
          top = rect.top - ph - gap;
          left = rect.left + rect.width / 2 - pw / 2;
          break;
        case "bottom":
          top = rect.bottom + gap;
          left = rect.left + rect.width / 2 - pw / 2;
          break;
        case "left":
          top = rect.top + rect.height / 2 - ph / 2;
          left = rect.left - pw - gap;
          break;
        case "right":
          top = rect.top + rect.height / 2 - ph / 2;
          left = rect.right + gap;
          break;
      }

      top = Math.max(12, Math.min(top, vh - ph - 12));
      left = Math.max(12, Math.min(left, vw - pw - 12));

      return { top, left, placement: p };
    },
    [],
  );

  const updatePositions = React.useCallback(() => {
    if (!currentStep) return;

    const el = document.querySelector(currentStep.target);
    if (!el) {
      // Keep last-known rect so the spotlight doesn't flash to full-dark
      // mid-transition. Popover is already hidden via stepReady gate.
      return;
    }

    targetRef.current = el;
    const rect = el.getBoundingClientRect();

    // Skip state updates when rect hasn't meaningfully changed — avoids
    // re-renders at 60fps when nothing moved.
    const prev = lastRectRef.current;
    if (
      prev &&
      Math.abs(prev.x - rect.x) < 0.5 &&
      Math.abs(prev.y - rect.y) < 0.5 &&
      Math.abs(prev.w - rect.width) < 0.5 &&
      Math.abs(prev.h - rect.height) < 0.5
    ) {
      return;
    }
    lastRectRef.current = { x: rect.x, y: rect.y, w: rect.width, h: rect.height };

    setTargetRect(rect);
    setPopoverPosition(calculatePosition(rect, currentStep.placement || "auto"));
  }, [currentStep, calculatePosition]);

  const trackPosition = React.useCallback(() => {
    updatePositions();
    rafRef.current = requestAnimationFrame(trackPosition);
  }, [updatePositions]);

  React.useEffect(() => {
    if (!state.isVisible || !currentStep) return;
    setStepReady(false);
    lastRectRef.current = null;
    stepPathRef.current = null;

    let cancelled = false;
    const init = async () => {
      if (currentStep.beforeShow) {
        await currentStep.beforeShow();
      }
      if (cancelled) return;

      // Wait for the target to mount (handles route transitions and
      // late-mounting React subtrees). If still missing, skip the step so a
      // broken anchor never stalls the tour. Window must exceed the longest
      // beforeShow waitForElement so steps that navigate to a slow-mounting
      // route (e.g. /compare with demo data, /optimizations/[id]) aren't
      // auto-skipped while their anchor is still hydrating.
      let el = document.querySelector(currentStep.target);
      if (!el) {
        const start = Date.now();
        while (!el && Date.now() - start < 5000) {
          await new Promise((r) => requestAnimationFrame(r));
          if (cancelled) return;
          el = document.querySelector(currentStep.target);
        }
      }
      if (!el) {
        // Skip in the SAME direction the user was navigating. Without this,
        // Backspace on a step whose anchor is gone (e.g. wizard remounted)
        // calls nextStep() and races toward COMPLETE_TRACK at the last step,
        // closing the tutorial instead of stepping back to a working anchor.
        const goingBack = state.lastDirection === "backward";
        console.warn(
          `[tutorial] step "${currentStep.id}" target not found: ${currentStep.target} — skipping ${goingBack ? "backward" : "forward"}`,
        );
        if (goingBack) prevStep();
        else nextStep();
        return;
      }

      // Scroll target into view only if off-screen
      const rect = el.getBoundingClientRect();
      const offScreen = rect.top < 0 || rect.bottom > window.innerHeight;
      if (offScreen) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        await new Promise((r) => setTimeout(r, 250));
        if (cancelled) return;
      }
      // Seed positions immediately so the popover mounts at the right spot.
      updatePositions();
      // Start rAF tracking — handles resize, scroll, layout shifts
      rafRef.current = requestAnimationFrame(trackPosition);
      stepPathRef.current = window.location.pathname;
      setStepReady(true);
    };

    void init();

    return () => {
      cancelled = true;
      cancelAnimationFrame(rafRef.current);
      // Best-effort per-step cleanup. Closure captures the OLD step, which
      // is what we want — clean up the step we're leaving before the next
      // one's beforeShow runs. Fire-and-forget; UI undo doesn't need await.
      if (currentStep.afterHide) {
        void currentStep.afterHide();
      }
    };
  }, [
    state.isVisible,
    state.lastDirection,
    currentStep,
    trackPosition,
    updatePositions,
    nextStep,
    prevStep,
  ]);

  // Detect manual navigation away from the active step's expected route
  // and exit the tour — the spotlight would otherwise point at a missing
  // element. The user's intentional navigation stands; we don't bounce
  // them back.
  React.useEffect(() => {
    if (!state.isVisible || !stepReady) return;
    if (!stepPathRef.current) return;
    // Compare against window.location.pathname (truth) instead of pathname
    // (React state from usePathname). The React value can lag behind during
    // route transitions, causing a transient mismatch with stepPathRef
    // (which init() sets from window.location.pathname). pathname stays in
    // deps so the effect still re-runs on every navigation.
    if (window.location.pathname !== stepPathRef.current) {
      exitTutorial();
    }
  }, [pathname, state.isVisible, stepReady, exitTutorial]);

  React.useEffect(() => {
    // Clear any pending timer before deciding whether to arm a new one.
    // The ref makes the "at most one autoplay timer alive" invariant
    // explicit and survives PREV/NEXT/pause races where two effect runs
    // could otherwise overlap if beforeShow resolves slowly.
    if (autoPlayTimerRef.current) {
      clearTimeout(autoPlayTimerRef.current);
      autoPlayTimerRef.current = null;
    }

    if (!stepReady || !state.isAutoPlaying || !currentStep) return;
    const track = state.activeTrack ? getTrack(state.activeTrack) : null;
    if (!track) return;

    const isLast = state.currentStepIndex >= track.steps.length - 1;
    const duration = (currentStep.readingTimeSec ?? 10) * 1000;

    autoPlayTimerRef.current = setTimeout(() => {
      autoPlayTimerRef.current = null;
      if (isLast) completeTrack();
      else nextStep();
    }, duration);

    return () => {
      if (autoPlayTimerRef.current) {
        clearTimeout(autoPlayTimerRef.current);
        autoPlayTimerRef.current = null;
      }
    };
  }, [
    stepReady,
    state.isAutoPlaying,
    state.activeTrack,
    state.currentStepIndex,
    currentStep,
    nextStep,
    completeTrack,
  ]);

  const handleExit = React.useCallback(() => {
    exitTutorial();
    // Always return to the dashboard so the user never lands on a page
    // still showing fake tutorial data (demo optimization, demo grid,
    // demo compare, etc.). The dashboard clears its demo overlay via
    // the `tutorial-exited` event.
    if (window.location.pathname !== "/") {
      router.push("/");
    }
  }, [exitTutorial, router]);

  React.useEffect(() => {
    if (!state.isVisible) return;

    const onKey = (e: KeyboardEvent) => {
      const tgt = e.target as HTMLElement | null;
      const tgtDesc = tgt
        ? `${tgt.tagName}${tgt.id ? `#${tgt.id}` : ""}.${(tgt.className || "").toString().slice(0, 30)}`
        : "?";
      console.warn(`[tut-key] ${e.key} target=${tgtDesc} default=${e.defaultPrevented}`);
      if (e.key === "Enter" || e.key === "ArrowLeft") {
        e.preventDefault();
        nextStep();
      } else if (e.key === "ArrowRight" || e.key === "Backspace") {
        e.preventDefault();
        prevStep();
      } else if (e.key === "Escape") {
        e.preventDefault();
        handleExit();
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state.isVisible, nextStep, prevStep, handleExit]);

  // Splash must render independently of tutorial visibility
  const splashPortal = showSplash
    ? createPortal(
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
        document.body,
      )
    : null;

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

          <AnimatePresence mode="wait">
            {stepReady && popoverPosition && (
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
          </AnimatePresence>
        </div>,
        document.body,
      )}
    </>
  );
}
