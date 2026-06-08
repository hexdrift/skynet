"use client";

import type React from "react";
import { Badge } from "@/shared/ui/primitives/badge";
import type { OptimizationSummaryResponse } from "@/shared/types/api";
import { formatPercent } from "@/shared/lib";
import { msg } from "@/shared/lib/messages";

export function typeBadge(jobType: string) {
  if (jobType === "grid_search") {
    return (
      <Badge variant="outline" className="border-primary/30 text-primary">
        {msg("auto.features.dashboard.lib.status.badges.1")}
      </Badge>
    );
  }
  return <Badge variant="secondary">{msg("auto.features.dashboard.lib.status.badges.2")}</Badge>;
}

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
    const deltaPct = improvement.toFixed(1);
    return (
      <span
        className="inline-flex items-center gap-1 text-xs whitespace-nowrap"
        title={`${formatPercent(baseline)} → ${formatPercent(optimized)}`}
      >
        <span className="font-medium">{formatPercent(optimized)}</span>
        <span className={`${color} font-medium`}>
          ({sign}
          {deltaPct}%)
        </span>
      </span>
    );
  }

  if (optimized != null)
    return <span className="font-medium text-xs">{formatPercent(optimized)}</span>;
  if (baseline != null)
    return <span className="text-muted-foreground text-xs">{formatPercent(baseline)}</span>;
  return "-";
}
