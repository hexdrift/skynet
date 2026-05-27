"use client";

import * as React from "react";
import { formatElapsed } from "@/shared/lib";

type LiveElapsedProps = {
  startedAt?: string | null;
  createdAt?: string | null;
  elapsedSeconds?: number | null;
  isActive: boolean;
};

// Backend emits timezone-naive UTC datetimes; without appending Z, Chrome
// parses them as local time and the live clock either stops at 0 or shows "—"
// for users east/west of UTC.
function parseTimestampMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value);
  const ms = Date.parse(hasTz ? value : `${value}Z`);
  return Number.isFinite(ms) ? ms : null;
}

export function LiveElapsed({
  startedAt,
  createdAt,
  elapsedSeconds,
  isActive,
}: LiveElapsedProps) {
  // Anchor on the server-computed elapsed_seconds and tick locally between
  // refreshes — immune to client/server clock skew that otherwise drives the
  // wall-clock derivation negative.
  const [anchor, setAnchor] = React.useState<{ ms: number; sec: number } | null>(null);
  React.useEffect(() => {
    if (elapsedSeconds != null && Number.isFinite(elapsedSeconds) && elapsedSeconds >= 0) {
      setAnchor({ ms: Date.now(), sec: elapsedSeconds });
    }
  }, [elapsedSeconds]);

  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    if (!isActive) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [isActive]);

  if (!isActive) return <>{formatElapsed(elapsedSeconds)}</>;

  // Take the larger of wallclock (now - reference) and the server anchor so a
  // stale upstream `elapsed_seconds` (e.g. cached 0) doesn't reset the counter
  // back to zero on every page reload. Reference is `started_at` once the
  // worker picks the job up; pending/validating rows fall back to
  // `created_at` so the cell shows a live counter from row creation instead
  // of "—" until work actually begins.
  const startMs = parseTimestampMs(startedAt);
  const refMs = startMs ?? parseTimestampMs(createdAt);
  const wall = refMs !== null ? Math.max(0, (now - refMs) / 1000) : 0;
  const anchored = anchor ? anchor.sec + Math.max(0, (now - anchor.ms) / 1000) : 0;
  const elapsed = Math.max(wall, anchored);
  if (elapsed > 0 || refMs !== null || anchor) return <>{formatElapsed(elapsed)}</>;
  return <>{formatElapsed(elapsedSeconds)}</>;
}
