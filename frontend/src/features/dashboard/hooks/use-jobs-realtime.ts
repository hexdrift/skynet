import { useEffect, useRef } from "react";
import { ACTIVE_STATUSES } from "@/shared/constants/job-status";
import type { PaginatedJobsResponse } from "@/shared/types/api";

const POLL_FALLBACK_MS = 15_000;

type UseJobsRealtimeArgs = {
  data: PaginatedJobsResponse | null;
  fetchJobs: () => Promise<void> | void;
};

export function useJobsRealtime({ data, fetchJobs }: UseJobsRealtimeArgs) {
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    const hasActive = data?.items.some((j) => ACTIVE_STATUSES.has(j.status));
    if (!hasActive) return;

    const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    let eventSource: EventSource | null = null;

    try {
      eventSource = new EventSource(`${API}/optimizations/stream`);
      eventSource.onmessage = () => {
        fetchJobs();
      };
      eventSource.addEventListener("idle", () => {
        eventSource?.close();
        fetchJobs();
      });
      eventSource.onerror = () => {
        eventSource?.close();
        eventSource = null;
        timerRef.current = setInterval(fetchJobs, POLL_FALLBACK_MS);
      };
    } catch {
      timerRef.current = setInterval(fetchJobs, POLL_FALLBACK_MS);
    }

    return () => {
      eventSource?.close();
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [data, fetchJobs]);
}
