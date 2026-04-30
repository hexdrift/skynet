"use client";

import { Badge } from "@/shared/ui/primitives/badge";
import { PingDot } from "@/shared/ui/ping-dot";
import { getStatusLabel } from "@/shared/constants/job-status";
import type { JobStatus } from "@/shared/types/api";

interface StatusBadgeProps {
  status: JobStatus | string;
  className?: string;
  /** Compact variant for table rows: smaller text, no PingDot. */
  compact?: boolean;
}

const STATUS_COLORS: Record<string, string> = {
  pending: "status-pill-pending",
  validating: "status-pill-running",
  running: "status-pill-running",
  success: "status-pill-success",
  failed: "status-pill-failed",
  cancelled: "status-pill-cancelled",
};

export function StatusBadge({ status, className = "", compact = false }: StatusBadgeProps) {
  const label = getStatusLabel(status);
  const colorClass = STATUS_COLORS[status] ?? "";
  const isRunning = status === "running";
  const sizeClass = compact ? "" : "text-[0.8125rem] px-3 py-1 font-bold tracking-wide";

  return (
    <Badge
      variant="outline"
      className={`${sizeClass} ${colorClass} ${isRunning ? "animate-pulse motion-reduce:animate-none" : ""} ${className}`.trim()}
    >
      {isRunning && !compact && <PingDot className="me-1" />}
      {label}
    </Badge>
  );
}
