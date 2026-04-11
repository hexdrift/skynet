/**
 * Shared formatting utilities
 * Pure functions for dates, numbers, durations, and data display
 * Consolidated from dashboard and optimizations formatters
 * All Hebrew strings and RTL-aware
 */

import type { OptimizationSummaryResponse } from "@/shared/types/api";

/* ── Date & Time Formatting ── */

/**
 * Format ISO date string to Hebrew locale
 * @example "2026-04-11T12:30:00" → "11/04/2026, 12:30:00"
 */
export function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("he-IL");
  } catch {
    return iso;
  }
}

/**
 * Format ISO date string to short Hebrew date
 * @example "2026-04-11T12:30:00" → "11/04/2026"
 */
export function formatDateShort(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("he-IL");
  } catch {
    return iso;
  }
}

/**
 * Format ISO date string to Hebrew time only
 * @example "2026-04-11T12:30:00" → "12:30:00"
 */
export function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("he-IL");
  } catch {
    return iso;
  }
}

/**
 * Format ISO date as relative time in Hebrew
 * @example "לפני 5 דק'" / "לפני 2 שע'" / "לפני 3 ימים"
 */
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
 * Format log timestamp for display
 * @example "2026-03-30T23:32:45.971393" → "30/03 23:32:45"
 */
export function formatLogTimestamp(ts: string): string {
  const m = ts.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/);
  if (!m) return ts;
  const [, , mm, dd, hh, mi, ss] = m;
  return `${dd}/${mm} ${hh}:${mi}:${ss}`;
}

/**
 * Group log timestamps by minute for filtering
 * @example "2026-03-30T23:32:45" → "30/03 23:32"
 */
export function logTimeBucket(ts: string): string {
  const m = ts.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (!m) return ts;
  const [, , mm, dd, hh, mi] = m;
  return `${dd}/${mm} ${hh}:${mi}`;
}

/* ── Duration Formatting ── */

/**
 * Format duration in seconds as HH:MM:SS or MM:SS
 * @example 3665 → "1:01:05", 125 → "2:05"
 */
export function formatDuration(seconds: number | undefined | null): string {
  if (seconds == null) return "—";
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  if (hrs > 0) return `${hrs}:${pad(mins)}:${pad(secs)}`;
  return `${mins}:${pad(secs)}`;
}

/**
 * Alias for formatDuration for backwards compatibility
 */
export const formatElapsed = formatDuration;

/* ── Number Formatting ── */

/**
 * Format a number (0..1 or 0..100) as percentage
 * @example 0.856 → "85.6%", 85.6 → "85.6%"
 */
export function formatPercent(n: number | undefined | null): string {
  if (n == null) return "—";
  const pct = n > 1 ? n : n * 100;
  return `${pct.toFixed(1)}%`;
}

/**
 * Format improvement metric with +/- sign
 * @example 0.15 → "+15.0%", -0.05 → "-5.0%"
 */
export function formatImprovement(v: number | undefined | null): string {
  if (v == null) return "—";
  const pct = Math.abs(v) > 1 ? v : v * 100;
  return pct >= 0 ? `+${pct.toFixed(1)}%` : `${pct.toFixed(1)}%`;
}

/**
 * Format large numbers with thousands separators (Hebrew locale)
 * @example 1234567 → "1,234,567"
 */
export function formatNumber(n: number | undefined | null): string {
  if (n == null) return "—";
  return new Intl.NumberFormat("he-IL").format(n);
}

/**
 * Format file size in bytes to human-readable string
 * @example 1536 → "1.5 KB", 2097152 → "2.0 MB"
 */
export function formatFileSize(bytes: number | undefined | null): string {
  if (bytes == null || bytes === 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${units[i]}`;
}

/* ── Data Formatting ── */

/**
 * Format unknown value as JSON preview
 */
export function jsonPreview(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "object") return JSON.stringify(v, null, 2);
  return String(v);
}

/**
 * Format output value (string, number, boolean, or JSON)
 */
export function formatOutput(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

/**
 * Format ID (passthrough, for consistency)
 */
export function formatId(id: string): string {
  return id;
}

/* ── Job Score Utilities ── */

/**
 * Normalize improvement value to 0..100 range
 * Handles both normalized (0..1) and pre-scaled (>1) inputs
 */
export function normalizeImprovement(improvement: number): number {
  return Math.abs(improvement) > 1 ? improvement : improvement * 100;
}

/**
 * Extract score parts from job summary for charts and tables
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
