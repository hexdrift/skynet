"use client";

import { useEffect, useRef } from "react";
import { fetchWithAuthRetry } from "@/shared/lib/api";
import { readServerSentEvents } from "@/shared/lib/sse";

export interface StreamWithPollFallbackOptions {
  url: string;
  enabled?: boolean;
  onMessage?: (event: MessageEvent) => void;
  events?: Record<string, (event: MessageEvent) => void>;
  /** Event names that should close the stream after their handler runs. */
  closeOnEvents?: string[];
  poll: () => void;
  pollIntervalMs: number;
  shouldStopPolling?: () => boolean;
  /**
   * When true (default), only fall back once the stream has actually ended
   * so transient blips don't lock the page into polling. Set false to fall
   * back on the first transport error.
   */
  pollOnlyOnClosed?: boolean;
  /**
   * Called when the stream fails authentication (HTTP 401) even after a
   * token refresh. Distinguished from a transport error so the caller can
   * surface it instead of silently degrading to polling.
   */
  onAuthError?: () => void;
}

/**
 * A `MessageEvent`-shaped object carrying the raw SSE `data:` payload as a
 * JSON string. The fetch-based reader synthesizes these so existing callers
 * (which `JSON.parse(event.data)`) keep working unchanged after the move off
 * the native `EventSource`.
 */
function syntheticMessageEvent(data: Record<string, unknown>): MessageEvent {
  return { data: JSON.stringify(data) } as MessageEvent;
}

export function useStreamWithPollFallback({
  url,
  enabled = true,
  onMessage,
  events,
  closeOnEvents,
  poll,
  pollIntervalMs,
  shouldStopPolling,
  pollOnlyOnClosed = true,
  onAuthError,
}: StreamWithPollFallbackOptions): void {
  const onMessageRef = useRef(onMessage);
  const eventsRef = useRef(events);
  const closeOnEventsRef = useRef(closeOnEvents);
  const pollRef = useRef(poll);
  const shouldStopRef = useRef(shouldStopPolling);
  const onAuthErrorRef = useRef(onAuthError);

  useEffect(() => {
    onMessageRef.current = onMessage;
    eventsRef.current = events;
    closeOnEventsRef.current = closeOnEvents;
    pollRef.current = poll;
    shouldStopRef.current = shouldStopPolling;
    onAuthErrorRef.current = onAuthError;
  });

  useEffect(() => {
    if (!enabled || !url) return;

    const abort = new AbortController();
    let fallbackInterval: ReturnType<typeof setInterval> | null = null;
    let stopped = false;

    const startPolling = () => {
      if (fallbackInterval || stopped) return;
      fallbackInterval = setInterval(() => {
        if (shouldStopRef.current?.()) {
          if (fallbackInterval) clearInterval(fallbackInterval);
          fallbackInterval = null;
          return;
        }
        pollRef.current();
      }, pollIntervalMs);
    };

    const stop = () => {
      stopped = true;
      abort.abort();
    };

    const run = async () => {
      let res: Response;
      try {
        // EventSource can't send an Authorization header; the SSE routes
        // require the bearer token, so use an authenticated fetch reader.
        res = await fetchWithAuthRetry(url, {
          headers: { Accept: "text/event-stream" },
          signal: abort.signal,
          cache: "no-store",
        });
      } catch (err) {
        if ((err as Error)?.name === "AbortError") return;
        startPolling();
        return;
      }

      // A 401 that survived the in-fetch token refresh is an auth failure,
      // not a transport blip — surface it instead of silently polling.
      if (res.status === 401) {
        onAuthErrorRef.current?.();
        if (!pollOnlyOnClosed) startPolling();
        return;
      }
      if (!res.ok || !res.body) {
        startPolling();
        return;
      }

      const handlers = eventsRef.current;
      const closeSet = new Set(closeOnEventsRef.current ?? []);
      try {
        await readServerSentEvents(res.body, ({ event, data }) => {
          if (stopped) return;
          const msgEvent = syntheticMessageEvent(data);
          if (event === "message") {
            onMessageRef.current?.(msgEvent);
            return;
          }
          handlers?.[event]?.(msgEvent);
          if (closeSet.has(event)) stop();
        });
      } catch (err) {
        if ((err as Error)?.name === "AbortError" || stopped) return;
        startPolling();
        return;
      }
      // Stream ended cleanly (server closed). Fall back to polling unless a
      // close-on event already terminated it on purpose.
      if (!stopped) startPolling();
    };

    void run();

    return () => {
      stop();
      if (fallbackInterval) clearInterval(fallbackInterval);
    };
  }, [url, enabled, pollIntervalMs, pollOnlyOnClosed]);
}
