"use client";

import * as React from "react";
import { getPopularQueries, type PopularQuery } from "@/shared/lib/api";

/**
 * Fetch the trending public-corpus search queries once on mount (the API
 * response is cache-deduped). Returns an empty list until loaded — and on
 * failure — so the caller can fall back to corpus-frequency terms for the
 * blank-field zero-state.
 */
export function usePopularQueries(): PopularQuery[] {
  const [queries, setQueries] = React.useState<PopularQuery[]>([]);

  React.useEffect(() => {
    let cancelled = false;
    void getPopularQueries()
      .then((data) => {
        if (!cancelled) setQueries(data.queries);
      })
      .catch(() => {
        // Best-effort: leave empty so the UI falls back to corpus terms.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return queries;
}
