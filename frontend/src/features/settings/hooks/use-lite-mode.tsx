"use client";

import * as React from "react";
import { MotionConfig } from "framer-motion";
import { useUserPrefs } from "./use-user-prefs";

/**
 * Applies Lite mode app-wide. Reflects `prefs.liteMode` onto a `data-lite`
 * attribute on <html> (globals.css hooks off it for instant transitions and no
 * backdrop-blur) and forces framer-motion's reduced-motion so every
 * `useReducedMotion()`-gated animation across the app goes static with no
 * per-component change. Heavy views read the flag directly via `useLiteMode()`
 * to render their static counterparts.
 */
export function LiteModeProvider({ children }: { children: React.ReactNode }) {
  const lite = useUserPrefs().prefs.liteMode;

  React.useEffect(() => {
    const root = document.documentElement;
    if (lite) root.setAttribute("data-lite", "");
    else root.removeAttribute("data-lite");
    return () => root.removeAttribute("data-lite");
  }, [lite]);

  return <MotionConfig reducedMotion={lite ? "always" : "user"}>{children}</MotionConfig>;
}

/** Whether Lite mode is active. Thin read over user prefs so heavy components
 * can branch to their static variant without coupling to the prefs shape. */
export function useLiteMode(): boolean {
  return useUserPrefs().prefs.liteMode;
}
