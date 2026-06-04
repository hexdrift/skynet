"use client";

import * as React from "react";

const STORAGE_KEY = "skynet:explore:recent-queries";
const MAX_RECENT = 6;

/**
 * Locally-persisted list of the user's recent explore queries, most-recent
 * first. Backed by localStorage (per-device, no server round-trip) so a blank
 * search field can offer a one-tap way back to what they searched before.
 *
 * All storage access is wrapped defensively — private-mode / blocked storage
 * throws on access, and we'd rather degrade to an empty list than crash the
 * page.
 */
export function useRecentQueries(): {
  recent: string[];
  push: (query: string) => void;
  clear: () => void;
} {
  const [recent, setRecent] = React.useState<string[]>([]);

  React.useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const parsed: unknown = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        setRecent(parsed.filter((v): v is string => typeof v === "string").slice(0, MAX_RECENT));
      }
    } catch {
      // Corrupt or inaccessible storage — start from an empty list.
    }
  }, []);

  const push = React.useCallback((query: string) => {
    const trimmed = query.trim();
    if (!trimmed) return;
    setRecent((prev) => {
      const next = [trimmed, ...prev.filter((r) => r !== trimmed)].slice(0, MAX_RECENT);
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // Best-effort persistence; the in-memory list still updates.
      }
      return next;
    });
  }, []);

  const clear = React.useCallback(() => {
    setRecent([]);
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Nothing to do if storage is unavailable.
    }
  }, []);

  return { recent, push, clear };
}
