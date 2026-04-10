/**
 * Pure formatter helpers for the dashboard.
 *
 * All functions are side-effect-free and return either strings or numbers.
 * Badge / React-node formatters live in ./status-badges.tsx so this module
 * stays .ts-only.
 */
import type { OptimizationSummaryResponse } from "@/lib/types";

export function formatElapsed(elapsedSeconds?: number): string {
  if (elapsedSeconds == null) return "-";
  const hrs = Math.floor(elapsedSeconds / 3600);
  const mins = Math.floor((elapsedSeconds % 3600) / 60);
  const secs = Math.floor(elapsedSeconds % 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  if (hrs > 0) return `${hrs}:${pad(mins)}:${pad(secs)}`;
  return `${mins}:${pad(secs)}`;
}

export function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("he-IL");
  } catch {
    return iso;
  }
}

export function formatRelativeTime(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "עכשיו";
    if (mins < 60) return `לפני ${mins} דק'`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `לפני ${hours} שע'`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `לפני ${days} ימים`;
    return formatDate(iso);
  } catch {
    return formatDate(iso);
  }
}

/**
 * Format a numeric score (0..1 or 0..100) as a percentage string.
 * Kept separate from {@link formatScore} so it can be reused by charts.
 */
export function formatPercent(n: number): string {
  return (n > 1 ? n : n * 100).toFixed(1) + "%";
}

export function formatId(id: string): string {
  return id;
}

/**
 * Returns the raw numeric improvement scaled to 0..100 range.
 * Handles both normalized (0..1) and pre-scaled (>1) inputs.
 */
export function normalizeImprovement(improvement: number): number {
  return Math.abs(improvement) > 1 ? improvement : improvement * 100;
}

/**
 * Extracts the best metrics from a job summary in a stable shape
 * the dashboard table + charts both consume.
 */
export interface JobScoreParts {
  baseline: number | null;
  optimized: number | null;
  improvement: number | null;
  bestPairLabel: string | null;
}

export function extractScoreParts(job: OptimizationSummaryResponse): JobScoreParts {
  return {
    baseline: job.baseline_test_metric ?? null,
    optimized: job.optimized_test_metric ?? null,
    improvement: job.metric_improvement ?? null,
    bestPairLabel: job.best_pair_label ?? null,
  };
}
