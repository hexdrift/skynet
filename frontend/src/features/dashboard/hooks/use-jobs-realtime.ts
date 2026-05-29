import { ACTIVE_STATUSES } from "@/shared/constants/job-status";
import type { PaginatedJobsResponse } from "@/shared/types/api";
import { useJobsStream } from "@/shared/hooks/use-jobs-stream";

type UseJobsRealtimeArgs = {
  data: PaginatedJobsResponse | null;
  fetchJobs: () => Promise<void> | void;
};

/**
 * Dashboard adapter over the shared jobs stream: keeps the live list in sync
 * while any job is active. The SSE connection itself is owned by
 * ``JobsStreamProvider`` and shared with the sidebar, so the dashboard no
 * longer opens its own duplicate ``/optimizations/stream`` connection.
 *
 * Args:
 *   data: The current paginated jobs page; its statuses decide whether the
 *     shared stream needs to be open.
 *   fetchJobs: Refetch the dashboard's list; fired on each shared stream tick.
 */
export function useJobsRealtime({ data, fetchJobs }: UseJobsRealtimeArgs) {
  const hasActive = data?.items.some((j) => ACTIVE_STATUSES.has(j.status)) ?? false;
  useJobsStream({ active: hasActive, onTick: () => void fetchJobs() });
}
