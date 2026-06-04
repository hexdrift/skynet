"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import type { SearchResult } from "@/shared/lib/api";

/**
 * Keyboard navigation over the results list while focus stays in the search
 * input (the combobox/aria-activedescendant pattern). ↑/↓ move a highlight,
 * Enter opens the highlighted row, Escape drops the highlight.
 *
 * Returns ``onInputKeyDown`` which the input calls first: a ``true`` result
 * means the key was consumed and the caller should stop (so Enter on a
 * highlighted row opens it instead of re-submitting the query). The highlight
 * resets whenever the result set changes.
 */
export function useResultKeyboardNav(
  results: SearchResult[],
  onOpen?: () => void,
): {
  activeIndex: number;
  onInputKeyDown: (event: React.KeyboardEvent) => boolean;
} {
  const router = useRouter();
  const [activeIndex, setActiveIndex] = React.useState(-1);
  // Kept in a ref so the keydown handler always calls the latest callback
  // (which closes over the current query) without re-creating itself.
  const onOpenRef = React.useRef(onOpen);
  React.useEffect(() => {
    onOpenRef.current = onOpen;
  }, [onOpen]);

  React.useEffect(() => {
    setActiveIndex(-1);
  }, [results]);

  const onInputKeyDown = React.useCallback(
    (event: React.KeyboardEvent): boolean => {
      const count = results.length;
      switch (event.key) {
        case "ArrowDown":
          if (count === 0) return false;
          event.preventDefault();
          setActiveIndex((i) => Math.min(count - 1, i + 1));
          return true;
        case "ArrowUp":
          if (count === 0) return false;
          event.preventDefault();
          setActiveIndex((i) => Math.max(-1, i - 1));
          return true;
        case "Enter": {
          const target = activeIndex >= 0 ? results[activeIndex] : undefined;
          if (!target) return false;
          event.preventDefault();
          onOpenRef.current?.();
          router.push(`/optimizations/${target.optimization_id}`);
          return true;
        }
        case "Escape":
          if (activeIndex < 0) return false;
          event.preventDefault();
          setActiveIndex(-1);
          return true;
        default:
          return false;
      }
    },
    [results, activeIndex, router],
  );

  return { activeIndex, onInputKeyDown };
}
