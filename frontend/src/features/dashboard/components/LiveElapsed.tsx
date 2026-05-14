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
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [canStream]);

  const seconds = canStream && startMs !== null ? (now - startMs) / 1000 : elapsedSeconds;
  return <>{formatElapsed(seconds)}</>;
}
