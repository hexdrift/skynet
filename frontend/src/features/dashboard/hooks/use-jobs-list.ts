import { useCallback, useEffect, useState } from "react";
import {
  listJobs,
  getOptimizationCounts,
  type OptimizationCounts,
} from "@/shared/lib/api";
import type { PaginatedJobsResponse } from "@/shared/types/api";
import { msg } from "@/features/shared/messages";
import { FETCH_PAGE_SIZE } from "../constants";

type UseJobsListArgs = {
  sessionUser: string;
  isAdmin: boolean;
};

export type UseJobsListReturn = {
  data: PaginatedJobsResponse | null;
  setData: React.Dispatch<React.SetStateAction<PaginatedJobsResponse | null>>;
  loading: boolean;
  initialLoad: boolean;
  error: string | null;
  pageOffset: number;
  setPageOffset: React.Dispatch<React.SetStateAction<number>>;
  counts: OptimizationCounts | null;
  fetchJobs: () => Promise<void>;
};

export function useJobsList({
  sessionUser,
  isAdmin,
}: UseJobsListArgs): UseJobsListReturn {
  const [data, setData] = useState<PaginatedJobsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [initialLoad, setInitialLoad] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pageOffset, setPageOffset] = useState(0);
  const [counts, setCounts] = useState<OptimizationCounts | null>(null);

  const fetchJobs = useCallback(async () => {
    try {
      const username = isAdmin ? undefined : sessionUser || undefined;
      const [result, countsResult] = await Promise.all([
        listJobs({ username, limit: FETCH_PAGE_SIZE, offset: pageOffset }),
        getOptimizationCounts(username).catch(() => null),
      ]);
      setData(result);
      if (countsResult) setCounts(countsResult);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : msg("dashboard.load_error"));
    } finally {
      setLoading(false);
      setInitialLoad(false);
    }
  }, [sessionUser, isAdmin, pageOffset]);

  useEffect(() => {
    if (!data) setLoading(true);
    fetchJobs();
    // fetchJobs changes whenever sessionUser/isAdmin/pageOffset change, so
    // `data` deliberately stays out of the dep array to avoid a refetch loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchJobs]);

  return {
    data,
    setData,
    loading,
    initialLoad,
    error,
    pageOffset,
    setPageOffset,
    counts,
    fetchJobs,
  };
}
