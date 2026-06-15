"use client";

import * as React from "react";
import {
  listDatasets,
  type DatasetSummary,
  type DatasetUsageMeter,
} from "@/shared/lib/api";

/** Loading/error/data shape returned by {@link useDatasets}. */
export interface UseDatasetsResult {
  datasets: DatasetSummary[];
  usage: DatasetUsageMeter | null;
  loading: boolean;
  error: boolean;
  refetch: () => void;
}

/**
 * Fetch the caller's library (owned + shared-in) plus their usage meter.
 *
 * Refetching is manual (after a save/clone/delete/rename mutation) — the list
 * isn't streamed, so callers bump it explicitly via the returned ``refetch``.
 *
 * Args:
 *     enabled: When false the fetch is deferred — used by the submit-wizard
 *         picker so the library loads only once its dialog opens.
 */
export function useDatasets(enabled = true): UseDatasetsResult {
  const [datasets, setDatasets] = React.useState<DatasetSummary[]>([]);
  const [usage, setUsage] = React.useState<DatasetUsageMeter | null>(null);
  const [loading, setLoading] = React.useState(enabled);
  const [error, setError] = React.useState(false);
  const [nonce, setNonce] = React.useState(0);

  const refetch = React.useCallback(() => setNonce((n) => n + 1), []);

  React.useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setLoading(true);
    setError(false);
    listDatasets()
      .then((res) => {
        if (cancelled) return;
        setDatasets(res.datasets);
        setUsage(res.usage);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [nonce, enabled]);

  return { datasets, usage, loading, error, refetch };
}
