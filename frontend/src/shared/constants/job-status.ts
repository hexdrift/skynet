import type { JobStatus } from "./types";

export const ACTIVE_STATUSES = new Set<JobStatus>(["pending", "validating", "running"]);
export const TERMINAL_STATUSES = new Set<JobStatus>(["success", "failed", "cancelled"]);

export const STATUS_LABELS: Record<string, string> = {
  pending: "ממתין",
  validating: "מאמת",
  running: "רץ",
  success: "הצליח",
  failed: "נכשל",
  cancelled: "בוטל",
};

export const JOB_TYPE_LABELS: Record<string, string> = {
  run: "ריצה בודדת",
  grid_search: "סריקה",
};
