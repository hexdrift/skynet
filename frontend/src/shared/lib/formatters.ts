import { formatMsg, msg } from "@/shared/lib/messages";

/**
 * Format ISO date string to Hebrew locale
 * @example "2026-04-11T12:30:00" → "11/04/2026, 12:30:00"
 */
export function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString("he-IL");
}

/**
 * Format ISO date as relative time in Hebrew
 * @example localized relative time for minutes, hours, or days ago
 */
export function formatRelativeTime(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return msg("auto.shared.lib.formatters.literal.1");
    if (mins < 60) return formatMsg("auto.shared.lib.formatters.template.1", { p1: mins });
    const hours = Math.floor(mins / 60);
    if (hours < 24) return formatMsg("auto.shared.lib.formatters.template.2", { p1: hours });
    const days = Math.floor(hours / 24);
    if (days < 7) return formatMsg("auto.shared.lib.formatters.template.3", { p1: days });
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

/**
 * Format duration in seconds as HH:MM:SS or MM:SS
 * @example 3665 → "1:01:05", 125 → "2:05"
 */
export function formatDuration(seconds: number | undefined | null): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "—";
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  if (hrs > 0) return `${hrs}:${pad(mins)}:${pad(secs)}`;
  return `${mins}:${pad(secs)}`;
}

export const formatElapsed = formatDuration;

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

export function jsonPreview(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "object") {
    try {
      return JSON.stringify(v, null, 2);
    } catch {
      return String(v);
    }
  }
  return String(v);
}

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

export function formatId(id: string): string {
  return id;
}

