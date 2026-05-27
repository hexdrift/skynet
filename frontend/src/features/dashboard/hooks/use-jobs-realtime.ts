import { ACTIVE_STATUSES } from "@/shared/constants/job-status";
import type { PaginatedJobsResponse } from "@/shared/types/api";
import { getRuntimeEnv } from "@/shared/lib/runtime-env";
import { useStreamWithPollFallback } from "@/shared/hooks/use-stream-with-poll-fallback";

const POLL_FALLBACK_MS = 15_000;

type UseJobsRealtimeArgs = {
  data: PaginatedJobsResponse | null;
  fetchJobs: () => Promise<void> | void;
};

export function useJobsRealtime({ data, fetchJobs }: UseJobsRealtimeArgs) {
  const hasActive = data?.items.some((j) => ACTIVE_STATUSES.has(j.status)) ?? false;
  const API = getRuntimeEnv().apiUrl;

  useStreamWithPollFallback({
    url: hasActive ? `${API}/optimizations/stream` : "",
    enabled: hasActive,
    onMessage: () => void fetchJobs(),
    events: { idle: () => void fetchJobs() },
    closeOnEvents: ["idle"],
    poll: () => void fetchJobs(),
    pollIntervalMs: POLL_FALLBACK_MS,
    pollOnlyOnClosed: false,
    // Stream auth failed even after a token refresh — fall back to the
    // self-healing fetchJobs() path instead of silently going stale.
    onAuthError: () => void fetchJobs(),
  });
}
