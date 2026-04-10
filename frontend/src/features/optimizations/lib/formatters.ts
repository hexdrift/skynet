/**
 * Pure formatter helpers for the optimization detail page.
 *
 * Extracted from app/optimizations/[id]/page.tsx. These functions are
 * side-effect-free and testable in isolation.
 */

export function formatPercent(v: number | undefined | null): string {
  if (v == null) return "—";
  // Backend may return 0-1 (fraction) or 0-100 (percentage)
  const pct = v > 1 ? v : v * 100;
  return `${pct.toFixed(1)}%`;
}

export function formatImprovement(v: number | undefined | null): string {
  if (v == null) return "—";
  // Backend may return 0-1 (fraction) or larger (already percentage points)
  const pct = Math.abs(v) > 1 ? v : v * 100;
  return pct >= 0 ? `+${pct.toFixed(1)}%` : `${pct.toFixed(1)}%`;
}

export function jsonPreview(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "object") return JSON.stringify(v, null, 2);
  return String(v);
}

export function formatDuration(seconds: number): string {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  if (hrs > 0) return `${hrs}:${pad(mins)}:${pad(secs)}`;
  return `${mins}:${pad(secs)}`;
}
