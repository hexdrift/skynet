"use client";

/**
 * Status badge component
 * Displays job status with appropriate color and animation
 * Consolidated from StatusBadge (features/optimizations) and statusBadge (features/dashboard)
 */

import { Badge } from "@/components/ui/badge";
import { STATUS_LABELS } from "@/lib/constants";
import type { JobStatus } from "@/lib/types";

interface StatusBadgeProps {
  status: JobStatus | string;
  className?: string;
}

const STATUS_COLORS: Record<string, string> = {
  pending: "status-pill-pending",
  validating: "status-pill-running",
  running: "status-pill-running",
  success: "status-pill-success",
  failed: "status-pill-failed",
  cancelled: "status-pill-cancelled",
};

export function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  const label = STATUS_LABELS[status] ?? status;
  const colorClass = STATUS_COLORS[status] ?? "";
  const isRunning = status === "running";

  return (
    <Badge
      variant="outline"
      className={`text-[13px] px-3 py-1 font-bold tracking-wide ${colorClass} ${isRunning ? "animate-pulse" : ""} ${className}`}
    >
      {isRunning && (
        <span className="relative flex size-2 me-1">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--warning)]/60" />
          <span className="relative inline-flex rounded-full size-2 bg-[var(--warning)]" />
        </span>
      )}
      {label}
    </Badge>
  );
}
