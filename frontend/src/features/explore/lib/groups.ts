/**
 * Variation grouping for the explore scatter.
 *
 * Backend dedups by ``compare_fingerprint`` (same task + same train/val/test
 * split) so two jobs that are row-by-row comparable arrive as one leader with
 * the rest in ``siblings``. Jobs that share a ``task_fingerprint`` but
 * evaluate on different splits arrive as separate points — the dot for each
 * is at its own UMAP coordinate. This module groups those points back together
 * by task so the canvas can render one shared marker per task (with a subtle
 * concentric ring when multiple variations exist).
 *
 * Rows without a ``task_fingerprint`` (legacy jobs that pre-date the field)
 * are never merged — each becomes its own singleton group keyed by its
 * ``optimization_id`` so they keep their own marker.
 */

import type { PublicDashboardPoint } from "@/shared/lib/api";

export interface VariationGroup {
  taskFingerprint: string;
  variations: PublicDashboardPoint[];
}

export interface VariationGrouping {
  leaders: PublicDashboardPoint[];
  byLeaderId: Map<string, PublicDashboardPoint[]>;
}

function parseCreatedAt(value: string | null): number {
  if (!value) return 0;
  const t = new Date(value).getTime();
  return Number.isNaN(t) ? 0 : t;
}

export function buildVariationGroups(points: PublicDashboardPoint[]): VariationGrouping {
  const groups = new Map<string, PublicDashboardPoint[]>();
  const order: string[] = [];
  for (const p of points) {
    const key = p.task_fingerprint ? `task:${p.task_fingerprint}` : `singleton:${p.optimization_id}`;
    let bucket = groups.get(key);
    if (!bucket) {
      bucket = [];
      groups.set(key, bucket);
      order.push(key);
    }
    bucket.push(p);
  }
  const leaders: PublicDashboardPoint[] = [];
  const byLeaderId = new Map<string, PublicDashboardPoint[]>();
  for (const key of order) {
    const bucket = groups.get(key)!;
    bucket.sort((a, b) => parseCreatedAt(b.created_at) - parseCreatedAt(a.created_at));
    const leader = bucket[0]!;
    leaders.push(leader);
    byLeaderId.set(leader.optimization_id, bucket);
  }
  return { leaders, byLeaderId };
}
