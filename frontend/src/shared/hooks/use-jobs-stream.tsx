"use client";

import * as React from "react";

import { getRuntimeEnv } from "@/shared/lib/runtime-env";
import { useStreamWithPollFallback } from "@/shared/hooks/use-stream-with-poll-fallback";

const POLL_FALLBACK_MS = 15_000;

interface JobsStreamContextValue {
  /**
   * Register a callback fired on every stream tick (and on each poll-fallback
   * cycle). Returns an unsubscribe function.
   */
  subscribe: (onTick: () => void) => () => void;
  /**
   * Report whether this consumer currently sees active jobs. The shared stream
   * stays open while ANY consumer reports ``true``.
   */
  reportActive: (key: string, active: boolean) => void;
}

const Ctx = React.createContext<JobsStreamContextValue | null>(null);

/**
 * Owns the single ``/optimizations/stream`` SSE connection shared by every
 * jobs-list surface (dashboard + sidebar).
 *
 * Without this, each surface opened its own stream — two connections plus
 * double the backend job-store polling whenever both were mounted. The stream
 * stays open while any consumer reports active jobs and broadcasts each tick to
 * all of them; each consumer refetches its own (differently-scoped) list in
 * response. The server emits an ``idle`` event and closes the moment nothing is
 * active, so the connection only exists while there is something to watch.
 */
export function JobsStreamProvider({ children }: { children: React.ReactNode }) {
  const subscribersRef = React.useRef<Set<() => void>>(new Set());
  const activeReportsRef = React.useRef<Map<string, boolean>>(new Map());
  const [hasActive, setHasActive] = React.useState(false);

  const reportActive = React.useCallback((key: string, active: boolean) => {
    if (activeReportsRef.current.get(key) === active) return;
    activeReportsRef.current.set(key, active);
    let any = false;
    for (const v of activeReportsRef.current.values()) {
      if (v) {
        any = true;
        break;
      }
    }
    setHasActive((prev) => (prev === any ? prev : any));
  }, []);

  const subscribe = React.useCallback((onTick: () => void) => {
    subscribersRef.current.add(onTick);
    return () => {
      subscribersRef.current.delete(onTick);
    };
  }, []);

  const broadcast = React.useCallback(() => {
    for (const fn of subscribersRef.current) fn();
  }, []);

  const apiUrl = getRuntimeEnv().apiUrl;
  useStreamWithPollFallback({
    url: hasActive ? `${apiUrl}/optimizations/stream` : "",
    enabled: hasActive,
    onMessage: broadcast,
    events: { idle: broadcast },
    closeOnEvents: ["idle"],
    poll: broadcast,
    pollIntervalMs: POLL_FALLBACK_MS,
    pollOnlyOnClosed: false,
    // Stream auth failed even after a token refresh — fall back to the
    // consumers' self-healing refetch instead of silently going stale.
    onAuthError: broadcast,
  });

  const value = React.useMemo<JobsStreamContextValue>(
    () => ({ subscribe, reportActive }),
    [subscribe, reportActive],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/**
 * Subscribe a jobs-list surface to the shared dashboard stream.
 *
 * While ``active`` is true the shared stream stays open (3s server cadence) and
 * ``onTick`` fires on every update — typically a refetch of the caller's own
 * list. Reporting ``active`` is also what re-opens the stream after it went
 * idle, so callers should pass a value derived from their freshest data. A
 * no-op when rendered outside a :func:`JobsStreamProvider`.
 *
 * Args:
 *   active: Whether the caller currently has at least one active job in view.
 *   onTick: Fired on each shared stream tick / poll-fallback cycle.
 */
export function useJobsStream({ active, onTick }: { active: boolean; onTick: () => void }): void {
  const ctx = React.useContext(Ctx);
  const key = React.useId();
  const onTickRef = React.useRef(onTick);
  React.useEffect(() => {
    onTickRef.current = onTick;
  });

  React.useEffect(() => {
    ctx?.reportActive(key, active);
  }, [ctx, key, active]);

  React.useEffect(() => {
    if (!ctx) return;
    const unsubscribe = ctx.subscribe(() => onTickRef.current());
    return () => {
      unsubscribe();
      // Drop our active report on unmount so a surface leaving the tree can't
      // hold the shared stream open by itself.
      ctx.reportActive(key, false);
    };
  }, [ctx, key]);
}
