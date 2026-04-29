import type { SidebarJobItem } from "@/shared/lib/api";
import { isActiveStatus } from "@/shared/constants/job-status";
import { msg } from "@/shared/lib/messages";

export interface JobGroup {
  label: string;
  jobs: SidebarJobItem[];
}

/**
 * Case-insensitive substring match across the sidebar's searchable fields.
 */
export function matchesJobSearch(job: SidebarJobItem, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (
    (job.name ?? "").toLowerCase().includes(q) ||
    (job.module_name ?? "").toLowerCase().includes(q) ||
    job.optimization_id.toLowerCase().includes(q) ||
    (job.optimizer_name ?? "").toLowerCase().includes(q) ||
    (job.model_name ?? "").toLowerCase().includes(q) ||
    (job.username ?? "").toLowerCase().includes(q)
  );
}

/**
 * Bucket jobs into pinned → active → today → yesterday → this week → older.
 * Empty buckets are dropped.
 */
export function groupJobsByRecency(jobs: SidebarJobItem[], now: Date = new Date()): JobGroup[] {
  const groups: JobGroup[] = [];
  const pinned: SidebarJobItem[] = [];
  const active: SidebarJobItem[] = [];
  const today: SidebarJobItem[] = [];
  const yesterday: SidebarJobItem[] = [];
  const thisWeek: SidebarJobItem[] = [];
  const older: SidebarJobItem[] = [];

  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart.getTime() - 86400000);
  const weekStart = new Date(todayStart.getTime() - 7 * 86400000);

  for (const job of jobs) {
    if (job.pinned) {
      pinned.push(job);
      continue;
    }
    if (isActiveStatus(job.status)) {
      active.push(job);
      continue;
    }
    // Missing created_at falls through epoch (1970) → "older" bucket.
    const created = new Date(job.created_at ?? 0);
    if (created >= todayStart) today.push(job);
    else if (created >= yesterdayStart) yesterday.push(job);
    else if (created >= weekStart) thisWeek.push(job);
    else older.push(job);
  }

  if (pinned.length)
    groups.push({ label: msg("auto.features.sidebar.lib.group.jobs.literal.1"), jobs: pinned });
  if (active.length)
    groups.push({ label: msg("auto.features.sidebar.lib.group.jobs.literal.2"), jobs: active });
  if (today.length)
    groups.push({ label: msg("auto.features.sidebar.lib.group.jobs.literal.3"), jobs: today });
  if (yesterday.length)
    groups.push({ label: msg("auto.features.sidebar.lib.group.jobs.literal.4"), jobs: yesterday });
  if (thisWeek.length)
    groups.push({ label: msg("auto.features.sidebar.lib.group.jobs.literal.5"), jobs: thisWeek });
  if (older.length)
    groups.push({ label: msg("auto.features.sidebar.lib.group.jobs.literal.6"), jobs: older });

  return groups;
}
