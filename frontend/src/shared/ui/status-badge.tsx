"use client";

import type { ReactNode } from "react";
import { Badge } from "@/shared/ui/primitives/badge";
import { PingDot } from "@/shared/ui/ping-dot";
import { getStatusLabel } from "@/shared/constants/job-status";
import { cn } from "@/shared/lib/utils";
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
  paused: "status-pill-paused",
};

const COMPACT_CLASS = "px-2 py-0.5 text-[0.6875rem] font-semibold";

export function StatusBadge({ status, className = "", compact = false }: StatusBadgeProps) {
  const label = getStatusLabel(status);
  const colorClass = STATUS_COLORS[status] ?? "";
  const isRunning = status === "running";
  const sizeClass = compact ? COMPACT_CLASS : "text-[0.8125rem] px-3 py-1 font-bold tracking-wide";

  return (
    <Badge
      variant="outline"
      size={compact ? "sm" : "md"}
      className={cn(
        sizeClass,
        colorClass,
        isRunning && "animate-pulse motion-reduce:animate-none",
        className,
      )}
    >
      {isRunning && !compact && <PingDot className="me-1" />}
      {label}
    </Badge>
  );
}

export type StatusTone = "success" | "running" | "failed" | "pending" | "cancelled" | "paused";

/** Compact status pill for non-job statuses (connectors, keys, transactions). */
export function StatusPill({
  tone,
  className,
  children,
}: {
  tone: StatusTone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Badge
      variant="outline"
      size="sm"
      className={cn(COMPACT_CLASS, `status-pill-${tone}`, className)}
    >
      {children}
    </Badge>
  );
}
