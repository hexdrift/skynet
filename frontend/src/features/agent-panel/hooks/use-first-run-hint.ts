"use client";

import * as React from "react";

import { STORAGE_KEY_FIRST_RUN_DISMISSED } from "../constants";

/**
 * Tracks whether the first-run hint tooltip should show. The hint is
 * dismissed permanently on any explicit interaction (open/close, pill
 * click, tooltip close) and persisted to localStorage so returning
 * users don't see it again.
 */
export function useFirstRunHint(): {
  visible: boolean;
  dismiss: () => void;
} {
  const [visible, setVisible] = React.useState(false);

  React.useEffect(() => {
    try {
      const done = window.localStorage.getItem(STORAGE_KEY_FIRST_RUN_DISMISSED) === "true";
      if (!done) setVisible(true);
    } catch {
      /* localStorage unavailable — skip hint */
    }
  }, []);

  const dismiss = React.useCallback(() => {
    setVisible(false);
    try {
      window.localStorage.setItem(STORAGE_KEY_FIRST_RUN_DISMISSED, "true");
    } catch {
      /* noop */
    }
  }, []);

  return { visible, dismiss };
}
