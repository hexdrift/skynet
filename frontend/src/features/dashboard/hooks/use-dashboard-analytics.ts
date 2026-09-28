import { useCallback, useEffect, useState } from "react";
import { getDashboardAnalytics, type DashboardAnalytics } from "@/shared/lib/api";
import type { AnalyticsBucket, AnalyticsRange } from "./use-analytics-filters";

type UseDashboardAnalyticsArgs = {
  sessionUser: string;
  isAdmin: boolean;
  activeTab: string;
  range: AnalyticsRange;
  optimizer: string;
  model: string;
  status: string;
  date: string | null;
  dateTo: string | null;
  owner: string | null;
  access: string | null;
  jobType: string | null;
  module: string | null;
  improvement: AnalyticsBucket | null;
  runtime: AnalyticsBucket | null;
  dataset: AnalyticsBucket | null;
};

export type UseDashboardAnalyticsReturn = {
  analyticsData: DashboardAnalytics | null;
  setAnalyticsData: React.Dispatch<React.SetStateAction<DashboardAnalytics | null>>;
  analyticsLoading: boolean;
  fetchDashboardAnalytics: () => Promise<void>;
};

const RANGE_DAYS: Record<AnalyticsRange, number | undefined> = {
  "7d": 7,
  "30d": 30,
  "90d": 90,
  all: undefined,
};

export function useDashboardAnalytics({
  sessionUser,
  isAdmin,
  activeTab,
  range,
  optimizer,
  model,
  status,
  date,
  dateTo,
  owner,
  access,
  jobType,
  module,
  improvement,
  runtime,
  dataset,
}: UseDashboardAnalyticsArgs): UseDashboardAnalyticsReturn {
  const [analyticsData, setAnalyticsData] = useState<DashboardAnalytics | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);

  const fetchDashboardAnalytics = useCallback(async () => {
    const username = isAdmin ? undefined : sessionUser || undefined;
    // Non-admins aggregate over their own + shared runs; admins see all.
    const includeShared = !isAdmin;
    setAnalyticsLoading(true);
    try {
      const result = await getDashboardAnalytics({
        username,
        days: RANGE_DAYS[range],
        optimizer: optimizer !== "all" ? optimizer : undefined,
        model: model !== "all" ? model : undefined,
        status: status !== "all" ? status : undefined,
        date: date ?? undefined,
        date_to: dateTo ?? undefined,
        include_shared: includeShared,
        owner: owner ?? undefined,
        access: access ?? undefined,
        job_type: jobType ?? undefined,
        module: module ?? undefined,
        improvement_min: improvement?.lower,
        improvement_max: improvement?.upper,
        runtime_min: runtime?.lower,
        runtime_max: runtime?.upper,
        dataset_min: dataset?.lower,
        dataset_max: dataset?.upper,
      });
      setAnalyticsData(result);
    } catch {
      // Leave analyticsData untouched; jobs-list error surfaces network issues.
    } finally {
      setAnalyticsLoading(false);
    }
  }, [
    isAdmin,
    sessionUser,
    range,
    optimizer,
    model,
    status,
    date,
    dateTo,
    owner,
    access,
    jobType,
    module,
    improvement,
    runtime,
    dataset,
  ]);

  useEffect(() => {
    if (activeTab !== "analytics") return;
    void fetchDashboardAnalytics();
  }, [activeTab, fetchDashboardAnalytics]);

  return {
    analyticsData,
    setAnalyticsData,
    analyticsLoading,
    fetchDashboardAnalytics,
  };
}
