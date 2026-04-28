"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { getPublicDashboard, invalidateCache, type PublicDashboardPoint } from "@/shared/lib/api";

const POLL_INTERVAL_MS = 30000;

export interface PublicDashboardState {
  points: PublicDashboardPoint[];
  loading: boolean;
  error: string | null;
}

export function usePublicDashboard(): PublicDashboardState {
  const [state, setState] = useState<PublicDashboardState>({
    points: [],
    loading: true,
    error: null,
  });
  const lastTickRef = useRef<number>(0);

  const load = useCallback(async () => {
    try {
      const data = await getPublicDashboard();
      lastTickRef.current = Date.now();
      setState({ points: data.points, loading: false, error: null });
    } catch (err) {
      setState((s) => ({
        ...s,
        loading: false,
        error: err instanceof Error ? err.message : "load failed",
      }));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    const tick = async () => {
      if (cancelled) return;
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      invalidateCache("/dashboard/public");
      await load();
    };

    const onVisibility = () => {
      if (typeof document === "undefined") return;
      if (document.visibilityState !== "visible") return;
      // Catch up if we missed ticks while hidden.
      if (Date.now() - lastTickRef.current > POLL_INTERVAL_MS) {
        void tick();
      }
    };

    void load();
    timer = setInterval(tick, POLL_INTERVAL_MS);
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisibility);
    }

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVisibility);
      }
    };
  }, [load]);

  return state;
}
