"use client";

import * as React from "react";

import type { TrustMode } from "../lib/types";

const STORAGE_KEY = "skynet.generalist-panel.trust-mode";
const MODES: TrustMode[] = ["ask", "auto_safe", "yolo"];

/** Persist the trust mode across sessions. Cycles via {@link next}. */
export function useTrustMode(): {
  mode: TrustMode;
  setMode: (m: TrustMode) => void;
  next: () => void;
} {
  const [mode, setModeState] = React.useState<TrustMode>("ask");

  React.useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw && (MODES as string[]).includes(raw)) {
        setModeState(raw as TrustMode);
      }
    } catch {
      /* localStorage unavailable */
    }
  }, []);

  const setMode = React.useCallback((m: TrustMode) => {
    setModeState(m);
    try {
      window.localStorage.setItem(STORAGE_KEY, m);
    } catch {
      /* noop */
    }
  }, []);

  const next = React.useCallback(() => {
    setModeState((prev) => {
      const idx = MODES.indexOf(prev);
      const nextMode = MODES[(idx + 1) % MODES.length] ?? "ask";
      try {
        window.localStorage.setItem(STORAGE_KEY, nextMode);
      } catch {
        /* noop */
      }
      return nextMode;
    });
  }, []);

  return { mode, setMode, next };
}

/** Per-mode ink hue used by the presence strip and trust pill. */
export const TRUST_MODE_HUE: Record<TrustMode, string> = {
  ask: "#3D2E22",
  auto_safe: "#5E7A5E",
  yolo: "#A85A1A",
};

export const TRUST_MODE_LABEL: Record<TrustMode, string> = {
  ask: "שואל",
  auto_safe: "אוטומטי",
  yolo: "חופשי",
};

export const TRUST_MODE_DESCRIPTION: Record<TrustMode, string> = {
  ask: "מבקש אישור לפני כל פעולה",
  auto_safe: "מבצע פעולות בטוחות ללא אישור",
  yolo: "מבצע הכל ללא אישור",
};
