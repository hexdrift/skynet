import { TERMS } from "@/shared/lib/terms";
import type { JobStatus, OptimizationType } from "@/shared/types/api";

export const ACTIVE_STATUSES = new Set<JobStatus>(["pending", "validating", "running"]);
export const TERMINAL_STATUSES = new Set<JobStatus>(["success", "failed", "cancelled"]);

export const STATUS_LABELS: Record<JobStatus, string> = {
  pending: TERMS.statusPending,
  validating: TERMS.statusValidating,
  running: TERMS.statusRunning,
  success: TERMS.statusSuccess,
  failed: TERMS.statusFailed,
  cancelled: TERMS.statusCancelled,
};

export const JOB_TYPE_LABELS: Record<OptimizationType, string> = {
  run: TERMS.optimizationTypeRun,
  grid_search: TERMS.optimizationTypeGrid,
};

export function getStatusLabel(status: string): string {
  return isJobStatus(status) ? STATUS_LABELS[status] : status;
}

export function getJobTypeLabel(type: string): string {
  return isOptimizationType(type) ? JOB_TYPE_LABELS[type] : type;
}

export function isActiveStatus(status: string): status is JobStatus {
  return isJobStatus(status) && ACTIVE_STATUSES.has(status);
}

function isJobStatus(status: string): status is JobStatus {
  return status in STATUS_LABELS;
}

function isOptimizationType(type: string): type is OptimizationType {
  return type in JOB_TYPE_LABELS;
}
