"use client";

import { useEffect, useRef, useState } from "react";
import {
  getPublicDashboard,
  invalidateCache,
  type PublicDashboardMeta,
  type PublicDashboardPoint,
} from "@/shared/lib/api";
import { POLL_CATCHUP_EPSILON_MS, POLL_INTERVAL_MS } from "../constants";

export interface PublicDashboardState {
  points: PublicDashboardPoint[];
  meta: PublicDashboardMeta | null;
  loading: boolean;
  error: string | null;
}

export function usePublicDashboard(): PublicDashboardState {
  const [state, setState] = useState<PublicDashboardState>({
    points: [],
    meta: null,
    loading: true,
    error: null,
  });
  const lastTickRef = useRef<number>(0);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      if (cancelled) return;
      try {
        const data = await getPublicDashboard();
        if (cancelled) return;
        lastTickRef.current = Date.now();
        setState({ points: data.points, meta: data.meta, loading: false, error: null });
      } catch (err) {
        if (cancelled) return;
        setState((s) => ({
          ...s,
          loading: false,
          error: err instanceof Error ? err.message : "load failed",
        }));
      }
    };

    const tick = () => {
      if (cancelled) return;
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      invalidateCache("/dashboard/public");
      void load();
    };

    const onVisibility = () => {
      if (typeof document === "undefined") return;
      if (document.visibilityState !== "visible") return;
      // Refresh only when we've drifted at least one full interval since the
      // last successful load — the epsilon absorbs sub-second jitter so a
      // visibility flip 29.9s after a tick doesn't immediately retrigger.
      const elapsed = Date.now() - lastTickRef.current;
      if (elapsed >= POLL_INTERVAL_MS - POLL_CATCHUP_EPSILON_MS) tick();
    };

    void load();
    const timer = setInterval(tick, POLL_INTERVAL_MS);
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisibility);
    }

    return () => {
      cancelled = true;
      clearInterval(timer);
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVisibility);
      }
    };
  }, []);

  return state;
}
