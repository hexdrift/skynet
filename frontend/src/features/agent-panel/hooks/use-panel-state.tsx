"use client";

import * as React from "react";
import { useUserPrefs, type AgentShortcut } from "@/features/settings";

import {
  DEFAULT_WIDTH,
  MAX_WIDTH,
  MIN_WIDTH,
  STORAGE_KEY_OPEN,
  STORAGE_KEY_WIDTH,
} from "../constants";

// The default shortcut is ``Ctrl+J`` (see ``DEFAULT_AGENT_SHORTCUT`` in
// ``features/settings/lib/prefs.ts``). On macOS users naturally press
// ``Cmd+J`` instead, so we treat ``ctrl`` and ``meta`` as interchangeable
// for the panel toggle. The exact-match ``matchShortcut`` from settings is
// still correct for the recorder UI and is intentionally not used here.
function matchPanelShortcut(e: KeyboardEvent, s: AgentShortcut): boolean {
  const ctrlOrMeta = e.ctrlKey || e.metaKey;
  const wantsCtrlOrMeta = s.ctrl || s.meta;
  if (ctrlOrMeta !== wantsCtrlOrMeta) return false;
  if (e.altKey !== s.alt) return false;
  if (e.shiftKey !== s.shift) return false;
  return e.key.toLowerCase() === s.key.toLowerCase();
}

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
  const { prefs } = useUserPrefs();
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

  const shortcut = prefs.agentShortcut;
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (matchPanelShortcut(e, shortcut)) {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [toggle, shortcut]);

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
