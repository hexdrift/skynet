"use client";

import { useEffect, useRef } from "react";

export interface StreamWithPollFallbackOptions {
  url: string;
  enabled?: boolean;
  onMessage?: (event: MessageEvent) => void;
  events?: Record<string, (event: MessageEvent) => void>;
  /** Event names that should `close()` the stream after their handler runs. */
  closeOnEvents?: string[];
  poll: () => void;
  pollIntervalMs: number;
  shouldStopPolling?: () => boolean;
  /**
   * When true (default), only fall back once `readyState === CLOSED` so
   * transient blips don't lock the page into polling. Set false to fall back
   * on the first `onerror`.
   */
  pollOnlyOnClosed?: boolean;
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
}: StreamWithPollFallbackOptions): void {
  const onMessageRef = useRef(onMessage);
  const eventsRef = useRef(events);
  const closeOnEventsRef = useRef(closeOnEvents);
  const pollRef = useRef(poll);
  const shouldStopRef = useRef(shouldStopPolling);

  useEffect(() => {
    onMessageRef.current = onMessage;
    eventsRef.current = events;
    closeOnEventsRef.current = closeOnEvents;
    pollRef.current = poll;
    shouldStopRef.current = shouldStopPolling;
  });

  useEffect(() => {
    if (!enabled || !url) return;

    let eventSource: EventSource | null = null;
    let fallbackInterval: ReturnType<typeof setInterval> | null = null;

    const startPolling = () => {
      if (fallbackInterval) return;
      fallbackInterval = setInterval(() => {
        if (shouldStopRef.current?.()) {
          if (fallbackInterval) clearInterval(fallbackInterval);
          fallbackInterval = null;
          return;
        }
        pollRef.current();
      }, pollIntervalMs);
    };

    try {
      eventSource = new EventSource(url);
      eventSource.onmessage = (e) => onMessageRef.current?.(e);

      const handlers = eventsRef.current;
      const closeSet = new Set(closeOnEventsRef.current ?? []);
      if (handlers) {
        for (const [name, handler] of Object.entries(handlers)) {
          eventSource.addEventListener(name, (e: Event) => {
            handler(e as MessageEvent);
            if (closeSet.has(name)) eventSource?.close();
          });
        }
      }

      eventSource.onerror = () => {
        if (pollOnlyOnClosed && eventSource?.readyState !== EventSource.CLOSED) return;
        eventSource?.close();
        eventSource = null;
        startPolling();
      };
    } catch {
      startPolling();
    }

    return () => {
      eventSource?.close();
      if (fallbackInterval) clearInterval(fallbackInterval);
    };
  }, [url, enabled, pollIntervalMs, pollOnlyOnClosed]);
}
