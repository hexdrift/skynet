"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
 Loader2,
 XCircle,
 Trash2,
 Clock,
 Code,
 Terminal,
 TrendingUp,
 ChevronLeft,
 Activity,
 CheckCircle2,
 Circle,
 Timer,
 Send,
 Zap,
 CopyPlus,
 MessageSquare,
 Database,
 Settings,
} from "lucide-react";
import { toast } from "react-toastify";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { useColumnFilters, useColumnResize } from "@/components/excel-filter";
import { FadeIn, TiltCard, StaggerContainer, StaggerItem } from "@/components/motion";
import dynamic from "next/dynamic";

const ScoreChart = dynamic(() => import("@/components/score-chart").then(m => m.ScoreChart), { ssr: false, loading: () => <div className="h-full" /> });
import { Tooltip as UiTooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { getJob, cancelJob, deleteJob, getOptimizationPayload, getServeInfo, getPairServeInfo, serveProgramStream, servePairProgramStream } from "@/lib/api";
import type { ServeInfoResponse } from "@/lib/types";
import { DEMO_OPTIMIZATION_ID, startDemoSimulation } from "@/lib/tutorial-demo-data";
import { Skeleton } from "boneyard-js/react";
import { optimizationDetailBones } from "@/components/optimization-detail-bones";
import { msg } from "@/features/shared/messages";
import { ACTIVE_STATUSES, TERMINAL_STATUSES } from "@/lib/constants";
import { registerTutorialHook } from "@/lib/tutorial-bridge";
import { HelpTip } from "@/components/help-tip";
import type {
 OptimizationStatusResponse,
 OptimizationLogEntry,
 OptimizationPayloadResponse,
} from "@/lib/types";

/* ── Helpers ── */
// Pure helpers, constants, and the pipeline-stage detector have moved
// to @/features/optimizations — see index.ts for the public surface.

import {
 PIPELINE_STAGES,
 type PipelineStage,
 formatPercent,
 formatImprovement,
 formatDuration,
 detectStage,
 extractScoresFromLogs,
 DataTab,
 LogsTab,
 ExportMenu,
 DeleteJobDialog,
 StatusBadge,
 InfoCard,
 CopyButton,
 ServeCodeSnippets,
 ServeChat,
 ConfigTab,
 CodeTab,
 StageInfoModal,
 GridOverview,
 PairDetailView,
} from "@/features/optimizations";






/* ── Page Component ── */

export default function JobDetailPage() {
 const { id } = useParams<{ id: string }>();
 const router = useRouter();
 const searchParams = useSearchParams();
 const initialTab = searchParams.get("tab") ?? "overview";
 const [detailTab, setDetailTab] = useState(initialTab);
 // Expose for tutorial via the typed bridge (see lib/tutorial-bridge.ts).
 useEffect(() => registerTutorialHook("setDetailTab", setDetailTab), []);

 const isDemoMode = id === DEMO_OPTIMIZATION_ID;

 const [job, setJob] = useState<OptimizationStatusResponse | null>(null);
 const [payload, setPayload] = useState<OptimizationPayloadResponse | null>(null);
 const [loading, setLoading] = useState(true);
 const [error, setError] = useState<string | null>(null);

 /* Demo simulation — runs instead of real API calls when id is tutorial-demo */
 useEffect(() => {
  if (!isDemoMode) return;
  return startDemoSimulation({ setJob: (fn) => setJob(fn), setLoading });
 }, [isDemoMode]);

 /* Serving playground */
 const [serveInfo, setServeInfo] = useState<ServeInfoResponse | null>(null);
 const [serveLoading, setServeLoading] = useState(false);
 const [runHistory, setRunHistory] = useState<Array<{ inputs: Record<string, string>; outputs: Record<string, unknown>; model: string; ts: number }>>([]);
 const [streamingRun, setStreamingRun] = useState<{ inputs: Record<string, string>; partial: Record<string, string> } | null>(null);
 const streamReqIdRef = useRef(0);
 const streamAbortRef = useRef<AbortController | null>(null);
 const chatScrollRef = useRef<HTMLDivElement>(null);
 const textareaRefs = useRef<Record<string, HTMLTextAreaElement | null>>({});
 const [serveError, setServeError] = useState<string | null>(null);
 const [stageModal, setStageModal] = useState<PipelineStage | null>(null);
 const [activeCodeTab, setActiveCodeTab] = useState<string>("signature");
 const recentLogsResize = useColumnResize();
 const recentLogsFilters = useColumnFilters();
 const gridResize = useColumnResize();
 const gridFilters = useColumnFilters();

 /* URL-based pair selection for grid search */
 const activePairIndex = searchParams.get("pair") != null ? parseInt(searchParams.get("pair")!, 10) : null;

 const activePair = useMemo(() => {
  if (activePairIndex === null || !job?.grid_result) return null;
  return job.grid_result.pair_results.find(p => p.pair_index === activePairIndex) ?? null;
 }, [activePairIndex, job?.grid_result]);

 const pairScorePoints = useMemo(() => {
  if (activePairIndex === null || !job?.logs) return [];
  // For single-pair grid search, all logs belong to that pair
  // For multi-pair, we heuristically filter
  const totalPairs = job.grid_result?.pair_results.length ?? 1;
  if (totalPairs === 1) return extractScoresFromLogs(job.logs);
  // Multi-pair: filter logs by pair mention
  const pairNum = activePairIndex + 1;
  const pairLogs = job.logs.filter(l =>
   l.message.includes(`Grid pair ${pairNum}/`) || l.message.includes(`Grid pair ${pairNum}:`)
  );
  return extractScoresFromLogs(pairLogs.length > 0 ? pairLogs : job.logs);
 }, [activePairIndex, job?.logs, job?.grid_result]);

 const pairFilteredLogs = useMemo(() => {
  if (activePairIndex === null || !job?.logs) return job?.logs ?? [];
  const pairNum = activePairIndex + 1;
  const filtered = job.logs.filter(l =>
   l.message.includes(`Grid pair ${pairNum}/`) || l.message.includes(`Grid pair ${pairNum}:`)
  );
  return filtered.length > 0 ? filtered : job.logs;
 }, [activePairIndex, job?.logs]);

 /* Fetch job data */
 const fetchJob = useCallback(async () => {
 try {
 const data = await getJob(id);
 setJob(data);
 setError(null);
 } catch (err) {
 setError("האופטימיזציה לא נמצאה");
 } finally {
 setLoading(false);
 }
 }, [id]);

 /* Fetch payload (once) */
 useEffect(() => {
 if (isDemoMode) return;
 getOptimizationPayload(id)
 .then(setPayload)
 .catch(() => {});
 }, [id, isDemoMode]);

 /* Initial fetch + SSE streaming for real-time updates */
 const jobRef = useRef(job);
 jobRef.current = job;

 useEffect(() => {
 if (isDemoMode) return;
 fetchJob();

 const API = process.env.NEXT_PUBLIC_API_URL ??"http://localhost:8000";
 let eventSource: EventSource | null = null;
 let fallbackInterval: ReturnType<typeof setInterval> | null = null;

 try {
 eventSource = new EventSource(`${API}/optimizations/${id}/stream`);

 const lastCountsRef = useRef({ logs: 0, progress: 0 });
 eventSource.onmessage = (event) => {
 try {
   const sseData = JSON.parse(event.data);
   const logCount = sseData.log_count ?? 0;
   const progressCount = sseData.progress_count ?? 0;
   const prev = lastCountsRef.current;
   // Full re-fetch when new logs/events arrive or status changes
   if (logCount > prev.logs || progressCount > prev.progress || sseData.status !== jobRef.current?.status) {
     lastCountsRef.current = { logs: logCount, progress: progressCount };
     fetchJob();
   } else {
     // Lightweight merge for metrics-only updates
     setJob((p) => p ? {
       ...p,
       status: sseData.status ?? p.status,
       message: sseData.message ?? p.message,
       latest_metrics: sseData.latest_metrics ?? p.latest_metrics,
     } : p);
   }
 } catch {
   fetchJob();
 }
 };

 eventSource.addEventListener("done", () => {
 eventSource?.close();
 fetchJob();
 });

 eventSource.onerror = () => {
 eventSource?.close();
 eventSource = null;
 // Fall back to polling
 fallbackInterval = setInterval(() => {
 if (jobRef.current && TERMINAL_STATUSES.has(jobRef.current.status)) {
 if (fallbackInterval) clearInterval(fallbackInterval);
 return;
 }
 fetchJob();
 }, 5000);
 };
 } catch {
 // SSE not supported — use polling
 fallbackInterval = setInterval(() => {
 if (jobRef.current && TERMINAL_STATUSES.has(jobRef.current.status)) {
 if (fallbackInterval) clearInterval(fallbackInterval);
 return;
 }
 fetchJob();
 }, 5000);
 }

 return () => {
 eventSource?.close();
 if (fallbackInterval) clearInterval(fallbackInterval);
 };
 }, [id, isDemoMode, fetchJob]);

 /* Listen for rename/update events from sidebar */
 useEffect(() => {
 if (isDemoMode) return;
 const onRenamed = (e: Event) => {
 const { optimizationId, name } = (e as CustomEvent).detail;
 if (optimizationId === id) setJob(prev => prev ? { ...prev, name } : prev);
 };
 const onUpdated = (e: Event) => {
 const { optimizationId } = (e as CustomEvent).detail;
 if (optimizationId === id) fetchJob();
 };
 window.addEventListener("optimization-renamed", onRenamed);
 window.addEventListener("optimization-updated", onUpdated);
 return () => {
 window.removeEventListener("optimization-renamed", onRenamed);
 window.removeEventListener("optimization-updated", onUpdated);
 };
 }, [id, fetchJob]);

 /* Actions */
 const handleCancel = async () => {
 if (isDemoMode) return;
 try {
 await cancelJob(id);
 toast.success(msg("optimization.cancel.sent"));
 fetchJob();
 } catch (err) {
 toast.error(err instanceof Error ? err.message : msg("optimization.cancel.failed"));
 }
 };


 /* Provide mock serve info for demo mode */
 useEffect(() => {
 if (isDemoMode && job?.status === "success") {
  setServeInfo({
   optimization_id: id,
   module_name: "Predict",
   optimizer_name: "MIPROv2",
   model_name: "gpt-4o-mini",
   input_fields: ["email_text"],
   output_fields: ["category"],
   instructions: "Classify an email into a category: spam, important, or promotional.",
   demo_count: 3,
  });
 }
 }, [isDemoMode, id, job?.status]);

 /* Fetch serve info once job succeeds */
 useEffect(() => {
 if (isDemoMode) return;
 if (job?.status !=="success") return;
 if (job.optimization_type === "grid_search") {
  if (activePairIndex != null) {
   getPairServeInfo(id, activePairIndex).then(setServeInfo).catch(() => setServeInfo(null));
  } else {
   // Grid overview — fetch serve info for best pair (used for playground on overview)
   getServeInfo(id).then(setServeInfo).catch(() => setServeInfo(null));
  }
 } else {
  getServeInfo(id).then(setServeInfo).catch(() => setServeInfo(null));
 }
 }, [id, job?.status, job?.optimization_type, activePairIndex]);

 /* Auto-scroll chat — keep up with new messages unless user scrolled up */
 useEffect(() => {
 if (chatScrollRef.current) {
 const el = chatScrollRef.current;
 if (el.scrollHeight - el.scrollTop - el.clientHeight < 300) {
 el.scrollTop = el.scrollHeight;
 }
 }
 }, [runHistory, streamingRun]);

 /* Abort any active stream when the page unmounts */
 useEffect(() => {
 return () => { streamAbortRef.current?.abort(); };
 }, []);

 /* Reset serve state when switching between pairs */
 useEffect(() => {
 streamAbortRef.current?.abort();
 setRunHistory([]);
 setStreamingRun(null);
 setServeLoading(false);
 setServeError(null);
 setServeInfo(null);
 }, [activePairIndex]);

 const readServeInputs = () => {
 const vals: Record<string, string> = {};
 for (const f of (serveInfo?.input_fields ?? [])) vals[f] = textareaRefs.current[f]?.value ?? "";
 return vals;
 };

 const handleServe = async (overrideInputs?: Record<string, string>) => {
 if (!serveInfo) return;
 const inputs = overrideInputs ?? readServeInputs();
 const missing = serveInfo.input_fields.filter((f) => !inputs[f]?.trim());
 if (missing.length > 0) {
 toast.error(<div>נא למלא את כל השדות:<br />{missing.join(", ")}</div>);
 return;
 }
 // Abort any in-flight stream, then start a new one tagged with a fresh id
 streamAbortRef.current?.abort();
 const reqId = ++streamReqIdRef.current;
 const controller = new AbortController();
 streamAbortRef.current = controller;
 setServeLoading(true);
 setServeError(null);
 setStreamingRun({ inputs: { ...inputs }, partial: {} });
 if (!overrideInputs) {
 Object.values(textareaRefs.current).forEach((el) => {
  if (el) { el.value = ""; el.style.height = "auto"; }
 });
 }
 const isStale = () => reqId !== streamReqIdRef.current;
 const streamFn = (job?.optimization_type === "grid_search" && activePairIndex != null)
  ? (i: Record<string, string>, h: Parameters<typeof serveProgramStream>[2]) => servePairProgramStream(id, activePairIndex, i, h)
  : (i: Record<string, string>, h: Parameters<typeof serveProgramStream>[2]) => serveProgramStream(id, i, h);
 await streamFn(inputs, {
 signal: controller.signal,
 onToken: (field, chunk) => {
  if (isStale()) return;
  setStreamingRun((prev) => prev
  ? { ...prev, partial: { ...prev.partial, [field]: (prev.partial[field] ?? "") + chunk } }
  : prev);
 },
 onFinal: (res) => {
  if (isStale()) return;
  setRunHistory((prev) => [{ inputs: { ...inputs }, outputs: res.outputs, model: res.model_used, ts: Date.now() }, ...prev]);
  setStreamingRun(null);
 },
 onError: (msg) => {
  if (isStale()) return;
  setServeError(msg);
  setStreamingRun(null);
 },
 });
 if (!isStale()) setServeLoading(false);
 };

 const handleClearHistory = () => {
 setRunHistory([]);
 setServeError(null);
 };

 /* Progress metrics */
 const metrics = job?.latest_metrics ?? {};

 /* Signature & metric code from payload */
 const signatureCode =
 (payload?.payload?.signature_code as string) ?? null;
 const metricCode =
 (payload?.payload?.metric_code as string) ?? null;

 /* Optimized prompt */
 /* Score progression from logs */
 const scorePoints = useMemo(() => {
 if (!job?.logs?.length) return [];
 return extractScoresFromLogs(job.logs);
 }, [job?.logs]);

 const optimizedPrompt =
 job?.result?.program_artifact?.optimized_prompt ??
 job?.grid_result?.best_pair?.program_artifact?.optimized_prompt ??
 null;

 // Live elapsed timer — ticks every second for active jobs (must be before early returns)
 const isActive = job ? ACTIVE_STATUSES.has(job.status) : false;
 const [liveElapsed, setLiveElapsed] = useState("00:00:00");
 useEffect(() => {
 const startStr = job?.started_at ?? job?.created_at;
 if (!startStr) return;
 const start = new Date(startStr).getTime();

 // For completed/cancelled/failed jobs: use server-provided elapsed or completed_at
 if (!isActive) {
 if (job?.elapsed_seconds != null && job.elapsed_seconds > 0) {
 const diff = Math.floor(job.elapsed_seconds);
 const h = String(Math.floor(diff / 3600)).padStart(2, "0");
 const m = String(Math.floor((diff % 3600) / 60)).padStart(2, "0");
 const s = String(diff % 60).padStart(2, "0");
 setLiveElapsed(`${h}:${m}:${s}`);
 } else if (job?.completed_at) {
 const end = new Date(job.completed_at).getTime();
 const diff = Math.max(0, Math.floor((end - start) / 1000));
 const h = String(Math.floor(diff / 3600)).padStart(2, "0");
 const m = String(Math.floor((diff % 3600) / 60)).padStart(2, "0");
 const s = String(diff % 60).padStart(2, "0");
 setLiveElapsed(`${h}:${m}:${s}`);
 }
 return;
 }

 // For active jobs: live tick from now
 const fmt = () => {
 const diff = Math.max(0, Math.floor((Date.now() - start) / 1000));
 const h = String(Math.floor(diff / 3600)).padStart(2, "0");
 const m = String(Math.floor((diff % 3600) / 60)).padStart(2, "0");
 const s = String(diff % 60).padStart(2, "0");
 setLiveElapsed(`${h}:${m}:${s}`);
 };
 fmt();
 const id = setInterval(fmt, 1000);
 return () => clearInterval(id);
 }, [job?.started_at ?? null, job?.created_at ?? null, job?.completed_at ?? null, job?.elapsed_seconds ?? null, isActive]);

 /* ── Render ── */

 if (loading) {
 return (
 <Skeleton name="optimization-detail" loading initialBones={optimizationDetailBones} color="var(--muted)" animate="shimmer">
 <div className="min-h-[60vh]" />
 </Skeleton>
 );
 }

 if (error || !job) {
 return (
 <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
 <XCircle className="size-12 text-destructive"/>
 <p className="text-lg text-muted-foreground">{error ??"האופטימיזציה לא נמצאה"}</p>
 </div>
 );
 }

 const isTerminal = TERMINAL_STATUSES.has(job.status);

 return (
 <div className="space-y-6 pb-12">
 {/* Breadcrumb */}
 <FadeIn>
 <div className="flex items-center gap-2 text-sm text-muted-foreground">
 <Link href="/" className="hover:text-foreground transition-colors">לוח בקרה</Link>
 <ChevronLeft className="h-3 w-3"/>
 <span className="text-foreground font-medium text-xs sm:text-sm break-all" dir="auto">{job.name || job.optimization_id.slice(0, 8)}</span>
 </div>
 </FadeIn>

 {/* ── 1. Header (hidden when viewing a grid pair) ── */}
 {!(job.optimization_type === "grid_search" && activePairIndex !== null) && (
 <FadeIn delay={0.1}>
 <div className=" rounded-xl border border-border/40 bg-gradient-to-br from-card to-card/80 p-5" data-tutorial="detail-header">
 <div className="flex flex-wrap items-start justify-between gap-4">
 <div className="space-y-2 min-w-0">
 <div className="flex items-center gap-3 flex-wrap">
 {job.name && (
 <h2 className="text-lg sm:text-xl font-bold tracking-tight" dir="auto">{job.name}</h2>
 )}
 <StatusBadge status={job.status} />
 </div>
 {job.description && (
 <p className="text-sm text-muted-foreground/70 leading-relaxed">{job.description}</p>
 )}
 <code
 className="text-xs font-mono text-muted-foreground/60 cursor-pointer hover:text-primary transition-colors break-all"
 title="לחץ להעתקה"
 aria-label="העתק מזהה אופטימיזציה"
 role="button"
 tabIndex={0}
 onClick={() => { navigator.clipboard.writeText(job.optimization_id); toast.success(msg("clipboard.copied_short"), { autoClose: 1000 });}}
 onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); navigator.clipboard.writeText(job.optimization_id); toast.success(msg("clipboard.copied_short"), { autoClose: 1000 });} }}
 >
 {job.optimization_id}
 </code>
 <div className="flex items-center gap-3 flex-wrap text-sm text-muted-foreground">
 <Badge variant="secondary" className="text-[11px]">{job.optimization_type === "grid_search"?"סריקה":"ריצה בודדת"}</Badge>
 <span className="flex items-center gap-1.5 tabular-nums" dir="ltr">
 <Clock className="size-3.5"/>
 {liveElapsed}
 </span>
 {isActive && job.estimated_remaining && (
 <span className="flex items-center gap-1.5">
 <Timer className="size-3.5"/>
 נותר: {job.estimated_remaining}
 </span>
 )}
 </div>
 </div>
 <div className="flex items-center gap-2">
 <TooltipProvider>
 <UiTooltip>
 <TooltipTrigger asChild>
 <Button variant="ghost" size="icon" className="size-8" onClick={() => router.push(`/submit?clone=${job.optimization_id}`)} aria-label="שכפול">
 <CopyPlus className="size-4"/>
 </Button>
 </TooltipTrigger>
 <TooltipContent side="bottom">שכפול</TooltipContent>
 </UiTooltip>
 </TooltipProvider>
 {isActive && (
 <TooltipProvider>
 <UiTooltip>
 <TooltipTrigger asChild>
 <Button variant="ghost" size="icon" className="size-8 text-destructive hover:bg-destructive/10 hover:text-destructive focus-visible:ring-0 focus-visible:border-0" onClick={handleCancel} aria-label="ביטול">
 <XCircle className="size-4"/>
 </Button>
 </TooltipTrigger>
 <TooltipContent side="bottom">ביטול</TooltipContent>
 </UiTooltip>
 </TooltipProvider>
 )}
 {isTerminal && <DeleteJobDialog optimizationId={job.optimization_id} onDeleted={() => router.push("/")} />}
 </div>
 </div>
 </div>
 </FadeIn>
 )}

 {/* ── Failure message ── */}
 {job.status === "failed" && (job.message || (metrics.error as string)) && (
 <FadeIn delay={0.15}>
 <div className="p-5 rounded-xl border border-red-300/60 bg-gradient-to-br from-red-50 to-red-100/40 shadow-[0_0_15px_rgba(239,68,68,0.06)]">
 <div className="flex items-start gap-3">
 <XCircle className="size-5 text-red-500 shrink-0 mt-0.5"/>
 <p className="text-sm font-semibold text-red-800">נכשלה</p>
 </div>
 <pre className="text-xs text-red-700 mt-3 whitespace-pre-wrap break-words font-mono leading-relaxed" dir="ltr">
{(job.message ?? "")?.split(/(https?:\/\/[^\s]+)/g).map((part, i) =>
 /^https?:\/\//.test(part) ? <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="underline hover:text-red-900 transition-colors">{part}</a> : part
 )}
 </pre>
 {typeof metrics.error === "string" && !job.message?.includes(metrics.error) && (
 <pre className="text-xs text-red-700 mt-2 whitespace-pre-wrap break-words font-mono leading-relaxed border-t border-red-200 pt-2" dir="ltr">
{String(metrics.error).split(/(https?:\/\/[^\s]+)/g).map((part: string, i: number) =>
 /^https?:\/\//.test(part) ? <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="underline hover:text-red-900 transition-colors">{part}</a> : part
 )}
 </pre>
 )}
 </div>
 </FadeIn>
 )}

 {/* Old live view removed — live content now in tabbed overview */}

 {/* ── Cancelled banner ── */}
 {job.status === "cancelled" && (
 <FadeIn>
 <div className="flex items-center gap-3 p-4 rounded-xl border border-stone-300 bg-stone-50 text-stone-700">
 <XCircle className="size-5 shrink-0" />
 <div>
 <p className="text-sm font-semibold">האופטימיזציה בוטלה</p>
 <p className="text-xs text-stone-500 mt-0.5">{job.message || "המשימה בוטלה על ידי המשתמש."}</p>
 </div>
 </div>
 </FadeIn>
 )}

 {/* ── Export Bar (hidden when viewing a grid pair — pair has its own) ── */}
 {isTerminal && job.status !== "cancelled" && !(job.optimization_type === "grid_search" && activePairIndex !== null) && (optimizedPrompt || (job.logs && job.logs.length > 0) || job.result?.program_artifact?.program_pickle_base64 || job.grid_result?.best_pair?.program_artifact?.program_pickle_base64) && (
 <FadeIn delay={0.25}>
 <div className="flex items-center gap-3 p-5 rounded-xl border border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10 shadow-[0_0_20px_rgba(var(--primary),0.06)]">
 <div className="flex-1">
 <p className="text-sm font-medium">ייצוא תוצאות</p>
 </div>
 <ExportMenu job={job} optimizedPrompt={optimizedPrompt} />
 </div>
 </FadeIn>
 )}

 {/* ── Per-pair full view (grid search with ?pair=N) ── */}
 {isTerminal && job.optimization_type === "grid_search" && activePairIndex !== null && activePair && job.grid_result && (
  <PairDetailView
   job={job}
   activePair={activePair}
   activePairIndex={activePairIndex}
   pairCount={job.grid_result.pair_results.length}
   pairFilteredLogs={pairFilteredLogs}
   pairScorePoints={pairScorePoints}
   initialTab={initialTab}
   serveInfo={serveInfo}
   runHistory={runHistory}
   setRunHistory={setRunHistory}
   streamingRun={streamingRun}
   serveLoading={serveLoading}
   serveError={serveError}
   setServeError={setServeError}
   textareaRefs={textareaRefs}
   chatScrollRef={chatScrollRef}
   handleServe={handleServe}
   onBack={() => router.push(`/optimizations/${id}`)}
   onPrev={() => router.push(`/optimizations/${id}?pair=${activePairIndex - 1}`)}
   onNext={() => router.push(`/optimizations/${id}?pair=${activePairIndex + 1}`)}
   onClearHistory={handleClearHistory}
  />
 )}

 {/* ── Tabbed sections (normal view / grid overview) ── */}
 {!(job.optimization_type === "grid_search" && activePairIndex !== null) && (() => {
 const tabCls = "relative px-4 py-2.5 rounded-none border-b-2 border-transparent data-[state=active]:border-transparent data-[state=active]:border-b-primary data-[state=active]:text-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none transition-all duration-200";
 return (
 <Tabs value={detailTab} onValueChange={setDetailTab} dir="rtl">
 <TabsList variant="line" className="border-b border-border/50 pb-0 gap-0" data-tutorial="detail-tabs">
 <TabsTrigger value="overview" className={tabCls}><TrendingUp className="size-3.5"/> סקירה{isActive && <span className="relative flex size-2 ms-1"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--warning)]/60"/><span className="relative inline-flex rounded-full size-2 bg-[var(--warning)]"/></span>}</TabsTrigger>
 {serveInfo && job.optimization_type !== "grid_search" && isTerminal && <TabsTrigger value="playground" className={tabCls} data-tutorial="playground-tab"><Send className="size-3.5"/> שימוש</TabsTrigger>}
 {job.optimization_type !== "grid_search" && isTerminal && <TabsTrigger value="data" className={tabCls} data-tutorial="data-tab-trigger"><Database className="size-3.5"/> נתונים</TabsTrigger>}
 <TabsTrigger value="code" className={tabCls}><Code className="size-3.5"/> קוד</TabsTrigger>
 <TabsTrigger value="logs" className={tabCls} data-tutorial="logs-tab-trigger"><Terminal className="size-3.5"/> לוגים{isActive && <span className="relative flex size-2 ms-1"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--warning)]/60"/><span className="relative inline-flex rounded-full size-2 bg-[var(--warning)]"/></span>}</TabsTrigger>
 <TabsTrigger value="config" className={tabCls} data-tutorial="config-tab-trigger"><Settings className="size-3.5"/> הגדרות</TabsTrigger>
 </TabsList>

 {/* ── Overview tab ── */}
 <TabsContent value="overview" className="space-y-6 mt-4" data-tutorial="overview-tab">
 <FadeIn>
 <p className="text-sm text-muted-foreground">
 {isActive ? "האופטימיזציה רצה כעת — ניתן לעקוב אחר ההתקדמות בזמן אמת." : job.status === "cancelled" ? "האופטימיזציה בוטלה — להלן מצב התהליך בעת הביטול." : job.status === "failed" ? "האופטימיזציה נכשלה." : "תוצאות האופטימיזציה, ציונים ומטריקות ביצוע."}
 </p>
 </FadeIn>

 {/* ── Live progress bar ── */}
 {isActive && (() => {
 const tqdmPercent = metrics.tqdm_percent as number | undefined;
 const tqdmDesc = metrics.tqdm_desc as string | undefined;
 const tqdmN = metrics.tqdm_n as number | undefined;
 const tqdmTotal = metrics.tqdm_total as number | undefined;
 return tqdmPercent != null ? (
 <FadeIn>
 <div className="space-y-1.5">
  <div className="flex items-center justify-between text-xs text-muted-foreground">
   <span>{tqdmDesc || "אופטימיזציה"}</span>
   <span className="font-mono tabular-nums">{tqdmN ?? 0}/{tqdmTotal ?? "?"} ({tqdmPercent.toFixed(0)}%)</span>
  </div>
  <div className="h-2 rounded-full bg-border/50 overflow-hidden">
   <div className="h-full bg-primary rounded-full transition-all duration-500" style={{ width: `${tqdmPercent}%` }} />
  </div>
 </div>
 </FadeIn>
 ) : null;
 })()}

 {/* ── Live metric cards ── */}
 {isActive && (() => {
 const tqdmN = metrics.tqdm_n as number | undefined;
 const tqdmTotal = metrics.tqdm_total as number | undefined;
 const tqdmElapsed = metrics.tqdm_elapsed as number | undefined;
 const tqdmRemaining = metrics.tqdm_remaining as number | undefined;
 const tqdmRate = metrics.tqdm_rate as number | undefined;
 const baselineEvent = job.progress_events?.find((e) => e.event === "baseline_evaluated");
 const baselineScore = baselineEvent?.metrics?.baseline_test_metric as number | undefined;
 const splitsEvent = job.progress_events?.find((e) => e.event === "dataset_splits_ready");
 const trainCount = (splitsEvent?.metrics?.train_examples ?? metrics.train_examples) as number | undefined;
 const valCount = (splitsEvent?.metrics?.val_examples ?? metrics.val_examples) as number | undefined;
 const testCount = (splitsEvent?.metrics?.test_examples ?? metrics.test_examples) as number | undefined;
 const hasAny = tqdmN != null || tqdmElapsed != null || baselineScore != null || trainCount != null;
 if (!hasAny) return null;
 return (
 <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(120px, 100%), 1fr))" }}>
  {tqdmN != null && tqdmTotal != null && (
   <InfoCard label="צעד" value={`${tqdmN}/${tqdmTotal}`} icon={<Activity className="size-3.5" />} />
  )}
  {tqdmElapsed != null && (
   <InfoCard label="זמן שעבר" value={formatDuration(tqdmElapsed)} icon={<Timer className="size-3.5" />} />
  )}
  {tqdmRemaining != null && (
   <InfoCard label="נותר" value={formatDuration(Number(tqdmRemaining))} icon={<Clock className="size-3.5" />} />
  )}
  {tqdmRate != null && (
   <InfoCard label="קצב" value={`${tqdmRate.toFixed(2)}/שנ׳`} icon={<Zap className="size-3.5" />} />
  )}
  {baselineScore != null && (
   <InfoCard label="ציון התחלתי" value={formatPercent(baselineScore)} icon={<TrendingUp className="size-3.5" />} />
  )}
  {trainCount != null && (
   <InfoCard label="נתונים" value={`${trainCount}/${valCount}/${testCount}`} icon={<Database className="size-3.5" />} />
  )}
 </div>
 );
 })()}

 {/* ── Completed pipeline timeline (single runs only) ── */}
 {job.optimization_type !== "grid_search" && (
 <FadeIn delay={0.05}>
 {(() => {
 const completedStageIdx = job.status === "success" ? PIPELINE_STAGES.length : detectStage(job) === "done" ? PIPELINE_STAGES.length : PIPELINE_STAGES.findIndex((s) => s.key === detectStage(job));
 const eventToStage: Record<string, PipelineStage> = {
 "validation_passed": "validating",
 "dataset_splits_ready": "splitting",
 "baseline_evaluated": "baseline",
 "grid_pair_started": "baseline",
 "optimizer_progress": "optimizing",
 "optimized_evaluated": "evaluating",
 "grid_pair_completed": "evaluating",
 };
 const stageTs: Partial<Record<PipelineStage, string>> = {};
 for (const ev of (job.progress_events ?? [])) {
 const sk = ev.event ? eventToStage[ev.event] : undefined;
 if (sk && ev.timestamp) {
 const d = new Date(ev.timestamp);
 stageTs[sk] = `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })}|${d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}`;
 }
 }
 if (job.started_at && !stageTs.validating) {
 const d = new Date(job.started_at);
 stageTs.validating = `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })}|${d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}`;
 }
 if (job.completed_at) {
 const d = new Date(job.completed_at);
 stageTs.evaluating = `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })}|${d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}`;
 }
 const isFailed = job.status === "failed" || job.status === "cancelled";
 return (
 <div className="relative flex items-start justify-between" dir="rtl" data-tutorial="pipeline-stages">
 {/* Track line */}
 <div className="absolute top-[14px] right-[14px] left-[14px] h-[2px] bg-border/50 rounded-full" />
 <div className={`absolute top-[14px] right-[14px] h-[2px] rounded-full transition-all duration-700 ease-out ${isFailed ? "bg-destructive/60" : "bg-[#3D2E22]"}`} style={{ width: `calc(${(Math.min(completedStageIdx, PIPELINE_STAGES.length - 1) / (PIPELINE_STAGES.length - 1)) * 100}% - 28px)` }} />

 {PIPELINE_STAGES.map((s, i) => {
 const isDone = i < completedStageIdx;
 const isCurrent = isActive && i === completedStageIdx;
 const isStopped = isFailed && i === completedStageIdx;
 const ts = stageTs[s.key];
 return (
 <div key={s.key} className="relative z-10 flex flex-col items-center gap-2 min-w-0 group/node cursor-pointer" onClick={() => setStageModal(s.key)}>
  <div className={`size-7 rounded-full flex items-center justify-center transition-all duration-300 group-hover/node:scale-125 group-hover/node:shadow-[0_0_0_6px_rgba(61,46,34,0.1)] ${
   isStopped
    ? "bg-destructive text-white shadow-[0_0_0_4px_rgba(176,64,48,0.15)]"
    : isCurrent
    ? "bg-[#3D2E22] text-white shadow-[0_0_0_4px_rgba(61,46,34,0.15)]"
    : isDone
    ? "bg-[#3D2E22] text-white"
    : "bg-[#E5DDD4] text-[#8C7A6B]"
  }`}>
   {isDone ? (
    <CheckCircle2 className="size-3.5"/>
   ) : isCurrent ? (
    <Loader2 className="size-3.5 animate-spin"/>
   ) : isStopped ? (
    <XCircle className="size-3.5"/>
   ) : (
    <Circle className="size-3"/>
   )}
  </div>
  <span className={`text-[11px] whitespace-nowrap transition-colors duration-200 group-hover/node:text-[#3D2E22] ${
   isCurrent ? "text-[#3D2E22] font-semibold" : isStopped ? "text-destructive font-semibold" : isDone ? "text-[#3D2E22]/80" : "text-muted-foreground/40"
  }`}>{s.label}</span>
  {ts && isDone && (() => {
   const [date, time] = ts.split("|");
   return (
    <div className="flex flex-col items-center -mt-0.5" dir="ltr">
     <span className="text-[10px] text-muted-foreground/50 tracking-wide uppercase">{date}</span>
     <span className="text-[11px] text-muted-foreground/70 font-mono tabular-nums">{time}</span>
    </div>
   );
  })()}
 </div>
 );
 })}
 </div>
 );
 })()}
 </FadeIn>
 )}

 {/* LM call metrics for single runs */}
 {job.status === "success" && job.optimization_type === "run" && job.result && (job.result.num_lm_calls || job.result.avg_response_time_ms) && (
 <FadeIn delay={0.1}>
 <div className="grid grid-cols-2 gap-2.5">
  {job.result.num_lm_calls != null && (
   <InfoCard label={<HelpTip text="מספר הפעמים שהמערכת פנתה למודל השפה במהלך האופטימיזציה">קריאות למודל שפה</HelpTip>} value={`${job.result.num_lm_calls} קריאות`} icon={<MessageSquare className="size-3.5" />} />
  )}
  {job.result.avg_response_time_ms != null && (
   <InfoCard label={<HelpTip text="משך זמן ממוצע לכל קריאה בודדת למודל השפה">זמן תגובה ממוצע לקריאה</HelpTip>} value={`${(job.result.avg_response_time_ms / 1000).toFixed(1)} שניות לקריאה`} icon={<Timer className="size-3.5" />} />
  )}
 </div>
 </FadeIn>
 )}

 {/* ── 3. Results ── */}
 {job.status ==="success"&& job.optimization_type ==="run"&& job.result && (
 <div data-tutorial="score-cards">
 <StaggerContainer className="grid grid-cols-1 sm:grid-cols-3 gap-4">
 <StaggerItem>
 <TiltCard className=" rounded-xl border border-border/50 bg-card p-6 text-center">
 <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide"><HelpTip text="ציון המדידה לפני אופטימיזציה — התוכנית רצה ללא הנחיות או דוגמאות">ציון התחלתי</HelpTip></p>
 <p className="text-3xl font-mono font-bold">
 {formatPercent(job.result.baseline_test_metric)}
 </p>
 </TiltCard>
 </StaggerItem>
 <StaggerItem>
 <TiltCard className="rounded-xl border border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10 p-6 text-center shadow-[0_0_20px_rgba(var(--primary),0.08)]">
 <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide"><HelpTip text="ציון המדידה אחרי אופטימיזציה — התוכנית רצה עם ההנחיות והדוגמאות שנבחרו">ציון משופר</HelpTip></p>
 <p className="text-3xl font-mono font-bold text-primary">
 {formatPercent(job.result.optimized_test_metric)}
 </p>
 </TiltCard>
 </StaggerItem>
 <StaggerItem>
 <TiltCard className={`rounded-xl border p-6 text-center ${(job.result.metric_improvement ?? 0) >= 0 ? "border-stone-400/50 bg-gradient-to-br from-stone-100/50 to-stone-200/30" : "border-red-300/50 bg-gradient-to-br from-red-50/50 to-red-100/30"}`}>
 <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide"><HelpTip text="ההפרש בין הציון המשופר לציון ההתחלתי — ככל שגבוה יותר, האופטימיזציה הועילה יותר">שיפור</HelpTip></p>
 <p className={`text-3xl font-mono font-bold ${(job.result.metric_improvement ?? 0) >= 0 ? "text-stone-600" : "text-red-600"}`}>
 {formatImprovement(job.result.metric_improvement)}
 </p>
 </TiltCard>
 </StaggerItem>
 </StaggerContainer>
 </div>
 )}

 {/* Score progression chart for single runs */}
 {job.optimization_type === "run" && scorePoints.length > 1 && (
 <FadeIn delay={0.1}>
 <Card className="relative overflow-hidden shadow-[0_1px_3px_rgba(28,22,18,0.04),inset_0_1px_0_rgba(255,255,255,0.5)]" data-tutorial="score-chart">
 <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-l from-transparent via-[#C8A882]/40 to-transparent" aria-hidden="true" />
 <CardHeader>
 <CardTitle className="text-base flex items-center gap-2">
 <TrendingUp className="size-4 text-[#7C6350]" aria-hidden="true" />
 <HelpTip text="שינוי הציון לאורך הניסיונות השונים של האופטימייזר"><span className="font-bold tracking-tight">מהלך הציונים</span></HelpTip>
 </CardTitle>
 </CardHeader>
 <CardContent>
 <div className="h-[220px]">
 <ScoreChart data={scorePoints} />
 </div>
 </CardContent>
 </Card>
 </FadeIn>
 )}

 {job.status === "success" && job.optimization_type === "grid_search" && job.grid_result && activePairIndex === null && (
  <GridOverview job={job} onPairSelect={(pi) => router.push(`/optimizations/${id}?pair=${pi}`)} />
 )}

 </TabsContent>

 {/* ── Playground tab ── */}
 {serveInfo && (
 <TabsContent value="playground" className="space-y-4 mt-4" data-tutorial="serve-playground">
 <FadeIn>
 <div className="flex items-center justify-between pb-3 border-b border-border/60">
 <p className="text-sm text-muted-foreground">הרצת התוכנית המאומנת בזמן אמת — הזן קלט וקבל תשובה.</p>
 {runHistory.length > 0 && (
 <TooltipProvider>
 <UiTooltip>
 <TooltipTrigger asChild>
  <Button variant="ghost" size="icon" className="size-8" onClick={handleClearHistory} aria-label="נקה היסטוריה">
  <Trash2 className="size-4" />
  </Button>
 </TooltipTrigger>
 <TooltipContent side="bottom">נקה היסטוריה</TooltipContent>
 </UiTooltip>
 </TooltipProvider>
 )}
 </div>
 </FadeIn>
 <ServeChat
  serveInfo={serveInfo}
  runHistory={runHistory}
  setRunHistory={setRunHistory}
  streamingRun={streamingRun}
  serveLoading={serveLoading}
  serveError={serveError}
  setServeError={setServeError}
  textareaRefs={textareaRefs}
  chatScrollRef={chatScrollRef}
  handleServe={handleServe}
  demos={job?.result?.program_artifact?.optimized_prompt?.demos
  ?? job?.grid_result?.best_pair?.program_artifact?.optimized_prompt?.demos
  ?? []}
 />

 {/* Endpoint + Code Snippets (merged) */}
 <Card>
 <CardHeader className="pb-2">
 <CardTitle className="text-sm"><HelpTip text="כתובת API וקוד לשילוב התוכנית המאומנת באפליקציה שלך">הרצה</HelpTip></CardTitle>
 </CardHeader>
 <CardContent className="space-y-4">
 <div className="space-y-1.5">
 <p className="text-[10px] text-muted-foreground uppercase tracking-wider"><HelpTip text="כתובת ה-API שאליה שולחים בקשות POST עם שדות הקלט כדי לקבל תשובה מהתוכנית המאומנת">כתובת שירות</HelpTip></p>
 <div className="rounded-lg bg-muted/40 p-2.5 pe-8 relative group" dir="ltr">
 <code className="text-xs font-mono break-all">POST {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/serve/{id}</code>
 <CopyButton text={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/serve/${id}`} className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100"/>
 </div>
 </div>

 <Separator />

 <div className="space-y-2">
 <p className="text-[10px] text-muted-foreground uppercase tracking-wider"><HelpTip text="דוגמאות קוד מוכנות להעתקה לשילוב התוכנית המאומנת באפליקציה שלך">קוד לשילוב</HelpTip></p>
 <ServeCodeSnippets serveInfo={serveInfo} optimizationId={id} />
 </div>
 </CardContent>
 </Card>
 </TabsContent>
 )}

 {/* ── Data tab ── */}
 <TabsContent value="data">
 <DataTab job={job} />
 </TabsContent>

 {/* ── Code tab ── */}
 <TabsContent value="code" className="space-y-6 mt-4">
  <CodeTab signatureCode={signatureCode} metricCode={metricCode} optimizedPrompt={optimizedPrompt} />
 </TabsContent>

 {/* ── Logs tab ── */}
 <TabsContent value="logs" data-tutorial="live-logs">
 <LogsTab logs={job.logs} pairNames={job.optimization_type === "grid_search" && job.grid_result ? Object.fromEntries(job.grid_result.pair_results.map(p => [p.pair_index, `${p.generation_model.split("/").pop()} × ${p.reflection_model.split("/").pop()}`])) : undefined} live={isActive} />
 </TabsContent>

 {/* ── Config tab ── */}
 <TabsContent value="config" className="mt-4" data-tutorial="config-section">
  <ConfigTab job={job} payload={payload} />
 </TabsContent>

 </Tabs>
 );
 })()}

 <StageInfoModal stage={stageModal} job={job} onClose={() => setStageModal(null)} />

 </div>
 );
}
