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
    return (
      <span className="flex items-center gap-1 text-xs">
        <span className="text-muted-foreground">{formatPercent(baseline)}</span>
        <span className="text-muted-foreground/50">&larr;</span>
        <span className="font-medium">{formatPercent(optimized)}</span>
        <span className={`${color} font-medium`}>
          ({sign}
          {(Math.abs(improvement) > 1 ? improvement : improvement * 100).toFixed(1)}%)
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
