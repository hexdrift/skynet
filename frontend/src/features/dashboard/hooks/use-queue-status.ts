import { useEffect, useState } from "react";
import { getQueueStatus } from "@/shared/lib/api";
import type { QueueStatusResponse } from "@/shared/types/api";

const POLL_INTERVAL_MS = 30_000;

export function useQueueStatus(): QueueStatusResponse | null {
  const [queueStatus, setQueueStatus] = useState<QueueStatusResponse | null>(
    null,
  );

  useEffect(() => {
    const load = () => {
      getQueueStatus()
        .then(setQueueStatus)
        .catch(() => {});
    };
    load();
    const interval = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  return queueStatus;
}
