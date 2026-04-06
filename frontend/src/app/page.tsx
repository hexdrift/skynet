"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { Plus, ChevronRight, ChevronLeft, Loader2, BarChart3, TableIcon, Trash2, Activity, CheckCircle2, XCircle, Layers, TrendingUp, Clock, Database, ArrowLeftRight } from "lucide-react";
import { toast } from "react-toastify";
import { AnimatePresence, motion } from "framer-motion";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

import { Button } from "@/components/ui/button";
import { Tooltip as UiTooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FadeIn, TiltCard, AnimatedNumber, StaggerContainer, StaggerItem } from "@/components/motion";
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
 TableBody,
 TableCell,
 TableRow,
} from "@/components/ui/table";
import { ColumnHeader, useColumnFilters, type SortDir } from "@/components/excel-filter";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "boneyard-js/react";
import { listJobs, cancelJob, deleteJob, getQueueStatus } from "@/lib/api";
import { ACTIVE_STATUSES, STATUS_LABELS } from "@/lib/constants";
import { dashboardBones } from "@/components/dashboard-bones";
import type { PaginatedJobsResponse, JobSummaryResponse, JobStatus, QueueStatusResponse } from "@/lib/types";

const PAGE_SIZE = 20;


const STATUS_COLORS: Record<string, string> = {
 success: "var(--color-chart-2)",
 failed: "var(--color-chart-1)",
 running: "var(--color-chart-3)",
 pending: "var(--color-chart-4)",
 cancelled: "var(--color-chart-5)",
 validating: "var(--color-chart-3)",
};

function statusBadge(status: JobStatus) {
 const label = STATUS_LABELS[status] ?? status;
 switch (status) {
 case "pending":
 return <Badge variant="outline" className="status-pill-pending">{label}</Badge>;
 case "validating":
 return <Badge variant="outline" className="border-primary/40 text-primary">{label}</Badge>;
 case "running":
 return <Badge variant="outline" className="status-pill-running animate-pulse">{label}</Badge>;
 case "success":
 return <Badge variant="outline" className="status-pill-success">{label}</Badge>;
 case "failed":
 return <Badge variant="outline" className="status-pill-failed">{label}</Badge>;
 case "cancelled":
 return <Badge variant="secondary">{label}</Badge>;
 default:
 return <Badge variant="outline">{status}</Badge>;
 }
}

function typeBadge(jobType: string) {
 if (jobType === "grid_search") {
 return <Badge variant="outline" className="border-primary/30 text-primary">סריקה</Badge>;
 }
 return <Badge variant="secondary">ריצה בודדת</Badge>;
}

function formatElapsed(elapsedSeconds?: number): string {
 if (elapsedSeconds == null) return "-";
 const hrs = Math.floor(elapsedSeconds / 3600);
 const mins = Math.floor((elapsedSeconds % 3600) / 60);
 const secs = Math.floor(elapsedSeconds % 60);
 const pad = (n: number) => String(n).padStart(2,"0");
 if (hrs > 0) return `${hrs}:${pad(mins)}:${pad(secs)}`;
 return `${mins}:${pad(secs)}`;
}

function formatDate(iso: string): string {
 try {
 return new Date(iso).toLocaleString("he-IL");
 } catch {
 return iso;
 }
}

function formatRelativeTime(iso: string): string {
 try {
 const diff = Date.now() - new Date(iso).getTime();
 const mins = Math.floor(diff / 60000);
 if (mins < 1) return "עכשיו";
 if (mins < 60) return `לפני ${mins} דק'`;
 const hours = Math.floor(mins / 60);
 if (hours < 24) return `לפני ${hours} שע'`;
 const days = Math.floor(hours / 24);
 if (days < 7) return `לפני ${days} ימים`;
 return formatDate(iso);
 } catch {
 return formatDate(iso);
 }
}

function formatScore(job: JobSummaryResponse): React.ReactNode {
 const baseline = job.baseline_test_metric;
 const optimized = job.optimized_test_metric;
 const improvement = job.metric_improvement;

 if (baseline == null && optimized == null) return "-";

 const fmt = (n: number) => (n > 1 ? n : n * 100).toFixed(1) +"%";

 if (baseline != null && optimized != null && improvement != null) {
 const color = improvement > 0 ? "text-[var(--success)]": improvement < 0 ? "text-[var(--danger)]":"text-muted-foreground";
 const sign = improvement > 0 ?"+":"";
 return (
 <span className="flex flex-col gap-0.5">
 <span className="flex items-center gap-1 text-xs">
 <span className="text-muted-foreground">{fmt(baseline)}</span>
 <span className="text-muted-foreground/50">&rarr;</span>
 <span className="font-medium">{fmt(optimized)}</span>
 <span className={`${color} font-medium`}>({sign}{(Math.abs(improvement) > 1 ? improvement : improvement * 100).toFixed(1)}%)</span>
 </span>
 {job.best_pair_label && (
 <span className="text-[10px] text-muted-foreground truncate max-w-[160px]" title={job.best_pair_label}>{job.best_pair_label}</span>
 )}
 </span>
 );
 }

 if (optimized != null) return <span className="font-medium text-xs">{fmt(optimized)}</span>;
 if (baseline != null) return <span className="text-muted-foreground text-xs">{fmt(baseline)}</span>;
 return "-";
}

function formatId(id: string): string {
 return id;
}

/* ── Custom tooltip for charts ── */
function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number; name: string; color?: string }>; label?: string }) {
 if (!active || !payload?.length) return null;
 return (
 <div className="rounded-xl border border-border/60 bg-background/95 backdrop-blur-sm p-3 shadow-lg text-sm" dir="rtl">
 {label && <p className="font-semibold mb-2 text-foreground">{label}</p>}
 <div className="space-y-1">
 {payload.map((p, i) => (
 <div key={i} className="flex items-center gap-2 text-muted-foreground">
 {p.color && <span className="size-2.5 rounded-full shrink-0 ring-1 ring-black/5" style={{ backgroundColor: p.color }} />}
 <span className="text-xs">{p.name}:</span>
 <span className="font-mono font-semibold text-foreground ms-auto tabular-nums" dir="ltr">{p.value}</span>
 </div>
 ))}
 </div>
 </div>
 );
}

export default function DashboardPage() {
 const router = useRouter();
 const { data: session } = useSession();
 const sessionUser = session?.user?.name ??"";
 const isAdmin = (session?.user as Record<string, unknown> | undefined)?.role ==="admin";

 const [mounted, setMounted] = useState(false);
 useEffect(() => setMounted(true), []);

 // Analytics filters
 const [activeTab, setActiveTab] = useState("jobs");
 const [analyticsOptimizer, setAnalyticsOptimizer] = useState<string>("all");
 const [analyticsModel, setAnalyticsModel] = useState<string>("all");
 const [analyticsStatus, setAnalyticsStatus] = useState<string>("all");

 const [data, setData] = useState<PaginatedJobsResponse | null>(null);
 const [loading, setLoading] = useState(true);
 const [error, setError] = useState<string | null>(null);
 const [offset, setOffset] = useState(0);
 const [queueStatus, setQueueStatus] = useState<QueueStatusResponse | null>(null);

 // Excel-style column filters + sort
 const { filters, setColumnFilter, openFilter, setOpenFilter, clearAll, activeCount } = useColumnFilters();
 const [sortKey, setSortKey] = useState<string>("created_at");
 const [sortDir, setSortDir] = useState<SortDir>("desc");
 const toggleSort = (key: string) => {
 if (sortKey === key) setSortDir((d) => d ==="asc"? "desc":"asc");
 else { setSortKey(key); setSortDir("asc"); }
 };

 const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
 const [deleteTarget, setDeleteTarget] = useState<{ id: string; status: string } | null>(null);
 const [deleting, setDeleting] = useState(false);
 const [compareMode, setCompareMode] = useState(false);
 const [compareSelection, setCompareSelection] = useState<Set<string>>(new Set());

 const toggleCompare = (jobId: string, e: React.MouseEvent) => {
 e.stopPropagation();
 setCompareSelection((prev) => {
 const next = new Set(prev);
 if (next.has(jobId)) { next.delete(jobId); }
 else if (next.size < 2) { next.add(jobId); }
 return next;
 });
 };

 const fetchJobs = useCallback(async () => {
 try {
 const result = await listJobs({
 username: isAdmin ? undefined : (sessionUser || undefined),
 limit: 200,
 });
 setData(result);
 setError(null);
 } catch (e) {
 setError(e instanceof Error ? e.message : "שגיאה בטעינת אופטימיזציות");
 } finally {
 setLoading(false);
 }
 }, [sessionUser, isAdmin]);

 useEffect(() => { setLoading(true); fetchJobs(); }, [fetchJobs]);

 useEffect(() => {
 getQueueStatus().then(setQueueStatus).catch(() => {});
 const interval = setInterval(() => {
 getQueueStatus().then(setQueueStatus).catch(() => {});
 }, 10000);
 return () => clearInterval(interval);
 }, []);

 const confirmDelete = async () => {
 if (!deleteTarget) return;
 setDeleting(true);
 try {
 if (ACTIVE_STATUSES.has(deleteTarget.status as JobStatus)) {
 await cancelJob(deleteTarget.id);
 await new Promise((r) => setTimeout(r, 500));
 }
 await deleteJob(deleteTarget.id);
 setDeleteTarget(null);
 fetchJobs();
 } catch (err) {
 toast.error(err instanceof Error ? err.message : "מחיקה נכשלה");
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
 eventSource = new EventSource(`${API}/jobs/stream`);
 eventSource.onmessage = () => { fetchJobs(); };
 eventSource.addEventListener("idle", () => { eventSource?.close(); fetchJobs(); });
 eventSource.onerror = () => {
 eventSource?.close();
 eventSource = null;
 // Fall back to polling
 timerRef.current = setInterval(fetchJobs, 5000);
 };
 } catch {
 timerRef.current = setInterval(fetchJobs, 5000);
 }

 return () => {
 eventSource?.close();
 if (timerRef.current) clearInterval(timerRef.current);
 };
 }, [data, fetchJobs]);

 useEffect(() => { setOffset(0); }, [filters, sortKey, sortDir]);

 /* ── Client-side filter + sort ── */
 const filteredItems = useMemo(() => {
 if (!data) return [];
 let items = data.items.filter((job) => {
 for (const [col, allowed] of Object.entries(filters)) {
 if (allowed.size === 0) continue;
 const val = String((job as unknown as Record<string, unknown>)[col] ??"");
 if (!allowed.has(val)) return false;
 }
 return true;
 });
 items.sort((a, b) => {
 const av = (a as unknown as Record<string, unknown>)[sortKey];
 const bv = (b as unknown as Record<string, unknown>)[sortKey];
 const cmp = String(av ??"").localeCompare(String(bv ??""),"he", { numeric: true });
 return sortDir ==="asc"? cmp : -cmp;
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
 const vals = [...new Set(items.map((j) => String((j as unknown as Record<string, unknown>)[key] ??"")))].filter(Boolean).sort();
 return vals.map((v) => ({ value: v, label: labelFn ? labelFn(v) : v }));
 };
 return {
 job_id: unique("job_id"),
 status: unique("status", (v) => STATUS_LABELS[v] ?? v),
 job_type: unique("job_type", (v) => v ==="grid_search"?"סריקה":"ריצה בודדת"),
 module_name: unique("module_name"),
 optimizer_name: unique("optimizer_name"),
 };
 }, [data]);

 /* ── Aggregated chart data ── */
 // Unique values for analytics filter dropdowns
 const analyticsOptions = useMemo(() => {
 if (!data) return { optimizers: [], models: [] };
 const optimizers = [...new Set(data.items.map(j => j.optimizer_name).filter(Boolean))] as string[];
 const models = [...new Set(data.items.map(j => j.model_name).filter(Boolean))] as string[];
 return { optimizers, models };
 }, [data]);

 const chartData = useMemo(() => {
 if (!data) return { status: [], improvement: [], optimizer: [], kpis: null, avgByOptimizer: [], runtimeByOptimizer: [], modelUsage: [], topJobs: [], jobTypeData: [] };
 let items = data.items;
 if (analyticsOptimizer !== "all") items = items.filter(j => j.optimizer_name === analyticsOptimizer);
 if (analyticsModel !== "all") items = items.filter(j => j.model_name === analyticsModel);
 if (analyticsStatus !== "all") items = items.filter(j => j.status === analyticsStatus);
 const successful = items.filter((j) => j.status ==="success");
 const terminal = items.filter((j) => j.status ==="success"|| j.status ==="failed");

 // Status distribution
 const statusCounts: Record<string, number> = {};
 for (const j of items) {
 statusCounts[j.status] = (statusCounts[j.status] ?? 0) + 1;
 }
 const statusData = Object.entries(statusCounts).map(([status, count]) => ({
 name: STATUS_LABELS[status] ?? status,
 value: count,
 fill: STATUS_COLORS[status] ?? "var(--color-chart-5)",
 }));

 // Improvement per completed job (bar chart)
 const improvementData = items
 .filter((j) => j.status ==="success"&& j.optimized_test_metric != null)
 .slice(0, 10)
 .map((j) => {
 const opt = j.optimized_test_metric ?? 0;
 const bl = j.baseline_test_metric ?? 0;
 return {
 name: j.job_id.slice(0, 6),
 ציון_משופר: Math.round(opt > 1 ? opt : opt * 100),
 ציון_התחלתי: Math.round(bl > 1 ? bl : bl * 100),
 };
 });

 // Optimizer usage
 const optCounts: Record<string, number> = {};
 for (const j of items) {
 const opt = j.optimizer_name ??"אחר";
 optCounts[opt] = (optCounts[opt] ?? 0) + 1;
 }
 const optimizerData = Object.entries(optCounts).map(([name, count]) => ({ name, value: count }));

 // ── KPIs ──
 const successRate = terminal.length > 0 ? (successful.length / terminal.length) * 100 : 0;
 const improvements = successful.filter((j) => j.metric_improvement != null).map((j) => {
 const v = j.metric_improvement!;
 return Math.abs(v) > 1 ? v : v * 100;
 });
 const avgImprovement = improvements.length > 0 ? improvements.reduce((a, b) => a + b, 0) / improvements.length : 0;
 const runtimes = successful.filter((j) => j.elapsed_seconds != null).map((j) => j.elapsed_seconds!);
 const avgRuntime = runtimes.length > 0 ? runtimes.reduce((a, b) => a + b, 0) / runtimes.length : 0;
 const totalRows = items.reduce((sum, j) => sum + (j.dataset_rows ?? 0), 0);
 const kpis = { successRate, avgImprovement, avgRuntime, totalRows, successCount: successful.length, terminalCount: terminal.length };

 // ── Average improvement by optimizer ──
 const optGroups: Record<string, number[]> = {};
 for (const j of successful) {
 if (j.metric_improvement == null || !j.optimizer_name) continue;
 const v = Math.abs(j.metric_improvement) > 1 ? j.metric_improvement : j.metric_improvement * 100;
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
 const m = j.model_name ?? (j.best_pair_label?.split(" + ")[0]);
 if (m) modelCounts[m] = (modelCounts[m] ?? 0) + 1;
 }
 const modelUsage = Object.entries(modelCounts)
 .sort((a, b) => b[1] - a[1])
 .slice(0, 8)
 .map(([name, count]) => ({ name, count }));

 // ── Job type distribution ──
 const typeCounts: Record<string, number> = {};
 for (const j of items) {
 const t = j.job_type ==="grid_search"?"סריקה":"ריצה בודדת";
 typeCounts[t] = (typeCounts[t] ?? 0) + 1;
 }
 const jobTypeData = Object.entries(typeCounts).map(([name, value]) => ({ name, value }));

 // ── Top improvements ──
 const topJobs = [...successful]
 .filter((j) => j.metric_improvement != null)
 .sort((a, b) => {
 const ai = Math.abs(a.metric_improvement!) > 1 ? a.metric_improvement! : a.metric_improvement! * 100;
 const bi = Math.abs(b.metric_improvement!) > 1 ? b.metric_improvement! : b.metric_improvement! * 100;
 return bi - ai;
 })
 .slice(0, 5);

 return { status: statusData, improvement: improvementData, optimizer: optimizerData, kpis, avgByOptimizer, runtimeByOptimizer, modelUsage, topJobs, jobTypeData };
 }, [data, analyticsOptimizer, analyticsModel, analyticsStatus]);

 const analyticsFilteredItems = useMemo(() => {
 if (!data) return [];
 let items = data.items;
 if (analyticsOptimizer !== "all") items = items.filter(j => j.optimizer_name === analyticsOptimizer);
 if (analyticsModel !== "all") items = items.filter(j => j.model_name === analyticsModel);
 if (analyticsStatus !== "all") items = items.filter(j => j.status === analyticsStatus);
 return items;
 }, [data, analyticsOptimizer, analyticsModel, analyticsStatus]);

 const statsSource = activeTab === "analytics" ? analyticsFilteredItems : filteredItems;
 const stats = data ? {
 total: statsSource.length,
 success: statsSource.filter(j => j.status === "success").length,
 running: statsSource.filter(j => ACTIVE_STATUSES.has(j.status)).length,
 failed: statsSource.filter(j => j.status === "failed").length,
 } : null;

 return (
 <Skeleton
  name="dashboard"
  loading={loading && !data}
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
 {stats.running > 0 && <span className="text-amber-500 font-medium"> &middot; {stats.running} פעילות</span>}
 </p>
 )}
 </div>
 </div>
 </FadeIn>

 {/* Stats cards */}
 {stats && (
 <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
 <TiltCard>
 <Card className="relative overflow-hidden group/stat">
 <div className="absolute inset-0 bg-gradient-to-br from-stone-600/[0.06] via-transparent to-amber-600/[0.04] opacity-0 group-hover/stat:opacity-100 transition-opacity duration-300"/>
 <CardContent className="p-4 sm:p-5 relative">
 <div className="flex items-center justify-between mb-3">
 <p className="text-sm font-medium text-muted-foreground">סה״כ</p>
 <div className=" size-10 rounded-xl bg-gradient-to-br from-stone-600/15 to-amber-600/10 flex items-center justify-center ring-1 ring-stone-600/10">
 <Layers className="size-[18px] text-stone-700" />
 </div>
 </div>
 <p className="text-3xl font-bold tracking-tight tabular-nums"><AnimatedNumber value={stats.total} /></p>
 <p className="text-[11px] text-muted-foreground/70 mt-1.5">אופטימיזציות</p>
 </CardContent>
 </Card>
 </TiltCard>
 <TiltCard>
 <Card className="relative overflow-hidden group/stat">
 <div className={`absolute inset-0 transition-opacity duration-300 ${stats.running > 0 ? "bg-gradient-to-br from-amber-500/[0.08] via-transparent to-stone-500/[0.04] opacity-100": "opacity-0"}`} />
 <CardContent className="p-4 sm:p-5 relative">
 <div className="flex items-center justify-between mb-3">
 <p className="text-sm font-medium text-muted-foreground">פעילות</p>
 <div className={`size-10 rounded-xl flex items-center justify-center ring-1 ${stats.running > 0 ? "bg-gradient-to-br from-amber-500/15 to-stone-500/10 ring-amber-500/15" : "bg-muted ring-transparent"}`}>
 <Activity className={`size-[18px] ${stats.running > 0 ? "text-amber-600 animate-pulse": "text-muted-foreground"}`} />
 </div>
 </div>
 <p className={`text-3xl font-bold tracking-tight tabular-nums ${stats.running > 0 ? "text-amber-600" : "text-muted-foreground"}`}><AnimatedNumber value={stats.running} /></p>
 <p className="text-[11px] text-muted-foreground/70 mt-1.5">כרגע רצות</p>
 </CardContent>
 </Card>
 </TiltCard>
 <TiltCard>
 <Card className="relative overflow-hidden group/stat">
 <div className={`absolute inset-0 transition-opacity duration-300 ${stats.success > 0 ? "bg-gradient-to-br from-stone-500/[0.07] via-transparent to-stone-400/[0.04] opacity-100": "opacity-0"}`} />
 <CardContent className="p-4 sm:p-5 relative">
 <div className="flex items-center justify-between mb-3">
 <p className="text-sm font-medium text-muted-foreground">הצליחו</p>
 <div className={`size-10 rounded-xl flex items-center justify-center ring-1 ${stats.success > 0 ? "bg-gradient-to-br from-stone-500/15 to-stone-400/10 ring-stone-500/10" : "bg-muted ring-transparent"}`}>
 <CheckCircle2 className={`size-[18px] ${stats.success > 0 ? "text-stone-600" : "text-muted-foreground"}`} />
 </div>
 </div>
 <p className={`text-3xl font-bold tracking-tight tabular-nums ${stats.success > 0 ? "text-stone-600" : "text-muted-foreground"}`}><AnimatedNumber value={stats.success} /></p>
 {stats.total > 0 && (
 <div className="mt-2.5 h-1.5 rounded-full bg-muted/80 overflow-hidden">
 <div className="h-full rounded-full bg-gradient-to-l from-stone-500 to-stone-500 transition-all duration-500" style={{ width: `${(stats.success / stats.total) * 100}%` }} />
 </div>
 )}
 </CardContent>
 </Card>
 </TiltCard>
 <TiltCard>
 <Card className="relative overflow-hidden group/stat">
 <div className={`absolute inset-0 transition-opacity duration-300 ${stats.failed > 0 ? "bg-gradient-to-br from-stone-500/[0.07] via-transparent to-stone-600/[0.04] opacity-100": "opacity-0"}`} />
 <CardContent className="p-4 sm:p-5 relative">
 <div className="flex items-center justify-between mb-3">
 <p className="text-sm font-medium text-muted-foreground">נכשלו</p>
 <div className={`size-10 rounded-xl flex items-center justify-center ring-1 ${stats.failed > 0 ? "bg-gradient-to-br from-stone-500/15 to-stone-600/10 ring-stone-500/10" : "bg-muted ring-transparent"}`}>
 <XCircle className={`size-[18px] ${stats.failed > 0 ? "text-stone-600" : "text-muted-foreground"}`} />
 </div>
 </div>
 <p className={`text-3xl font-bold tracking-tight tabular-nums ${stats.failed > 0 ? "text-stone-600" : "text-muted-foreground"}`}><AnimatedNumber value={stats.failed} /></p>
 {stats.total > 0 && (
 <div className="mt-2.5 h-1.5 rounded-full bg-muted/80 overflow-hidden">
 <div className="h-full rounded-full bg-gradient-to-l from-stone-500 to-stone-600 transition-all duration-500" style={{ width: `${(stats.failed / stats.total) * 100}%` }} />
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
 {mounted && <Tabs defaultValue="jobs" dir="rtl" onValueChange={setActiveTab}>
 <TabsList className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1 border-none shadow-none h-auto">
 <div
 className="absolute top-1 bottom-1 w-[calc(50%-6px)] rounded-md bg-[#3D2E22] shadow-sm transition-[inset-inline-start] duration-200 ease-out"
 style={{ insetInlineStart: activeTab === "jobs" ? 4 : "calc(50% + 2px)" }}
 />
 <TabsTrigger value="jobs" className="relative z-10 rounded-md px-4 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5">
 <TableIcon className="size-3.5"/>
 אופטימיזציות
 </TabsTrigger>
 <TabsTrigger value="analytics" className="relative z-10 rounded-md px-4 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5">
 <BarChart3 className="size-3.5"/>
 סטטיסטיקות
 </TabsTrigger>
 </TabsList>

 {/* ── Jobs tab ── */}
 <TabsContent value="jobs">
 <Card className="border-border/60">
 <CardContent className="pt-5">
 {/* Compare bar */}
 {compareMode && (
 <div className="flex items-center gap-3 mb-3 -mx-6 px-6 py-3 border-b border-primary/20 bg-gradient-to-l from-primary/5 to-primary/10 rounded-t-lg">
 <div className="size-8 rounded-full bg-primary/10 flex items-center justify-center">
 <ArrowLeftRight className="size-4 text-primary" />
 </div>
 <div>
 <span className="text-sm font-semibold">{compareSelection.size}/2 נבחרו להשוואה</span>
 <p className="text-[11px] text-muted-foreground">סמן 2 אופטימיזציות להשוואה</p>
 </div>
 <div className="flex items-center gap-2 ms-auto">
 <Button
 size="sm"
 disabled={compareSelection.size !== 2}
 onClick={() => router.push(`/compare?jobs=${[...compareSelection].join(",")}`)}
 className="gap-1.5 transition-all hover:scale-[1.02]"
 >
 <ArrowLeftRight className="size-3.5" />
 השווה
 </Button>
 <Button variant="ghost" size="sm" onClick={() => { setCompareMode(false); setCompareSelection(new Set()); }} className="text-xs text-muted-foreground">
 ביטול
 </Button>
 </div>
 </div>
 )}

 {/* Toolbar: compare button + filter count */}
 <div className="flex items-center gap-2 mb-3">
 {!compareMode && filteredItems.length >= 2 && (
 <TooltipProvider>
 <UiTooltip>
 <TooltipTrigger asChild>
 <Button variant="ghost" size="icon" className="size-8" onClick={() => setCompareMode(true)} aria-label="השוואה">
 <ArrowLeftRight className="size-3.5" />
 </Button>
 </TooltipTrigger>
 <TooltipContent side="bottom">השוואה</TooltipContent>
 </UiTooltip>
 </TooltipProvider>
 )}
 {activeCount > 0 && (
 <>
 <Badge variant="secondary" className="text-xs">{activeCount} סינונים פעילים</Badge>
 <button type="button" onClick={clearAll} className="text-xs text-muted-foreground hover:text-foreground cursor-pointer">נקה הכל</button>
 </>
 )}
 {filteredItems.length > 0 && (
 <span className="text-[11px] text-muted-foreground tabular-nums ms-auto">{filteredItems.length} תוצאות</span>
 )}
 </div>

 {error && (
 <div className="rounded-lg border border-[var(--danger-border)] bg-[var(--danger-dim)] py-3 px-4 text-sm text-[var(--danger)] mb-4">{error}</div>
 )}


 {!loading && data && filteredItems.length === 0 && (
 <div className="flex flex-col items-center gap-3 py-16 text-center">
 <p className="text-base font-medium">לא נמצאו אופטימיזציות</p>
 <p className="text-sm text-muted-foreground max-w-xs">צור אופטימיזציה חדשה כדי להתחיל</p>
 <Button asChild size="pill" className="mt-2">
 <Link href="/submit">
 <Plus className="size-4"/>
 אופטימיזציה חדשה
 </Link>
 </Button>
 </div>
 )}

 {pagedItems.length > 0 && (
 <div className="overflow-x-auto -mx-6" style={{ maskImage: "linear-gradient(to right, transparent, black 16px, black calc(100% - 16px), transparent)", WebkitMaskImage: "linear-gradient(to right, transparent, black 16px, black calc(100% - 16px), transparent)"}}>
 <Table>
 <thead className="bg-muted/30 [&_tr]:border-b [&_tr]:border-border/50">
 <tr>
 {compareMode && <th className="w-8 px-2"><span className="sr-only">השוואה</span></th>}
 <ColumnHeader label="מזהה"sortKey="job_id"currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} filterCol="job_id"filterOptions={filterOptions.job_id} filters={filters} onFilter={setColumnFilter} openFilter={openFilter} setOpenFilter={setOpenFilter} />
 <ColumnHeader label="סוג"sortKey="job_type"currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} filterCol="job_type"filterOptions={filterOptions.job_type} filters={filters} onFilter={setColumnFilter} openFilter={openFilter} setOpenFilter={setOpenFilter} />
 <ColumnHeader label="סטטוס"sortKey="status"currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} filterCol="status"filterOptions={filterOptions.status} filters={filters} onFilter={setColumnFilter} openFilter={openFilter} setOpenFilter={setOpenFilter} />
 <ColumnHeader label="מודול"sortKey="module_name"currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} filterCol="module_name"filterOptions={filterOptions.module_name} filters={filters} onFilter={setColumnFilter} openFilter={openFilter} setOpenFilter={setOpenFilter} />
 <ColumnHeader label="אופטימייזר"sortKey="optimizer_name"currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} filterCol="optimizer_name"filterOptions={filterOptions.optimizer_name} filters={filters} onFilter={setColumnFilter} openFilter={openFilter} setOpenFilter={setOpenFilter} />
 <ColumnHeader label="שורות"sortKey="dataset_rows"currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} />
 <ColumnHeader label="נוצר"sortKey="created_at"currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} />
 <ColumnHeader label="זמן"sortKey="elapsed_seconds"currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} />
 <ColumnHeader label="ציון"sortKey="optimized_test_metric"currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} />
 {isAdmin && <th className="w-10"/>}
 </tr>
 </thead>
 <TableBody className="transition-opacity duration-200">
 {pagedItems.map((job, idx) => (
 <TableRow
 key={job.job_id}
 className="group hover:bg-accent/40 cursor-pointer transition-all duration-150 border-border/40"
 onClick={() => router.push(`/jobs/${job.job_id}`)}
 onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); router.push(`/jobs/${job.job_id}`); } }}
 tabIndex={0}
 role="link"
 style={{ animation: `fadeSlideIn 0.25s ease-out ${idx * 0.03}s both` }}
 >
 {compareMode && (
 <TableCell className="px-2" onClick={(e) => e.stopPropagation()}>
 <label className="flex items-center justify-center size-8 cursor-pointer" title="בחר להשוואה">
 <input
 type="checkbox"
 checked={compareSelection.has(job.job_id)}
 disabled={!compareSelection.has(job.job_id) && compareSelection.size >= 2}
 onClick={(e) => toggleCompare(job.job_id, e)}
 onChange={() => {}}
 className="size-4 cursor-pointer accent-primary"
 />
 </label>
 </TableCell>
 )}
 <TableCell>
 <div className="flex items-center gap-1.5">
 {ACTIVE_STATUSES.has(job.status) && (
 <span className="relative flex size-2 shrink-0">
 <span className=" animate-ping absolute inline-flex h-full w-full rounded-full bg-primary/60"/>
 <span className="relative inline-flex rounded-full size-2 bg-primary"/>
 </span>
 )}
 <span className="font-mono text-xs text-primary whitespace-nowrap">
 {formatId(job.job_id)}
 </span>
 </div>
 </TableCell>
 <TableCell>{typeBadge(job.job_type)}</TableCell>
 <TableCell>{statusBadge(job.status)}</TableCell>
 <TableCell className="text-sm">{job.module_name ??"-"}</TableCell>
 <TableCell className="text-sm">{job.optimizer_name ??"-"}</TableCell>
 <TableCell className="text-sm tabular-nums">{job.dataset_rows ??"-"}</TableCell>
 <TableCell className="text-xs text-muted-foreground whitespace-nowrap"title={formatDate(job.created_at)}>
 {formatRelativeTime(job.created_at)}
 </TableCell>
 <TableCell className="text-xs tabular-nums whitespace-nowrap">
 {formatElapsed(job.elapsed_seconds)}
 </TableCell>
 <TableCell>{formatScore(job)}</TableCell>
 {isAdmin && (
 <TableCell>
 <TooltipProvider>
 <UiTooltip>
 <TooltipTrigger asChild>
 <button
 type="button" onClick={(e) => { e.stopPropagation(); setDeleteTarget({ id: job.job_id, status: job.status }); }}
 className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-destructive/10 hover:text-destructive transition-all cursor-pointer"
 aria-label="מחק אופטימיזציה">
 <Trash2 className="size-3.5"/>
 </button>
 </TooltipTrigger>
 <TooltipContent side="bottom">מחיקה</TooltipContent>
 </UiTooltip>
 </TooltipProvider>
 </TableCell>
 )}
 </TableRow>
 ))}
 </TableBody>
 </Table>
 </div>
 )}

 {data && totalPages > 1 && (
 <div className="flex items-center justify-center gap-3 pt-5 border-t border-border/50 mt-4">
 <Button variant="outline"size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} className="gap-1">
 <ChevronRight className="size-3.5"/>
 הקודם
 </Button>
 <span className="text-sm text-muted-foreground tabular-nums px-3 py-1 rounded-md bg-muted/50">{currentPage} / {totalPages}</span>
 <Button variant="outline"size="sm" disabled={offset + PAGE_SIZE >= (data?.total ?? 0)} onClick={() => setOffset(offset + PAGE_SIZE)} className="gap-1">
 הבא
 <ChevronLeft className="size-3.5"/>
 </Button>
 </div>
 )}
 </CardContent>
 </Card>
 </TabsContent>

 {/* ── Analytics tab ── */}
 <TabsContent value="analytics">
 {data && data.items.length > 0 ? (
 <div className="space-y-6">
 {/* ── Filter bar (stable, doesn't re-animate) ── */}
 <div className="grid grid-cols-3 gap-3">
 <Select value={analyticsOptimizer} onValueChange={setAnalyticsOptimizer}>
 <SelectTrigger className="w-full text-xs h-8">
 <SelectValue />
 </SelectTrigger>
 <SelectContent>
 <SelectItem value="all">כל האופטימייזרים</SelectItem>
 {analyticsOptions.optimizers.map(o => <SelectItem key={o} value={o}>{o}</SelectItem>)}
 </SelectContent>
 </Select>
 <Select value={analyticsModel} onValueChange={setAnalyticsModel}>
 <SelectTrigger className="w-full text-xs h-8">
 <SelectValue />
 </SelectTrigger>
 <SelectContent>
 <SelectItem value="all">כל המודלים</SelectItem>
 {analyticsOptions.models.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}
 </SelectContent>
 </Select>
 <Select value={analyticsStatus} onValueChange={setAnalyticsStatus}>
 <SelectTrigger className="w-full text-xs h-8">
 <SelectValue />
 </SelectTrigger>
 <SelectContent>
 <SelectItem value="all">כל הסטטוסים</SelectItem>
 <SelectItem value="success">הצליח</SelectItem>
 <SelectItem value="failed">נכשל</SelectItem>
 <SelectItem value="running">רץ</SelectItem>
 <SelectItem value="pending">ממתין</SelectItem>
 <SelectItem value="cancelled">בוטל</SelectItem>
 </SelectContent>
 </Select>
 </div>
 {/* ── Charts — cross-fade on filter change, numbers animate smoothly ── */}
 <AnimatePresence mode="wait">
 <motion.div
 key={`${analyticsOptimizer}-${analyticsModel}-${analyticsStatus}`}
 initial={{ opacity: 0, y: 8 }}
 animate={{ opacity: 1, y: 0 }}
 exit={{ opacity: 0, y: -4 }}
 transition={{ duration: 0.3, ease: [0.2, 0.8, 0.2, 1] }}
 >
 <StaggerContainer className="space-y-6" staggerDelay={0.06}>
 {/* ── KPI summary row ── */}
 {chartData.kpis && (
 <StaggerItem><div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
 <TiltCard>
 <Card className="relative overflow-hidden group/kpi">
 <div className="absolute inset-0 bg-gradient-to-br from-stone-500/[0.06] via-transparent to-stone-400/[0.04] opacity-0 group-hover/kpi:opacity-100 transition-opacity duration-300"/>
 <CardContent className="p-4 sm:p-5 relative">
 <div className="flex items-center justify-between mb-3">
 <p className="text-sm font-medium text-muted-foreground">אחוז הצלחה</p>
 <div className=" size-10 rounded-xl bg-gradient-to-br from-stone-500/15 to-stone-400/10 flex items-center justify-center ring-1 ring-stone-500/10">
 <CheckCircle2 className="size-[18px] text-stone-600" />
 </div>
 </div>
 <p className="text-3xl font-bold tracking-tight tabular-nums">
 <AnimatedNumber value={Math.round(chartData.kpis.successRate)} suffix="%" />
 </p>
 <p className="text-[11px] text-muted-foreground/70 mt-1.5"><AnimatedNumber value={chartData.kpis.successCount} /> מתוך <AnimatedNumber value={chartData.kpis.terminalCount} /> שהושלמו</p>
 </CardContent>
 </Card>
 </TiltCard>
 <TiltCard>
 <Card className="relative overflow-hidden group/kpi">
 <div className={`absolute inset-0 transition-opacity duration-300 ${chartData.kpis.avgImprovement > 0 ? "bg-gradient-to-br from-stone-500/[0.06] via-transparent to-amber-600/[0.04]" : chartData.kpis.avgImprovement < 0 ? "bg-gradient-to-br from-stone-500/[0.06] via-transparent to-stone-600/[0.04]" : ""} opacity-0 group-hover/kpi:opacity-100`} />
 <CardContent className="p-4 sm:p-5 relative">
 <div className="flex items-center justify-between mb-3">
 <p className="text-sm font-medium text-muted-foreground">שיפור ממוצע</p>
 <div className={`size-10 rounded-xl flex items-center justify-center ring-1 ${chartData.kpis.avgImprovement > 0 ? "bg-gradient-to-br from-stone-500/15 to-amber-600/10 ring-stone-500/10" : chartData.kpis.avgImprovement < 0 ? "bg-gradient-to-br from-stone-500/15 to-stone-600/10 ring-stone-500/10" : "bg-muted ring-transparent"}`}>
 <TrendingUp className={`size-[18px] ${chartData.kpis.avgImprovement > 0 ? "text-stone-600" : chartData.kpis.avgImprovement < 0 ? "text-stone-600" : "text-muted-foreground"}`} />
 </div>
 </div>
 <p className={`text-3xl font-bold tracking-tight tabular-nums ${chartData.kpis.avgImprovement > 0 ? "text-stone-600" : chartData.kpis.avgImprovement < 0 ? "text-stone-600" : ""}`}>
 <AnimatedNumber value={parseFloat(chartData.kpis.avgImprovement.toFixed(1))} decimals={1} prefix={chartData.kpis.avgImprovement >= 0 ? "+" : ""} suffix="%" />
 </p>
 <p className="text-[11px] text-muted-foreground/70 mt-1.5">שיפור ביצועים</p>
 </CardContent>
 </Card>
 </TiltCard>
 <TiltCard>
 <Card className="relative overflow-hidden group/kpi">
 <div className="absolute inset-0 bg-gradient-to-br from-stone-500/[0.06] via-transparent to-stone-600/[0.04] opacity-0 group-hover/kpi:opacity-100 transition-opacity duration-300"/>
 <CardContent className="p-4 sm:p-5 relative">
 <div className="flex items-center justify-between mb-3">
 <p className="text-sm font-medium text-muted-foreground">זמן ריצה ממוצע</p>
 <div className=" size-10 rounded-xl bg-gradient-to-br from-stone-500/15 to-stone-600/10 flex items-center justify-center ring-1 ring-stone-500/10">
 <Clock className="size-[18px] text-stone-600" />
 </div>
 </div>
 <p className="text-3xl font-bold tracking-tight tabular-nums" dir="ltr">
 {formatElapsed(chartData.kpis.avgRuntime)}
 </p>
 <p className="text-[11px] text-muted-foreground/70 mt-1.5">לכל אופטימיזציה</p>
 </CardContent>
 </Card>
 </TiltCard>
 <TiltCard>
 <Card className="relative overflow-hidden group/kpi">
 <div className="absolute inset-0 bg-gradient-to-br from-stone-500/[0.06] via-transparent to-amber-800/[0.04] opacity-0 group-hover/kpi:opacity-100 transition-opacity duration-300"/>
 <CardContent className="p-4 sm:p-5 relative">
 <div className="flex items-center justify-between mb-3">
 <p className="text-sm font-medium text-muted-foreground">נתונים שנותחו</p>
 <div className=" size-10 rounded-xl bg-gradient-to-br from-stone-500/15 to-amber-800/10 flex items-center justify-center ring-1 ring-stone-500/10">
 <Database className="size-[18px] text-stone-600" />
 </div>
 </div>
 <p className="text-3xl font-bold tracking-tight tabular-nums">
 <AnimatedNumber value={chartData.kpis.totalRows} />
 </p>
 <p className="text-[11px] text-muted-foreground/70 mt-1.5">סה״כ נתונים</p>
 </CardContent>
 </Card>
 </TiltCard>
 </div>
 </StaggerItem>
 )}

 {/* ── Primary row: scores chart (wider) + status breakdown ── */}
 <StaggerItem><div className="grid gap-5 md:grid-cols-7 transition-opacity duration-300"
 >
 {/* Scores comparison — primary chart */}
 <Card className="md:col-span-4 border-border/60">
 <CardHeader className="pb-2">
 <CardTitle className="text-base font-semibold">ציונים לפי אופטימיזציה</CardTitle>
 </CardHeader>
 <CardContent className="pt-0">
 {chartData.improvement.length > 0 ? (
 <>
 <div className="h-[300px]">
 <ResponsiveContainer width="100%" height="100%">
 <BarChart data={chartData.improvement} layout="vertical" margin={{ left: 10, right: 20, top: 20, bottom: 10 }}>
 <CartesianGrid horizontal={false} strokeDasharray="3 3" className="stroke-muted"/>
 <XAxis type="number" domain={[0, 105]} tickLine={false} axisLine={false} tick={{ fontSize: 11 }} className="fill-muted-foreground" ticks={[0, 25, 50, 75, 100]} label={{ value: "ציון (%)", position: "insideBottom", offset: -5, fontSize: 11 }} />
 <YAxis type="category" dataKey="name" hide label={{ value: "אופטימיזציה", angle: -90, position: "insideLeft", offset: 10, fontSize: 11 }} />
 <Tooltip content={<ChartTooltip />} />
 <Bar dataKey="ציון_התחלתי" name="ציון התחלתי"fill="var(--color-chart-4)"radius={[0, 4, 4, 0]} barSize={16} animationDuration={600} />
 <Bar dataKey="ציון_משופר" name="ציון משופר"fill="var(--color-chart-2)"radius={[0, 4, 4, 0]} barSize={16} animationDuration={600} />
 </BarChart>
 </ResponsiveContainer>
 </div>
 <div className="flex justify-center gap-4 mt-2">
 <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
 <span className="size-2.5 rounded-full" style={{ backgroundColor: "var(--color-chart-4)"}} />
 ציון התחלתי
 </div>
 <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
 <span className="size-2.5 rounded-full" style={{ backgroundColor: "var(--color-chart-2)"}} />
 ציון משופר
 </div>
 </div>
 </>
 ) : (
 <div className="flex h-[300px] items-center justify-center">
 <p className="text-sm text-muted-foreground">אין עדיין אופטימיזציות שהושלמו</p>
 </div>
 )}
 </CardContent>
 </Card>

 {/* Status + optimizer breakdown — sidebar */}
 <Card className="md:col-span-3 border-border/60">
 <CardHeader className="pb-2">
 <CardTitle className="text-base font-semibold">סטטוסים ואופטימייזרים</CardTitle>
 </CardHeader>
 <CardContent className="pt-0 space-y-6">
 {/* Status — as stat bars instead of pie when few categories */}
 <div className="space-y-3">
 <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest">סטטוסים</p>
 {chartData.status.map((s, i) => {
 const total = chartData.status.reduce((a, b) => a + b.value, 0);
 return (
 <div key={i} className="space-y-1.5">
 <div className="flex items-center justify-between text-sm">
 <span className="flex items-center gap-2">
 <span className=" size-2.5 rounded-full shrink-0 ring-1 ring-black/5" style={{ backgroundColor: s.fill }} />
 <span className="text-[13px]">{s.name}</span>
 </span>
 <span className="tabular-nums font-semibold text-[13px]">{s.value}</span>
 </div>
 <div className="h-2 rounded-full bg-muted/60 overflow-hidden">
 <div className="h-full rounded-full transition-all duration-500" style={{ width: `${(s.value / total) * 100}%`, backgroundColor: s.fill }} />
 </div>
 </div>
 );
 })}
 </div>

 <div className="border-t border-border"/>

 {/* Optimizers — as stat bars */}
 <div className="space-y-3">
 <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest">אופטימייזרים</p>
 {chartData.optimizer.map((o, i) => {
 const total = chartData.optimizer.reduce((a, b) => a + b.value, 0);
 return (
 <div key={i} className="space-y-1.5">
 <div className="flex items-center justify-between text-sm">
 <span className="flex items-center gap-2">
 <span className="size-2.5 rounded-full shrink-0 ring-1 ring-black/5" style={{ backgroundColor: `var(--color-chart-${(i % 5) + 1})` }} />
 <span className="text-[13px]">{o.name}</span>
 </span>
 <span className="tabular-nums font-semibold text-[13px]">{o.value}</span>
 </div>
 <div className="h-2 rounded-full bg-muted/60 overflow-hidden">
 <div className="h-full rounded-full transition-all duration-500" style={{ width: `${(o.value / total) * 100}%`, backgroundColor: `var(--color-chart-${(i % 5) + 1})` }} />
 </div>
 </div>
 );
 })}
 </div>

 {/* Job type inline */}
 {chartData.jobTypeData.length > 1 && (
 <>
 <div className="border-t border-border"/>
 <div className="space-y-3">
 <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">סוג אופטימיזציה</p>
 {chartData.jobTypeData.map((d, i) => {
 const total = chartData.jobTypeData.reduce((a, b) => a + b.value, 0);
 return (
 <div key={i} className="space-y-1">
 <div className="flex items-center justify-between text-sm">
 <span>{d.name}</span>
 <span className="tabular-nums font-medium">{d.value}</span>
 </div>
 <div className="h-2 rounded-full bg-muted overflow-hidden">
 <div className="h-full rounded-full bg-primary/70 transition-all" style={{ width: `${(d.value / total) * 100}%` }} />
 </div>
 </div>
 );
 })}
 </div>
 </>
 )}
 </CardContent>
 </Card>
 </div>
 </StaggerItem>

 {/* ── Secondary row: optimizer comparisons + model usage ── */}
 <StaggerItem><div className="grid gap-5 md:grid-cols-7 transition-opacity duration-300">
 {/* Avg improvement by optimizer */}
 {chartData.avgByOptimizer.length > 0 && (
 <Card className="md:col-span-4 border-border/60">
 <CardHeader className="pb-2">
 <CardTitle className="text-base font-semibold">ביצועים לפי אופטימייזר</CardTitle>
 </CardHeader>
 <CardContent className="pt-0">
 <div className="h-[280px]">
 <ResponsiveContainer width="100%" height="100%">
 <BarChart data={chartData.avgByOptimizer} margin={{ left: 10, right: 20, top: 20, bottom: 10 }}>
 <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-muted"/>
 <XAxis dataKey="name" tickLine={false} axisLine={false} tick={{ fontSize: 12 }} className="fill-muted-foreground" dy={10} label={{ value: "אופטימייזר", position: "insideBottom", offset: -5, fontSize: 11 }} />
 <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 11 }} className="fill-muted-foreground"unit="%"dx={-5} label={{ value: "שיפור ממוצע (%)", angle: -90, position: "insideLeft", offset: 15, fontSize: 11 }} />
 <Tooltip content={<ChartTooltip />} />
 <Bar dataKey="שיפור_ממוצע" name="שיפור ממוצע (%)"fill="var(--color-chart-2)"radius={[4, 4, 0, 0]} barSize={36} animationDuration={600} />
 </BarChart>
 </ResponsiveContainer>
 </div>
 <div className="flex justify-center gap-6 mt-1">
 {chartData.avgByOptimizer.map((o, i) => (
 <span key={i} className="text-xs text-muted-foreground">{o.name}: <span className="font-medium text-foreground">{o.שיפור_ממוצע}%</span> <span className="text-muted-foreground/60">(n={o.count})</span></span>
 ))}
 </div>
 </CardContent>
 </Card>
 )}

 {/* Model usage */}
 <Card className={`border-border/60 ${chartData.avgByOptimizer.length > 0 ? "md:col-span-3": "md:col-span-7"}`}>
 <CardHeader className="pb-2">
 <CardTitle className="text-base font-semibold">מודלים פופולריים</CardTitle>
 </CardHeader>
 <CardContent className="pt-0">
 {chartData.modelUsage.length > 0 ? (
 <div className="space-y-3 pt-2">
 {chartData.modelUsage.map((m, i) => {
 const maxCount = chartData.modelUsage[0]?.count ?? 1;
 return (
 <div key={i} className="space-y-1.5">
 <div className="flex items-center justify-between text-sm" dir="ltr">
 <span className="font-mono truncate max-w-[200px]" title={m.name}>{m.name}</span>
 <span className="tabular-nums font-medium">{m.count}</span>
 </div>
 <div className="h-2 rounded-full bg-muted overflow-hidden">
 <div className="h-full rounded-full bg-primary/60 transition-all" style={{ width: `${(m.count / maxCount) * 100}%` }} />
 </div>
 </div>
 );
 })}
 </div>
 ) : (
 <div className="flex h-[200px] items-center justify-center">
 <p className="text-sm text-muted-foreground">אין מידע על מודלים</p>
 </div>
 )}
 </CardContent>
 </Card>
 </div>
 </StaggerItem>

 {/* ── Leaderboard ── */}
 {chartData.topJobs.length > 0 && (
 <StaggerItem>
 <Card className="border-border/60">
 <CardHeader className="pb-2">
 <CardTitle className="text-base font-semibold flex items-center gap-2">
 <span className=" size-5 rounded-md bg-gradient-to-br from-stone-400/20 to-stone-500/10 flex items-center justify-center ring-1 ring-stone-400/10">
 <TrendingUp className="size-3 text-stone-600" />
 </span>
 השיפורים הגדולים ביותר
 </CardTitle>
 </CardHeader>
 <CardContent className="pt-0">
 <div className="rounded-lg border border-border/50 overflow-x-auto">
 <table className="w-full text-sm min-w-[500px]">
 <thead>
 <tr className=" border-b border-border/50 bg-muted/30">
 <th scope="col" className="px-4 py-3 text-start text-xs font-medium text-muted-foreground tracking-wide">#</th>
 <th scope="col" className="px-4 py-3 text-start text-xs font-medium text-muted-foreground tracking-wide">מזהה</th>
 <th scope="col" className="px-4 py-3 text-start text-xs font-medium text-muted-foreground tracking-wide">אופטימייזר</th>
 <th scope="col" className="px-4 py-3 text-start text-xs font-medium text-muted-foreground tracking-wide">ציון התחלתי</th>
 <th scope="col" className="px-4 py-3 text-start text-xs font-medium text-muted-foreground tracking-wide">ציון משופר</th>
 <th scope="col" className="px-4 py-3 text-start text-xs font-medium text-muted-foreground tracking-wide">שיפור</th>
 </tr>
 </thead>
 <tbody>
 {chartData.topJobs.map((j, i) => {
 const fmt = (n: number | undefined | null) => {
 if (n == null) return "\u2014";
 return ((n > 1 ? n : n * 100).toFixed(1)) +"%";
 };
 const imp = j.metric_improvement!;
 const impPct = (Math.abs(imp) > 1 ? imp : imp * 100);
 return (
 <tr key={j.job_id} className="border-b border-border/30 last:border-0 hover:bg-accent/40 cursor-pointer transition-colors duration-150" onClick={() => router.push(`/jobs/${j.job_id}`)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); router.push(`/jobs/${j.job_id}`); } }} tabIndex={0} role="button">
 <td className="px-4 py-3 text-sm">
 <span className={`inline-flex items-center justify-center size-6 rounded-full text-xs font-bold ${i === 0 ? "bg-gradient-to-br from-stone-400/20 to-stone-500/15 text-stone-600" : i === 1 ? "bg-muted/80 text-muted-foreground" : "text-muted-foreground"}`}>
 {i + 1}
 </span>
 </td>
 <td className="px-4 py-3 font-mono text-sm text-primary">{j.job_id}</td>
 <td className="px-4 py-3 text-sm">{j.optimizer_name}</td>
 <td className="px-4 py-3 font-mono text-sm tabular-nums text-muted-foreground">{fmt(j.baseline_test_metric)}</td>
 <td className="px-4 py-3 font-mono text-sm tabular-nums font-medium">{fmt(j.optimized_test_metric)}</td>
 <td className="px-4 py-3 font-mono text-sm tabular-nums font-bold text-stone-600">
 {impPct >= 0 ? "+" : ""}{impPct.toFixed(1)}%
 </td>
 </tr>
 );
 })}
 </tbody>
 </table>
 </div>
 </CardContent>
 </Card>
 </StaggerItem>
 )}
 </StaggerContainer>
 </motion.div>
 </AnimatePresence>
 </div>
 ) : (
 <Card>
 <CardContent className="py-16 text-center">
 <p className="text-muted-foreground">אין נתונים להצגה</p>
 </CardContent>
 </Card>
 )}
 </TabsContent>
 </Tabs>}
 </FadeIn>

 {/* Delete confirmation dialog */}
 <Dialog open={!!deleteTarget} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}>
 <DialogContent className="max-w-sm">
 <DialogHeader>
 <DialogTitle>מחיקת אופטימיזציה</DialogTitle>
 <DialogDescription>
 האם למחוק את האופטימיזציה{""}
 <span className="font-mono font-medium text-foreground break-all">{deleteTarget?.id}</span>
 ?
 </DialogDescription>
 </DialogHeader>
 <DialogFooter className="grid grid-cols-2 gap-2">
 <Button variant="outline" onClick={() => setDeleteTarget(null)} disabled={deleting} className="w-full justify-center">
 ביטול
 </Button>
 <Button variant="destructive" onClick={confirmDelete} disabled={deleting} className="w-full justify-center">
 {deleting ? <Loader2 className="size-4 animate-spin"/> : "מחיקה"}
 </Button>
 </DialogFooter>
 </DialogContent>
 </Dialog>
 </div>
 </Skeleton>
 );
}
