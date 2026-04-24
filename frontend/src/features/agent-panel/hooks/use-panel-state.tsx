"use client";

import * as React from "react";

const DEFAULT_WIDTH = 420;
const MIN_WIDTH = 360;
const MAX_WIDTH = 720;

const STORAGE_KEY_OPEN = "skynet.generalist-panel.open";
const STORAGE_KEY_WIDTH = "skynet.generalist-panel.width";

interface PanelState {
  open: boolean;
  setOpen: (v: boolean) => void;
  toggle: () => void;
  width: number;
  setWidth: (v: number) => void;
}

const PanelContext = React.createContext<PanelState | null>(null);

function clampWidth(n: number): number {
  return Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, Math.round(n)));
}

/**
 * Provides the generalist panel's persistent UI state (open/closed,
 * width) and owns the global ``Ctrl+J`` toggle.
 *
 * Mounted once in the app shell so the panel's thread survives route
 * changes. Hydrates from ``localStorage`` on the client only to avoid
 * SSR mismatches.
 */
export function GeneralistPanelProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpenState] = React.useState(false);
  const [width, setWidthState] = React.useState(DEFAULT_WIDTH);

  React.useEffect(() => {
    try {
      setOpenState(window.localStorage.getItem(STORAGE_KEY_OPEN) === "true");
      const raw = window.localStorage.getItem(STORAGE_KEY_WIDTH);
      const n = raw ? Number(raw) : NaN;
      if (Number.isFinite(n)) setWidthState(clampWidth(n));
    } catch {
      /* localStorage unavailable */
    }
  }, []);

  const setOpen = React.useCallback((next: boolean) => {
    setOpenState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY_OPEN, String(next));
    } catch {
      /* noop */
    }
  }, []);

  const toggle = React.useCallback(() => {
    setOpenState((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(STORAGE_KEY_OPEN, String(next));
      } catch {
        /* noop */
      }
      return next;
    });
  }, []);

  const setWidth = React.useCallback((next: number) => {
    const clamped = clampWidth(next);
    setWidthState(clamped);
    try {
      window.localStorage.setItem(STORAGE_KEY_WIDTH, String(clamped));
    } catch {
      /* noop */
    }
  }, []);

  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!e.ctrlKey || e.metaKey) return;
      if (e.key === "j" || e.key === "J") {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [toggle]);

  const value = React.useMemo<PanelState>(
    () => ({ open, setOpen, toggle, width, setWidth }),
    [open, setOpen, toggle, width, setWidth],
  );

  return <PanelContext.Provider value={value}>{children}</PanelContext.Provider>;
}

export function useGeneralistPanelState(): PanelState {
  const ctx = React.useContext(PanelContext);
  if (!ctx) {
    throw new Error("useGeneralistPanelState must be used within GeneralistPanelProvider");
  }
  return ctx;
}
