"use client";

import { useSyncExternalStore } from "react";

/** Tailwind's `lg` breakpoint: from here the filters sit beside the results. */
const WIDE_MEDIA_QUERY = "(min-width: 1024px)";

function subscribe(onChange: () => void) {
  const mq = window.matchMedia(WIDE_MEDIA_QUERY);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

/**
 * True at desktop widths, where the filter panel is part of the page layout
 * instead of a sheet; false on the server, so the first paint mounts nothing
 * until the viewport is known.
 */
export function useIsWideViewport(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(WIDE_MEDIA_QUERY).matches,
    () => false,
  );
}
