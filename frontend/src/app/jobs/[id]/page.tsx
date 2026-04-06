"use client";

import { Fragment, startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import {
 Loader2,
 XCircle,
 Trash2,
 Clock,
 Code,
 Terminal,
 TrendingUp,
 ChevronRight,
 ChevronLeft,
 Activity,
 CheckCircle2,
 Circle,
 Timer,
 Clipboard,
 Check,
 Send,
 Zap,
 Sparkles,
 CopyPlus,
 Download,
 ChevronDown,
 FileText,
 FileJson,
 FileSpreadsheet,
 Package,
 Pencil,
 MessageSquare,
 Component,
 Target,
 Cpu,
 Lightbulb,
 Quote,
 ListTodo,
 User,
 Database,
 PieChart,
 Shuffle,
 Dices,
} from "lucide-react";
import { toast } from "react-toastify";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
 Table,
 TableBody,
 TableCell,
 TableHead,
 TableHeader,
 TableRow,
} from "@/components/ui/table";
import { ColumnHeader, useColumnFilters, type SortDir } from "@/components/excel-filter";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { motion, AnimatePresence } from "framer-motion";
import { FadeIn, TiltCard, StaggerContainer, StaggerItem } from "@/components/motion";
import dynamic from "next/dynamic";

const CodeEditor = dynamic(
 () => import("@/components/code-editor").then((m) => m.CodeEditor),
 { ssr: false, loading: () => <div className="h-[180px] rounded-lg border border-border/40 bg-muted/20 animate-pulse" /> },
);
import { Tooltip as UiTooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { getJob, cancelJob, deleteJob, getJobPayload, getServeInfo, serveProgramStream } from "@/lib/api";
import type { ServeInfoResponse } from "@/lib/types";
import { ACTIVE_STATUSES, TERMINAL_STATUSES, STATUS_LABELS } from "@/lib/constants";
import type {
 JobStatusResponse,
 JobLogEntry,
 JobPayloadResponse,
} from "@/lib/types";

/* ── Helpers ── */

const STATUS_COLORS: Record<string, string> = {
 pending: "status-pill-pending",
 validating: "bg-stone-200 text-stone-700 border-stone-400 shadow-[0_0_8px_rgba(124,99,80,0.2)]",
 running: "status-pill-running",
 success: "status-pill-success",
 failed: "status-pill-failed",
 cancelled: "bg-stone-100 text-stone-700 border-stone-300",
};


function StatusBadge({ status }: { status: string }) {
 return (
 <Badge variant="outline" className={`text-[13px] px-3 py-1 font-bold tracking-wide ${STATUS_COLORS[status] ??""}`}>
 {status === "running" && <span className="relative flex size-2 me-1"><span className=" animate-ping absolute inline-flex h-full w-full rounded-full bg-stone-500/60"/><span className="relative inline-flex rounded-full size-2 bg-stone-500"/></span>}
 {STATUS_LABELS[status] ?? status}
 </Badge>
 );
}

function InfoCard({ label, value, icon }: { label: string; value: React.ReactNode; icon?: React.ReactNode }) {
 return (
 <motion.div
 whileHover={{ y: -1 }}
 transition={{ duration: 0.2, ease: [0.2, 0.8, 0.2, 1] }}
 className="group relative rounded-lg border border-[#E3DCD0] bg-[#FBF9F4] px-3.5 py-3 transition-[border-color,box-shadow] duration-200 hover:border-[#C8A882]/55 hover:shadow-[0_2px_8px_-2px_rgba(124,99,80,0.1)]"
 >
 <div className="flex items-center gap-1.5 mb-1.5">
 {icon && (
 <span className="shrink-0 inline-flex items-center justify-center size-3.5 text-[#A89680] transition-colors duration-200 group-hover:text-[#7C6350]" aria-hidden="true">
 {icon}
 </span>
 )}
 <p className="text-[10px] font-semibold tracking-[0.08em] uppercase text-[#A89680] truncate">
 {label}
 </p>
 </div>
 <p className="text-sm font-semibold text-[#1C1612] truncate">
 {value ?? <span className="text-[#BFB3A3] font-normal">—</span>}
 </p>
 </motion.div>
 );
}

function formatPercent(v: number | undefined | null): string {
 if (v == null) return "—";
 // Backend may return 0-1 (fraction) or 0-100 (percentage)
 const pct = v > 1 ? v : v * 100;
 return `${pct.toFixed(1)}%`;
}

function formatImprovement(v: number | undefined | null): string {
 if (v == null) return "—";
 // Backend may return 0-1 (fraction) or larger (already percentage points)
 const pct = Math.abs(v) > 1 ? v : v * 100;
 return pct >= 0 ? `+${pct.toFixed(1)}%` : `${pct.toFixed(1)}%`;
}

function jsonPreview(v: unknown): string {
 if (v == null) return "—";
 if (typeof v ==="object") return JSON.stringify(v, null, 2);
 return String(v);
}

function formatDuration(seconds: number): string {
 const hrs = Math.floor(seconds / 3600);
 const mins = Math.floor((seconds % 3600) / 60);
 const secs = Math.floor(seconds % 60);
 const pad = (n: number) => String(n).padStart(2, "0");
 if (hrs > 0) return `${hrs}:${pad(mins)}:${pad(secs)}`;
 return `${mins}:${pad(secs)}`;
}

/* ── Pipeline stage detection ── */
type PipelineStage ="validating"|"splitting"|"baseline"|"optimizing"|"evaluating"|"done";

function detectStage(job: JobStatusResponse): PipelineStage {
 if (job.status ==="validating") return "validating";
 if (job.status ==="success") return "done";

 const events = job.progress_events ?? [];
 const eventNames = events.map((e) => e.event);

 if (eventNames.includes("optimized_evaluated")) return "done";
 if (eventNames.includes("baseline_evaluated")) return "optimizing";
 if (eventNames.includes("dataset_splits_ready")) return "baseline";
 if (job.status ==="running") return "splitting";
 return "validating";
}

const PIPELINE_STAGES: { key: PipelineStage; label: string }[] = [
 { key: "validating", label: "אימות"},
 { key: "splitting", label: "חלוקת נתונים"},
 { key: "baseline", label: "ציון התחלתי"},
 { key: "optimizing", label: "אופטימיזציה"},
 { key: "evaluating", label: "הערכה"},
];

/* ── Score extraction from optimizer logs ── */

interface ScorePoint {
 trial: number;
 score: number;
 best: number;
}

function extractScoresFromLogs(logs: { message: string }[]): ScorePoint[] {
 const points: ScorePoint[] = [];
 let currentTrial = 0;
 let bestSoFar = -1;

 for (const log of logs) {
 const msg = log.message;

 // MIPROv2: "===== Trial N / M =====" or "== Trial N / M"
 const trialMatch = msg.match(/Trial (\d+)\s*\/\s*\d+/);
 if (trialMatch) {
 currentTrial = parseInt(trialMatch[1], 10);
 }

 // MIPROv2: "Score: 85.0 with parameters ..."
 const scoreMatch = msg.match(/^Score:\s*([\d.]+)\s+(?:with parameters|on minibatch)/);
 if (scoreMatch && currentTrial > 0) {
 const score = parseFloat(scoreMatch[1]);
 bestSoFar = Math.max(bestSoFar, score);
 points.push({ trial: currentTrial, score, best: bestSoFar });
 continue;
 }

 // MIPROv2: "Default program score: 85.0"
 const defaultMatch = msg.match(/Default program score:\s*([\d.]+)/);
 if (defaultMatch) {
 const score = parseFloat(defaultMatch[1]);
 bestSoFar = Math.max(bestSoFar, score);
 points.push({ trial: currentTrial || 1, score, best: bestSoFar });
 continue;
 }

 // GEPA: "Iteration N: Full valset score for new program: 0.78"
 const gepaScoreMatch = msg.match(/Iteration (\d+):\s*Full valset score for new program:\s*([\d.]+)/);
 if (gepaScoreMatch) {
 const iter = parseInt(gepaScoreMatch[1], 10);
 const score = parseFloat(gepaScoreMatch[2]);
 bestSoFar = Math.max(bestSoFar, score);
 points.push({ trial: iter, score, best: bestSoFar });
 continue;
 }

 // GEPA: "Iteration N: Base program full valset score: 0.65"
 const gepaBaseMatch = msg.match(/Iteration (\d+):\s*Base program full valset score:\s*([\d.]+)/);
 if (gepaBaseMatch) {
 const iter = parseInt(gepaBaseMatch[1], 10);
 const score = parseFloat(gepaBaseMatch[2]);
 bestSoFar = Math.max(bestSoFar, score);
 points.push({ trial: iter, score, best: bestSoFar });
 }
 }

 return points;
}

function ScoreChartTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number; name: string; color: string }>; label?: string }) {
 if (!active || !payload?.length) return null;
 return (
 <div className="rounded-lg border bg-background p-3 shadow-md text-sm" dir="rtl">
 <p className="font-medium mb-1.5">ניסיון {label}</p>
 {payload.map((p, i) => (
 <div key={i} className="flex items-center gap-2">
 <span className="size-2.5 rounded-full shrink-0" style={{ backgroundColor: p.color }} />
 <span className="text-muted-foreground">{p.name}:</span>
 <span className="font-mono font-bold ms-auto" dir="ltr">{p.value.toFixed(1)}</span>
 </div>
 ))}
 </div>
 );
}

function LangPicker<T extends string>({ value, onChange, labels }: {
 value: T;
 onChange: (v: T) => void;
 labels: Record<T, string>;
}) {
 const [open, setOpen] = useState(false);
 const ref = useRef<HTMLDivElement>(null);
 useEffect(() => {
 if (!open) return;
 const onClick = (e: MouseEvent) => {
  if (!ref.current?.contains(e.target as Node)) setOpen(false);
 };
 const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
 window.addEventListener("mousedown", onClick);
 window.addEventListener("keydown", onKey);
 return () => {
  window.removeEventListener("mousedown", onClick);
  window.removeEventListener("keydown", onKey);
 };
 }, [open]);
 const keys = Object.keys(labels) as T[];
 return (
 <div ref={ref} className="relative">
 <button
  type="button"
  onClick={() => setOpen(o => !o)}
  className="flex items-center gap-1 px-1.5 py-0.5 -mx-1.5 -my-0.5 rounded-md font-semibold text-[#7C6350] tracking-wide hover:bg-black/5 transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/50"
  aria-haspopup="listbox"
  aria-expanded={open}
 >
  <span>{labels[value]}</span>
  <ChevronDown className={`size-3 text-[#8C7A6B] transition-transform duration-150 ${open ? "rotate-180" : ""}`} />
 </button>
 <AnimatePresence>
 {open && (
 <motion.ul
  role="listbox"
  initial={{ opacity: 0, y: -4, scale: 0.96 }}
  animate={{ opacity: 1, y: 0, scale: 1 }}
  exit={{ opacity: 0, y: -4, scale: 0.96 }}
  transition={{ duration: 0.12, ease: [0.16, 1, 0.3, 1] }}
  className="absolute top-full mt-1.5 start-0 z-20 min-w-[120px] rounded-lg border border-[#E5DDD4] bg-[#FAF6F0] shadow-lg overflow-hidden py-1"
 >
  {keys.map((k) => (
  <li key={k}>
   <button
   type="button"
   onClick={() => { onChange(k); setOpen(false); }}
   className={`w-full text-start px-3 py-1.5 text-[11px] font-semibold tracking-wide transition-colors cursor-pointer flex items-center justify-between ${k === value ? "bg-[#3D2E22]/8 text-[#3D2E22]" : "text-[#7C6350] hover:bg-black/5"}`}
   role="option"
   aria-selected={k === value}
   >
   <span>{labels[k]}</span>
   {k === value && <Check className="size-3" />}
   </button>
  </li>
  ))}
 </motion.ul>
 )}
 </AnimatePresence>
 </div>
 );
}

function CopyButton({ text, className =""}: { text: string; className?: string }) {
 const [copied, setCopied] = useState(false);
 return (
 <button
 type="button" onClick={() => {
 navigator.clipboard.writeText(text);
 setCopied(true);
 setTimeout(() => setCopied(false), 1500);
 }}
 className={`p-1.5 cursor-pointer transition-opacity duration-200 outline-none border-none shadow-none ring-0 bg-transparent hover:opacity-100 ${className}`}
 title="העתק"
 aria-label="העתק">
 {copied
 ? <Check className="size-3.5 text-foreground/70"/>
 : <Clipboard className="size-3.5 text-foreground/40 hover:text-foreground/70"/>}
 </button>
 );
}

/* ── Download helpers ── */

function formatLogTimestamp(ts: string): string {
  // Accept ISO "2026-03-30T23:32:45.971393" — return "30/03 23:32:45"
  const m = ts.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/);
  if (!m) return ts;
  const [, , mm, dd, hh, mi, ss] = m;
  return `${dd}/${mm} ${hh}:${mi}:${ss}`;
}

function logTimeBucket(ts: string): string {
  // Group timestamps by minute for filter options: "30/03 23:32"
  const m = ts.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (!m) return ts;
  const [, , mm, dd, hh, mi] = m;
  return `${dd}/${mm} ${hh}:${mi}`;
}

function formatOutput(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try { return JSON.stringify(v, null, 2); } catch { return String(v); }
}

function downloadFile(content: string, filename: string, mimeType: string) {
 const blob = new Blob([content], { type: mimeType });
 const url = URL.createObjectURL(blob);
 const a = document.createElement("a");
 a.href = url;
 a.download = filename;
 a.click();
 URL.revokeObjectURL(url);
}

function exportPromptAsText(prompt: import("@/lib/types").OptimizedPredictor, jobId: string) {
 let text = `# Optimized Prompt — ${prompt.predictor_name}\n\n`;
 text += `## Instructions\n${prompt.instructions}\n\n`;
 if (prompt.demos.length > 0) {
 text += `## Demos (${prompt.demos.length})\n\n`;
 prompt.demos.forEach((demo, i) => {
 text += `--- Demo ${i + 1} ---\n`;
 for (const [k, v] of Object.entries(demo.inputs)) text += `[Input] ${k}: ${v}\n`;
 for (const [k, v] of Object.entries(demo.outputs)) text += `[Output] ${k}: ${v}\n`;
 text += "\n";
 });
 }
 if (prompt.formatted_prompt) {
 text += `## Full Formatted Prompt\n${prompt.formatted_prompt}\n`;
 }
 downloadFile(text, `prompt_${jobId.slice(0, 8)}.txt`, "text/plain");
}

function exportPromptAsJson(prompt: import("@/lib/types").OptimizedPredictor, jobId: string) {
 downloadFile(JSON.stringify(prompt, null, 2), `prompt_${jobId.slice(0, 8)}.json`, "application/json");
}

function exportLogsAsCsv(logs: import("@/lib/types").JobLogEntry[], jobId: string) {
 const header = "timestamp,level,logger,message\n";
 const rows = logs.map((l) => {
 const escapedMsg = `"${l.message.replace(/"/g, '""')}"`;
 return `${l.timestamp},${l.level},${l.logger},${escapedMsg}`;
 }).join("\n");
 downloadFile(header + rows, `logs_${jobId.slice(0, 8)}.csv`, "text/csv");
}

/* ── Page Component ── */

export default function JobDetailPage() {
 const { id } = useParams<{ id: string }>();
 const router = useRouter();
 const searchParams = useSearchParams();
 const initialTab = searchParams.get("tab") ?? "overview";

 const [job, setJob] = useState<JobStatusResponse | null>(null);
 const [payload, setPayload] = useState<JobPayloadResponse | null>(null);
 const [loading, setLoading] = useState(true);
 const [error, setError] = useState<string | null>(null);

 /* Log filters */
 const logFilters = useColumnFilters();
 const [logMessageSearch, setLogMessageSearch] = useState("");
 const [logSortKey, setLogSortKey] = useState<string>("timestamp");
 const [logSortDir, setLogSortDir] = useState<SortDir>("desc");
 const toggleLogSort = (key: string) => {
 if (logSortKey === key) setLogSortDir((d) => (d === "asc" ? "desc" : "asc"));
 else { setLogSortKey(key); setLogSortDir("asc"); }
 };

 /* Serving playground */
 const [serveInfo, setServeInfo] = useState<ServeInfoResponse | null>(null);
 const [serveInputs, setServeInputs] = useState<Record<string, string>>({});
 const [serveLoading, setServeLoading] = useState(false);
 const [runHistory, setRunHistory] = useState<Array<{ inputs: Record<string, string>; outputs: Record<string, unknown>; model: string; ts: number }>>([]);
 const [streamingRun, setStreamingRun] = useState<{ inputs: Record<string, string>; partial: Record<string, string> } | null>(null);
 const streamReqIdRef = useRef(0);
 const streamAbortRef = useRef<AbortController | null>(null);
 const chatScrollRef = useRef<HTMLDivElement>(null);
 const textareaRefs = useRef<Record<string, HTMLTextAreaElement | null>>({});
 const [serveError, setServeError] = useState<string | null>(null);
 const [editingRunTs, setEditingRunTs] = useState<number | null>(null);
 const [editInputs, setEditInputs] = useState<Record<string, string>>({});
 const [codeTab, setCodeTab] = useState<"curl" | "python" | "dspy">("curl");

 /* Fetch job data */
 const fetchJob = useCallback(async () => {
 try {
 const data = await getJob(id);
 setJob(data);
 setError(null);
 } catch (err) {
 const msg = err instanceof Error ? err.message :"";
 setError(msg ? `שגיאה בטעינת האופטימיזציה: ${msg}` :"שגיאה בטעינת האופטימיזציה");
 } finally {
 setLoading(false);
 }
 }, [id]);

 /* Fetch payload (once) */
 useEffect(() => {
 getJobPayload(id)
 .then(setPayload)
 .catch(() => {});
 }, [id]);

 /* Initial fetch + SSE streaming for real-time updates */
 const jobRef = useRef(job);
 jobRef.current = job;

 useEffect(() => {
 fetchJob();

 const API = process.env.NEXT_PUBLIC_API_URL ??"http://localhost:8000";
 let eventSource: EventSource | null = null;
 let fallbackInterval: ReturnType<typeof setInterval> | null = null;

 try {
 eventSource = new EventSource(`${API}/jobs/${id}/stream`);

 eventSource.onmessage = () => {
 fetchJob();
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
 }, [id, fetchJob]);

 /* Listen for rename/update events from sidebar */
 useEffect(() => {
 const onRenamed = (e: Event) => {
 const { jobId, name } = (e as CustomEvent).detail;
 if (jobId === id) setJob(prev => prev ? { ...prev, name } : prev);
 };
 const onUpdated = (e: Event) => {
 const { jobId } = (e as CustomEvent).detail;
 if (jobId === id) fetchJob();
 };
 window.addEventListener("job-renamed", onRenamed);
 window.addEventListener("job-updated", onUpdated);
 return () => {
 window.removeEventListener("job-renamed", onRenamed);
 window.removeEventListener("job-updated", onUpdated);
 };
 }, [id, fetchJob]);

 /* Actions */
 const handleCancel = async () => {
 try {
 await cancelJob(id);
 toast.success("בקשת ביטול נשלחה");
 fetchJob();
 } catch (err) {
 toast.error(err instanceof Error ? err.message :"ביטול נכשל");
 }
 };

 const [showDeleteDialog, setShowDeleteDialog] = useState(false);
 const [exportMenuOpen, setExportMenuOpen] = useState(false);
 const exportMenuRef = useRef<HTMLDivElement>(null);

 /* Close export menu on outside click */
 useEffect(() => {
 if (!exportMenuOpen) return;
 const handler = (e: MouseEvent) => {
 if (exportMenuRef.current && !exportMenuRef.current.contains(e.target as Node)) setExportMenuOpen(false);
 };
 document.addEventListener("mousedown", handler);
 return () => document.removeEventListener("mousedown", handler);
 }, [exportMenuOpen]);
 const [deleteLoading, setDeleteLoading] = useState(false);

 const handleDelete = async () => {
 setDeleteLoading(true);
 try {
 await deleteJob(id);
 router.push("/");
 } catch (err) {
 toast.error(err instanceof Error ? err.message :"מחיקה נכשלה");
 } finally {
 setDeleteLoading(false);
 setShowDeleteDialog(false);
 }
 };

 /* Fetch serve info once job succeeds */
 useEffect(() => {
 if (job?.status !=="success") return;
 getServeInfo(id)
 .then((info) => {
 setServeInfo(info);
 const initial: Record<string, string> = {};
 for (const f of info.input_fields) initial[f] ="";
 setServeInputs(initial);
 })
 .catch(() => {});
 }, [id, job?.status]);

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

 const handleServe = async (overrideInputs?: Record<string, string>) => {
 if (!serveInfo) return;
 const inputs = overrideInputs ?? serveInputs;
 const missing = serveInfo.input_fields.filter((f) => !inputs[f]?.trim());
 if (missing.length > 0) {
 toast.error(`נא למלא את כל השדות: ${missing.join(",")}`);
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
 const cleared: Record<string, string> = {};
 for (const f of serveInfo.input_fields) cleared[f] = "";
 setServeInputs(cleared);
 Object.values(textareaRefs.current).forEach((el) => {
  if (el) el.style.height = "auto";
 });
 }
 const isStale = () => reqId !== streamReqIdRef.current;
 await serveProgramStream(id, inputs, {
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

 const handleEditAndResend = (runTs: number) => {
 // runHistory is newest-first. "Remove this run and everything after it"
 // means keeping older turns only, which are AT indices > idx.
 setRunHistory((prev) => {
 const idx = prev.findIndex((r) => r.ts === runTs);
 if (idx === -1) return prev;
 return prev.slice(idx + 1);
 });
 // Submit with the edited inputs
 handleServe(editInputs);
 setEditingRunTs(null);
 };

 const handleClearHistory = () => {
 setRunHistory([]);
 setServeError(null);
 };

 /* Filtered + sorted logs */
 const filteredLogs = useMemo(() => {
 if (!job) return [];
 const q = logMessageSearch.trim().toLowerCase();
 let logs = job.logs.filter((l) => {
 if (q && !l.message.toLowerCase().includes(q)) return false;
 for (const [col, allowed] of Object.entries(logFilters.filters)) {
  if (allowed.size === 0) continue;
  const val = col === "timestamp"
  ? logTimeBucket(l.timestamp)
  : String((l as unknown as Record<string, unknown>)[col] ?? "");
  if (!allowed.has(val)) return false;
 }
 return true;
 });
 logs = [...logs].sort((a, b) => {
 const av = String((a as unknown as Record<string, unknown>)[logSortKey] ?? "");
 const bv = String((b as unknown as Record<string, unknown>)[logSortKey] ?? "");
 const cmp = av.localeCompare(bv, "he", { numeric: true });
 return logSortDir === "asc" ? cmp : -cmp;
 });
 return logs;
 }, [job, logFilters.filters, logSortKey, logSortDir, logMessageSearch]);

 /* Unique values for log filter dropdowns */
 const logFilterOptions = useMemo(() => {
 if (!job) return { level: [], logger: [], timestamp: [] };
 const unique = (key: keyof JobLogEntry) => {
 const vals = [...new Set(job.logs.map((l) => String(l[key] ?? "")))].filter(Boolean).sort();
 return vals.map((v) => ({ value: v, label: v }));
 };
 const timestampBuckets = [...new Set(job.logs.map((l) => logTimeBucket(l.timestamp)))]
 .filter(Boolean)
 .sort()
 .map((v) => ({ value: v, label: v }));
 return { level: unique("level"), logger: unique("logger"), timestamp: timestampBuckets };
 }, [job]);

 /* Progress metrics */
 const metrics = job?.latest_metrics ?? {};
 const tqdmPercent = metrics.tqdm_percent as number | undefined;
 const tqdmN = metrics.tqdm_n as number | undefined;
 const tqdmTotal = metrics.tqdm_total as number | undefined;
 const tqdmRate = metrics.tqdm_rate as number | undefined;
 const tqdmRemaining = metrics.tqdm_remaining as string | undefined;

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
 const fmt = () => {
 const diff = Math.max(0, Math.floor((Date.now() - start) / 1000));
 const h = String(Math.floor(diff / 3600)).padStart(2, "0");
 const m = String(Math.floor((diff % 3600) / 60)).padStart(2, "0");
 const s = String(diff % 60).padStart(2, "0");
 setLiveElapsed(`${h}:${m}:${s}`);
 };
 fmt();
 if (!isActive) return;
 const id = setInterval(fmt, 1000);
 return () => clearInterval(id);
 }, [job?.started_at, job?.created_at, isActive]);

 /* ── Render ── */

 if (loading) {
 return (
 <div className="flex items-center justify-center min-h-[60vh]">
 <Loader2 className="size-8 animate-spin text-primary"/>
 </div>
 );
 }

 if (error || !job) {
 return (
 <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
 <XCircle className="size-12 text-destructive"/>
 <p className="text-lg text-muted-foreground">{error ??"האופטימיזציה לא נמצאה"}</p>
 <Button variant="outline" asChild>
 <Link href="/">חזרה</Link>
 </Button>
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
 <span className="text-foreground font-medium text-xs sm:text-sm break-all" dir="auto">{job.name || job.job_id.slice(0, 8)}</span>
 </div>
 </FadeIn>

 {/* ── 1. Header ── */}
 <FadeIn delay={0.1}>
 <div className=" rounded-xl border border-border/40 bg-gradient-to-br from-card to-card/80 p-5">
 <div className="flex flex-wrap items-start justify-between gap-4">
 <div className="space-y-2 min-w-0">
 <div className="flex items-center gap-3 flex-wrap">
 {job.name && (
 <h2 className="text-lg sm:text-xl font-bold tracking-tight" dir="auto">{job.name}</h2>
 )}
 <StatusBadge status={job.status} />
 </div>
 <code
 className="text-xs font-mono text-muted-foreground/60 cursor-pointer hover:text-primary transition-colors break-all"
 title="לחץ להעתקה"
 aria-label="העתק מזהה"
 role="button"
 tabIndex={0}
 onClick={() => { navigator.clipboard.writeText(job.job_id); toast.success("הועתק", { autoClose: 1000 }); }}
 onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); navigator.clipboard.writeText(job.job_id); toast.success("הועתק", { autoClose: 1000 }); } }}
 >
 {job.job_id}
 </code>
 <div className="flex items-center gap-3 flex-wrap text-sm text-muted-foreground">
 <Badge variant="secondary" className="text-[11px]">{job.job_type === "grid_search"?"סריקה":"ריצה בודדת"}</Badge>
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
 <Button variant="ghost" size="icon" className="size-8" onClick={() => router.push(`/submit?clone=${job.job_id}`)} aria-label="שכפול">
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
 <Button variant="destructive" size="icon" className="size-8" onClick={handleCancel} aria-label="ביטול">
 <XCircle className="size-4"/>
 </Button>
 </TooltipTrigger>
 <TooltipContent side="bottom">ביטול</TooltipContent>
 </UiTooltip>
 </TooltipProvider>
 )}
 </div>
 </div>
 </div>
 </FadeIn>

 {/* ── Failure message ── */}
 {job.status === "failed" && job.message && (
 <FadeIn delay={0.15}>
 <div className="p-5 rounded-xl border border-red-300/60 bg-gradient-to-br from-red-50 to-red-100/40 shadow-[0_0_15px_rgba(239,68,68,0.06)]">
 <div className="flex items-start gap-3">
 <XCircle className="size-5 text-red-500 shrink-0 mt-0.5"/>
 <p className="text-sm font-semibold text-red-800">נכשלה</p>
 </div>
 <pre className="text-xs text-red-700 mt-3 whitespace-pre-wrap break-words font-mono leading-relaxed" dir="ltr">
{job.message?.split(/(https?:\/\/[^\s]+)/g).map((part, i) =>
 /^https?:\/\//.test(part) ? <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="underline hover:text-red-900 transition-colors">{part}</a> : part
 )}
 </pre>
 </div>
 </FadeIn>
 )}

 {/* ── 2. Live optimization view (active jobs) ── */}
 {isActive && (() => {
 const stage = detectStage(job);
 const stageIdx = PIPELINE_STAGES.findIndex((s) => s.key === stage);
 const baselineEvent = job.progress_events?.find((e) => e.event === "baseline_evaluated");
 const baselineScore = baselineEvent?.metrics?.baseline_test_metric as number | undefined;
 const splitsEvent = job.progress_events?.find((e) => e.event === "dataset_splits_ready");
 const trainCount = (splitsEvent?.metrics?.train_examples ?? metrics.train_examples) as number | undefined;
 const valCount = (splitsEvent?.metrics?.val_examples ?? metrics.val_examples) as number | undefined;
 const testCount = (splitsEvent?.metrics?.test_examples ?? metrics.test_examples) as number | undefined;
 const tqdmDesc = metrics.tqdm_desc as string | undefined;
 const tqdmElapsed = metrics.tqdm_elapsed as number | undefined;
 const recentLogs = [...(job.logs ?? [])].reverse().slice(0, 12);
 const pct = tqdmPercent != null ? Math.min(tqdmPercent * 100, 100) : null;
 const isGridSearch = job.job_type === "grid_search";
 const totalPairs = job.total_pairs as number | undefined;
 const completedPairs = job.completed_pairs as number | undefined;
 const failedPairs = job.failed_pairs as number | undefined;

 return (
 <Card className="border-primary/20 overflow-hidden">
 {/* Animated top accent */}
 <div className="h-1 bg-gradient-to-l from-primary/80 via-primary/40 to-transparent animate-pulse"/>

 <CardHeader className="pb-3">
 <CardTitle className="flex items-center gap-2 text-base">
 <Loader2 className="size-4 animate-spin text-primary"/>
 אופטימיזציה בתהליך
 </CardTitle>
 </CardHeader>

 <CardContent className="space-y-5">
 {/* ── Stage pipeline ── */}
 {(() => {
 // Map stage keys to their completion timestamps from progress events
 const eventToStage: Record<string, PipelineStage> = {
 "validation_passed": "validating",
 "dataset_splits_ready": "splitting",
 "baseline_evaluated": "baseline",
 "optimized_evaluated": "optimizing",
 };
 const stageTimestamps: Partial<Record<PipelineStage, string>> = {};
 for (const ev of (job.progress_events ?? [])) {
 const stageKey = ev.event ? eventToStage[ev.event] : undefined;
 if (stageKey && ev.timestamp) {
 stageTimestamps[stageKey] = new Date(ev.timestamp).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
 }
 }
 // Use job.started_at for the validating stage start
 if (job.started_at && !stageTimestamps.validating) {
 // Only show if validating is done
 if (stageIdx > 0) stageTimestamps.validating = new Date(job.started_at).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
 }
 return (
 <div className="flex items-center gap-0" dir="rtl">
 {PIPELINE_STAGES.map((s, i) => {
 const isDone = i < stageIdx;
 const isCurrent = i === stageIdx;
 const lineAfter = i < PIPELINE_STAGES.length - 1;
 const nextDone = (i + 1) < stageIdx;
 const nextCurrent = (i + 1) === stageIdx;
 const ts = stageTimestamps[s.key];
 return (
 <Fragment key={s.key}>
 <div className="flex flex-col items-center shrink-0 gap-0.5">
 <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-full whitespace-nowrap text-xs transition-colors ${
 isCurrent
 ?"bg-primary/10 text-primary font-semibold ring-1 ring-primary/30"
 : isDone
 ?"text-primary"
 :"text-muted-foreground/40"
 }`}>
 {isDone ? (
 <CheckCircle2 className="size-3.5 shrink-0"/>
 ) : isCurrent ? (
 <Loader2 className="size-3.5 animate-spin shrink-0"/>
 ) : (
 <Circle className="size-3.5 shrink-0"/>
 )}
 {s.label}
 </div>
 {ts && isDone && (
 <span className="text-[9px] text-muted-foreground tabular-nums" dir="ltr">{ts}</span>
 )}
 </div>
 {lineAfter && (
 <div className={`flex-1 h-px min-w-3 ${nextDone || nextCurrent ? "bg-primary" : "bg-border"}`} />
 )}
 </Fragment>
 );
 })}
 </div>
 );
 })()}

 {/* ── Grid search pair progress ── */}
 {isGridSearch && totalPairs != null && totalPairs > 0 && (
 <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 space-y-2">
 <div className="flex items-center justify-between text-sm">
 <span className="font-medium">התקדמות זוגות מודלים</span>
 <span className="font-mono font-bold text-primary">{(completedPairs ?? 0) + (failedPairs ?? 0)}/{totalPairs}</span>
 </div>
 <div className="h-2.5 rounded-full bg-muted overflow-hidden flex">
 {(completedPairs ?? 0) > 0 && (
 <div className="h-full bg-stone-500 transition-all duration-500" style={{ width: `${((completedPairs ?? 0) / totalPairs) * 100}%` }} />
 )}
 {(failedPairs ?? 0) > 0 && (
 <div className="h-full bg-red-500 transition-all duration-500" style={{ width: `${((failedPairs ?? 0) / totalPairs) * 100}%` }} />
 )}
 </div>
 <div className="flex gap-4 text-xs text-muted-foreground">
 {(completedPairs ?? 0) > 0 && <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-stone-500"/>{completedPairs} הושלמו</span>}
 {(failedPairs ?? 0) > 0 && <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-red-500"/>{failedPairs} נכשלו</span>}
 <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-muted-foreground/30"/>{totalPairs - (completedPairs ?? 0) - (failedPairs ?? 0)} ממתינים</span>
 </div>
 </div>
 )}

 {/* ── Progress bar ── */}
 {pct != null && (
 <div className="space-y-2">
 <div className="flex items-center justify-between text-sm">
 <span className="text-muted-foreground">{tqdmDesc ?? "התקדמות"}</span>
 <span className="font-mono font-bold text-primary">{pct.toFixed(0)}%</span>
 </div>
 <div className="h-3 rounded-full bg-muted overflow-hidden">
 <div
 className="h-full rounded-full bg-gradient-to-l from-primary to-primary/60 transition-all duration-700 ease-out"
 style={{ width: `${pct}%` }}
 />
 </div>
 </div>
 )}

 {/* ── Live metrics ── */}
 <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
 {tqdmN != null && tqdmTotal != null && (
 <div className="rounded-xl border border-border/40 bg-gradient-to-br from-muted/30 to-muted/5 p-3 text-center transition-colors hover:border-primary/30">
 <Activity className="size-4 text-primary mx-auto mb-1.5"/>
 <p className="text-[10px] text-muted-foreground font-medium">צעד</p>
 <p className="text-sm font-mono font-bold mt-0.5">{tqdmN}/{tqdmTotal}</p>
 </div>
 )}
 {tqdmElapsed != null && (
 <div className=" rounded-xl border border-border/40 bg-gradient-to-br from-muted/30 to-muted/5 p-3 text-center transition-colors hover:border-primary/30">
 <Timer className="size-4 text-primary mx-auto mb-1.5"/>
 <p className="text-[10px] text-muted-foreground font-medium">זמן שעבר</p>
 <p className="text-sm font-mono font-bold mt-0.5">{formatDuration(tqdmElapsed)}</p>
 </div>
 )}
 {tqdmRemaining != null && (
 <div className="rounded-xl border border-border/40 bg-gradient-to-br from-muted/30 to-muted/5 p-3 text-center transition-colors hover:border-primary/30">
 <Clock className="size-4 text-muted-foreground mx-auto mb-1.5"/>
 <p className="text-[10px] text-muted-foreground font-medium">נותר</p>
 <p className="text-sm font-mono font-bold mt-0.5">{formatDuration(Number(tqdmRemaining))}</p>
 </div>
 )}
 {tqdmRate != null && (
 <div className=" rounded-xl border border-border/40 bg-gradient-to-br from-yellow-50/30 to-muted/5 p-3 text-center transition-colors hover:border-yellow-400/30">
 <Zap className="size-4 text-yellow-500 mx-auto mb-1.5"/>
 <p className="text-[10px] text-muted-foreground font-medium">קצב</p>
 <p className="text-sm font-mono font-bold mt-0.5">{tqdmRate.toFixed(2)}/שנ׳</p>
 </div>
 )}
 {baselineScore != null && (
 <div className="rounded-xl border border-border/40 bg-gradient-to-br from-stone-100/30 to-muted/5 p-3 text-center transition-colors hover:border-stone-400/30">
 <TrendingUp className="size-4 text-stone-500 mx-auto mb-1.5"/>
 <p className="text-[10px] text-muted-foreground font-medium">ציון התחלתי</p>
 <p className="text-sm font-mono font-bold mt-0.5">{formatPercent(baselineScore)}</p>
 </div>
 )}
 {trainCount != null && (
 <div className=" rounded-xl border border-border/40 bg-gradient-to-br from-muted/30 to-muted/5 p-3 text-center transition-colors hover:border-primary/30">
 <Code className="size-4 text-muted-foreground mx-auto mb-1.5"/>
 <p className="text-[10px] text-muted-foreground font-medium">נתונים</p>
 <p className="text-sm font-mono font-bold mt-0.5">{trainCount}/{valCount}/{testCount}</p>
 </div>
 )}
 </div>

 {/* ── Live score chart ── */}
 {scorePoints.length > 1 && (
 <div className="space-y-2">
 <p className="text-sm font-medium">מהלך ציונים</p>
 <div className="h-72 rounded-lg border border-border/50 bg-muted/10 p-3" dir="ltr">
 <ResponsiveContainer width="100%" height="100%">
 <LineChart data={scorePoints} margin={{ top: 5, right: 10, left: 5, bottom: 18 }}>
 <CartesianGrid strokeDasharray="3 3" className="stroke-muted" vertical={false} />
 <XAxis dataKey="trial" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} className="fill-muted-foreground" label={{ value: "ניסיון", position: "insideBottom", offset: -12, fontSize: 10, fill: "var(--muted-foreground)" }} />
 <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 10 }} className="fill-muted-foreground" label={{ value: "ציון", angle: -90, position: "insideLeft", offset: 10, fontSize: 10, fill: "var(--muted-foreground)" }} domain={[0,"auto"]} />
 <Tooltip content={<ScoreChartTooltip />} />
 <Line type="monotone" dataKey="score" name="ציון הניסיון" stroke="var(--color-chart-4)" strokeWidth={1.5} dot={{ r: 2 }} isAnimationActive={false} />
 <Line type="stepAfter" dataKey="best" name="שיא" stroke="var(--color-chart-2)" strokeWidth={2} dot={false} isAnimationActive={false} />
 </LineChart>
 </ResponsiveContainer>
 </div>
 </div>
 )}

 {/* ── Live log ── */}
 {recentLogs.length > 0 && (
 <div className="space-y-2">
 <div className="flex items-center justify-between">
 <div className="flex items-center gap-2 text-sm font-medium">
 <Terminal className="size-3.5"/>
 לוגים חיים
 <span className="relative flex size-2">
 <span className=" animate-ping absolute inline-flex h-full w-full rounded-full bg-primary/60"/>
 <span className="relative inline-flex rounded-full size-2 bg-primary"/>
 </span>
 </div>
 <Badge variant="secondary" className="text-[10px]">{job.logs?.length ?? 0}</Badge>
 </div>
 <Card>
 <CardContent className="p-0">
 <div className="max-h-[400px] overflow-auto">
 <Table>
 <TableHeader>
 <TableRow>
 <TableHead className="text-xs w-[100px]">זמן</TableHead>
 <TableHead className="text-xs w-[60px]">רמה</TableHead>
 <TableHead className="text-xs w-[100px]">לוגר</TableHead>
 <TableHead className="text-xs">הודעה</TableHead>
 </TableRow>
 </TableHeader>
 <TableBody>
 {recentLogs.map((log, i) => (
 <TableRow
 key={i}
 className={`cursor-pointer transition-all duration-150 ${i === 0 ? "bg-primary/5" : ""}`}
 onClick={() => { navigator.clipboard.writeText(log.message); toast.success("הועתק", { autoClose: 1500 }); }}
 >
 <TableCell className="text-xs font-mono text-muted-foreground whitespace-nowrap" dir="ltr">{formatLogTimestamp(log.timestamp)}</TableCell>
 <TableCell>
 <Badge variant={
 log.level === "ERROR" ? "destructive" :
 log.level === "WARNING" ? "outline" : "secondary"} className="text-[10px] font-mono">
 {log.level}
 </Badge>
 </TableCell>
 <TableCell className="text-xs font-mono text-muted-foreground truncate max-w-[120px]">{log.logger}</TableCell>
 <TableCell className="text-xs font-mono whitespace-pre-wrap break-all">{log.message}</TableCell>
 </TableRow>
 ))}
 </TableBody>
 </Table>
 </div>
 </CardContent>
 </Card>
 </div>
 )}
 </CardContent>
 </Card>
 );
 })()}

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

 {/* ── Export Bar ── */}
 {isTerminal && job.status !== "cancelled" && (optimizedPrompt || (job.logs && job.logs.length > 0) || job.result?.program_artifact?.program_pickle_base64 || job.grid_result?.best_pair?.program_artifact?.program_pickle_base64) && (
 <FadeIn delay={0.25}>
 <div className="flex items-center gap-3 p-5 rounded-xl border border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10 shadow-[0_0_20px_rgba(var(--primary),0.06)]">
 <div className="flex-1">
 <p className="text-sm font-medium">ייצוא תוצאות</p>
 </div>
 <div className="relative" ref={exportMenuRef}>
 <Button size="sm" onClick={() => setExportMenuOpen(o => !o)} className="gap-1.5">
 <Download className="size-4" />
 הורדה
 <ChevronDown className={`size-3.5 transition-transform duration-150 ${exportMenuOpen ? "rotate-180" : ""}`} />
 </Button>
 <AnimatePresence>
 {exportMenuOpen && (() => {
 const itemCls = "w-full flex items-center gap-2.5 px-3.5 py-2 text-[12px] text-foreground hover:bg-muted/40 cursor-pointer transition-colors";
 const iconCls = "size-4 shrink-0 text-muted-foreground/60";
 const extCls = "text-muted-foreground/60 font-mono text-[10px] ms-auto";
 const divider = <div className="h-px bg-border/40 mx-2 my-1" />;
 const hasPkl = !!(job.result?.program_artifact?.program_pickle_base64 || job.grid_result?.best_pair?.program_artifact?.program_pickle_base64);
 return (
 <motion.div
 role="menu"
 initial={{ opacity: 0, scale: 0.95, y: -4 }}
 animate={{ opacity: 1, scale: 1, y: 0 }}
 exit={{ opacity: 0, scale: 0.95, y: -4 }}
 transition={{ duration: 0.12 }}
 className="absolute end-0 top-full mt-1.5 z-50 w-[210px] rounded-2xl border border-border/40 bg-card shadow-[0_4px_24px_rgba(28,22,18,0.1)] py-1.5"
 >
 {hasPkl && (
 <button type="button" role="menuitem" onClick={() => {
 setExportMenuOpen(false);
 const b64 = job.result?.program_artifact?.program_pickle_base64 ?? job.grid_result?.best_pair?.program_artifact?.program_pickle_base64;
 if (!b64) return;
 try {
 const blob = new Blob([Uint8Array.from(atob(b64), c => c.charCodeAt(0))], { type: "application/octet-stream" });
 const url = URL.createObjectURL(blob);
 const a = document.createElement("a");
 a.href = url; a.download = `program_${job.job_id.slice(0, 8)}.pkl`; a.click();
 URL.revokeObjectURL(url);
 } catch { toast.error("שגיאה בפענוח הקובץ"); }
 }} className={itemCls}>
 <Package className={iconCls} />
 <span className="flex-1">תוכנית מאומנת</span>
 <span className={extCls}>.pkl</span>
 </button>
 )}
 {optimizedPrompt && (
 <>
 {hasPkl && divider}
 <button type="button" role="menuitem" onClick={() => { setExportMenuOpen(false); exportPromptAsJson(optimizedPrompt, job.job_id); }} className={itemCls}>
 <FileJson className={iconCls} />
 <span className="flex-1">פרומפט</span>
 <span className={extCls}>.json</span>
 </button>
 </>
 )}
 {job.logs && job.logs.length > 0 && (
 <>
 {divider}
 <button type="button" role="menuitem" onClick={() => { setExportMenuOpen(false); exportLogsAsCsv(job.logs, job.job_id); }} className={itemCls}>
 <FileSpreadsheet className={iconCls} />
 <span className="flex-1">לוגים</span>
 <span className={extCls}>.csv</span>
 </button>
 </>
 )}
 </motion.div>
 );
 })()}
 </AnimatePresence>
 </div>
 </div>
 </FadeIn>
 )}

 {/* ── Tabbed sections ── */}
 {isTerminal && (
 <Tabs defaultValue={initialTab} dir="rtl">
 <TabsList variant="line" className="border-b border-border/50 pb-0 gap-0">
 <TabsTrigger value="overview" className="relative px-4 py-2.5 rounded-none border-b-2 border-transparent data-[state=active]:border-transparent data-[state=active]:border-b-primary data-[state=active]:text-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none transition-all duration-200">
 <TrendingUp className="size-3.5"/>
 סקירה
 </TabsTrigger>
 {serveInfo && <TabsTrigger value="playground" className="relative px-4 py-2.5 rounded-none border-b-2 border-transparent data-[state=active]:border-transparent data-[state=active]:border-b-primary data-[state=active]:text-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none transition-all duration-200">
 <Send className="size-3.5"/>
 שימוש
 </TabsTrigger>}
 <TabsTrigger value="code" className="relative px-4 py-2.5 rounded-none border-b-2 border-transparent data-[state=active]:border-transparent data-[state=active]:border-b-primary data-[state=active]:text-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none transition-all duration-200">
 <Code className="size-3.5"/>
 קוד
 </TabsTrigger>
 <TabsTrigger value="logs" className="relative px-4 py-2.5 rounded-none border-b-2 border-transparent data-[state=active]:border-transparent data-[state=active]:border-b-primary data-[state=active]:text-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none transition-all duration-200">
 <Terminal className="size-3.5"/>
 לוגים
 </TabsTrigger>
 <TabsTrigger value="config" className="relative px-4 py-2.5 rounded-none border-b-2 border-transparent data-[state=active]:border-transparent data-[state=active]:border-b-primary data-[state=active]:text-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none transition-all duration-200">
 <Clock className="size-3.5"/>
 הגדרות
 </TabsTrigger>
 </TabsList>

 {/* ── Overview tab ── */}
 <TabsContent value="overview" className="space-y-6 mt-4">
 <FadeIn>
 <p className="text-sm text-muted-foreground">
 {job.status === "cancelled" ? "האופטימיזציה בוטלה — להלן מצב התהליך בעת הביטול." : job.status === "failed" ? "האופטימיזציה נכשלה." : "תוצאות האופטימיזציה, ציונים ומטריקות ביצוע."}
 </p>
 </FadeIn>

 {/* ── Completed pipeline timeline ── */}
 <FadeIn delay={0.05}>
 {(() => {
 const completedStageIdx = job.status === "success" ? PIPELINE_STAGES.length : detectStage(job) === "done" ? PIPELINE_STAGES.length : PIPELINE_STAGES.findIndex((s) => s.key === detectStage(job));
 const eventToStage: Record<string, PipelineStage> = {
 "validation_passed": "validating",
 "dataset_splits_ready": "splitting",
 "baseline_evaluated": "baseline",
 "optimized_evaluated": "optimizing",
 };
 const stageTs: Partial<Record<PipelineStage, string>> = {};
 for (const ev of (job.progress_events ?? [])) {
 const sk = ev.event ? eventToStage[ev.event] : undefined;
 if (sk && ev.timestamp) {
 stageTs[sk] = new Date(ev.timestamp).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
 }
 }
 if (job.started_at && !stageTs.validating) {
 stageTs.validating = new Date(job.started_at).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
 }
 if (job.completed_at) {
 stageTs.evaluating = new Date(job.completed_at).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
 }
 const isFailed = job.status === "failed" || job.status === "cancelled";
 return (
 <div className="flex items-center gap-0" dir="rtl">
 {PIPELINE_STAGES.map((s, i) => {
 const isDone = i < completedStageIdx;
 const isStopped = isFailed && i === completedStageIdx;
 const isPending = i > completedStageIdx;
 const lineAfter = i < PIPELINE_STAGES.length - 1;
 const nextDone = (i + 1) < completedStageIdx;
 const ts = stageTs[s.key];
 return (
 <Fragment key={s.key}>
 <div className="flex flex-col items-center shrink-0 gap-0.5">
 <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-full whitespace-nowrap text-xs ${
 isStopped ? "text-destructive bg-destructive/10 ring-1 ring-destructive/20 font-semibold"
 : isDone ? "text-primary"
 : "text-muted-foreground/40"
 }`}>
 {isDone ? (
 <CheckCircle2 className="size-3.5 shrink-0"/>
 ) : isStopped ? (
 <XCircle className="size-3.5 shrink-0"/>
 ) : (
 <Circle className="size-3.5 shrink-0"/>
 )}
 {s.label}
 </div>
 {ts && isDone && <span className="text-[9px] text-muted-foreground tabular-nums" dir="ltr">{ts}</span>}
 </div>
 {lineAfter && <div className={`flex-1 h-px min-w-3 ${nextDone ? "bg-primary" : isStopped || (isDone && i + 1 === completedStageIdx) ? "bg-destructive/30" : "bg-border"}`} />}
 </Fragment>
 );
 })}
 </div>
 );
 })()}
 </FadeIn>

 {/* ── 3. Results ── */}
 {job.status ==="success"&& job.job_type ==="run"&& job.result && (
 <StaggerContainer className="grid grid-cols-1 sm:grid-cols-3 gap-4">
 <StaggerItem>
 <TiltCard className=" rounded-xl border border-border/50 bg-card p-6 text-center">
 <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide">ציון התחלתי</p>
 <p className="text-3xl font-mono font-bold">
 {formatPercent(job.result.baseline_test_metric)}
 </p>
 </TiltCard>
 </StaggerItem>
 <StaggerItem>
 <TiltCard className="rounded-xl border border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10 p-6 text-center shadow-[0_0_20px_rgba(var(--primary),0.08)]">
 <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide">ציון משופר</p>
 <p className="text-3xl font-mono font-bold text-primary">
 {formatPercent(job.result.optimized_test_metric)}
 </p>
 </TiltCard>
 </StaggerItem>
 <StaggerItem>
 <TiltCard className={`rounded-xl border p-6 text-center ${(job.result.metric_improvement ?? 0) >= 0 ? "border-stone-400/50 bg-gradient-to-br from-stone-100/50 to-stone-200/30" : "border-red-300/50 bg-gradient-to-br from-red-50/50 to-red-100/30"}`}>
 <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide">שיפור</p>
 <p className={`text-3xl font-mono font-bold ${(job.result.metric_improvement ?? 0) >= 0 ? "text-stone-600" : "text-red-600"}`}>
 {formatImprovement(job.result.metric_improvement)}
 </p>
 </TiltCard>
 </StaggerItem>
 </StaggerContainer>
 )}

 {job.status ==="success"&& job.job_type ==="grid_search"&& job.grid_result && (
 <Card>
 <CardHeader>
 <CardTitle className="flex items-center gap-2 text-base">
 <TrendingUp className="size-4"/>
 תוצאות
 </CardTitle>
 </CardHeader>
 <CardContent className="overflow-x-auto">
 <Table>
 <TableHeader>
 <TableRow>
 <TableHead>#</TableHead>
 <TableHead>מודל יצירה</TableHead>
 <TableHead>מודל רפלקציה</TableHead>
 <TableHead>ציון התחלתי</TableHead>
 <TableHead>ציון משופר</TableHead>
 <TableHead>שיפור</TableHead>
 <TableHead>סטטוס</TableHead>
 </TableRow>
 </TableHeader>
 <TableBody>
 {job.grid_result.pair_results.map((pr) => {
 const isBest =
 job.grid_result!.best_pair?.pair_index === pr.pair_index;
 return (
 <TableRow
 key={pr.pair_index}
 className={isBest ?"bg-primary/5 font-medium":""}
 >
 <TableCell className="font-mono">
 {pr.pair_index}
 {isBest && (
 <Badge variant="default" className="ms-2 text-[10px]">
 מנצח
 </Badge>
 )}
 </TableCell>
 <TableCell className="font-mono text-xs">
 {pr.generation_model}
 </TableCell>
 <TableCell className="font-mono text-xs">
 {pr.reflection_model}
 </TableCell>
 <TableCell className="font-mono">
 {formatPercent(pr.baseline_test_metric)}
 </TableCell>
 <TableCell className="font-mono">
 {formatPercent(pr.optimized_test_metric)}
 </TableCell>
 <TableCell
 className={`font-mono ${
 (pr.metric_improvement ?? 0) >= 0
 ?"text-stone-500":"text-red-500"}`}
 >
 {formatImprovement(pr.metric_improvement)}
 </TableCell>
 <TableCell>
 {pr.error ? (
 <Badge variant="destructive">שגיאה</Badge>
 ) : (
 <Badge variant="outline" className="bg-stone-500/10 text-stone-600 border-stone-500/30">
 הושלם
 </Badge>
 )}
 </TableCell>
 </TableRow>
 );
 })}
 </TableBody>
 </Table>
 </CardContent>
 </Card>
 )}

 {/* Score progression chart */}
 {scorePoints.length > 1 && (
 <Card>
 <CardHeader className="pb-2">
 <CardTitle className="text-base font-medium">מהלך הציונים</CardTitle>
 </CardHeader>
 <CardContent className="pt-0">
 <div className="h-[300px]" dir="ltr">
 <ResponsiveContainer width="100%" height="100%">
 <LineChart data={scorePoints} margin={{ top: 20, right: 20, left: 10, bottom: 20 }}>
 <CartesianGrid strokeDasharray="3 3" className="stroke-muted"vertical={false} />
 <XAxis
 dataKey="trial"tickLine={false}
 axisLine={false}
 tick={{ fontSize: 11 }}
 className="fill-muted-foreground"label={{ value: "ניסיון", position: "insideBottom", offset: -10, fontSize: 11 }}
 />
 <YAxis
 tickLine={false}
 axisLine={false}
 tick={{ fontSize: 11 }}
 className="fill-muted-foreground"domain={[0,"auto"]}
 label={{ value: "ציון", angle: -90, position: "insideLeft", offset: 0, fontSize: 11 }}
 />
 <Tooltip content={<ScoreChartTooltip />} />
 <Line
 type="monotone"dataKey="score" name="ציון הניסיון"stroke="var(--color-chart-4)"strokeWidth={1.5}
 dot={{ r: 3, fill: "var(--color-chart-4)"}}
 isAnimationActive={false}
 />
 <Line
 type="stepAfter"dataKey="best" name="השיא עד כה"stroke="var(--color-chart-2)"strokeWidth={2}
 dot={false}
 strokeDasharray="none"isAnimationActive={false}
 />
 </LineChart>
 </ResponsiveContainer>
 </div>
 <div className="flex flex-wrap justify-center gap-x-5 gap-y-1 mt-2">
 <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
 <span className="inline-block w-3 h-0.5 rounded-full" style={{ backgroundColor: "var(--color-chart-4)"}} />
 <span>הציון של הניסיון הנוכחי</span>
 </div>
 <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
 <span className="inline-block w-3 h-[2px] rounded-full" style={{ backgroundColor: "var(--color-chart-2)"}} />
 <span>הציון הגבוה ביותר עד כה</span>
 </div>
 </div>
 </CardContent>
 </Card>
 )}

 </TabsContent>

 {/* ── Playground tab ── */}
 {serveInfo && (
 <TabsContent value="playground" className="space-y-4 mt-4">
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
 {/* Chat-style interface */}
 <div className="flex flex-col max-h-[560px] pt-2">
 {/* Message history */}
 <div ref={chatScrollRef} className="flex-1 overflow-y-auto pb-4 space-y-6">
 {runHistory.length === 0 && !streamingRun && (
 <div className="flex flex-col items-center justify-center py-16 gap-5 text-center">
 <div className="size-12 rounded-2xl bg-[#3D2E22]/8 flex items-center justify-center">
  <MessageSquare className="size-5 text-[#3D2E22]/35" />
 </div>
 <div className="space-y-2">
  <p className="text-sm font-medium text-foreground/60">הרצת התוכנית המאומנת</p>
  <p className="text-xs text-muted-foreground/50 max-w-xs leading-relaxed">
  הזן ערכים בשדות הקלט למטה ולחץ על כפתור השליחה.
  </p>
 </div>
 {/* Starter cards from demos */}
 {(() => {
  const demos = job?.result?.program_artifact?.optimized_prompt?.demos
  ?? job?.grid_result?.best_pair?.program_artifact?.optimized_prompt?.demos
  ?? [];
  if (demos.length === 0) return null;
  return (
  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-md w-full mt-2">
  {demos.slice(0, 4).map((demo, i) => (
   <button
   key={i}
   onClick={() => {
    const filled: Record<string, string> = {};
    for (const f of serveInfo.input_fields) filled[f] = String(demo.inputs[f] ?? "");
    setServeInputs(filled);
   }}
   className="text-right p-3 rounded-xl border border-[#DDD4C8]/60 hover:border-[#C8A882]/60 bg-muted/10 hover:bg-muted/20 transition-all group"
   dir="auto"
   >
   <div className="text-[10px] font-medium text-[#3D2E22]/50 mb-1">דוגמה {i + 1}</div>
   <div className="text-xs text-foreground/70 line-clamp-2 font-mono" dir="ltr">
    {Object.entries(demo.inputs).map(([k, v]) => `${k}: ${String(v)}`).join(", ").slice(0, 80)}
    {Object.entries(demo.inputs).map(([k, v]) => `${k}: ${String(v)}`).join(", ").length > 80 ? "..." : ""}
   </div>
   </button>
  ))}
  </div>
  );
 })()}
 </div>
 )}
 {[...runHistory].reverse().map((run) => {
 const isEditing = editingRunTs === run.ts;
 return (
 <div key={run.ts} className="space-y-3">
  {/* User message */}
  {isEditing ? (
  <div className="flex justify-start">
   <div className="max-w-[85%] w-full space-y-2">
   {serveInfo.input_fields.map((field) => (
    <div key={field}>
    {serveInfo.input_fields.length > 1 && (
     <label className="text-[10px] text-muted-foreground/50 font-mono px-1 mb-0.5 block" dir="ltr">{field}</label>
    )}
    <textarea
     ref={(el) => {
     if (el && editInputs[field]) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 120) + "px";
     }
     }}
     dir="auto"
     value={editInputs[field] ?? ""}
     onChange={(e) => {
     const val = e.target.value;
     e.target.style.height = "auto";
     e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
     startTransition(() => {
     setEditInputs((prev) => ({ ...prev, [field]: val }));
     });
     }}
     className="w-full bg-white border border-[#DDD4C8] rounded-xl px-3 py-2 text-sm font-mono resize-none outline-none focus:border-[#C8A882] transition-colors min-h-[40px] max-h-[120px]"
     rows={1}
     autoFocus={serveInfo.input_fields[0] === field}
    />
    </div>
   ))}
   <div className="flex justify-start gap-1.5">
    <button onClick={() => setEditingRunTs(null)} className="text-[11px] text-muted-foreground hover:text-foreground px-3 py-1 rounded-lg hover:bg-muted transition-colors">
    ביטול
    </button>
    <button
    onClick={() => handleEditAndResend(run.ts)}
    disabled={serveInfo.input_fields.some((f) => !editInputs[f]?.trim())}
    className="text-[11px] text-white bg-[#3D2E22] hover:bg-[#3D2E22]/90 disabled:opacity-40 px-3 py-1 rounded-lg transition-colors"
    >
    שלח
    </button>
   </div>
   </div>
  </div>
  ) : (
  <div className="flex justify-start group/user">
   <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-[#3D2E22] text-[#FAF8F5] px-4 py-3 text-sm shadow-sm" dir="ltr">
   {serveInfo.input_fields.map((k, i, arr) => (
    <div key={k} className="font-mono leading-relaxed">
    <span className="text-[#C8A882] text-xs">{k}: </span>
    <span className="whitespace-pre-wrap break-words">{run.inputs[k] ?? ""}</span>
    {i < arr.length - 1 && arr.length > 1 && <div className="h-px bg-white/10 my-1.5" />}
    </div>
   ))}
   </div>
   {!serveLoading && (
   <button
    onClick={() => {
    setEditingRunTs(run.ts);
    setEditInputs({ ...run.inputs });
    }}
    className="self-center ms-1.5 opacity-0 group-hover/user:opacity-100 transition-opacity p-1.5 rounded-lg hover:bg-muted/60"
    title="ערוך ושלח שוב"
   >
    <Pencil className="size-3 text-muted-foreground" />
   </button>
   )}
  </div>
  )}
  {/* AI response */}
  {!isEditing && (
  <div className="px-1" dir="ltr">
   {serveInfo.output_fields.map((k, i, arr) => (
   <div key={k} className={`font-mono text-sm leading-relaxed ${arr.length > 1 ? "mb-1" : ""}`}>
    <span className="text-muted-foreground text-xs">{k}: </span>
    <span className="whitespace-pre-wrap break-words">{formatOutput(run.outputs[k])}</span>
   </div>
   ))}
   {/* Action bar */}
   <div className="flex items-center gap-0.5 mt-1 -ms-1">
   <CopyButton text={serveInfo.output_fields.map((k) => `${k}: ${formatOutput(run.outputs[k])}`).join("\n")} />
   <span className="text-[9px] text-muted-foreground/30 ms-1 font-mono" dir="ltr">{run.model}</span>
   </div>
  </div>
  )}
 </div>
 );
 })}
 {/* Streaming run (live) */}
 {streamingRun && (
 <div className="space-y-3">
 <div className="flex justify-start">
 <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-[#3D2E22] text-[#FAF8F5] px-4 py-3 text-sm shadow-sm" dir="ltr">
  {serveInfo.input_fields.map((k, i, arr) => (
  <div key={k} className="font-mono leading-relaxed">
   <span className="text-[#C8A882] text-xs">{k}: </span>
   <span className="whitespace-pre-wrap break-words">{streamingRun.inputs[k] ?? ""}</span>
   {i < arr.length - 1 && arr.length > 1 && <div className="h-px bg-white/10 my-1.5" />}
  </div>
  ))}
 </div>
 </div>
 <div className="px-1" dir="ltr">
 {Object.keys(streamingRun.partial).length === 0 ? (
  <div className="flex items-center gap-1.5 py-2">
  <span className="w-1.5 h-1.5 rounded-full bg-[#3D2E22]/30 animate-bounce" />
  <span className="w-1.5 h-1.5 rounded-full bg-[#3D2E22]/30 animate-bounce" style={{ animationDelay: "150ms" }} />
  <span className="w-1.5 h-1.5 rounded-full bg-[#3D2E22]/30 animate-bounce" style={{ animationDelay: "300ms" }} />
  <span className="text-xs text-muted-foreground/40">חושב</span>
  </div>
 ) : (
  serveInfo.output_fields.map((k, i, arr) => (
  <div key={k} className={`font-mono text-sm leading-relaxed ${arr.length > 1 ? "mb-1" : ""}`}>
   <span className="text-muted-foreground text-xs">{k}: </span>
   <span className="whitespace-pre-wrap break-words">{streamingRun.partial[k] ?? ""}</span>
   {streamingRun.partial[k] && <span className="inline-block w-1 h-3 bg-foreground/40 ms-0.5 animate-pulse" />}
  </div>
  ))
 )}
 </div>
 </div>
 )}
 </div>

 {/* Input bar — sticky bottom */}
 <div className="border-t border-border/40 pt-3">
 {/* Inline error */}
 {serveError && (
 <div className="flex items-center gap-1.5 text-xs text-red-600 bg-red-50 rounded-lg px-2.5 py-1.5 mb-2 max-w-2xl mx-auto">
  <XCircle className="size-3 shrink-0" />
  <span>{serveError}</span>
  <button onClick={() => setServeError(null)} className="ms-auto p-0.5 hover:bg-red-100 rounded">
  <span className="sr-only">סגור</span>×
  </button>
 </div>
 )}
 <form
 onSubmit={(e) => { e.preventDefault(); handleServe(); }}
 className="max-w-2xl mx-auto"
 >
 <div className={`flex gap-2 ${serveInfo.input_fields.length > 1 ? "items-center" : "items-start"}`}>
  <Button
  type="submit"
  size="icon"
  className="shrink-0 rounded-full !size-[42px]"
  disabled={serveLoading || serveInfo.input_fields.some((f) => !serveInputs[f]?.trim())}
  aria-label="שלח"
  >
  {serveLoading
  ? <Loader2 className="size-4 animate-spin" />
  : <svg viewBox="0 0 24 24" fill="currentColor" className="size-4"><path d="M12 2L12 22M12 2L5 9M12 2L19 9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none" /></svg>
  }
  </Button>
  <div className={`flex-1 ${serveInfo.input_fields.length > 1 ? "space-y-2" : "flex gap-2 items-start"}`}>
  {serveInfo.input_fields.map((field) => (
   <div key={field} className="flex-1 min-w-0">
   {serveInfo.input_fields.length > 1 && (
    <label htmlFor={`serve-${field}`} className="text-[10px] text-muted-foreground/50 font-mono px-3 mb-0.5 block" dir="ltr">{field}</label>
   )}
   <textarea
    id={`serve-${field}`}
    ref={(el) => {
    textareaRefs.current[field] = el;
    if (el && serveInputs[field]) {
     // Auto-resize prefilled content (e.g. from demo or retry)
     el.style.height = "auto";
     el.style.height = Math.min(el.scrollHeight, 120) + "px";
    }
    }}
    dir="auto"
    placeholder={field}
    value={serveInputs[field] ?? ""}
    onChange={(e) => {
    const val = e.target.value;
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
    startTransition(() => {
    setServeInputs((prev) => ({ ...prev, [field]: val }));
    if (serveError) setServeError(null);
    });
    }}
    onKeyDown={(e) => {
    if (e.key === "Enter" && !e.shiftKey) {
     e.preventDefault();
     if (!serveLoading && serveInfo.input_fields.every((f) => serveInputs[f]?.trim())) handleServe();
    }
    }}
    rows={1}
    className="block w-full bg-muted/20 rounded-2xl border border-[#DDD4C8] px-4 py-[11px] text-sm font-mono leading-[20px] outline-none ring-0 shadow-none resize-none overflow-hidden h-[42px] max-h-[120px] focus:outline-none focus-visible:outline-none focus-visible:ring-0 focus:border-[#C8A882] transition-colors placeholder:text-muted-foreground/40"
   />
   </div>
  ))}
  </div>
 </div>
 </form>
 </div>
 </div>

 {/* Endpoint + Code Snippets (merged) */}
 <Card>
 <CardHeader className="pb-2">
 <CardTitle className="text-sm">הרצה</CardTitle>
 </CardHeader>
 <CardContent className="space-y-4">
 <div className="space-y-1.5">
 <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Serve URL</p>
 <div className="rounded-lg bg-muted/40 p-2.5 pe-8 relative group" dir="ltr">
 <code className="text-xs font-mono break-all">POST {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/serve/{id}</code>
 <CopyButton text={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/serve/${id}`} className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100"/>
 </div>
 </div>

 <Separator />

 <div className="space-y-2">
 <p className="text-[10px] text-muted-foreground uppercase tracking-wider">קוד לשילוב</p>
 {(() => {
 const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
 const inputsJson = JSON.stringify({ inputs: Object.fromEntries(serveInfo.input_fields.map(f => [f, `<${f}>`])) });
 const snippets = {
  curl: `curl -X POST ${apiBase}/serve/${id} \\\n  -H "Content-Type: application/json" \\\n  -d '${inputsJson}'`,
  python: `import requests\n\nresponse = requests.post(\n    "${apiBase}/serve/${id}",\n    json={"inputs": {${serveInfo.input_fields.map(f => `"${f}": "<${f}>"`).join(", ")}}},\n)\nresult = response.json()\n${serveInfo.output_fields.map(f => `print(result["outputs"]["${f}"])`).join("\n")}`,
  dspy: `import dspy\nimport base64, pickle, requests\n\n# Load the optimized program from the service\nartifact = requests.get(\n    "${apiBase}/jobs/${id}/artifact"\n).json()\nprogram = pickle.loads(\n    base64.b64decode(artifact["program_artifact"]["program_pickle_base64"])\n)\n\n# Configure your LM\nlm = dspy.LM("gpt-4o-mini")\nwith dspy.context(lm=lm):\n    result = program(${serveInfo.input_fields.map(f => `${f}="<${f}>"`).join(", ")})\n${serveInfo.output_fields.map(f => `    print(result.${f})`).join("\n")}`,
 } as const;
 const labels = { curl: "cURL", python: "Python", dspy: "DSPy" } as const;
 return (
 <AnimatePresence mode="wait" initial={false}>
 <motion.div
 key={codeTab}
 initial={{ opacity: 0, y: -5 }}
 animate={{ opacity: 1, y: 0 }}
 exit={{ opacity: 0, y: -5 }}
 transition={{ duration: 0.15 }}
 >
 <CodeEditor
  value={snippets[codeTab]}
  onChange={() => {}}
  height={`${(snippets[codeTab].split("\n").length + 1) * 19.6 + 8}px`}
  readOnly
  label={<LangPicker value={codeTab} onChange={setCodeTab} labels={labels} />}
 />
 </motion.div>
 </AnimatePresence>
 );
 })()}
 </div>
 </CardContent>
 </Card>
 </TabsContent>
 )}

 {/* ── Code tab ── */}
 <TabsContent value="code" className="space-y-6 mt-4">
 <FadeIn>
 <p className="text-sm text-muted-foreground">קוד המקור של החתימה, המטריקה, והפרומפט המאומן.</p>
 </FadeIn>
 {(signatureCode || metricCode) && (
 <Card>
 <CardHeader>
 <CardTitle className="flex items-center gap-2 text-base">
 <Code className="size-4"/>
 קוד
 </CardTitle>
 </CardHeader>
 <CardContent>
 <Tabs defaultValue={signatureCode ?"signature":"metric"} dir="ltr">
 <TabsList>
 {signatureCode && <TabsTrigger value="signature">חתימה (Signature)</TabsTrigger>}
 {metricCode && <TabsTrigger value="metric">מטריקה (Metric)</TabsTrigger>}
 </TabsList>
 {signatureCode && (
 <TabsContent value="signature">
 <CodeEditor value={signatureCode} onChange={() => {}} height={`${(signatureCode.split("\n").length + 1) * 19.6 + 8}px`} readOnly />
 </TabsContent>
 )}
 {metricCode && (
 <TabsContent value="metric">
 <CodeEditor value={metricCode} onChange={() => {}} height={`${(metricCode.split("\n").length + 1) * 19.6 + 8}px`} readOnly />
 </TabsContent>
 )}
 </Tabs>
 </CardContent>
 </Card>
 )}

 {optimizedPrompt && (
 <Card>
 <CardHeader>
 <CardTitle className="text-base flex items-center gap-2"><Sparkles className="size-4" />פרומפטים מאופטמים</CardTitle>
 </CardHeader>
 <CardContent>
 <div className="relative group">
 <pre className="text-sm font-mono bg-muted/50 rounded-lg p-4 pe-10 overflow-x-auto whitespace-pre-wrap leading-relaxed" dir="ltr">{optimizedPrompt.formatted_prompt}</pre>
 <CopyButton text={optimizedPrompt.formatted_prompt} className="absolute top-2 right-2 opacity-0 group-hover:opacity-100"/>
 </div>
 {optimizedPrompt.demos && optimizedPrompt.demos.length > 0 && (
 <div className="mt-4 pt-4 border-t border-border">
 <p className="text-xs text-muted-foreground mb-2">{optimizedPrompt.demos.length} דוגמאות מובנות</p>
 <div className="space-y-2">
 {optimizedPrompt.demos.map((demo, i) => (
 <div key={i} className="text-xs font-mono bg-muted/50 rounded-lg p-3" dir="ltr">
 {Object.entries(demo.inputs).map(([k, v]) => (
 <div key={k}><span className="text-muted-foreground">{k}:</span> {String(v)}</div>
 ))}
 {Object.entries(demo.outputs).map(([k, v]) => (
 <div key={k}><span className="text-stone-600">{k}:</span> {String(v)}</div>
 ))}
 </div>
 ))}
 </div>
 </div>
 )}
 </CardContent>
 </Card>
 )}
 </TabsContent>

 {/* ── Logs tab ── */}
 <TabsContent value="logs">
 <div className="space-y-3 mt-4">
 <FadeIn>
 <div className="flex items-center justify-between gap-3">
 <p className="text-sm text-muted-foreground">לוגים מפורטים מתהליך האופטימיזציה — סננו לפי עמודה או חפשו בתוכן.</p>
 <span className="text-xs text-muted-foreground shrink-0">{filteredLogs.length} רשומות</span>
 </div>
 </FadeIn>
 <Input
 type="text"
 value={logMessageSearch}
 onChange={(e) => setLogMessageSearch(e.target.value)}
 placeholder="חיפוש בתוכן ההודעות..."
 aria-label="חיפוש בתוכן ההודעות"
 dir="rtl"
 className="text-right max-w-md"
 />

 {filteredLogs.length === 0 ? (
 <p className="text-sm text-muted-foreground py-8 text-center">אין לוגים</p>
 ) : (
 <Card>
 <CardContent className="p-0">
 <div className="max-h-[600px] overflow-auto">
 <Table>
 <TableHeader>
 <TableRow>
 <ColumnHeader label="זמן" sortKey="timestamp" currentSort={logSortKey} sortDir={logSortDir} onSort={toggleLogSort} filterCol="timestamp" filterOptions={logFilterOptions.timestamp} filters={logFilters.filters} onFilter={logFilters.setColumnFilter} openFilter={logFilters.openFilter} setOpenFilter={logFilters.setOpenFilter} />
 <ColumnHeader label="רמה" sortKey="level" currentSort={logSortKey} sortDir={logSortDir} onSort={toggleLogSort} filterCol="level" filterOptions={logFilterOptions.level} filters={logFilters.filters} onFilter={logFilters.setColumnFilter} openFilter={logFilters.openFilter} setOpenFilter={logFilters.setOpenFilter} />
 <ColumnHeader label="לוגר" sortKey="logger" currentSort={logSortKey} sortDir={logSortDir} onSort={toggleLogSort} filterCol="logger" filterOptions={logFilterOptions.logger} filters={logFilters.filters} onFilter={logFilters.setColumnFilter} openFilter={logFilters.openFilter} setOpenFilter={logFilters.setOpenFilter} />
 <ColumnHeader label="הודעה" sortKey="message" currentSort={logSortKey} sortDir={logSortDir} onSort={toggleLogSort} />
 </TableRow>
 </TableHeader>
 <TableBody>
 {filteredLogs.map((log, i) => (
 <TableRow
 key={i}
 className="cursor-pointer transition-all duration-150"
 onClick={() => { navigator.clipboard.writeText(log.message); toast.success("הועתק", { autoClose: 1500 }); }}
 style={{ animation: `fadeSlideIn 0.2s ease-out ${Math.min(i, 20) * 0.02}s both` }}
 >
 <TableCell className="text-xs font-mono text-muted-foreground whitespace-nowrap" dir="ltr">{formatLogTimestamp(log.timestamp)}</TableCell>
 <TableCell>
 <Badge variant={
 log.level ==="ERROR"?"destructive":
 log.level ==="WARNING"?"outline":"secondary"} className="text-[10px] font-mono">
 {log.level}
 </Badge>
 </TableCell>
 <TableCell className="text-xs font-mono text-muted-foreground truncate max-w-[120px]">{log.logger}</TableCell>
 <TableCell className="text-xs font-mono whitespace-pre-wrap break-all">{log.message}</TableCell>
 </TableRow>
 ))}
 </TableBody>
 </Table>
 </div>
 </CardContent>
 </Card>
 )}
 </div>
 </TabsContent>

 {/* ── Config tab ── */}
 <TabsContent value="config" className="mt-4">
 <FadeIn>
 <p className="text-sm text-muted-foreground mb-4">פרטי ההגדרות שנבחרו לאופטימיזציה זו — מודל, אופטימייזר, ופרמטרים.</p>
 </FadeIn>
 <Card className="relative overflow-hidden shadow-[0_1px_3px_rgba(28,22,18,0.04),inset_0_1px_0_rgba(255,255,255,0.5)]">
 {/* Top-edge highlight */}
 <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-l from-transparent via-[#C8A882]/40 to-transparent" aria-hidden="true" />

 <CardHeader>
 <CardTitle className="text-base flex items-center gap-2">
 <Clock className="size-4 text-[#7C6350]" aria-hidden="true" />
 <span className="font-bold tracking-tight">הגדרות</span>
 </CardTitle>
 </CardHeader>
 <CardContent>
 <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5">
 <InfoCard
 label="מודול"
 value={job.module_name}
 icon={<Component className="size-3.5" />}
 />
 <InfoCard
 label="אופטימייזר"
 value={job.optimizer_name}
 icon={<Target className="size-3.5" />}
 />
 <InfoCard
 label="מודל"
 value={
 job.model_name ? (
 <span>
 {job.model_name}
 {job.model_settings && (
 <span className="text-[#3D2E22]/50 text-[10px] block mt-0.5">
 {job.model_settings.temperature != null && `temp: ${String(job.model_settings.temperature)}`}
 {job.model_settings.max_tokens ? ` · max: ${String(job.model_settings.max_tokens)}` : null}
 </span>
 )}
 </span>
 ) : job.job_type ==="grid_search"? (
 <span className="text-xs">{job.total_pairs} זוגות</span>
 ) : undefined
 }
 icon={<Cpu className="size-3.5" />}
 />
 {job.reflection_model_name && (
 <InfoCard
 label="מודל רפלקציה"
 value={job.reflection_model_name}
 icon={<Lightbulb className="size-3.5" />}
 />
 )}
 {job.prompt_model_name && (
 <InfoCard
 label="מודל Prompt"
 value={job.prompt_model_name}
 icon={<Quote className="size-3.5" />}
 />
 )}
 {job.task_model_name && (
 <InfoCard
 label="מודל Task"
 value={job.task_model_name}
 icon={<ListTodo className="size-3.5" />}
 />
 )}
 <InfoCard
 label="שם משתמש"
 value={job.username}
 icon={<User className="size-3.5" />}
 />
 <InfoCard
 label="שורות נתונים"
 value={job.dataset_rows}
 icon={<Database className="size-3.5" />}
 />
 <InfoCard
 label="חלוקת נתונים"
 value={(() => {
 const s = job.split_fractions ?? { train: 0.7, val: 0.15, test: 0.15 };
 return (
 <span className="inline-flex items-baseline gap-1">
 <span className="tabular-nums" dir="ltr">{s.train}</span>
 <span className="text-[10px] font-medium text-[#A89680]">אימון</span>
 <span className="text-[#BFB3A3] mx-0.5">·</span>
 <span className="tabular-nums" dir="ltr">{s.val}</span>
 <span className="text-[10px] font-medium text-[#A89680]">ולידציה</span>
 <span className="text-[#BFB3A3] mx-0.5">·</span>
 <span className="tabular-nums" dir="ltr">{s.test}</span>
 <span className="text-[10px] font-medium text-[#A89680]">מבחן</span>
 </span>
 );
 })()}
 icon={<PieChart className="size-3.5" />}
 />
 <InfoCard
 label="ערבוב"
 value={job.shuffle != null ? (job.shuffle ? "כן" : "לא") : "כן"}
 icon={<Shuffle className="size-3.5" />}
 />
 {job.seed != null && (
 <InfoCard
 label="seed"
 value={job.seed}
 icon={<Dices className="size-3.5" />}
 />
 )}
 </div>
 {(job.optimizer_kwargs || job.compile_kwargs) && (
 <>
 <Separator className="my-4"/>
 <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
 {job.optimizer_kwargs && (
 <div>
 <p className="text-xs text-muted-foreground mb-1">פרמטרי אופטימייזר</p>
 <pre className="text-xs font-mono bg-muted/50 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">{jsonPreview(job.optimizer_kwargs)}</pre>
 </div>
 )}
 {job.compile_kwargs && (
 <div>
 <p className="text-xs text-muted-foreground mb-1">פרמטרי קומפילציה</p>
 <pre className="text-xs font-mono bg-muted/50 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">{jsonPreview(job.compile_kwargs)}</pre>
 </div>
 )}
 </div>
 </>
 )}
 {job.job_type ==="grid_search"&& job.generation_models && job.reflection_models && (
 <>
 <Separator className="my-4"/>
 <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
 <div>
 <p className="text-xs text-muted-foreground mb-2">מודלי יצירה</p>
 <div className="space-y-1.5">
 {job.generation_models.map((m, i) => (
 <div key={i} className="rounded-lg border border-border/50 bg-muted/30 px-3 py-2">
 <p className="text-sm font-mono font-medium">{m.name}</p>
 {(m.temperature != null || m.max_tokens != null) && (
 <p className="text-[10px] text-muted-foreground">
 {m.temperature != null && `temperature: ${m.temperature}`}
 {m.max_tokens ? ` · max=${m.max_tokens}` :""}
 </p>
 )}
 </div>
 ))}
 </div>
 </div>
 <div>
 <p className="text-xs text-muted-foreground mb-2">מודלי רפלקציה</p>
 <div className="space-y-1.5">
 {job.reflection_models.map((m, i) => (
 <div key={i} className="rounded-lg border border-border/50 bg-muted/30 px-3 py-2">
 <p className="text-sm font-mono font-medium">{m.name}</p>
 {(m.temperature != null || m.max_tokens != null) && (
 <p className="text-[10px] text-muted-foreground">
 {m.temperature != null && `temperature: ${m.temperature}`}
 {m.max_tokens ? ` · max=${m.max_tokens}` :""}
 </p>
 )}
 </div>
 ))}
 </div>
 </div>
 </div>
 </>
 )}
 </CardContent>
 </Card>
 </TabsContent>

 </Tabs>
 )}

 {/* Delete confirmation dialog */}
 <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
 <DialogContent className="max-w-sm">
 <DialogHeader>
 <DialogTitle>מחיקת אופטימיזציה</DialogTitle>
 <DialogDescription>
 האם למחוק את האופטימיזציה{""}
 <span className="font-mono font-medium text-foreground break-all">{job.job_id}</span>
 ?
 </DialogDescription>
 </DialogHeader>
 <DialogFooter className="gap-2 sm:gap-0">
 <Button variant="outline" onClick={() => setShowDeleteDialog(false)} disabled={deleteLoading}>
 ביטול
 </Button>
 <Button variant="destructive" onClick={handleDelete} disabled={deleteLoading}>
 {deleteLoading ? <Loader2 className="size-4 me-2 animate-spin"/> : <Trash2 className="size-4 me-2"/>}
 מחיקה
 </Button>
 </DialogFooter>
 </DialogContent>
 </Dialog>
 </div>
 );
}
