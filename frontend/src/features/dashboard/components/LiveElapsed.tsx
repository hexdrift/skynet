"use client";

import * as React from "react";
import { formatElapsed } from "@/shared/lib";

type LiveElapsedProps = {
  startedAt?: string | null;
  elapsedSeconds?: number | null;
  isActive: boolean;
};

export function LiveElapsed({ startedAt, elapsedSeconds, isActive }: LiveElapsedProps) {
  const startMs = React.useMemo(() => {
    if (!startedAt) return null;
    const t = Date.parse(startedAt);
    return Number.isFinite(t) ? t : null;
  }, [startedAt]);

  const canStream = isActive && startMs !== null;
  const [now, setNow] = React.useState(() => Date.now());

  React.useEffect(() => {
    if (!canStream) return;
    setNow(Date.now());
    // Pause the per-second tick in background tabs (mirrors the
    // visibility-gated polling in the sidebar / public dashboard).
    const tick = () => {
      if (document.visibilityState === "visible") setNow(Date.now());
    };
    const id = setInterval(tick, 1000);
    const onVisibility = () => {
      if (document.visibilityState === "visible") setNow(Date.now());
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [canStream]);

  const seconds = canStream && startMs !== null ? (now - startMs) / 1000 : elapsedSeconds;
  return <>{formatElapsed(seconds)}</>;
}
