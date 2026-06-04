import type { DashboardAnalytics, OptimizationCounts } from "@/shared/lib/api";
import type { OptimizationSummaryResponse, PaginatedJobsResponse } from "@/shared/types/api";
import { ACTIVE_STATUSES } from "@/shared/constants/job-status";

export type DashboardStats = {
  total: number;
  success: number;
  running: number;
  failed: number;
  shared: number;
} | null;

type GetDashboardStatsArgs = {
  data: PaginatedJobsResponse | null;
  filteredItems: OptimizationSummaryResponse[];
  counts: OptimizationCounts | null;
  analyticsData: DashboardAnalytics | null;
  activeTab: string;
};

export function getDashboardStats({
  data,
  filteredItems,
  counts,
  analyticsData,
  activeTab,
}: GetDashboardStatsArgs): DashboardStats {
  if (!data) return null;

  // "Shared with me" is a stable property of the caller, not of the active
  // tab or filter, so it always comes from the counts payload.
  const shared = counts?.shared ?? 0;

  if (activeTab === "analytics" && analyticsData) {
    return {
      total: analyticsData.filtered_total,
      success: analyticsData.success_count,
      running: analyticsData.running_count,
      failed: analyticsData.failed_count,
      shared,
    };
  }

  if (!counts) {
    return {
      total: filteredItems.length,
      success: filteredItems.filter((j) => j.status === "success").length,
      running: filteredItems.filter((j) => ACTIVE_STATUSES.has(j.status)).length,
      failed: filteredItems.filter((j) => j.status === "failed").length,
      shared,
    };
  }

  return {
    total: counts.total,
    success: counts.success,
    running: counts.pending + counts.validating + counts.running,
    failed: counts.failed,
    shared,
  };
}
