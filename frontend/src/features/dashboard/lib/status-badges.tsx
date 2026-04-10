"use client";

import type React from "react";
import { Badge } from "@/components/ui/badge";
import { STATUS_LABELS } from "@/lib/constants";
import type { OptimizationSummaryResponse, JobStatus } from "@/lib/types";
import { formatPercent } from "./formatters";

export function statusBadge(status: JobStatus) {
  const label = STATUS_LABELS[status] ?? status;
  switch (status) {
    case "pending":
      return (
        <Badge variant="outline" className="status-pill-pending">
          {label}
        </Badge>
      );
    case "validating":
      return (
        <Badge variant="outline" className="status-pill-running">
          {label}
        </Badge>
      );
    case "running":
      return (
        <Badge variant="outline" className="status-pill-running animate-pulse">
          {label}
        </Badge>
      );
    case "success":
      return (
        <Badge variant="outline" className="status-pill-success">
          {label}
        </Badge>
      );
    case "failed":
      return (
        <Badge variant="outline" className="status-pill-failed">
          {label}
        </Badge>
      );
    case "cancelled":
      return (
        <Badge variant="outline" className="status-pill-cancelled">
          {label}
        </Badge>
      );
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
}

export function typeBadge(jobType: string) {
  if (jobType === "grid_search") {
    return (
      <Badge variant="outline" className="border-primary/30 text-primary">
        סריקה
      </Badge>
    );
  }
  return <Badge variant="secondary">ריצה בודדת</Badge>;
}

/**
 * Renders a job's baseline -> optimized score with percentage improvement.
 * Colour-codes by sign of improvement; shows best-pair label for grid searches.
 */
export function formatScore(job: OptimizationSummaryResponse): React.ReactNode {
  const baseline = job.baseline_test_metric;
  const optimized = job.optimized_test_metric;
  const improvement = job.metric_improvement;

  if (baseline == null && optimized == null) return "-";

  if (baseline != null && optimized != null && improvement != null) {
    const color =
      improvement > 0
        ? "text-[var(--success)]"
        : improvement < 0
          ? "text-[var(--danger)]"
          : "text-muted-foreground";
    const sign = improvement > 0 ? "+" : "";
    return (
      <span className="flex flex-col gap-0.5">
        <span className="flex items-center gap-1 text-xs">
          <span className="text-muted-foreground">{formatPercent(baseline)}</span>
          <span className="text-muted-foreground/50">&larr;</span>
          <span className="font-medium">{formatPercent(optimized)}</span>
          <span className={`${color} font-medium`}>
            ({sign}
            {(Math.abs(improvement) > 1 ? improvement : improvement * 100).toFixed(1)}%)
          </span>
        </span>
        {job.best_pair_label && (
          <span
            className="text-[10px] text-muted-foreground truncate max-w-[160px]"
            title={job.best_pair_label}
          >
            {job.best_pair_label}
          </span>
        )}
      </span>
    );
  }

  if (optimized != null)
    return <span className="font-medium text-xs">{formatPercent(optimized)}</span>;
  if (baseline != null)
    return <span className="text-muted-foreground text-xs">{formatPercent(baseline)}</span>;
  return "-";
}
