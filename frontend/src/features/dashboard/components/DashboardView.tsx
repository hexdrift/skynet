"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { BarChart3, TableIcon } from "lucide-react";
import { Skeleton } from "boneyard-js/react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FadeIn } from "@/shared/ui/motion";
import {
  useColumnFilters,
  useColumnResize,
  type SortDir,
} from "@/shared/ui/excel-filter";
import { STATUS_LABELS } from "@/shared/constants/job-status";
import { dashboardBones } from "@/features/dashboard/lib/bones";
import { registerTutorialHook } from "@/features/tutorial/lib/bridge";
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

export function DashboardView() {
  const router = useRouter();
  const { data: session } = useSession();
  const sessionUser = session?.user?.name ?? "";
  const isAdmin = (session?.user as Record<string, unknown> | undefined)?.role === "admin";

  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const [activeTab, setActiveTab] = useState("jobs");
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

  const {
    analyticsData,
    setAnalyticsData,
    analyticsLoading,
  } = useDashboardAnalytics({
    sessionUser,
    isAdmin,
    activeTab,
    optimizer: analyticsFilters.optimizer,
    model: analyticsFilters.model,
    status: analyticsFilters.status,
    jobId: analyticsFilters.jobId,
    date: analyticsFilters.date,
  });

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
    return () =>
      window.removeEventListener("optimizations-changed", onJobsChanged);
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
  } = useBulkDelete({ data, setData, setPageOffset, fetchJobs });

  /* ── Client-side filter + sort ── */
  const filteredItems = useMemo(() => {
    if (!data) return [];
    let items = data.items.filter((job) => {
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
  }, [data, filters, sortKey, sortDir]);

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
    if (!data) return {} as Record<string, { value: string; label: string }[]>;
    const items = data.items;
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
      status: unique("status", (v) => STATUS_LABELS[v] ?? v),
      optimization_type: unique("optimization_type", (v) =>
        v === "grid_search" ? "סריקה" : "ריצה בודדת",
      ),
      module_name: unique("module_name"),
      optimizer_name: unique("optimizer_name"),
    };
  }, [data]);

  const chartData = useMemo(
    () => transformChartData(analyticsData),
    [analyticsData],
  );

  const stats = useDashboardStats({
    data,
    filteredItems,
    counts,
    analyticsData,
    activeTab,
  });

  return (
    <Skeleton
      name="dashboard"
      loading={initialLoad && !data}
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
                  className="absolute top-1 bottom-1 w-[calc(50%-6px)] rounded-md bg-[#3D2E22] shadow-sm transition-[inset-inline-start] duration-200 ease-out"
                  style={{ insetInlineStart: activeTab === "jobs" ? 4 : "calc(50% + 2px)" }}
                />
                <TabsTrigger
                  value="jobs"
                  className="relative z-10 rounded-md px-4 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5"
                >
                  <TableIcon className="size-3.5" />
                  אופטימיזציות
                </TabsTrigger>
                <TabsTrigger
                  value="analytics"
                  data-tutorial="analytics-tab"
                  className="relative z-10 rounded-md px-4 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5"
                >
                  <BarChart3 className="size-3.5" />
                  סטטיסטיקות
                </TabsTrigger>
              </TabsList>

              <TabsContent value="jobs">
                <JobsTab
                  data={data}
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
                  analyticsData={analyticsData}
                  chartData={chartData}
                  filters={analyticsFilters}
                />
              </TabsContent>
            </Tabs>
          )}
        </FadeIn>

        <BulkActionBar
          isAdmin={isAdmin}
          selectedCount={selectedIds.size}
          onClear={clearSelection}
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
