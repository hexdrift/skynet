/**
 * Pure formatters and projection helpers for the explore slice.
 *
 * Score values from the public dashboard are already on a 0–100 scale —
 * see `backend/service_gateway/embedding_pipeline._extract_scores`. Any
 * value received as a 0–1 ratio is an upstream bug; this module
 * canonicalizes to 0–100 without a runtime guess.
 */

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

// Spread cluster colors evenly around the hue circle. Lightness and chroma
// are held constant so palettes look coherent across granularity levels —
// only the spacing on the hue wheel changes when the slider moves.
//
// When there are fewer than two distinct clusters the palette collapses
// to the original warm monochrome — used by the tutorial demo data and by
// the very-small-N case where coloring adds no information.
export function colorForCluster(clusterId: number, clusterCount: number, match: boolean): string {
  if (clusterCount <= 1) {
    const chroma = match ? 0.05 : 0.01;
    return `oklch(0.3 ${chroma} 40)`;
  }
  const hue = (clusterId * 360) / clusterCount;
  const chroma = match ? 0.13 : 0.04;
  const lightness = match ? 0.55 : 0.62;
  return `oklch(${lightness} ${chroma} ${hue})`;
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

export type ClusterLabel = {
  clusterId: number;
  label: string;
  cx: number;
  cy: number;
  count: number;
};

// Picks one label per cluster at the requested granularity by taking the
// modal task_name among each cluster's points. Centroid is the mean of
// the points' raw x/y in [-1, 1] — the canvas projects to pixels later.
//
// Clusters with fewer than minPoints members or with no labeled points
// are dropped — they're typically too small to read or unhelpful at the
// current zoom level.
export function computeClusterLabels(
  points: ReadonlyArray<{
    x: number;
    y: number;
    task_name: string | null;
    cluster_levels?: number[];
  }>,
  granularityLevel: number,
  minPoints = 3,
): ClusterLabel[] {
  if (points.length === 0) return [];
  type Bucket = { sumX: number; sumY: number; n: number; tasks: Map<string, number> };
  const buckets = new Map<number, Bucket>();
  for (const p of points) {
    const cid = (p.cluster_levels ?? [])[granularityLevel] ?? 0;
    let b = buckets.get(cid);
    if (!b) {
      b = { sumX: 0, sumY: 0, n: 0, tasks: new Map() };
      buckets.set(cid, b);
    }
    b.sumX += p.x;
    b.sumY += p.y;
    b.n += 1;
    if (p.task_name) b.tasks.set(p.task_name, (b.tasks.get(p.task_name) ?? 0) + 1);
  }
  const out: ClusterLabel[] = [];
  for (const [clusterId, b] of buckets) {
    if (b.n < minPoints) continue;
    let topTask: string | null = null;
    let topCount = 0;
    for (const [t, c] of b.tasks) {
      if (c > topCount) {
        topTask = t;
        topCount = c;
      }
    }
    if (!topTask) continue;
    out.push({
      clusterId,
      label: topTask,
      cx: b.sumX / b.n,
      cy: b.sumY / b.n,
      count: b.n,
    });
  }
  return out;
}

export type ClusterHull = {
  clusterId: number;
  // Hull vertices in normalized [-1, 1] space, ordered counter-clockwise.
  hull: Array<{ x: number; y: number }>;
  count: number;
};

// Convex hull per cluster at the given granularity, used to draw cluster
// boundaries and to hit-test "is the cursor inside this cluster?". Clusters
// with fewer than minPoints members are dropped — a triangle is the smallest
// shape that reads as a region.
export function computeClusterHulls(
  points: ReadonlyArray<{
    x: number;
    y: number;
    cluster_levels?: number[];
  }>,
  granularityLevel: number,
  minPoints = 3,
): ClusterHull[] {
  if (points.length === 0) return [];
  const buckets = new Map<number, Array<{ x: number; y: number }>>();
  for (const p of points) {
    const cid = (p.cluster_levels ?? [])[granularityLevel] ?? 0;
    let arr = buckets.get(cid);
    if (!arr) {
      arr = [];
      buckets.set(cid, arr);
    }
    arr.push({ x: clampNorm(p.x), y: clampNorm(p.y) });
  }
  const out: ClusterHull[] = [];
  for (const [clusterId, pts] of buckets) {
    if (pts.length < minPoints) continue;
    const hull = convexHull(pts);
    if (hull.length < 3) continue;
    out.push({ clusterId, hull, count: pts.length });
  }
  return out;
}

// Andrew's monotone chain — O(n log n). Returns vertices in CCW order.
function convexHull(
  points: ReadonlyArray<{ x: number; y: number }>,
): Array<{ x: number; y: number }> {
  const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  const cross = (
    o: { x: number; y: number },
    a: { x: number; y: number },
    b: { x: number; y: number },
  ) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const lower: Array<{ x: number; y: number }> = [];
  for (const p of sorted) {
    while (
      lower.length >= 2 &&
      cross(lower[lower.length - 2]!, lower[lower.length - 1]!, p) <= 0
    ) {
      lower.pop();
    }
    lower.push(p);
  }
  const upper: Array<{ x: number; y: number }> = [];
  for (let i = sorted.length - 1; i >= 0; i--) {
    const p = sorted[i]!;
    while (
      upper.length >= 2 &&
      cross(upper[upper.length - 2]!, upper[upper.length - 1]!, p) <= 0
    ) {
      upper.pop();
    }
    upper.push(p);
  }
  lower.pop();
  upper.pop();
  return lower.concat(upper);
}

// Ray-casting test. Used to detect cluster hover when the cursor is in
// empty space inside a hull but not directly over a point.
export function pointInPolygon(
  x: number,
  y: number,
  polygon: ReadonlyArray<{ x: number; y: number }>,
): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i]!.x;
    const yi = polygon[i]!.y;
    const xj = polygon[j]!.x;
    const yj = polygon[j]!.y;
    const intersect =
      (yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

// Fallback for when the backend meta is absent (tutorial demo points,
// half-rolled-back deploy) but the points themselves carry cluster_levels.
// Walks the points once and reports the max id + 1 at each level.
export function deriveLevelCounts(points: ReadonlyArray<{ cluster_levels?: number[] }>): number[] {
  if (points.length === 0) return [];
  const sample = points[0]?.cluster_levels;
  if (!sample || sample.length === 0) return [];
  const counts = sample.map(() => 0);
  for (const p of points) {
    const lvls = p.cluster_levels ?? [];
    const n = Math.min(lvls.length, counts.length);
    for (let i = 0; i < n; i++) {
      const c = (lvls[i] ?? 0) + 1;
      if (c > counts[i]!) counts[i] = c;
    }
  }
  return counts;
}
