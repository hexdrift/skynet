import { useCallback, useEffect, useState } from "react";
import { getDashboardAnalytics, type DashboardAnalytics } from "@/shared/lib/api";

type UseDashboardAnalyticsArgs = {
  sessionUser: string;
  isAdmin: boolean;
  activeTab: string;
  model: string;
  status: string;
  jobId: string | null;
  date: string | null;
};

export type UseDashboardAnalyticsReturn = {
  analyticsData: DashboardAnalytics | null;
  setAnalyticsData: React.Dispatch<React.SetStateAction<DashboardAnalytics | null>>;
  analyticsLoading: boolean;
  fetchDashboardAnalytics: () => Promise<void>;
};

export function useDashboardAnalytics({
  sessionUser,
  isAdmin,
  activeTab,
  model,
  status,
  jobId,
  date,
}: UseDashboardAnalyticsArgs): UseDashboardAnalyticsReturn {
  const [analyticsData, setAnalyticsData] = useState<DashboardAnalytics | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);

  const fetchDashboardAnalytics = useCallback(async () => {
    const username = isAdmin ? undefined : sessionUser || undefined;
    setAnalyticsLoading(true);
    try {
      const result = await getDashboardAnalytics({
        username,
        model: model !== "all" ? model : undefined,
        status: status !== "all" ? status : undefined,
        optimization_id: jobId ?? undefined,
        date: date ?? undefined,
      });
      setAnalyticsData(result);
    } catch {
      // Leave analyticsData untouched; jobs-list error surfaces network issues.
    } finally {
      setAnalyticsLoading(false);
    }
  }, [isAdmin, sessionUser, model, status, jobId, date]);

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
