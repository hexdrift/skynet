import type { ProbeScalingFit } from "@/shared/lib/api";
import type { CatalogModel } from "@/shared/types/api";

export type RowStatus = "pending" | "running" | "done" | "error";

export interface TrajectoryPoint {
  step: number;
  score: number;
}

export interface ProbeLogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
}

export interface ModelRow {
  position: number;
  model: string;
  label: string;
  provider: string;
  status: RowStatus;
  logs: ProbeLogEntry[];
  score: number | null;
  scaling: ProbeScalingFit | null;
  trajectory: TrajectoryPoint[];
  durationMs: number | null;
  errorMessage: string | null;
  startedAt: number | null;
}

export function rowAsymptote(row: ModelRow): number | null {
  const signal = row.scaling?.signal;
  if ((signal === "strong" || signal === "observed") && row.scaling?.asymptote != null) {
    return row.scaling.asymptote;
  }
  return null;
}

export function rowRankingScore(row: ModelRow): number {
  return rowAsymptote(row) ?? row.score ?? -Infinity;
}

export const MIN_ROWS = 16;
export const MAX_LOG_LINES = 60;
export const MODEL_COLORS = [
  "#3D2E22",
  "#C8A882",
  "#8C7A6B",
  "#5B7B7A",
  "#A85A4A",
  "#6B8E23",
  "#7A6B8C",
  "#B8860B",
];

export function rowColor(row: ModelRow): string {
  return MODEL_COLORS[row.position % MODEL_COLORS.length]!;
}

export function bestSoFar(points: TrajectoryPoint[]): TrajectoryPoint[] {
  const out: TrajectoryPoint[] = [];
  let max = -Infinity;
  for (const p of points) {
    max = Math.max(max, p.score);
    out.push({ step: p.step, score: max });
  }
  return out;
}
export const EXCLUDE_PATTERN =
  /preview|audio|realtime|search|embedding|tts|dall-?e|image|whisper|vision|container|chatgpt|-latest$/i;
export const DEPRECATED_PATTERN =
  /gpt-3\.5|gpt-4$|gpt-4-(\d{4}|turbo)|claude-(1|2|instant)|gemini-1/i;
export const TINY_PATTERN = /nano|tiny/i;
export const SMALL_PATTERN = /mini|small|haiku|flash/i;

export function scoreModel(value: string): number {
  const v = value.toLowerCase();
  let score = 0;
  const versionMatch = v.match(/[-/](\d+(?:\.\d+)?)/);
  if (versionMatch && versionMatch[1]) score += parseFloat(versionMatch[1]) * 100;
  if (TINY_PATTERN.test(v)) score -= 60;
  else if (SMALL_PATTERN.test(v)) score -= 40;
  if (/opus/.test(v)) score += 10;
  else if (/sonnet/.test(v)) score += 5;
  if (/-(chat|instruct|api)(-|$)/.test(v)) score -= 5;
  return score;
}

export function smartDefaults(models: CatalogModel[]): Set<string> {
  const eligible = models
    .filter((m) => !EXCLUDE_PATTERN.test(m.value) && !DEPRECATED_PATTERN.test(m.value))
    .sort((a, b) => scoreModel(b.value) - scoreModel(a.value));
  const seen = new Set<string>();
  const picks = new Set<string>();
  for (const m of eligible) {
    if (picks.size >= 5) break;
    if (seen.has(m.provider)) continue;
    seen.add(m.provider);
    picks.add(m.value);
  }
  return picks;
}

export function groupByProvider(models: CatalogModel[]): Map<string, CatalogModel[]> {
  const out = new Map<string, CatalogModel[]>();
  for (const m of models) {
    const list = out.get(m.provider) ?? [];
    list.push(m);
    out.set(m.provider, list);
  }
  return out;
}
