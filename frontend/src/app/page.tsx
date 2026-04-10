"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import {
  Plus,
  ChevronRight,
  ChevronLeft,
  Loader2,
  BarChart3,
  TableIcon,
  Trash2,
  Activity,
  CheckCircle2,
  XCircle,
  Layers,
  TrendingUp,
  Clock,
  Database,
  ExternalLink,
  Zap,
  Medal,
  Trophy,
  Sparkles,
  X,
} from "lucide-react";
import { toast } from "react-toastify";
import { AnimatePresence, motion } from "framer-motion";
import dynamic from "next/dynamic";

const ScoresChart = dynamic(
  () => import("@/components/analytics-charts").then((m) => m.ScoresChart),
  {
    ssr: false,
    loading: () => (
      <div className="h-[300px] flex items-center justify-center">
        <span className="text-sm text-muted-foreground">טוען גרפים...</span>
      </div>
    ),
  },
);
const OptimizerChart = dynamic(
  () => import("@/components/analytics-charts").then((m) => m.OptimizerChart),
  { ssr: false, loading: () => <div className="h-[280px]" /> },
);
const RuntimeDistributionChart = dynamic(
  () => import("@/components/analytics-charts").then((m) => m.RuntimeDistributionChart),
  { ssr: false, loading: () => <div className="h-[250px]" /> },
);
const DatasetVsImprovementChart = dynamic(
  () => import("@/components/analytics-charts").then((m) => m.DatasetVsImprovementChart),
  { ssr: false, loading: () => <div className="h-[250px]" /> },
);
const EfficiencyChart = dynamic(
  () => import("@/components/analytics-charts").then((m) => m.EfficiencyChart),
  { ssr: false, loading: () => <div className="h-[250px]" /> },
);
const TimelineChart = dynamic(
  () => import("@/components/analytics-charts").then((m) => m.TimelineChart),
  { ssr: false, loading: () => <div className="h-[160px]" /> },
);

import { AnalyticsSection } from "@/components/analytics-sections";
import { AnalyticsEmpty } from "@/components/analytics-empty";
import { OptimizerComparisonTable, ModelPerformanceTable } from "@/components/analytics-tables";

import { Button } from "@/components/ui/button";
import {
  Tooltip as UiTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  FadeIn,
  TiltCard,
  AnimatedNumber,
  StaggerContainer,
  StaggerItem,
} from "@/components/motion";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableHeader,
  TableHead,
  TableBody,
  TableCell,
  TableRow,
} from "@/components/ui/table";
import {
  ColumnHeader,
  useColumnFilters,
  useColumnResize,
  ResetColumnsButton,
  type SortDir,
} from "@/components/excel-filter";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "boneyard-js/react";
import { listJobs, cancelJob, deleteJob, getQueueStatus } from "@/lib/api";
import { HelpTip } from "@/components/help-tip";
import { ACTIVE_STATUSES, STATUS_LABELS } from "@/lib/constants";
import { dashboardBones } from "@/components/dashboard-bones";
import type {
  PaginatedJobsResponse,
  OptimizationSummaryResponse,
  JobStatus,
  QueueStatusResponse,
} from "@/lib/types";
import {
  PAGE_SIZE,
  STATUS_COLORS,
  statusBadge,
  typeBadge,
  formatElapsed,
  formatDate,
  formatRelativeTime,
  formatScore,
  formatId,
} from "@/features/dashboard";
import { registerTutorialHook } from "@/lib/tutorial-bridge";
import { msg } from "@/features/shared/messages";

export default function DashboardPage() {
  const router = useRouter();
  const { data: session } = useSession();
  const sessionUser = session?.user?.name ?? "";
  const isAdmin = (session?.user as Record<string, unknown> | undefined)?.role === "admin";

  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // Analytics filters
  const [activeTab, setActiveTab] = useState("jobs");
  // Expose for tutorial beforeShow
  useEffect(() => registerTutorialHook("setTab", setActiveTab), []);
  const [analyticsOptimizer, setAnalyticsOptimizer] = useState<string>("all");
  const [analyticsModel, setAnalyticsModel] = useState<string>("all");
  const [analyticsStatus, setAnalyticsStatus] = useState<string>("all");
  const [analyticsJobId, setAnalyticsJobId] = useState<string | null>(null);
  const [analyticsDate, setAnalyticsDate] = useState<string | null>(null);
  const [leaderboardLimit, setLeaderboardLimit] = useState<number>(5);

  const [data, setData] = useState<PaginatedJobsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [initialLoad, setInitialLoad] = useState(true); // only true on first mount
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [queueStatus, setQueueStatus] = useState<QueueStatusResponse | null>(null);

  // Excel-style column filters + sort
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

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; status: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  // The per-user job quota (constants.MAX_JOBS_PER_USER) guarantees the
  // result set stays bounded, so the dashboard fetches the full list and
  // filters + sorts client-side. Admins can exceed the cap via
  // job_quota_overrides.ADMIN_USERNAMES and will see everyone's jobs.
  const fetchJobs = useCallback(async () => {
    try {
      const result = await listJobs({
        username: isAdmin ? undefined : sessionUser || undefined,
      });
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : msg("dashboard.load_error"));
    } finally {
      setLoading(false);
      setInitialLoad(false);
    }
  }, [sessionUser, isAdmin]);

  useEffect(() => {
    // Only show skeleton on very first load, not on revisits
    if (!data) setLoading(true);
    fetchJobs();

    // Listen for cross-component sync (sidebar delete, rename, etc.)
    const onJobsChanged = () => fetchJobs();
    window.addEventListener("optimizations-changed", onJobsChanged);
    return () => window.removeEventListener("optimizations-changed", onJobsChanged);
  }, [fetchJobs]);

  useEffect(() => {
    getQueueStatus()
      .then(setQueueStatus)
      .catch(() => {});
    const interval = setInterval(() => {
      getQueueStatus()
        .then(setQueueStatus)
        .catch(() => {});
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const targetId = deleteTarget.id;
    const targetStatus = deleteTarget.status;
    setDeleting(true);

    // Optimistic: remove from UI immediately
    setData((prev) =>
      prev
        ? {
            ...prev,
            items: prev.items.filter((j) => j.optimization_id !== targetId),
            total: prev.total - 1,
          }
        : prev,
    );
    setDeleteTarget(null);

    try {
      if (ACTIVE_STATUSES.has(targetStatus as JobStatus)) {
        await cancelJob(targetId);
      }
      await deleteJob(targetId);
      // Notify sidebar + re-fetch
      window.dispatchEvent(new Event("optimizations-changed"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("dashboard.delete_failed"));
      // Revert: re-fetch real data
      fetchJobs();
    } finally {
      setDeleting(false);
    }
  };

  /* ── SSE real-time dashboard updates (with polling fallback) ── */
  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    const hasActive = data?.items.some((j) => ACTIVE_STATUSES.has(j.status));
    if (!hasActive) return;

    const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    let eventSource: EventSource | null = null;

    try {
      eventSource = new EventSource(`${API}/optimizations/stream`);
      eventSource.onmessage = () => {
        fetchJobs();
      };
      eventSource.addEventListener("idle", () => {
        eventSource?.close();
        fetchJobs();
      });
      eventSource.onerror = () => {
        eventSource?.close();
        eventSource = null;
        // Fall back to polling
        timerRef.current = setInterval(fetchJobs, 15000);
      };
    } catch {
      timerRef.current = setInterval(fetchJobs, 15000);
    }

    return () => {
      eventSource?.close();
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [data, fetchJobs]);

  useEffect(() => {
    setOffset(0);
  }, [filters, sortKey, sortDir]);

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

  const pagedItems = filteredItems.slice(offset, offset + PAGE_SIZE);
  const totalPages = Math.ceil(filteredItems.length / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

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

  /* ── Aggregated chart data ── */
  // Unique values for analytics filter dropdowns
  const analyticsOptions = useMemo(() => {
    if (!data) return { optimizers: [], models: [] };
    const optimizers = [
      ...new Set(data.items.map((j) => j.optimizer_name).filter(Boolean)),
    ] as string[];
    const models = [...new Set(data.items.map((j) => j.model_name).filter(Boolean))] as string[];
    return { optimizers, models };
  }, [data]);

  const chartData = useMemo(() => {
    if (!data)
      return {
        status: [],
        improvement: [],
        improvementJobIds: [] as string[],
        optimizer: [],
        kpis: null,
        avgByOptimizer: [],
        runtimeByOptimizer: [],
        modelUsage: [],
        topJobs: [],
        jobTypeData: [],
        runtimeDistribution: [],
        runtimeDistributionJobIds: [] as string[],
        datasetVsImprovement: [],
        datasetVsImprovementIds: [] as string[],
        efficiencyData: [],
        efficiencyJobIds: [] as string[],
        timelineData: [],
        timelineDates: [] as string[],
      };
    let items = data.items;
    if (analyticsJobId) items = items.filter((j) => j.optimization_id === analyticsJobId);
    if (analyticsDate) items = items.filter((j) => j.created_at.slice(0, 10) === analyticsDate);
    if (analyticsOptimizer !== "all")
      items = items.filter((j) => j.optimizer_name === analyticsOptimizer);
    if (analyticsModel !== "all") items = items.filter((j) => j.model_name === analyticsModel);
    if (analyticsStatus !== "all") items = items.filter((j) => j.status === analyticsStatus);
    const successful = items.filter((j) => j.status === "success");
    const terminal = items.filter((j) => j.status === "success" || j.status === "failed");

    // Status distribution
    const statusCounts: Record<string, number> = {};
    for (const j of items) {
      statusCounts[j.status] = (statusCounts[j.status] ?? 0) + 1;
    }
    const statusData = Object.entries(statusCounts).map(([status, count]) => ({
      key: status,
      name: STATUS_LABELS[status] ?? status,
      value: count,
      fill: STATUS_COLORS[status] ?? "var(--color-chart-5)",
    }));

    // Improvement per completed job (bar chart)
    const successJobsForChart = items
      .filter((j) => j.status === "success" && j.optimized_test_metric != null)
      .slice(0, 10);
    const improvementData = successJobsForChart.map((j) => {
      const opt = j.optimized_test_metric ?? 0;
      const bl = j.baseline_test_metric ?? 0;
      const imp = j.metric_improvement;
      const delta = imp != null ? (Math.abs(imp) > 1 ? imp : imp * 100) : undefined;
      return {
        name: j.optimization_id.slice(0, 8) + "…",
        ציון_משופר: Math.round(opt > 1 ? opt : opt * 100),
        ציון_התחלתי: Math.round(bl > 1 ? bl : bl * 100),
        delta,
      };
    });
    const improvementJobIds = successJobsForChart.map((j) => j.optimization_id);

    // Optimizer usage
    const optCounts: Record<string, number> = {};
    for (const j of items) {
      const opt = j.optimizer_name ?? "אחר";
      optCounts[opt] = (optCounts[opt] ?? 0) + 1;
    }
    const optimizerData = Object.entries(optCounts).map(([name, count]) => ({
      name,
      value: count,
    }));

    // ── KPIs ──
    const successRate = terminal.length > 0 ? (successful.length / terminal.length) * 100 : 0;
    const improvements = successful
      .filter((j) => j.metric_improvement != null)
      .map((j) => {
        const v = j.metric_improvement!;
        return Math.abs(v) > 1 ? v : v * 100;
      });
    const avgImprovement =
      improvements.length > 0 ? improvements.reduce((a, b) => a + b, 0) / improvements.length : 0;
    const runtimes = successful
      .filter((j) => j.elapsed_seconds != null)
      .map((j) => j.elapsed_seconds!);
    const avgRuntime =
      runtimes.length > 0 ? runtimes.reduce((a, b) => a + b, 0) / runtimes.length : 0;
    const totalRows = items.reduce((sum, j) => sum + (j.dataset_rows ?? 0), 0);
    const totalPairsRun = items.reduce(
      (sum, j) => sum + (j.total_pairs ?? (j.optimization_type === "run" ? 1 : 0)),
      0,
    );
    const gridSearchCount = items.filter((j) => j.optimization_type === "grid_search").length;
    const singleRunCount = items.filter((j) => j.optimization_type === "run").length;
    const bestImprovement = improvements.length > 0 ? Math.max(...improvements) : 0;
    const kpis = {
      successRate,
      avgImprovement,
      avgRuntime,
      totalRows,
      successCount: successful.length,
      terminalCount: terminal.length,
      totalPairsRun,
      gridSearchCount,
      singleRunCount,
      bestImprovement,
    };

    // ── Average improvement by optimizer ──
    const optGroups: Record<string, number[]> = {};
    for (const j of successful) {
      if (j.metric_improvement == null || !j.optimizer_name) continue;
      const v =
        Math.abs(j.metric_improvement) > 1 ? j.metric_improvement : j.metric_improvement * 100;
      (optGroups[j.optimizer_name] ??= []).push(v);
    }
    const avgByOptimizer = Object.entries(optGroups).map(([name, vals]) => ({
      name,
      שיפור_ממוצע: +(vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1),
      count: vals.length,
    }));

    // ── Average runtime by optimizer ──
    const rtGroups: Record<string, number[]> = {};
    for (const j of successful) {
      if (j.elapsed_seconds == null || !j.optimizer_name) continue;
      (rtGroups[j.optimizer_name] ??= []).push(j.elapsed_seconds);
    }
    const runtimeByOptimizer = Object.entries(rtGroups).map(([name, vals]) => ({
      name,
      זמן_ממוצע: +(vals.reduce((a, b) => a + b, 0) / vals.length / 60).toFixed(1),
      count: vals.length,
    }));

    // ── Model usage ──
    const modelCounts: Record<string, number> = {};
    for (const j of items) {
      const m = j.model_name ?? j.best_pair_label?.split(" + ")[0];
      if (m) modelCounts[m] = (modelCounts[m] ?? 0) + 1;
    }
    const modelUsage = Object.entries(modelCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([name, count]) => ({ name, count }));

    // ── Job type distribution ──
    const typeCounts: Record<string, number> = {};
    for (const j of items) {
      const t = j.optimization_type === "grid_search" ? "סריקה" : "ריצה בודדת";
      typeCounts[t] = (typeCounts[t] ?? 0) + 1;
    }
    const jobTypeData = Object.entries(typeCounts).map(([name, value]) => ({ name, value }));

    // ── Top improvements ──
    const topJobs = [...successful]
      .filter((j) => j.metric_improvement != null)
      .sort((a, b) => {
        const ai =
          Math.abs(a.metric_improvement!) > 1 ? a.metric_improvement! : a.metric_improvement! * 100;
        const bi =
          Math.abs(b.metric_improvement!) > 1 ? b.metric_improvement! : b.metric_improvement! * 100;
        return bi - ai;
      })
      .slice(0, 5);

    // ── Runtime distribution ──
    const runtimeJobs = successful.filter((j) => j.elapsed_seconds != null).slice(0, 15);
    const runtimeDistribution = runtimeJobs.map((j) => ({
      name: j.optimization_id.slice(0, 8) + "…",
      זמן_דקות: +(j.elapsed_seconds! / 60).toFixed(1),
    }));
    const runtimeDistributionJobIds = runtimeJobs.map((j) => j.optimization_id);

    // ── Dataset size vs improvement ──
    const dvsJobs = successful.filter(
      (j) => j.dataset_rows != null && j.metric_improvement != null,
    );
    const datasetVsImprovement = dvsJobs.map((j) => ({
      שורות: j.dataset_rows!,
      שיפור: +(
        Math.abs(j.metric_improvement!) > 1 ? j.metric_improvement! : j.metric_improvement! * 100
      ).toFixed(1),
      name: j.optimization_id.slice(0, 8) + "…",
    }));
    const datasetVsImprovementIds = dvsJobs.map((j) => j.optimization_id);

    // ── Efficiency (improvement per minute) ──
    const effJobs = successful
      .filter(
        (j) => j.metric_improvement != null && j.elapsed_seconds != null && j.elapsed_seconds > 0,
      )
      .map((j) => {
        const imp =
          Math.abs(j.metric_improvement!) > 1 ? j.metric_improvement! : j.metric_improvement! * 100;
        return {
          name: j.optimization_id.slice(0, 8) + "…",
          יעילות: +((imp / j.elapsed_seconds!) * 60).toFixed(2),
          _id: j.optimization_id,
        };
      })
      .sort((a, b) => b.יעילות - a.יעילות)
      .slice(0, 10);
    const efficiencyData = effJobs.map(({ name, יעילות }) => ({ name, יעילות }));
    const efficiencyJobIds = effJobs.map((j) => j._id);

    // ── Timeline (jobs per day) ──
    const timelineBuckets: Record<string, number> = {};
    for (const j of items) {
      const day = j.created_at.slice(0, 10);
      timelineBuckets[day] = (timelineBuckets[day] ?? 0) + 1;
    }
    const timelineEntries = Object.entries(timelineBuckets)
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-14);
    const timelineData = timelineEntries.map(([date, count]) => ({
      name: new Date(date).toLocaleDateString("he-IL", { day: "numeric", month: "short" }),
      אופטימיזציות: count,
    }));
    const timelineDates = timelineEntries.map(([date]) => date);

    return {
      status: statusData,
      improvement: improvementData,
      improvementJobIds,
      optimizer: optimizerData,
      kpis,
      avgByOptimizer,
      runtimeByOptimizer,
      modelUsage,
      topJobs,
      jobTypeData,
      runtimeDistribution,
      runtimeDistributionJobIds,
      datasetVsImprovement,
      datasetVsImprovementIds,
      efficiencyData,
      efficiencyJobIds,
      timelineData,
      timelineDates,
    };
  }, [data, analyticsJobId, analyticsDate, analyticsOptimizer, analyticsModel, analyticsStatus]);

  const analyticsFilteredItems = useMemo(() => {
    if (!data) return [];
    let items = data.items;
    if (analyticsJobId) items = items.filter((j) => j.optimization_id === analyticsJobId);
    if (analyticsDate) items = items.filter((j) => j.created_at.slice(0, 10) === analyticsDate);
    if (analyticsOptimizer !== "all")
      items = items.filter((j) => j.optimizer_name === analyticsOptimizer);
    if (analyticsModel !== "all") items = items.filter((j) => j.model_name === analyticsModel);
    if (analyticsStatus !== "all") items = items.filter((j) => j.status === analyticsStatus);
    return items;
  }, [data, analyticsJobId, analyticsDate, analyticsOptimizer, analyticsModel, analyticsStatus]);

  const statsSource = activeTab === "analytics" ? analyticsFilteredItems : filteredItems;
  const stats = data
    ? {
        total: statsSource.length,
        success: statsSource.filter((j) => j.status === "success").length,
        running: statsSource.filter((j) => ACTIVE_STATUSES.has(j.status)).length,
        failed: statsSource.filter((j) => j.status === "failed").length,
      }
    : null;

  return (
    <Skeleton
      name="dashboard"
      loading={initialLoad && !data}
      initialBones={dashboardBones}
      color="var(--muted)"
      animate="shimmer"
    >
      <div className="flex flex-col gap-8">
        {/* Header */}
        <FadeIn>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">לוח בקרה</h1>
              {stats && (
                <p className="text-sm text-muted-foreground mt-1">
                  {stats.total} אופטימיזציות
                  {stats.running > 0 && (
                    <span className="text-[var(--warning)] font-medium">
                      {" "}
                      &middot; {stats.running} פעילות
                    </span>
                  )}
                </p>
              )}
            </div>
          </div>
        </FadeIn>

        {/* Stats cards */}
        {stats && (
          <div
            className="stats-grid grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4"
            style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(180px, 100%), 1fr))" }}
            data-tutorial="dashboard-kpis"
          >
            {/* Total */}
            <TiltCard>
              <Card className="border-border/40 hover:border-border/70 transition-colors duration-300">
                <CardContent className="p-5 sm:p-6">
                  <div className="flex items-start justify-between">
                    <div className="space-y-3">
                      <p className="text-[12px] font-medium text-muted-foreground/80 tracking-wide">
                        סה״כ
                      </p>
                      <p className="text-4xl font-bold tracking-tighter tabular-nums">
                        <AnimatedNumber value={stats.total} />
                      </p>
                    </div>
                    <div className="size-9 rounded-lg bg-stone-500/[0.07] flex items-center justify-center">
                      <Layers className="size-4 text-stone-500" />
                    </div>
                  </div>
                  <p className="mt-3 text-[10px] text-muted-foreground/50">אופטימיזציות</p>
                </CardContent>
              </Card>
            </TiltCard>
            {/* Running */}
            <TiltCard>
              <Card
                className={`border-border/40 hover:border-border/70 transition-colors duration-300 ${stats.running > 0 ? "border-[var(--warning)]/20" : ""}`}
              >
                <CardContent className="p-5 sm:p-6">
                  <div className="flex items-start justify-between">
                    <div className="space-y-3">
                      <p className="text-[12px] font-medium text-muted-foreground/80 tracking-wide">
                        פעילות
                      </p>
                      <p
                        className={`text-4xl font-bold tracking-tighter tabular-nums ${stats.running > 0 ? "text-[var(--warning)]" : "text-muted-foreground"}`}
                      >
                        <AnimatedNumber value={stats.running} />
                      </p>
                    </div>
                    <div
                      className={`size-9 rounded-lg flex items-center justify-center ${stats.running > 0 ? "bg-[var(--warning)]/[0.08]" : "bg-stone-500/[0.07]"}`}
                    >
                      <Activity
                        className={`size-4 ${stats.running > 0 ? "text-[var(--warning)] animate-pulse" : "text-stone-500"}`}
                      />
                    </div>
                  </div>
                  <p className="mt-3 text-[10px] text-muted-foreground/50">כרגע רצות</p>
                </CardContent>
              </Card>
            </TiltCard>
            {/* Success */}
            <TiltCard>
              <Card className="border-border/40 hover:border-border/70 transition-colors duration-300">
                <CardContent className="p-5 sm:p-6">
                  <div className="flex items-start justify-between">
                    <div className="space-y-3">
                      <p className="text-[12px] font-medium text-muted-foreground/80 tracking-wide">
                        הצליחו
                      </p>
                      <p
                        className={`text-4xl font-bold tracking-tighter tabular-nums ${stats.success > 0 ? "text-emerald-700" : "text-muted-foreground"}`}
                      >
                        <AnimatedNumber value={stats.success} />
                      </p>
                    </div>
                    <div
                      className={`size-9 rounded-lg flex items-center justify-center ${stats.success > 0 ? "bg-emerald-500/[0.07]" : "bg-stone-500/[0.07]"}`}
                    >
                      <CheckCircle2
                        className={`size-4 ${stats.success > 0 ? "text-emerald-600" : "text-stone-500"}`}
                      />
                    </div>
                  </div>
                  {stats.total > 0 && (
                    <div className="mt-3 flex items-center gap-2">
                      <div className="flex-1 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-emerald-500/40 transition-all duration-700"
                          style={{ width: `${(stats.success / stats.total) * 100}%` }}
                        />
                      </div>
                      <span className="text-[10px] tabular-nums text-muted-foreground/50">
                        {Math.round((stats.success / stats.total) * 100)}%
                      </span>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TiltCard>
            {/* Failed */}
            <TiltCard>
              <Card className="border-border/40 hover:border-border/70 transition-colors duration-300">
                <CardContent className="p-5 sm:p-6">
                  <div className="flex items-start justify-between">
                    <div className="space-y-3">
                      <p className="text-[12px] font-medium text-muted-foreground/80 tracking-wide">
                        נכשלו
                      </p>
                      <p
                        className={`text-4xl font-bold tracking-tighter tabular-nums ${stats.failed > 0 ? "text-red-600" : "text-muted-foreground"}`}
                      >
                        <AnimatedNumber value={stats.failed} />
                      </p>
                    </div>
                    <div
                      className={`size-9 rounded-lg flex items-center justify-center ${stats.failed > 0 ? "bg-red-500/[0.07]" : "bg-stone-500/[0.07]"}`}
                    >
                      <XCircle
                        className={`size-4 ${stats.failed > 0 ? "text-red-500" : "text-stone-500"}`}
                      />
                    </div>
                  </div>
                  {stats.total > 0 && (
                    <div className="mt-3 flex items-center gap-2">
                      <div className="flex-1 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-red-500/40 transition-all duration-700"
                          style={{ width: `${(stats.failed / stats.total) * 100}%` }}
                        />
                      </div>
                      <span className="text-[10px] tabular-nums text-muted-foreground/50">
                        {Math.round((stats.failed / stats.total) * 100)}%
                      </span>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TiltCard>
          </div>
        )}

        {/* Queue status — only show when server is down */}
        {queueStatus && !queueStatus.workers_alive && (
          <div className="flex items-center gap-4 text-xs text-muted-foreground px-2 py-2 rounded-lg bg-muted/30 border border-border/30">
            <span className="flex items-center gap-1.5">
              <span className="size-2 rounded-full bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.4)]" />
              <span className="font-medium">שרת לא זמין</span>
            </span>
          </div>
        )}

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

              {/* ── Jobs tab ── */}
              <TabsContent value="jobs">
                <Card className="border-border/60">
                  <CardContent className="pt-5">
                    {/* Toolbar: filter count */}
                    <div className="flex items-center gap-2 mb-3">
                      {activeCount > 0 && (
                        <>
                          <Badge variant="secondary" className="text-xs">
                            {activeCount} סינונים פעילים
                          </Badge>
                          <button
                            type="button"
                            onClick={clearAll}
                            className="text-xs text-muted-foreground hover:text-foreground cursor-pointer"
                          >
                            נקה הכל
                          </button>
                        </>
                      )}
                      <ResetColumnsButton resize={colResize} />
                      {filteredItems.length > 0 && (
                        <span className="text-[11px] text-muted-foreground tabular-nums ms-auto">
                          {filteredItems.length} תוצאות
                        </span>
                      )}
                    </div>

                    {error && (
                      <div className="rounded-lg border border-[var(--danger-border)] bg-[var(--danger-dim)] py-3 px-4 text-sm text-[var(--danger)] mb-4">
                        {error}
                      </div>
                    )}

                    {!loading && data && filteredItems.length === 0 && (
                      <div className="flex flex-col items-center gap-3 py-16 text-center">
                        <p className="text-base font-medium">לא נמצאו אופטימיזציות</p>
                        <p className="text-sm text-muted-foreground max-w-xs">
                          העלה דאטאסט, הגדר חתימה ומטריקה, והמערכת תשפר את הפרומפט אוטומטית
                        </p>
                        <Button asChild size="pill" className="mt-2">
                          <Link href="/submit">
                            <Plus className="size-4" />
                            אופטימיזציה חדשה
                          </Link>
                        </Button>
                      </div>
                    )}

                    {pagedItems.length > 0 && (
                      <div className="overflow-x-auto" data-tutorial="dashboard-table">
                        <Table style={{ minWidth: "800px" }}>
                          <thead className="bg-muted/30 [&_tr]:border-b [&_tr]:border-border/50">
                            <tr>
                              <ColumnHeader
                                label="מזהה אופטימיזציה"
                                sortKey="optimization_id"
                                currentSort={sortKey}
                                sortDir={sortDir}
                                onSort={toggleSort}
                                filterCol="optimization_id"
                                filterOptions={filterOptions.optimization_id}
                                filters={filters}
                                onFilter={setColumnFilter}
                                openFilter={openFilter}
                                setOpenFilter={setOpenFilter}
                                width={colResize.widths["optimization_id"]}
                                onResize={colResize.setColumnWidth}
                              />
                              <ColumnHeader
                                label="סוג"
                                sortKey="optimization_type"
                                currentSort={sortKey}
                                sortDir={sortDir}
                                onSort={toggleSort}
                                filterCol="optimization_type"
                                filterOptions={filterOptions.optimization_type}
                                filters={filters}
                                onFilter={setColumnFilter}
                                openFilter={openFilter}
                                setOpenFilter={setOpenFilter}
                                width={colResize.widths["optimization_type"]}
                                onResize={colResize.setColumnWidth}
                              />
                              <ColumnHeader
                                label="סטטוס"
                                sortKey="status"
                                currentSort={sortKey}
                                sortDir={sortDir}
                                onSort={toggleSort}
                                filterCol="status"
                                filterOptions={filterOptions.status}
                                filters={filters}
                                onFilter={setColumnFilter}
                                openFilter={openFilter}
                                setOpenFilter={setOpenFilter}
                                width={colResize.widths["status"]}
                                onResize={colResize.setColumnWidth}
                              />
                              <ColumnHeader
                                label="מודול"
                                sortKey="module_name"
                                currentSort={sortKey}
                                sortDir={sortDir}
                                onSort={toggleSort}
                                filterCol="module_name"
                                filterOptions={filterOptions.module_name}
                                filters={filters}
                                onFilter={setColumnFilter}
                                openFilter={openFilter}
                                setOpenFilter={setOpenFilter}
                                width={colResize.widths["module_name"]}
                                onResize={colResize.setColumnWidth}
                              />
                              <ColumnHeader
                                label="אופטימייזר"
                                sortKey="optimizer_name"
                                currentSort={sortKey}
                                sortDir={sortDir}
                                onSort={toggleSort}
                                filterCol="optimizer_name"
                                filterOptions={filterOptions.optimizer_name}
                                filters={filters}
                                onFilter={setColumnFilter}
                                openFilter={openFilter}
                                setOpenFilter={setOpenFilter}
                                width={colResize.widths["optimizer_name"]}
                                onResize={colResize.setColumnWidth}
                              />
                              <ColumnHeader
                                label="שורות"
                                sortKey="dataset_rows"
                                currentSort={sortKey}
                                sortDir={sortDir}
                                onSort={toggleSort}
                                width={colResize.widths["dataset_rows"]}
                                onResize={colResize.setColumnWidth}
                              />
                              <ColumnHeader
                                label="נוצר"
                                sortKey="created_at"
                                currentSort={sortKey}
                                sortDir={sortDir}
                                onSort={toggleSort}
                                width={colResize.widths["created_at"]}
                                onResize={colResize.setColumnWidth}
                              />
                              <ColumnHeader
                                label="זמן"
                                sortKey="elapsed_seconds"
                                currentSort={sortKey}
                                sortDir={sortDir}
                                onSort={toggleSort}
                                width={colResize.widths["elapsed_seconds"]}
                                onResize={colResize.setColumnWidth}
                              />
                              <ColumnHeader
                                label="ציון"
                                sortKey="optimized_test_metric"
                                currentSort={sortKey}
                                sortDir={sortDir}
                                onSort={toggleSort}
                                width={colResize.widths["optimized_test_metric"]}
                                onResize={colResize.setColumnWidth}
                              />
                              <th className="w-16" />
                            </tr>
                          </thead>
                          <TableBody className="transition-opacity duration-200">
                            {pagedItems.map((job, idx) => (
                              <TableRow
                                key={job.optimization_id}
                                className="group border-border/40 cursor-pointer [&_td:last-child]:cursor-default"
                                style={{
                                  animation: `fadeSlideIn 0.25s ease-out ${idx * 0.03}s both`,
                                }}
                                onClick={(e) => {
                                  const td = (e.target as HTMLElement).closest("td");
                                  if (!td || td === td.parentElement?.lastElementChild) return;
                                  const text = td.textContent?.trim();
                                  if (text) {
                                    navigator.clipboard.writeText(text);
                                    toast.success(msg("clipboard.copied"));
                                  }
                                }}
                                data-tutorial="job-link"
                              >
                                <TableCell
                                  className="max-w-[180px] truncate overflow-hidden"
                                  title={job.optimization_id}
                                >
                                  <div className="flex items-center gap-1.5">
                                    {ACTIVE_STATUSES.has(job.status) && (
                                      <span className="relative flex size-2 shrink-0">
                                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--warning)]/60" />
                                        <span className="relative inline-flex rounded-full size-2 bg-[var(--warning)]" />
                                      </span>
                                    )}
                                    <span className="font-mono text-xs text-primary truncate">
                                      {formatId(job.optimization_id)}
                                    </span>
                                  </div>
                                </TableCell>
                                <TableCell className="truncate overflow-hidden">
                                  {typeBadge(job.optimization_type)}
                                </TableCell>
                                <TableCell className="truncate overflow-hidden">
                                  {statusBadge(job.status)}
                                </TableCell>
                                <TableCell
                                  className="text-sm truncate overflow-hidden"
                                  title={job.module_name ?? ""}
                                >
                                  {job.module_name ?? "-"}
                                </TableCell>
                                <TableCell
                                  className="text-sm truncate overflow-hidden"
                                  title={job.optimizer_name ?? ""}
                                >
                                  {job.optimizer_name ?? "-"}
                                </TableCell>
                                <TableCell
                                  className="text-sm tabular-nums truncate overflow-hidden"
                                  title={String(job.dataset_rows ?? "")}
                                >
                                  {job.dataset_rows ?? "-"}
                                </TableCell>
                                <TableCell
                                  className="text-xs text-muted-foreground truncate overflow-hidden"
                                  title={formatDate(job.created_at)}
                                >
                                  {formatRelativeTime(job.created_at)}
                                </TableCell>
                                <TableCell
                                  className="text-xs tabular-nums truncate overflow-hidden"
                                  title={formatElapsed(job.elapsed_seconds) ?? ""}
                                >
                                  {formatElapsed(job.elapsed_seconds)}
                                </TableCell>
                                <TableCell className="truncate overflow-hidden">
                                  {formatScore(job)}
                                </TableCell>
                                <TableCell>
                                  <div className="flex items-center gap-0.5">
                                    <TooltipProvider>
                                      <UiTooltip>
                                        <TooltipTrigger asChild>
                                          <button
                                            type="button"
                                            onClick={() =>
                                              router.push(`/optimizations/${job.optimization_id}`)
                                            }
                                            className="p-1 rounded hover:bg-accent/60 text-muted-foreground hover:text-foreground transition-all cursor-pointer"
                                            aria-label="פרטי אופטימיזציה"
                                          >
                                            <ExternalLink className="size-3.5" />
                                          </button>
                                        </TooltipTrigger>
                                        <TooltipContent side="bottom">פרטים</TooltipContent>
                                      </UiTooltip>
                                    </TooltipProvider>
                                    {isAdmin && (
                                      <TooltipProvider>
                                        <UiTooltip>
                                          <TooltipTrigger asChild>
                                            <button
                                              type="button"
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                setDeleteTarget({
                                                  id: job.optimization_id,
                                                  status: job.status,
                                                });
                                              }}
                                              className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-all cursor-pointer"
                                              aria-label="מחק אופטימיזציה"
                                            >
                                              <Trash2 className="size-3.5" />
                                            </button>
                                          </TooltipTrigger>
                                          <TooltipContent side="bottom">מחיקה</TooltipContent>
                                        </UiTooltip>
                                      </TooltipProvider>
                                    )}
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    )}

                    {data && totalPages > 1 && (
                      <div className="flex items-center justify-center gap-3 pt-5 border-t border-border/50 mt-4">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={offset === 0}
                          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                          className="gap-1"
                        >
                          <ChevronRight className="size-3.5" />
                          הקודם
                        </Button>
                        <span className="text-sm text-muted-foreground tabular-nums px-3 py-1 rounded-md bg-muted/50">
                          {currentPage} / {totalPages}
                        </span>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={offset + PAGE_SIZE >= (data?.total ?? 0)}
                          onClick={() => setOffset(offset + PAGE_SIZE)}
                          className="gap-1"
                        >
                          הבא
                          <ChevronLeft className="size-3.5" />
                        </Button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              {/* ── Analytics tab ── */}
              <TabsContent value="analytics" data-tutorial="dashboard-stats">
                {data && data.items.length > 0 ? (
                  <div className="space-y-6">
                    {/* ── Active filter chips ── */}
                    {(() => {
                      const hasFilters =
                        analyticsJobId ||
                        analyticsDate ||
                        analyticsOptimizer !== "all" ||
                        analyticsModel !== "all" ||
                        analyticsStatus !== "all";
                      if (!hasFilters) return null;
                      const clearAll = () => {
                        setAnalyticsJobId(null);
                        setAnalyticsDate(null);
                        setAnalyticsOptimizer("all");
                        setAnalyticsModel("all");
                        setAnalyticsStatus("all");
                      };
                      return (
                        <div className="flex items-center gap-2 flex-wrap">
                          {analyticsJobId && (
                            <span className="group inline-flex items-center gap-1.5 rounded-lg bg-[#3D2E22]/[0.06] border border-[#3D2E22]/10 pe-1 ps-2.5 py-1 transition-all duration-150 hover:bg-[#3D2E22]/[0.1] hover:border-[#3D2E22]/20">
                              <span
                                className="font-mono text-[11px] font-medium text-[#3D2E22]/80"
                                dir="ltr"
                              >
                                {analyticsJobId.slice(0, 8)}…
                              </span>
                              <button
                                onClick={() => setAnalyticsJobId(null)}
                                className="size-5 rounded-md flex items-center justify-center text-[#3D2E22]/40 hover:text-[#3D2E22] hover:bg-[#3D2E22]/10 transition-colors cursor-pointer"
                                aria-label="הסר סינון"
                              >
                                <X className="size-3" />
                              </button>
                            </span>
                          )}
                          {analyticsDate && (
                            <span className="group inline-flex items-center gap-1.5 rounded-lg bg-[#3D2E22]/[0.06] border border-[#3D2E22]/10 pe-1 ps-2.5 py-1 transition-all duration-150 hover:bg-[#3D2E22]/[0.1] hover:border-[#3D2E22]/20">
                              <span className="text-[11px] font-medium text-[#3D2E22]/80">
                                {new Date(analyticsDate).toLocaleDateString("he-IL", {
                                  day: "numeric",
                                  month: "short",
                                  year: "numeric",
                                })}
                              </span>
                              <button
                                onClick={() => setAnalyticsDate(null)}
                                className="size-5 rounded-md flex items-center justify-center text-[#3D2E22]/40 hover:text-[#3D2E22] hover:bg-[#3D2E22]/10 transition-colors cursor-pointer"
                                aria-label="הסר סינון"
                              >
                                <X className="size-3" />
                              </button>
                            </span>
                          )}
                          {analyticsOptimizer !== "all" && (
                            <span className="group inline-flex items-center gap-1.5 rounded-lg bg-[#3D2E22]/[0.06] border border-[#3D2E22]/10 pe-1 ps-2.5 py-1 transition-all duration-150 hover:bg-[#3D2E22]/[0.1] hover:border-[#3D2E22]/20">
                              <span className="text-[11px] font-medium text-[#3D2E22]/80" dir="ltr">
                                {analyticsOptimizer}
                              </span>
                              <button
                                onClick={() => setAnalyticsOptimizer("all")}
                                className="size-5 rounded-md flex items-center justify-center text-[#3D2E22]/40 hover:text-[#3D2E22] hover:bg-[#3D2E22]/10 transition-colors cursor-pointer"
                                aria-label="הסר סינון"
                              >
                                <X className="size-3" />
                              </button>
                            </span>
                          )}
                          {analyticsModel !== "all" && (
                            <span className="group inline-flex items-center gap-1.5 rounded-lg bg-[#3D2E22]/[0.06] border border-[#3D2E22]/10 pe-1 ps-2.5 py-1 transition-all duration-150 hover:bg-[#3D2E22]/[0.1] hover:border-[#3D2E22]/20">
                              <span
                                className="font-mono text-[11px] font-medium text-[#3D2E22]/80 truncate max-w-[140px]"
                                dir="ltr"
                                title={analyticsModel}
                              >
                                {analyticsModel}
                              </span>
                              <button
                                onClick={() => setAnalyticsModel("all")}
                                className="size-5 rounded-md flex items-center justify-center text-[#3D2E22]/40 hover:text-[#3D2E22] hover:bg-[#3D2E22]/10 transition-colors cursor-pointer"
                                aria-label="הסר סינון"
                              >
                                <X className="size-3" />
                              </button>
                            </span>
                          )}
                          {analyticsStatus !== "all" && (
                            <span className="group inline-flex items-center gap-1.5 rounded-lg bg-[#3D2E22]/[0.06] border border-[#3D2E22]/10 pe-1 ps-2.5 py-1 transition-all duration-150 hover:bg-[#3D2E22]/[0.1] hover:border-[#3D2E22]/20">
                              <span className="text-[11px] font-medium text-[#3D2E22]/80">
                                {STATUS_LABELS[analyticsStatus] ?? analyticsStatus}
                              </span>
                              <button
                                onClick={() => setAnalyticsStatus("all")}
                                className="size-5 rounded-md flex items-center justify-center text-[#3D2E22]/40 hover:text-[#3D2E22] hover:bg-[#3D2E22]/10 transition-colors cursor-pointer"
                                aria-label="הסר סינון"
                              >
                                <X className="size-3" />
                              </button>
                            </span>
                          )}
                          <button
                            onClick={clearAll}
                            className="text-[10px] text-[#3D2E22]/40 hover:text-[#3D2E22]/70 transition-colors cursor-pointer ms-0.5"
                          >
                            נקה הכל
                          </button>
                        </div>
                      );
                    })()}
                    {/* ── Charts — cross-fade on filter change, numbers animate smoothly ── */}
                    <AnimatePresence mode="wait">
                      <motion.div
                        key={`${analyticsJobId ?? "all"}-${analyticsDate ?? "all"}-${analyticsOptimizer}-${analyticsModel}-${analyticsStatus}`}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.3, ease: [0.2, 0.8, 0.2, 1] }}
                      >
                        <StaggerContainer className="space-y-6" staggerDelay={0.03}>
                          {/* ── KPI summary row ── */}
                          {chartData.kpis && (
                            <StaggerItem>
                              <div className="grid gap-3 sm:gap-4 grid-cols-2 lg:grid-cols-4">
                                {/* Success rate */}
                                <TooltipProvider>
                                  <UiTooltip>
                                    <TooltipTrigger asChild>
                                      <TiltCard>
                                        <Card className="relative overflow-hidden group/kpi border-border/40 hover:border-border/70 transition-colors duration-300">
                                          <CardContent className="p-5 sm:p-6 relative">
                                            <div className="flex items-start justify-between">
                                              <div className="space-y-3">
                                                <p className="text-[12px] font-medium text-muted-foreground/80 tracking-wide">
                                                  אחוז הצלחה
                                                </p>
                                                <p className="text-4xl font-bold tracking-tighter tabular-nums">
                                                  <AnimatedNumber
                                                    value={Math.round(chartData.kpis.successRate)}
                                                    suffix="%"
                                                  />
                                                </p>
                                              </div>
                                              <div className="size-9 rounded-lg bg-stone-500/[0.07] flex items-center justify-center">
                                                <CheckCircle2 className="size-4 text-stone-500" />
                                              </div>
                                            </div>
                                            <div className="mt-3 flex items-center gap-2">
                                              <div className="flex-1 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                                                <div
                                                  className="h-full rounded-full bg-stone-500/40 transition-all duration-700"
                                                  style={{
                                                    width: `${chartData.kpis.successRate}%`,
                                                  }}
                                                />
                                              </div>
                                              <span className="text-[10px] tabular-nums text-muted-foreground/60 shrink-0">
                                                <AnimatedNumber
                                                  value={chartData.kpis.successCount}
                                                />
                                                /
                                                <AnimatedNumber
                                                  value={chartData.kpis.terminalCount}
                                                />
                                              </span>
                                            </div>
                                          </CardContent>
                                        </Card>
                                      </TiltCard>
                                    </TooltipTrigger>
                                    <TooltipContent side="bottom" className="max-w-xs">
                                      <div className="space-y-1.5 text-xs">
                                        <p className="font-semibold">פרוט נוסף:</p>
                                        <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                                          <span className="text-muted-foreground">הצליחו:</span>
                                          <span className="font-mono tabular-nums">
                                            {chartData.kpis.successCount}
                                          </span>
                                          <span className="text-muted-foreground">
                                            סה"כ הסתיימו:
                                          </span>
                                          <span className="font-mono tabular-nums">
                                            {chartData.kpis.terminalCount}
                                          </span>
                                        </div>
                                      </div>
                                    </TooltipContent>
                                  </UiTooltip>
                                </TooltipProvider>
                                {/* Average improvement */}
                                <TooltipProvider>
                                  <UiTooltip>
                                    <TooltipTrigger asChild>
                                      <TiltCard>
                                        <Card className="relative overflow-hidden group/kpi border-border/40 hover:border-border/70 transition-colors duration-300">
                                          <CardContent className="p-5 sm:p-6 relative">
                                            <div className="flex items-start justify-between">
                                              <div className="space-y-3">
                                                <p className="text-[12px] font-medium text-muted-foreground/80 tracking-wide">
                                                  שיפור ממוצע
                                                </p>
                                                <p
                                                  className={`text-4xl font-bold tracking-tighter tabular-nums ${chartData.kpis.avgImprovement > 0 ? "text-emerald-700" : chartData.kpis.avgImprovement < 0 ? "text-red-600" : ""}`}
                                                >
                                                  <AnimatedNumber
                                                    value={parseFloat(
                                                      chartData.kpis.avgImprovement.toFixed(1),
                                                    )}
                                                    decimals={1}
                                                    prefix={
                                                      chartData.kpis.avgImprovement >= 0 ? "+" : ""
                                                    }
                                                    suffix="%"
                                                  />
                                                </p>
                                              </div>
                                              <div
                                                className={`size-9 rounded-lg flex items-center justify-center ${chartData.kpis.avgImprovement > 0 ? "bg-emerald-500/[0.07]" : chartData.kpis.avgImprovement < 0 ? "bg-red-500/[0.07]" : "bg-stone-500/[0.07]"}`}
                                              >
                                                <TrendingUp
                                                  className={`size-4 ${chartData.kpis.avgImprovement > 0 ? "text-emerald-600" : chartData.kpis.avgImprovement < 0 ? "text-red-500" : "text-stone-500"}`}
                                                />
                                              </div>
                                            </div>
                                            <div className="mt-3 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                                              <div
                                                className={`h-full rounded-full transition-all duration-700 ${chartData.kpis.avgImprovement > 0 ? "bg-emerald-500/40" : chartData.kpis.avgImprovement < 0 ? "bg-red-500/40" : "bg-stone-400/40"}`}
                                                style={{
                                                  width: `${Math.min(Math.abs(chartData.kpis.avgImprovement), 100)}%`,
                                                }}
                                              />
                                            </div>
                                          </CardContent>
                                        </Card>
                                      </TiltCard>
                                    </TooltipTrigger>
                                    <TooltipContent side="bottom" className="max-w-xs">
                                      <div className="space-y-1.5 text-xs">
                                        <p className="font-semibold">פרוט נוסף:</p>
                                        <p className="text-muted-foreground">
                                          שיפור ממוצע בציון הבדיקה לאחר אופטימיזציה
                                        </p>
                                      </div>
                                    </TooltipContent>
                                  </UiTooltip>
                                </TooltipProvider>
                                {/* Average runtime */}
                                <TooltipProvider>
                                  <UiTooltip>
                                    <TooltipTrigger asChild>
                                      <TiltCard>
                                        <Card className="relative overflow-hidden group/kpi border-border/40 hover:border-border/70 transition-colors duration-300">
                                          <CardContent className="p-5 sm:p-6 relative">
                                            <div className="flex items-start justify-between">
                                              <div className="space-y-3">
                                                <p className="text-[12px] font-medium text-muted-foreground/80 tracking-wide">
                                                  זמן ריצה ממוצע
                                                </p>
                                                <p
                                                  className="text-4xl font-bold tracking-tighter tabular-nums"
                                                  dir="ltr"
                                                >
                                                  {formatElapsed(chartData.kpis.avgRuntime)}
                                                </p>
                                              </div>
                                              <div className="size-9 rounded-lg bg-stone-500/[0.07] flex items-center justify-center">
                                                <Clock className="size-4 text-stone-500" />
                                              </div>
                                            </div>
                                            <p className="mt-3 text-[10px] text-muted-foreground/50">
                                              לכל אופטימיזציה
                                            </p>
                                          </CardContent>
                                        </Card>
                                      </TiltCard>
                                    </TooltipTrigger>
                                    <TooltipContent side="bottom" className="max-w-xs">
                                      <div className="space-y-1.5 text-xs">
                                        <p className="font-semibold">פרוט נוסף:</p>
                                        <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                                          <span className="text-muted-foreground">זוגות שרצו:</span>
                                          <span className="font-mono tabular-nums">
                                            {chartData.kpis.totalPairsRun}
                                          </span>
                                        </div>
                                      </div>
                                    </TooltipContent>
                                  </UiTooltip>
                                </TooltipProvider>
                                {/* Best improvement */}
                                <TooltipProvider>
                                  <UiTooltip>
                                    <TooltipTrigger asChild>
                                      <TiltCard>
                                        <Card className="relative overflow-hidden group/kpi border-border/40 hover:border-border/70 transition-colors duration-300">
                                          <CardContent className="p-5 sm:p-6 relative">
                                            <div className="flex items-start justify-between">
                                              <div className="space-y-3">
                                                <p className="text-[12px] font-medium text-muted-foreground/80 tracking-wide">
                                                  שיפור מקסימלי
                                                </p>
                                                <p className="text-4xl font-bold tracking-tighter tabular-nums text-amber-700">
                                                  <AnimatedNumber
                                                    value={parseFloat(
                                                      chartData.kpis.bestImprovement.toFixed(1),
                                                    )}
                                                    decimals={1}
                                                    prefix="+"
                                                    suffix="%"
                                                  />
                                                </p>
                                              </div>
                                              <div className="size-9 rounded-lg bg-amber-500/[0.07] flex items-center justify-center">
                                                <Zap className="size-4 text-amber-600" />
                                              </div>
                                            </div>
                                            <div className="mt-3 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                                              <div
                                                className="h-full rounded-full bg-amber-500/40 transition-all duration-700"
                                                style={{
                                                  width: `${Math.min(chartData.kpis.bestImprovement, 100)}%`,
                                                }}
                                              />
                                            </div>
                                          </CardContent>
                                        </Card>
                                      </TiltCard>
                                    </TooltipTrigger>
                                    <TooltipContent side="bottom" className="max-w-xs">
                                      <div className="space-y-1.5 text-xs">
                                        <p className="font-semibold">פרוט נוסף:</p>
                                        <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                                          <span className="text-muted-foreground">
                                            שורות שנותחו:
                                          </span>
                                          <span className="font-mono tabular-nums">
                                            {chartData.kpis.totalRows.toLocaleString("he-IL")}
                                          </span>
                                          <span className="text-muted-foreground">סריקות:</span>
                                          <span className="font-mono tabular-nums">
                                            {chartData.kpis.gridSearchCount}
                                          </span>
                                          <span className="text-muted-foreground">
                                            ריצות בודדות:
                                          </span>
                                          <span className="font-mono tabular-nums">
                                            {chartData.kpis.singleRunCount}
                                          </span>
                                        </div>
                                      </div>
                                    </TooltipContent>
                                  </UiTooltip>
                                </TooltipProvider>
                              </div>
                            </StaggerItem>
                          )}

                          {/* ── Primary row: scores chart (wider) + status breakdown ── */}
                          <StaggerItem>
                            <AnalyticsSection
                              title={
                                <HelpTip text="השוואת ציוני הבסיס מול הציון המשופר לכל אופטימיזציה שהושלמה">
                                  סקירת ביצועים
                                </HelpTip>
                              }
                              defaultOpen={true}
                              className="border-border/60"
                            >
                              <div className="grid gap-5 md:grid-cols-7">
                                {/* Scores comparison — primary chart */}
                                <div className="md:col-span-4">
                                  <div className="mb-3">
                                    <h4 className="text-sm font-semibold">
                                      ציונים לפי אופטימיזציה
                                    </h4>
                                  </div>
                                  <ScoresChart
                                    data={chartData.improvement}
                                    optimizationIds={chartData.improvementJobIds}
                                    onBarClick={(optimizationId) =>
                                      setAnalyticsJobId(optimizationId)
                                    }
                                  />
                                </div>

                                {/* Status + optimizer breakdown — sidebar */}
                                <div className="md:col-span-3 space-y-6">
                                  {/* Status — as stat bars instead of pie when few categories */}
                                  <div className="space-y-3">
                                    <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest">
                                      סטטוסים
                                    </p>
                                    {chartData.status.map((s, i) => {
                                      const total = chartData.status.reduce(
                                        (a, b) => a + b.value,
                                        0,
                                      );
                                      return (
                                        <div
                                          key={i}
                                          className="space-y-1.5 cursor-pointer hover:opacity-80 transition-opacity"
                                          onClick={() => setAnalyticsStatus(s.key)}
                                        >
                                          <div className="flex items-center justify-between text-sm">
                                            <span className="flex items-center gap-2">
                                              <span
                                                className=" size-2.5 rounded-full shrink-0 ring-1 ring-black/5"
                                                style={{ backgroundColor: s.fill }}
                                              />
                                              <span className="text-[13px]">{s.name}</span>
                                            </span>
                                            <span className="tabular-nums font-semibold text-[13px]">
                                              {s.value}
                                            </span>
                                          </div>
                                          <div className="h-2 rounded-full bg-muted/60 overflow-hidden">
                                            <div
                                              className="h-full rounded-full transition-all duration-500"
                                              style={{
                                                width: `${(s.value / total) * 100}%`,
                                                backgroundColor: s.fill,
                                              }}
                                            />
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>

                                  <div className="border-t border-border" />

                                  {/* Optimizers — as stat bars */}
                                  <div className="space-y-3">
                                    <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest">
                                      אופטימייזרים
                                    </p>
                                    {chartData.optimizer.map((o, i) => {
                                      const total = chartData.optimizer.reduce(
                                        (a, b) => a + b.value,
                                        0,
                                      );
                                      return (
                                        <div
                                          key={i}
                                          className="space-y-1.5 cursor-pointer hover:opacity-80 transition-opacity"
                                          dir="ltr"
                                          onClick={() => setAnalyticsOptimizer(o.name)}
                                        >
                                          <div className="flex items-center justify-between text-sm">
                                            <span className="flex items-center gap-2">
                                              <span
                                                className="size-2.5 rounded-full shrink-0 ring-1 ring-black/5"
                                                style={{
                                                  backgroundColor: `var(--color-chart-${(i % 5) + 1})`,
                                                }}
                                              />
                                              <span className="text-[13px]">{o.name}</span>
                                            </span>
                                            <span className="tabular-nums font-semibold text-[13px]">
                                              {o.value}
                                            </span>
                                          </div>
                                          <div className="h-2 rounded-full bg-muted/60 overflow-hidden">
                                            <div
                                              className="h-full rounded-full transition-all duration-500"
                                              style={{
                                                width: `${(o.value / total) * 100}%`,
                                                backgroundColor: `var(--color-chart-${(i % 5) + 1})`,
                                              }}
                                            />
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>

                                  {/* Job type inline */}
                                  {chartData.jobTypeData.length > 0 && (
                                    <>
                                      <div className="border-t border-border" />
                                      <div className="space-y-3">
                                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                                          סוג אופטימיזציה
                                        </p>
                                        {chartData.jobTypeData.map((d, i) => {
                                          const total = chartData.jobTypeData.reduce(
                                            (a, b) => a + b.value,
                                            0,
                                          );
                                          return (
                                            <div key={i} className="space-y-1">
                                              <div className="flex items-center justify-between text-sm">
                                                <span>{d.name}</span>
                                                <span className="tabular-nums font-medium">
                                                  {d.value}
                                                </span>
                                              </div>
                                              <div className="h-2 rounded-full bg-muted overflow-hidden">
                                                <div
                                                  className="h-full rounded-full bg-primary/70 transition-all"
                                                  style={{ width: `${(d.value / total) * 100}%` }}
                                                />
                                              </div>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    </>
                                  )}
                                </div>
                              </div>
                            </AnalyticsSection>
                          </StaggerItem>

                          {/* ── Efficiency & Runtime ── */}
                          {(chartData.runtimeDistribution.length > 0 ||
                            chartData.efficiencyData.length > 0) && (
                            <StaggerItem>
                              <AnalyticsSection
                                title={
                                  <HelpTip text="ניתוח זמני ריצה ויעילות — כמה שיפור מתקבל ביחס לזמן">
                                    יעילות וזמני ריצה
                                  </HelpTip>
                                }
                                defaultOpen={true}
                                className="border-border/60"
                              >
                                <div className="grid gap-5 md:grid-cols-2">
                                  {chartData.runtimeDistribution.length > 0 && (
                                    <div>
                                      <div className="mb-3">
                                        <h4 className="text-sm font-semibold">
                                          <HelpTip text="משך הריצה בדקות לכל אופטימיזציה שהושלמה">
                                            התפלגות זמני ריצה
                                          </HelpTip>
                                        </h4>
                                      </div>
                                      <RuntimeDistributionChart
                                        data={chartData.runtimeDistribution}
                                        optimizationIds={chartData.runtimeDistributionJobIds}
                                        onBarClick={(optimizationId) =>
                                          setAnalyticsJobId(optimizationId)
                                        }
                                      />
                                    </div>
                                  )}
                                  {chartData.efficiencyData.length > 0 && (
                                    <div>
                                      <div className="mb-3">
                                        <h4 className="text-sm font-semibold">
                                          <HelpTip text="אחוזי שיפור לכל דקת ריצה — ערך גבוה משמעו אופטימיזציה יעילה יותר">
                                            יעילות: שיפור לדקה
                                          </HelpTip>
                                        </h4>
                                      </div>
                                      <EfficiencyChart
                                        data={chartData.efficiencyData}
                                        optimizationIds={chartData.efficiencyJobIds}
                                        onBarClick={(optimizationId) =>
                                          setAnalyticsJobId(optimizationId)
                                        }
                                      />
                                    </div>
                                  )}
                                </div>
                                {chartData.datasetVsImprovement.length > 0 && (
                                  <div className="mt-5">
                                    <div className="mb-3">
                                      <h4 className="text-sm font-semibold">
                                        <HelpTip text="האם יותר נתונים מובילים לשיפור טוב יותר — כל נקודה היא אופטימיזציה אחת">
                                          גודל דאטאסט מול שיפור
                                        </HelpTip>
                                      </h4>
                                    </div>
                                    <DatasetVsImprovementChart
                                      data={chartData.datasetVsImprovement}
                                      optimizationIds={chartData.datasetVsImprovementIds}
                                      onDotClick={(id) => setAnalyticsJobId(id)}
                                    />
                                  </div>
                                )}
                              </AnalyticsSection>
                            </StaggerItem>
                          )}

                          {/* ── Timeline ── */}
                          {chartData.timelineData.length > 0 && (
                            <StaggerItem>
                              <AnalyticsSection
                                title={
                                  <HelpTip text="מספר האופטימיזציות שהוגשו לפי יום">
                                    ציר זמן
                                  </HelpTip>
                                }
                                defaultOpen={true}
                                className="border-border/60"
                              >
                                <TimelineChart
                                  data={chartData.timelineData}
                                  dates={chartData.timelineDates}
                                  onBarClick={(date) => setAnalyticsDate(date)}
                                />
                              </AnalyticsSection>
                            </StaggerItem>
                          )}

                          {/* ── Optimizer comparisons ── */}
                          {chartData.avgByOptimizer.length > 0 && (
                            <StaggerItem>
                              <AnalyticsSection
                                title={
                                  <HelpTip text="שיפור ממוצע באחוזים שכל אופטימייזר השיג על פני כל ההרצות">
                                    השוואת אופטימייזרים
                                  </HelpTip>
                                }
                                defaultOpen={true}
                                className="border-border/60"
                              >
                                <div className="grid gap-5 md:grid-cols-7">
                                  <div className="md:col-span-4">
                                    <OptimizerChart
                                      data={chartData.avgByOptimizer}
                                      onBarClick={(name) => setAnalyticsOptimizer(name)}
                                    />
                                  </div>
                                  <div className="md:col-span-3">
                                    <div className="mb-3">
                                      <h4 className="text-sm font-semibold">מודלים פופולריים</h4>
                                    </div>
                                    {chartData.modelUsage.length > 0 ? (
                                      <div className="space-y-3">
                                        {chartData.modelUsage.map((m, i) => {
                                          const maxCount = chartData.modelUsage[0]?.count ?? 1;
                                          return (
                                            <div
                                              key={i}
                                              className="space-y-1.5 cursor-pointer hover:opacity-80 transition-opacity"
                                              onClick={() => setAnalyticsModel(m.name)}
                                            >
                                              <div
                                                className="flex items-center justify-between text-sm"
                                                dir="ltr"
                                              >
                                                <span
                                                  className="font-mono truncate max-w-[200px]"
                                                  title={m.name}
                                                >
                                                  {m.name}
                                                </span>
                                                <span className="tabular-nums font-medium">
                                                  {m.count}
                                                </span>
                                              </div>
                                              <div
                                                className="h-2 rounded-full bg-muted overflow-hidden"
                                                dir="ltr"
                                              >
                                                <div
                                                  className="h-full rounded-full bg-primary/60 transition-all"
                                                  style={{
                                                    width: `${(m.count / maxCount) * 100}%`,
                                                  }}
                                                />
                                              </div>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    ) : (
                                      <div className="flex h-[150px] items-center justify-center">
                                        <p className="text-sm text-muted-foreground">
                                          אין מידע על מודלים
                                        </p>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </AnalyticsSection>
                            </StaggerItem>
                          )}

                          {/* ── Leaderboard ── */}
                          {chartData.topJobs.length > 0 && (
                            <StaggerItem>
                              <AnalyticsSection
                                title={
                                  <div className="flex items-center gap-2">
                                    <span className="size-5 rounded-md bg-gradient-to-br from-stone-400/20 to-stone-500/10 flex items-center justify-center ring-1 ring-stone-400/10">
                                      <TrendingUp className="size-3 text-stone-600" />
                                    </span>
                                    <HelpTip text="ההרצות שהשיגו את השיפור הגדול ביותר בציון, מהטוב לפחות טוב">
                                      השיפורים הגדולים ביותר
                                    </HelpTip>
                                  </div>
                                }
                                defaultOpen={true}
                                className="border-border/60"
                              >
                                <div className="pt-0">
                                  {/* Desktop table */}
                                  <div className="hidden sm:block overflow-x-auto" dir="rtl">
                                    <Table className="min-w-[500px]">
                                      <TableHeader>
                                        <TableRow className="border-b-0">
                                          <TableHead className="text-center w-10 text-[11px] uppercase tracking-wider text-stone-400">
                                            #
                                          </TableHead>
                                          <TableHead className="text-start text-[11px] uppercase tracking-wider text-stone-400">
                                            מזהה אופטימיזציה
                                          </TableHead>
                                          <TableHead className="text-start text-[11px] uppercase tracking-wider text-stone-400">
                                            אופטימייזר
                                          </TableHead>
                                          <TableHead className="text-center text-[11px] uppercase tracking-wider text-stone-400">
                                            לפני
                                          </TableHead>
                                          <TableHead className="text-center text-[11px] uppercase tracking-wider text-stone-400">
                                            אחרי
                                          </TableHead>
                                          <TableHead className="text-center text-[11px] uppercase tracking-wider text-stone-400">
                                            שיפור
                                          </TableHead>
                                          <TableHead className="w-10"></TableHead>
                                        </TableRow>
                                      </TableHeader>
                                      <TableBody>
                                        {chartData.topJobs
                                          .slice(0, leaderboardLimit)
                                          .map((j, i) => {
                                            const fmt = (n: number | undefined | null) => {
                                              if (n == null) return "\u2014";
                                              return (n > 1 ? n : n * 100).toFixed(1) + "%";
                                            };
                                            const imp = j.metric_improvement!;
                                            const impPct = Math.abs(imp) > 1 ? imp : imp * 100;
                                            const baseline =
                                              j.baseline_test_metric != null
                                                ? j.baseline_test_metric > 1
                                                  ? j.baseline_test_metric
                                                  : j.baseline_test_metric * 100
                                                : null;
                                            const optimized =
                                              j.optimized_test_metric != null
                                                ? j.optimized_test_metric > 1
                                                  ? j.optimized_test_metric
                                                  : j.optimized_test_metric * 100
                                                : null;

                                            const copyCell =
                                              (text: string) => (e: React.MouseEvent) => {
                                                e.stopPropagation();
                                                navigator.clipboard.writeText(text);
                                                toast.success(msg("clipboard.copied_short"), {
                                                  autoClose: 1000,
                                                });
                                              };
                                            const copyCls =
                                              "cursor-pointer hover:bg-stone-500/[0.04] transition-colors";
                                            return (
                                              <TableRow
                                                key={j.optimization_id}
                                                className="group/row border-border/40 hover:bg-stone-500/[0.03]"
                                              >
                                                <TableCell className="text-center py-3">
                                                  <Medal
                                                    className={`size-4 mx-auto ${i === 0 ? "text-yellow-500" : i === 1 ? "text-slate-400" : "text-amber-700"}`}
                                                  />
                                                </TableCell>
                                                <TableCell className="py-3 text-start">
                                                  <Link
                                                    href={`/optimizations/${j.optimization_id}`}
                                                    className="font-mono text-[11px] text-primary hover:text-primary/80 transition-colors underline-offset-4 hover:underline"
                                                    dir="ltr"
                                                    title={j.optimization_id}
                                                  >
                                                    {j.optimization_id.slice(0, 8)}…
                                                  </Link>
                                                </TableCell>
                                                <TableCell
                                                  className={`py-3 text-start ${copyCls}`}
                                                  onClick={copyCell(j.optimizer_name ?? "")}
                                                >
                                                  <span
                                                    className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-stone-500/[0.06] text-[12px] font-medium text-stone-700"
                                                    dir="ltr"
                                                  >
                                                    {j.optimizer_name}
                                                  </span>
                                                </TableCell>
                                                <TableCell
                                                  className={`text-center py-3 ${copyCls}`}
                                                  onClick={copyCell(fmt(j.baseline_test_metric))}
                                                >
                                                  <div className="flex flex-col items-center gap-1">
                                                    <span className="font-mono tabular-nums text-[12px] text-stone-400">
                                                      {fmt(j.baseline_test_metric)}
                                                    </span>
                                                    <div className="w-14 h-1 rounded-full bg-stone-200/60 overflow-hidden">
                                                      <div
                                                        className="h-full rounded-full bg-stone-400/40 transition-all"
                                                        style={{
                                                          width: `${baseline != null ? (baseline / 100) * 100 : 0}%`,
                                                        }}
                                                      />
                                                    </div>
                                                  </div>
                                                </TableCell>
                                                <TableCell
                                                  className={`text-center py-3 ${copyCls}`}
                                                  onClick={copyCell(fmt(j.optimized_test_metric))}
                                                >
                                                  <div className="flex flex-col items-center gap-1">
                                                    <span className="font-mono tabular-nums text-[12px] font-semibold text-stone-700">
                                                      {fmt(j.optimized_test_metric)}
                                                    </span>
                                                    <div className="w-14 h-1 rounded-full bg-stone-200/60 overflow-hidden">
                                                      <div
                                                        className="h-full rounded-full bg-stone-600/50 transition-all"
                                                        style={{
                                                          width: `${optimized != null ? (optimized / 100) * 100 : 0}%`,
                                                        }}
                                                      />
                                                    </div>
                                                  </div>
                                                </TableCell>
                                                <TableCell
                                                  className={`text-center py-3 ${copyCls}`}
                                                  onClick={copyCell(
                                                    `${impPct >= 0 ? "+" : ""}${impPct.toFixed(1)}%`,
                                                  )}
                                                >
                                                  <div className="flex flex-col items-center gap-1">
                                                    <span
                                                      className={`font-mono tabular-nums text-[12px] font-semibold ${impPct > 0 ? "text-emerald-700" : impPct < 0 ? "text-red-600" : "text-stone-500"}`}
                                                    >
                                                      {impPct >= 0 ? "+" : ""}
                                                      {impPct.toFixed(1)}%
                                                    </span>
                                                    <div className="w-14 h-1 rounded-full bg-stone-200/60 overflow-hidden">
                                                      <div
                                                        className={`h-full rounded-full transition-all ${impPct > 0 ? "bg-emerald-500/50" : impPct < 0 ? "bg-red-500/50" : "bg-stone-400/40"}`}
                                                        style={{
                                                          width: `${Math.min(Math.abs(impPct), 100)}%`,
                                                        }}
                                                      />
                                                    </div>
                                                  </div>
                                                </TableCell>
                                              </TableRow>
                                            );
                                          })}
                                      </TableBody>
                                    </Table>
                                  </div>

                                  {/* Mobile card view */}
                                  <div className="sm:hidden space-y-3">
                                    {chartData.topJobs.slice(0, leaderboardLimit).map((j, i) => {
                                      const fmt = (n: number | undefined | null) => {
                                        if (n == null) return "—";
                                        return (n > 1 ? n : n * 100).toFixed(1) + "%";
                                      };
                                      const imp = j.metric_improvement!;
                                      const impPct = Math.abs(imp) > 1 ? imp : imp * 100;

                                      return (
                                        <Card
                                          key={j.optimization_id}
                                          className="border-border/40 hover:border-border/60 transition-colors"
                                        >
                                          <CardContent className="p-4 space-y-3">
                                            <div className="flex items-start justify-between gap-3">
                                              <div className="flex items-center gap-2">
                                                <Medal
                                                  className={`size-5 shrink-0 ${i === 0 ? "text-yellow-500" : i === 1 ? "text-slate-400" : "text-amber-700"}`}
                                                />
                                                <div className="min-w-0">
                                                  <Link
                                                    href={`/optimizations/${j.optimization_id}`}
                                                    className="font-mono text-xs text-primary hover:text-primary/80 transition-colors underline-offset-4 hover:underline block truncate"
                                                    dir="ltr"
                                                    title={j.optimization_id}
                                                  >
                                                    {j.optimization_id.slice(0, 12)}…
                                                  </Link>
                                                  <span
                                                    className="text-xs text-muted-foreground"
                                                    dir="ltr"
                                                  >
                                                    {j.optimizer_name}
                                                  </span>
                                                </div>
                                              </div>
                                              <button
                                                onClick={() =>
                                                  router.push(`/optimizations/${j.optimization_id}`)
                                                }
                                                className="p-1.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-all shrink-0"
                                              >
                                                <ExternalLink className="size-3.5" />
                                              </button>
                                            </div>
                                            <div className="grid grid-cols-3 gap-3 text-center">
                                              <div>
                                                <p className="text-[10px] text-muted-foreground mb-1">
                                                  לפני
                                                </p>
                                                <p className="font-mono text-sm text-stone-500">
                                                  {fmt(j.baseline_test_metric)}
                                                </p>
                                              </div>
                                              <div>
                                                <p className="text-[10px] text-muted-foreground mb-1">
                                                  אחרי
                                                </p>
                                                <p className="font-mono text-sm font-semibold">
                                                  {fmt(j.optimized_test_metric)}
                                                </p>
                                              </div>
                                              <div>
                                                <p className="text-[10px] text-muted-foreground mb-1">
                                                  שיפור
                                                </p>
                                                <p
                                                  className={`font-mono text-sm font-bold ${impPct > 0 ? "text-emerald-700" : impPct < 0 ? "text-red-600" : "text-stone-500"}`}
                                                >
                                                  {impPct >= 0 ? "+" : ""}
                                                  {impPct.toFixed(1)}%
                                                </p>
                                              </div>
                                            </div>
                                          </CardContent>
                                        </Card>
                                      );
                                    })}
                                  </div>
                                </div>
                              </AnalyticsSection>
                            </StaggerItem>
                          )}
                        </StaggerContainer>
                      </motion.div>
                    </AnimatePresence>
                    {/* Empty state for filtered results */}
                    {analyticsFilteredItems.length === 0 &&
                      (analyticsJobId ||
                        analyticsDate ||
                        analyticsOptimizer !== "all" ||
                        analyticsModel !== "all" ||
                        analyticsStatus !== "all") && (
                        <AnalyticsEmpty
                          variant="no-results"
                          onClearFilters={() => {
                            setAnalyticsOptimizer("all");
                            setAnalyticsModel("all");
                            setAnalyticsStatus("all");
                          }}
                        />
                      )}
                  </div>
                ) : (
                  <AnalyticsEmpty variant="no-data" />
                )}
              </TabsContent>
            </Tabs>
          )}
        </FadeIn>

        {/* Delete confirmation dialog */}
        <Dialog
          open={!!deleteTarget}
          onOpenChange={(open) => {
            if (!open) setDeleteTarget(null);
          }}
        >
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle>מחיקת אופטימיזציה</DialogTitle>
              <DialogDescription>
                האם למחוק את האופטימיזציה{" "}
                <span className="font-mono font-medium text-foreground break-all">
                  {deleteTarget?.id}
                </span>
                ?
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="grid grid-cols-2 gap-2">
              <Button
                variant="outline"
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
                className="w-full justify-center"
              >
                ביטול
              </Button>
              <Button
                variant="destructive"
                onClick={confirmDelete}
                disabled={deleting}
                className="w-full justify-center"
              >
                {deleting ? <Loader2 className="size-4 animate-spin" /> : "מחיקה"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </Skeleton>
  );
}
