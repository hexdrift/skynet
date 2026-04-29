/**
 * Pure formatters and projection helpers for the explore slice.
 *
 * Score values from the public dashboard are already on a 0–100 scale —
 * see `backend/service_gateway/recommendations._extract_scores`. Any value
 * received as a 0–1 ratio is an upstream bug; this module canonicalizes
 * to 0–100 without a runtime guess.
 */

import { formatMsg, msg } from "@/shared/lib/messages";

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
 * Returns a relative-time duration (no "לפני" prefix) or null when the
 * timestamp is missing/unparseable. The caller decides whether to render a
 * sentinel ("—") or prepend the prefix.
 *
 * Future timestamps (clock skew, system clock drift) clamp to "just now"
 * rather than reading as a positive duration into the past.
 */
export function formatAgo(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const diffMs = Math.max(0, Date.now() - then);
  const mins = Math.round(diffMs / 60_000);
  if (mins < 1) return msg("explore.detail.time.now");
  if (mins < 60) return formatMsg("explore.detail.time.minutes", { p1: mins });
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return formatMsg("explore.detail.time.hours", { p1: hrs });
  const days = Math.round(hrs / 24);
  return formatMsg("explore.detail.time.days", { p1: days });
}

export function colorForPoint(match: boolean): string {
  const chroma = match ? 0.05 : 0.01;
  return `oklch(0.3 ${chroma} 40)`;
}

export function clampView(v: View, size: { w: number; h: number }): View {
  const maxPan = Math.max(size.w, size.h) * Math.max(0, v.k - 1);
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
