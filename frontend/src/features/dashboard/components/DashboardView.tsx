"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { BarChart3, Compass, TableIcon } from "lucide-react";
import { Skeleton } from "boneyard-js/react";
import { toast } from "react-toastify";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FadeIn } from "@/shared/ui/motion";
import { msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";
import { useColumnFilters, useColumnResize, type SortDir } from "@/shared/ui/excel-filter";
import { getJobTypeLabel, getStatusLabel } from "@/shared/constants/job-status";
import type { PaginatedJobsResponse } from "@/shared/types/api";
import type { DashboardAnalytics } from "@/shared/lib/api";
import { dashboardBones } from "@/features/dashboard/lib/bones";
import { registerTutorialHook, registerTutorialQuery } from "@/features/tutorial/lib/bridge";
import { transformChartData } from "../lib/transform-chart-data";
import { useQueueStatus } from "../hooks/use-queue-status";
import { useDashboardStats } from "../hooks/use-dashboard-stats";
import { useAnalyticsFilters } from "../hooks/use-analytics-filters";
import { useJobsList } from "../hooks/use-jobs-list";
import { useDashboardAnalytics } from "../hooks/use-dashboard-analytics";
import { useJobsRealtime } from "../hooks/use-jobs-realtime";
import { useBulkDelete } from "../hooks/use-bulk-delete";
import { DashboardHeader } from "./DashboardHeader";
import { QueueStatusAlert } from "./QueueStatusAlert";
import { BulkActionBar } from "./BulkActionBar";
import { DeleteDialogs } from "./DeleteDialogs";
import { JobsTab } from "./JobsTab";
import { AnalyticsTab } from "./AnalyticsTab";
import { ExploreView } from "@/features/explore/components/ExploreView";

const COMPARE_MAX = 8;

export function DashboardView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: session } = useSession();
  const sessionUser = session?.user?.name ?? "";
  const isAdmin = (session?.user as Record<string, unknown> | undefined)?.role === "admin";

  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const [activeTab, setActiveTab] = useState("jobs");
  // Sync from URL on mount / when ?tab= changes (supports deep-linking from
  // UserFieldPreview and bookmarked tab URLs).
  const urlTab = searchParams.get("tab");
  useEffect(() => {
    if (urlTab === "jobs" || urlTab === "analytics" || urlTab === "explore") {
      setActiveTab(urlTab);
    }
  }, [urlTab]);
  // Expose for tutorial beforeShow
  useEffect(() => registerTutorialHook("setTab", setActiveTab), []);

  const analyticsFilters = useAnalyticsFilters();

  const {
    data,
    setData,
    loading,
    initialLoad,
    error,
    pageOffset,
    setPageOffset,
    counts,
    fetchJobs,
  } = useJobsList({ sessionUser, isAdmin });

  const { analyticsData, setAnalyticsData, analyticsLoading } = useDashboardAnalytics({
    sessionUser,
    isAdmin,
    activeTab,
    optimizer: analyticsFilters.optimizer,
    model: analyticsFilters.model,
    status: analyticsFilters.status,
    jobId: analyticsFilters.jobId,
    date: analyticsFilters.date,
  });

  // Demo overlay state — tutorial injects fake data here so background
  // fetches (realtime polling, initial load) can never overwrite it.
  const [demoJobs, setDemoJobs] = useState<PaginatedJobsResponse | null>(null);
  const [demoAnalytics, setDemoAnalytics] = useState<DashboardAnalytics | null>(null);
  const effectiveData = demoJobs ?? data;
  const effectiveAnalytics = demoAnalytics ?? analyticsData;

  // Tutorial hooks — registered after data hooks are available
  useEffect(
    () => registerTutorialQuery("hasDashboardData", () => (data?.items.length ?? 0) > 0),
    [data],
  );
  useEffect(() => registerTutorialHook("setDemoJobs", setDemoJobs), []);
  useEffect(() => registerTutorialHook("setDemoAnalytics", setDemoAnalytics), []);

  // Clear demo overlay when tutorial exits so real data shows through
  useEffect(() => {
    const onExit = () => {
      setDemoJobs(null);
      setDemoAnalytics(null);
    };
    window.addEventListener("tutorial-exited", onExit);
    return () => window.removeEventListener("tutorial-exited", onExit);
  }, []);

  const queueStatus = useQueueStatus();

  // Cross-component sync (sidebar delete/rename, etc.): refetch the
  // current jobs page and invalidate the analytics cache so the next
  // analytics-tab visit re-pulls.
  useEffect(() => {
    const onJobsChanged = () => {
      fetchJobs();
      setAnalyticsData(null);
    };
    window.addEventListener("optimizations-changed", onJobsChanged);
    return () => window.removeEventListener("optimizations-changed", onJobsChanged);
  }, [fetchJobs, setAnalyticsData]);

  useJobsRealtime({ data, fetchJobs });

  const { filters, setColumnFilter, openFilter, setOpenFilter, clearAll, activeCount } =
    useColumnFilters();
  const colResize = useColumnResize();
  const [sortKey, setSortKey] = useState<string>("created_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const toggleSort = useCallback(
    (key: string) => {
      if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      else {
        setSortKey(key);
        setSortDir("asc");
      }
    },
    [sortKey],
  );

  const {
    deleteTarget,
    setDeleteTarget,
    deleting,
    selectedIds,
    setSelectedIds,
    toggleRowSelected,
    clearSelection,
    bulkDeleteOpen,
    setBulkDeleteOpen,
    bulkDeleting,
    confirmDelete,
    confirmBulkDelete,
  } = useBulkDelete({ data, setData, setPageOffset, fetchJobs, visibleData: effectiveData });

  useEffect(
    () => registerTutorialHook("setSelectedJobIds", (ids) => setSelectedIds(new Set(ids))),
    [setSelectedIds],
  );

  // Compare-eligible subset of the current selection: status=success and a
  // consistent task_fingerprint. Legacy jobs with a null fingerprint are let
  // through so comparison still works on older data.
  const compareEligibleIds = useMemo(() => {
    if (!effectiveData || selectedIds.size === 0) return [];
    const selectedItems = effectiveData.items.filter(
      (j) => selectedIds.has(j.optimization_id) && j.status === "success",
    );
    if (selectedItems.length < 2) return selectedItems.map((j) => j.optimization_id);
    const anchorFp = selectedItems.find((j) => j.task_fingerprint)?.task_fingerprint ?? null;
    const matching = selectedItems.filter(
      (j) => !anchorFp || !j.task_fingerprint || j.task_fingerprint === anchorFp,
    );
    return matching.map((j) => j.optimization_id);
  }, [effectiveData, selectedIds]);
  const canCompare = compareEligibleIds.length >= 2;
  const onCompare = useCallback(() => {
    if (compareEligibleIds.length < 2) return;
    if (compareEligibleIds.length > COMPARE_MAX) {
      toast.error(msg("compare.cap_reached"));
      return;
    }
    router.push(`/compare?jobs=${compareEligibleIds.join(",")}`);
  }, [compareEligibleIds, router]);

  /* ── Client-side filter + sort ── */
  const filteredItems = useMemo(() => {
    if (!effectiveData) return [];
    let items = effectiveData.items.filter((job) => {
      for (const [col, allowed] of Object.entries(filters)) {
        if (allowed.size === 0) continue;
        const val = String((job as unknown as Record<string, unknown>)[col] ?? "");
        if (!allowed.has(val)) return false;
      }
      return true;
    });
    items.sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortKey];
      const bv = (b as unknown as Record<string, unknown>)[sortKey];
      const cmp = String(av ?? "").localeCompare(String(bv ?? ""), "he", { numeric: true });
      return sortDir === "asc" ? cmp : -cmp;
    });
    return items;
  }, [effectiveData, filters, sortKey, sortDir]);

  // Every currently-visible (filtered + loaded) row is selectable. The
  // bulk-delete handler cancels active jobs before deleting, mirroring
  // the single-row delete button's behavior.
  const selectablePageIds = useMemo(
    () => filteredItems.map((j) => j.optimization_id),
    [filteredItems],
  );
  const selectedOnPage = selectablePageIds.filter((id) => selectedIds.has(id)).length;
  const pageAllSelected =
    selectablePageIds.length > 0 && selectedOnPage === selectablePageIds.length;
  const pageSomeSelected = selectedOnPage > 0 && !pageAllSelected;
  const togglePageSelection = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (pageAllSelected) {
        for (const id of selectablePageIds) next.delete(id);
      } else {
        for (const id of selectablePageIds) next.add(id);
      }
      return next;
    });
  };

  /* ── Unique values for filter dropdowns ── */
  const filterOptions = useMemo(() => {
    if (!effectiveData) return {} as Record<string, { value: string; label: string }[]>;
    const items = effectiveData.items;
    const unique = (key: string, labelFn?: (v: string) => string) => {
      const vals = [
        ...new Set(items.map((j) => String((j as unknown as Record<string, unknown>)[key] ?? ""))),
      ]
        .filter(Boolean)
        .sort();
      return vals.map((v) => ({ value: v, label: labelFn ? labelFn(v) : v }));
    };
    return {
      optimization_id: unique("optimization_id"),
      status: unique("status", getStatusLabel),
      optimization_type: unique("optimization_type", getJobTypeLabel),
      module_name: unique("module_name"),
      optimizer_name: unique("optimizer_name"),
    };
  }, [effectiveData]);

  const chartData = useMemo(() => transformChartData(effectiveAnalytics), [effectiveAnalytics]);

  const stats = useDashboardStats({
    data: effectiveData,
    filteredItems,
    counts,
    analyticsData: effectiveAnalytics,
    activeTab,
  });

  return (
    <Skeleton
      name="dashboard"
      loading={initialLoad && !effectiveData}
      initialBones={dashboardBones}
      color="var(--muted)"
      animate="shimmer"
    >
      <div className="flex flex-col gap-8">
        <DashboardHeader stats={stats} />
        <QueueStatusAlert queueStatus={queueStatus} />

        {/* Main content with tabs */}
        <FadeIn delay={0.2}>
          {mounted && (
            <Tabs value={activeTab} dir="rtl" onValueChange={setActiveTab}>
              <TabsList className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1 border-none shadow-none h-auto">
                <div
                  className="absolute top-1 bottom-1 w-[calc(33.333%-5.333px)] rounded-md bg-[#3D2E22] shadow-sm transition-[inset-inline-start] duration-200 ease-out"
                  style={{
                    insetInlineStart:
                      activeTab === "jobs"
                        ? 4
                        : activeTab === "analytics"
                          ? "calc(33.333% + 2.666px)"
                          : "calc(66.666% + 1.333px)",
                  }}
                />
                <TabsTrigger
                  value="jobs"
                  className="relative z-10 rounded-md px-4 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5"
                >
                  <TableIcon className="size-3.5" />
                  {TERMS.optimizationPlural}
                </TabsTrigger>
                <TabsTrigger
                  value="analytics"
                  data-tutorial="analytics-tab"
                  className="relative z-10 rounded-md px-4 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5"
                >
                  <BarChart3 className="size-3.5" />
                  סטטיסטיקות
                </TabsTrigger>
                <TabsTrigger
                  value="explore"
                  className="relative z-10 rounded-md px-4 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5"
                >
                  <Compass className="size-3.5" />
                  מפה
                </TabsTrigger>
              </TabsList>

              <TabsContent value="jobs">
                <JobsTab
                  data={effectiveData}
                  loading={loading}
                  error={error}
                  filteredItems={filteredItems}
                  activeCount={activeCount}
                  clearAllFilters={clearAll}
                  colResize={colResize}
                  sortKey={sortKey}
                  sortDir={sortDir}
                  toggleSort={toggleSort}
                  filters={filters}
                  setColumnFilter={setColumnFilter}
                  openFilter={openFilter}
                  setOpenFilter={setOpenFilter}
                  filterOptions={filterOptions}
                  isAdmin={isAdmin}
                  selectedIds={selectedIds}
                  toggleRowSelected={toggleRowSelected}
                  selectablePageIds={selectablePageIds}
                  pageAllSelected={pageAllSelected}
                  pageSomeSelected={pageSomeSelected}
                  togglePageSelection={togglePageSelection}
                  pageOffset={pageOffset}
                  setPageOffset={setPageOffset}
                  onOpenJob={(id) => router.push(`/optimizations/${id}`)}
                  onRequestDelete={setDeleteTarget}
                />
              </TabsContent>

              <TabsContent value="analytics" data-tutorial="dashboard-stats">
                <AnalyticsTab
                  analyticsLoading={analyticsLoading}
                  analyticsData={effectiveAnalytics}
                  chartData={chartData}
                  filters={analyticsFilters}
                />
              </TabsContent>

              <TabsContent value="explore">
                <ExploreView />
              </TabsContent>
            </Tabs>
          )}
        </FadeIn>

        <BulkActionBar
          isAdmin={isAdmin}
          selectedCount={selectedIds.size}
          compareEligibleCount={compareEligibleIds.length}
          canCompare={canCompare}
          onClear={clearSelection}
          onCompare={onCompare}
          onRequestBulkDelete={() => setBulkDeleteOpen(true)}
        />
        <DeleteDialogs
          deleteTarget={deleteTarget}
          setDeleteTarget={setDeleteTarget}
          deleting={deleting}
          confirmDelete={confirmDelete}
          bulkDeleteOpen={bulkDeleteOpen}
          setBulkDeleteOpen={setBulkDeleteOpen}
          bulkDeleting={bulkDeleting}
          confirmBulkDelete={confirmBulkDelete}
          selectedCount={selectedIds.size}
        />
      </div>
    </Skeleton>
  );
}
