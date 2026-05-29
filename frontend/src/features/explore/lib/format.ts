/**
 * Pure formatters and projection helpers for the explore slice.
 *
 * Score values from the public dashboard are already on a 0–100 scale —
 * see `backend/service_gateway/embedding_pipeline._extract_scores`. Any
 * value received as a 0–1 ratio is an upstream bug; this module
 * canonicalizes to 0–100 without a runtime guess.
 */

import { msg } from "@/shared/lib/messages";

export type GainBadge = {
  text: string;
  kind: "positive" | "negative" | "neutral";
};

export type View = {
  k: number;
  tx: number;
  ty: number;
};

export function formatScore(value: number | null | undefined): string | null {
  if (value == null || !Number.isFinite(value)) return null;
  return value.toFixed(1);
}

export function formatMetric(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toFixed(1);
}

export function formatGain(
  baseline: number | null | undefined,
  optimized: number | null | undefined,
): GainBadge | null {
  if (baseline == null || optimized == null) return null;
  if (!Number.isFinite(baseline) || !Number.isFinite(optimized)) return null;
  const gain = optimized - baseline;
  if (Math.abs(gain) < 0.05) return { text: "0.0", kind: "neutral" };
  if (gain > 0) return { text: `+${gain.toFixed(1)}`, kind: "positive" };
  return { text: gain.toFixed(1), kind: "negative" };
}

/**
 * Format an ISO timestamp as a numeric date (e.g. "14.5.2026").
 * Returns "—" for missing/unparseable input so callers can render the result
 * directly without a null check.
 */
export function formatExploreDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("he-IL", { day: "numeric", month: "numeric", year: "numeric" });
}

// Constructing Intl.RelativeTimeFormat is expensive (locale data + ICU
// pattern parse). Lift to module scope so every row reuses one instance.
const RTF_HE = new Intl.RelativeTimeFormat("he", { numeric: "auto" });

/**
 * Hebrew relative time (now / yesterday / N days ago / last week) that
 * falls back to a short absolute date for items older than a month so the
 * row metadata never balloons. Returns "—" for missing/unparseable input.
 *
 * Uses Intl.RelativeTimeFormat with `numeric: "auto"` which already knows
 * the Hebrew dual form (yesterday / two days / two weeks) so we don't
 * reinvent the pluralization table.
 *
 * Future timestamps (server clock ahead of client) are clamped to "now"
 * rather than rendering "in N minutes" — a job's `created_at` should never
 * be in the future from the reader's perspective. Unit selection uses
 * `Math.floor` (completed units, matching date-fns convention) so
 * something 6h59m old reads as "6 hours ago", not "7" that then races
 * the day boundary.
 */
export function formatRelativeDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const diffMs = Math.max(0, Date.now() - d.getTime());
  const minutes = Math.floor(diffMs / 60_000);
  const hours = Math.floor(diffMs / 3_600_000);
  const days = Math.floor(diffMs / 86_400_000);
  if (minutes < 1) return msg("explore.relative.now");
  if (minutes < 60) return RTF_HE.format(-minutes, "minute");
  if (hours < 24) return RTF_HE.format(-hours, "hour");
  if (days < 7) return RTF_HE.format(-days, "day");
  if (days < 30) return RTF_HE.format(-Math.floor(days / 7), "week");
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleDateString("he-IL", {
    day: "numeric",
    month: "long",
    ...(sameYear ? {} : { year: "numeric" }),
  });
}

export function clampView(v: View, size: { w: number; h: number }): View {
  const maxPan = Math.max(size.w, size.h) * Math.max(0.35, v.k - 1);
  return {
    k: v.k,
    tx: Math.max(-maxPan, Math.min(maxPan, v.tx)),
    ty: Math.max(-maxPan, Math.min(maxPan, v.ty)),
  };
}

export function clampNorm(v: number): number {
  if (v < -1) return -1;
  if (v > 1) return 1;
  return v;
}
