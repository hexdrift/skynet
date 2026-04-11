/**
 * Debounce hook
 * Delays updating a value until after a specified delay
 * Used for search inputs and other user-driven updates
 */

import { useEffect, useState } from "react";
import { ANIMATION } from "../constants";

export function useDebounce<T>(value: T, delay: number = ANIMATION.DEBOUNCE_SEARCH): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}
