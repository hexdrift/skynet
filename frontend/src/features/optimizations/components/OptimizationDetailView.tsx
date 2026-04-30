"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  XCircle,
  Trash2,
  Clock,
  Code,
  Terminal,
  TrendingUp,
  ChevronLeft,
  Timer,
  Send,
  CopyPlus,
  Database,
  Settings,
} from "lucide-react";
import { toast } from "react-toastify";

import { Button } from "@/shared/ui/primitives/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/primitives/card";
import { Badge } from "@/shared/ui/primitives/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/primitives/tabs";
import { Separator } from "@/shared/ui/primitives/separator";
import { FadeIn } from "@/shared/ui/motion";
import {
  Tooltip as UiTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/ui/primitives/tooltip";
import {
  getJob,
  cancelJob,
  getOptimizationPayload,
  getServeInfo,
  getPairServeInfo,
  serveProgramStream,
  servePairProgramStream,
} from "@/shared/lib/api";
import type { ServeInfoResponse } from "@/shared/types/api";
import {
  DEMO_OPTIMIZATION_ID,
  DEMO_GRID_OPTIMIZATION_ID,
  buildGridDemoJob,
  startDemoSimulation,
} from "@/features/tutorial";
import { Skeleton } from "boneyard-js/react";
import { optimizationDetailBones } from "../lib/bones";
import { formatMsg, msg } from "@/shared/lib/messages";
import { tip } from "@/shared/lib/tooltips";
import { TERMS } from "@/shared/lib/terms";
import { getRuntimeEnv } from "@/shared/lib/runtime-env";
import { ACTIVE_STATUSES, TERMINAL_STATUSES } from "@/shared/constants/job-status";
import { registerTutorialHook } from "@/features/tutorial";
import { HelpTip } from "@/shared/ui/help-tip";
import type { OptimizationStatusResponse, OptimizationPayloadResponse } from "@/shared/types/api";
import type { PipelineStage } from "../constants";
import { extractScoresFromLogs } from "../lib/extract-scores";
import { reconstructGridResult } from "../lib/reconstruct-grid";
import { DataTab } from "./DataTab";
import { LogsTab } from "./LogsTab";
import { ExportMenu } from "./ExportMenu";
import { DeleteJobDialog } from "./DeleteJobDialog";
import { StatusBadge, CopyButton } from "./ui-primitives";
import { ServeCodeSnippets } from "./ServeCodeSnippets";
import { ServeChat } from "./ServeChat";
import { ConfigTab } from "./ConfigTab";
import { CodeTab } from "./CodeTab";
import { StageInfoModal } from "./StageInfoModal";
import { PairDetailView } from "./PairDetailView";
import { OverviewTab } from "./OverviewTab";
import { GridServeTab } from "./GridServeTab";

const URL_RE = /https?:\/\/[^\s<>"]+/g;
const URL_TRAILING_RE = /[.,;:!?)\]}'"]+$/;

/**
 * Linkify URLs inside a string, keeping trailing sentence punctuation
 * (`.`, `,`, `)`, `]`, …) outside the anchor href so links like
 * `https://example.com).` don't render with a broken trailing `).`
 * inside the underline.
 */
function linkifyMessage(text: string, anchorClass: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let lastIdx = 0;
  let key = 0;
  for (const m of text.matchAll(URL_RE)) {
    const matchIdx = m.index ?? 0;
    if (matchIdx > lastIdx) nodes.push(text.slice(lastIdx, matchIdx));
    const raw = m[0];
    const trailingMatch = URL_TRAILING_RE.exec(raw);
    const trailing = trailingMatch ? trailingMatch[0] : "";
    const url = trailing ? raw.slice(0, raw.length - trailing.length) : raw;
    nodes.push(
      <a key={key++} href={url} target="_blank" rel="noopener noreferrer" className={anchorClass}>
        {url}
      </a>,
    );
    if (trailing) nodes.push(trailing);
    lastIdx = matchIdx + raw.length;
  }
  if (lastIdx < text.length) nodes.push(text.slice(lastIdx));
  return nodes;
}

export function OptimizationDetailView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialTab = searchParams.get("tab") ?? "overview";
  const [detailTab, setDetailTab] = useState(initialTab);
  // Expose for tutorial via the typed bridge (features/tutorial/lib/bridge.ts).
  useEffect(() => registerTutorialHook("setDetailTab", setDetailTab), []);

  const isDemoMode = id === DEMO_OPTIMIZATION_ID;
  const isGridDemoMode = id === DEMO_GRID_OPTIMIZATION_ID;
  const isAnyDemoMode = isDemoMode || isGridDemoMode;

  const [job, setJob] = useState<OptimizationStatusResponse | null>(null);
  const [payload, setPayload] = useState<OptimizationPayloadResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isDemoMode) return;
    return startDemoSimulation({ setJob: (fn) => setJob(fn), setLoading });
  }, [isDemoMode]);

  useEffect(() => {
    if (!isGridDemoMode) return;
    setJob(buildGridDemoJob());
    setLoading(false);
  }, [isGridDemoMode]);

  const [serveInfo, setServeInfo] = useState<ServeInfoResponse | null>(null);
  const [serveLoading, setServeLoading] = useState(false);
  const [runHistory, setRunHistory] = useState<
    Array<{
      inputs: Record<string, string>;
      outputs: Record<string, unknown>;
      model: string;
      ts: number;
    }>
  >([]);
  const [streamingRun, setStreamingRun] = useState<{
    inputs: Record<string, string>;
    partial: Record<string, string>;
  } | null>(null);
  const streamReqIdRef = useRef(0);
  const streamAbortRef = useRef<AbortController | null>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const textareaRefs = useRef<Record<string, HTMLTextAreaElement | null>>({});
  const [serveError, setServeError] = useState<string | null>(null);
  const [stageModal, setStageModal] = useState<PipelineStage | null>(null);

  const activePairIndex =
    searchParams.get("pair") != null ? parseInt(searchParams.get("pair")!, 10) : null;

  /* Cancelled/failed grid jobs have no persisted grid_result — rebuild from
     progress_events so overview + per-pair views still render. */
  const effectiveJob: OptimizationStatusResponse | null = (() => {
    if (!job) return null;
    if (job.grid_result || job.optimization_type !== "grid_search") return job;
    const rebuilt = reconstructGridResult(job);
    return rebuilt ? { ...job, grid_result: rebuilt } : job;
  })();

  const activePair =
    activePairIndex === null || !effectiveJob?.grid_result
      ? null
      : (effectiveJob.grid_result.pair_results.find((p) => p.pair_index === activePairIndex) ??
        null);

  const pairScorePoints = (() => {
    if (activePairIndex === null || !job?.logs) return [];
    const pairLogs = job.logs.filter((l) => l.pair_index === activePairIndex);
    return extractScoresFromLogs(pairLogs);
  })();

  const pairFilteredLogs =
    activePairIndex === null || !job?.logs
      ? (job?.logs ?? [])
      : job.logs.filter(
          (l) =>
            l.pair_index === activePairIndex || l.pair_index === null || l.pair_index === undefined,
        );

  const fetchJob = useCallback(async () => {
    try {
      const data = await getJob(id);
      setJob(data);
      setError(null);
    } catch (err) {
      // Distinguish auth/network failures from a genuine 404 — the previous
      // catch lumped 401/403/500/network into "not found" copy.
      console.warn("OptimizationDetailView: getJob failed", err);
      setError(formatMsg("auto.app.optimizations.id.page.template.1", { p1: TERMS.optimization }));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    if (isAnyDemoMode) return;
    getOptimizationPayload(id)
      .then(setPayload)
      .catch(() => {});
  }, [id, isAnyDemoMode]);

  const jobRef = useRef(job);
  useEffect(() => {
    jobRef.current = job;
  }, [job]);
  const lastCountsRef = useRef({ logs: 0, progress: 0 });

  useEffect(() => {
    if (isAnyDemoMode) return;
    void fetchJob();

    const API = getRuntimeEnv().apiUrl;
    let eventSource: EventSource | null = null;
    let fallbackInterval: ReturnType<typeof setInterval> | null = null;

    try {
      eventSource = new EventSource(`${API}/optimizations/${encodeURIComponent(id)}/stream`);

      eventSource.onmessage = (event) => {
        try {
          const sseData = JSON.parse(event.data);
          const logCount = sseData.log_count ?? 0;
          const progressCount = sseData.progress_count ?? 0;
          const prev = lastCountsRef.current;
          // Full re-fetch when new logs/events arrive or status changes
          if (
            logCount > prev.logs ||
            progressCount > prev.progress ||
            sseData.status !== jobRef.current?.status
          ) {
            lastCountsRef.current = { logs: logCount, progress: progressCount };
            void fetchJob();
          } else {
            // Lightweight merge for metrics-only updates
            setJob((p) =>
              p
                ? {
                    ...p,
                    status: sseData.status ?? p.status,
                    message: sseData.message ?? p.message,
                    latest_metrics: sseData.latest_metrics ?? p.latest_metrics,
                  }
                : p,
            );
          }
        } catch {
          void fetchJob();
        }
      };

      eventSource.addEventListener("done", () => {
        eventSource?.close();
        void fetchJob();
      });

      eventSource.onerror = () => {
        // Only fall back to polling once the browser's built-in reconnect has
        // given up (readyState === CLOSED). Transient blips set readyState to
        // CONNECTING — leave EventSource alone so it auto-retries instead of
        // locking the page into 5 s polling for the rest of the session.
        if (eventSource?.readyState !== EventSource.CLOSED) return;
        eventSource = null;
        if (fallbackInterval) return;
        fallbackInterval = setInterval(() => {
          if (jobRef.current && TERMINAL_STATUSES.has(jobRef.current.status)) {
            if (fallbackInterval) clearInterval(fallbackInterval);
            return;
          }
          void fetchJob();
        }, 5000);
      };
    } catch {
      // SSE not supported — use polling
      fallbackInterval = setInterval(() => {
        if (jobRef.current && TERMINAL_STATUSES.has(jobRef.current.status)) {
          if (fallbackInterval) clearInterval(fallbackInterval);
          return;
        }
        void fetchJob();
      }, 5000);
    }

    return () => {
      eventSource?.close();
      if (fallbackInterval) clearInterval(fallbackInterval);
    };
  }, [id, isAnyDemoMode, fetchJob]);

  useEffect(() => {
    if (isAnyDemoMode) return;
    const onRenamed = (e: Event) => {
      const { optimizationId, name } = (e as CustomEvent).detail;
      if (optimizationId === id) setJob((prev) => (prev ? { ...prev, name } : prev));
    };
    const onUpdated = (e: Event) => {
      const { optimizationId } = (e as CustomEvent).detail;
      if (optimizationId === id) void fetchJob();
    };
    window.addEventListener("optimization-renamed", onRenamed);
    window.addEventListener("optimization-updated", onUpdated);
    return () => {
      window.removeEventListener("optimization-renamed", onRenamed);
      window.removeEventListener("optimization-updated", onUpdated);
    };
  }, [id, fetchJob, isAnyDemoMode]);

  const handleCancel = async () => {
    if (isAnyDemoMode) return;
    try {
      await cancelJob(id);
      toast.success(msg("optimization.cancel.sent"));
      void fetchJob();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("optimization.cancel.failed"));
    }
  };

  useEffect(() => {
    if (isDemoMode && job?.status === "success") {
      setServeInfo({
        optimization_id: id,
        module_name: "Predict",
        optimizer_name: "GEPA",
        model_name: "gpt-4o-mini",
        input_fields: ["email_text"],
        output_fields: ["category"],
        instructions: "Classify an email into a category: spam, important, or promotional.",
        demo_count: 3,
      });
    }
    if (isGridDemoMode && job?.status === "success") {
      const best = job.grid_result?.best_pair;
      setServeInfo({
        optimization_id: id,
        module_name: "ChainOfThought",
        optimizer_name: "GEPA",
        model_name: best?.generation_model ?? "openai/gpt-4o-mini",
        input_fields: ["article"],
        output_fields: ["summary"],
        instructions: best?.program_artifact?.optimized_prompt?.instructions ?? "",
        demo_count: 1,
      });
    }
  }, [isDemoMode, isGridDemoMode, id, job?.status, job?.grid_result]);

  useEffect(() => {
    if (isAnyDemoMode) return;
    if (job?.status !== "success") return;
    if (job.optimization_type === "grid_search") {
      if (activePairIndex != null) {
        getPairServeInfo(id, activePairIndex)
          .then(setServeInfo)
          .catch(() => setServeInfo(null));
      } else {
        // Grid overview — fetch serve info for best pair (used for playground on overview)
        getServeInfo(id)
          .then(setServeInfo)
          .catch(() => setServeInfo(null));
      }
    } else {
      getServeInfo(id)
        .then(setServeInfo)
        .catch(() => setServeInfo(null));
    }
  }, [id, job?.status, job?.optimization_type, activePairIndex, isAnyDemoMode]);

  useEffect(() => {
    if (chatScrollRef.current) {
      const el = chatScrollRef.current;
      if (el.scrollHeight - el.scrollTop - el.clientHeight < 300) {
        el.scrollTop = el.scrollHeight;
      }
    }
  }, [runHistory, streamingRun]);

  useEffect(() => {
    return () => {
      streamAbortRef.current?.abort();
    };
  }, []);

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
    for (const f of serveInfo?.input_fields ?? []) vals[f] = textareaRefs.current[f]?.value ?? "";
    return vals;
  };

  const handleServe = async (overrideInputs?: Record<string, string>) => {
    if (!serveInfo) return;
    const inputs = overrideInputs ?? readServeInputs();
    const missing = serveInfo.input_fields.filter((f) => !inputs[f]?.trim());
    if (missing.length > 0) {
      toast.error(
        <div>
          {msg("auto.app.optimizations.id.page.1")}
          <br />
          {missing.join(", ")}
        </div>,
      );
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
        if (el) {
          el.value = "";
          el.style.height = "auto";
        }
      });
    }
    const isStale = () => reqId !== streamReqIdRef.current;
    const streamFn =
      job?.optimization_type === "grid_search" && activePairIndex != null
        ? (i: Record<string, string>, h: Parameters<typeof serveProgramStream>[2]) =>
            servePairProgramStream(id, activePairIndex, i, h)
        : (i: Record<string, string>, h: Parameters<typeof serveProgramStream>[2]) =>
            serveProgramStream(id, i, h);
    await streamFn(inputs, {
      signal: controller.signal,
      onToken: (field, chunk) => {
        if (isStale()) return;
        setStreamingRun((prev) =>
          prev
            ? {
                ...prev,
                partial: { ...prev.partial, [field]: (prev.partial[field] ?? "") + chunk },
              }
            : prev,
        );
      },
      onFinal: (res) => {
        if (isStale()) return;
        setRunHistory((prev) => {
          // Cap history so the chat panel stays responsive across long sessions.
          const next = [
            { inputs: { ...inputs }, outputs: res.outputs, model: res.model_used, ts: Date.now() },
            ...prev,
          ];
          return next.length > 50 ? next.slice(0, 50) : next;
        });
        setStreamingRun(null);
      },
      onError: (errorMsg) => {
        if (isStale()) return;
        setServeError(errorMsg);
        setStreamingRun(null);
      },
    });
    if (!isStale()) setServeLoading(false);
  };

  const handleClearHistory = () => {
    setRunHistory([]);
    setServeError(null);
  };

  const metrics = job?.latest_metrics ?? {};

  const signatureCode = (payload?.payload?.signature_code as string) ?? null;
  const metricCode = (payload?.payload?.metric_code as string) ?? null;

  const scorePoints = job?.logs?.length ? extractScoresFromLogs(job.logs) : [];

  const optimizedPrompt =
    job?.result?.program_artifact?.optimized_prompt ??
    job?.grid_result?.best_pair?.program_artifact?.optimized_prompt ??
    null;

  // Live elapsed timer — ticks every second for active jobs (must be before early returns)
  const isActive = job ? ACTIVE_STATUSES.has(job.status) : false;
  const [liveElapsed, setLiveElapsed] = useState("00:00:00");
  const startedAt = job?.started_at ?? null;
  const createdAt = job?.created_at ?? null;
  const completedAt = job?.completed_at ?? null;
  const elapsedSeconds = job?.elapsed_seconds ?? null;
  useEffect(() => {
    const startStr = startedAt ?? createdAt;
    if (!startStr) return;
    const start = new Date(startStr).getTime();

    // For completed/cancelled/failed jobs: use server-provided elapsed or completed_at
    if (!isActive) {
      if (elapsedSeconds != null && elapsedSeconds > 0) {
        const diff = Math.floor(elapsedSeconds);
        const h = String(Math.floor(diff / 3600)).padStart(2, "0");
        const m = String(Math.floor((diff % 3600) / 60)).padStart(2, "0");
        const s = String(diff % 60).padStart(2, "0");
        setLiveElapsed(`${h}:${m}:${s}`);
      } else if (completedAt) {
        const end = new Date(completedAt).getTime();
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
  }, [startedAt, createdAt, completedAt, elapsedSeconds, isActive]);

  if (loading) {
    return (
      <Skeleton
        name="optimization-detail"
        loading
        initialBones={optimizationDetailBones}
        color="var(--muted)"
        animate="shimmer"
      >
        <div className="min-h-[60vh]" />
      </Skeleton>
    );
  }

  if (error || !job) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <XCircle className="size-12 text-destructive" />
        <p className="text-lg text-muted-foreground">
          {error ??
            formatMsg("auto.app.optimizations.id.page.template.2", { p1: TERMS.optimization })}
        </p>
      </div>
    );
  }

  const isTerminal = TERMINAL_STATUSES.has(job.status);

  return (
    <div className="space-y-6 pb-12">
      <FadeIn>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Link href="/" className="hover:text-foreground transition-colors">
            {msg("auto.app.optimizations.id.page.2")}
          </Link>
          <ChevronLeft className="h-3 w-3" />
          <span className="text-foreground font-medium text-xs sm:text-sm break-all" dir="auto">
            {job.name || job.optimization_id.slice(0, 8)}
          </span>
        </div>
      </FadeIn>

      {!(job.optimization_type === "grid_search" && activePairIndex !== null) && (
        <FadeIn delay={0.1}>
          <div
            className=" rounded-xl border border-border/40 bg-gradient-to-br from-card to-card/80 p-5"
            data-tutorial="detail-header"
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-2 min-w-0">
                <div className="flex items-center gap-3 flex-wrap">
                  {job.name && (
                    <h2 className="text-lg sm:text-xl font-bold tracking-tight" dir="auto">
                      {job.name}
                    </h2>
                  )}
                  <StatusBadge status={job.status} />
                </div>
                {job.description && (
                  <p className="text-sm text-muted-foreground/70 leading-relaxed">
                    {job.description}
                  </p>
                )}
                <code
                  className="text-xs font-mono text-muted-foreground/60 cursor-pointer hover:text-primary transition-colors break-all"
                  title={msg("auto.app.optimizations.id.page.literal.1")}
                  aria-label={formatMsg("auto.app.optimizations.id.page.template.3", {
                    p1: TERMS.optimization,
                  })}
                  role="button"
                  tabIndex={0}
                  onClick={() => {
                    void navigator.clipboard.writeText(job.optimization_id);
                    toast.success(msg("clipboard.copied_short"), { autoClose: 1000 });
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      void navigator.clipboard.writeText(job.optimization_id);
                      toast.success(msg("clipboard.copied_short"), { autoClose: 1000 });
                    }
                  }}
                >
                  {job.optimization_id}
                </code>
                <div className="flex items-center gap-3 flex-wrap text-sm text-muted-foreground">
                  <Badge variant="secondary" className="text-[0.6875rem]">
                    {job.optimization_type === "grid_search"
                      ? msg("auto.app.optimizations.id.page.literal.2")
                      : msg("auto.app.optimizations.id.page.literal.3")}
                  </Badge>
                  <span className="flex items-center gap-1.5 tabular-nums" dir="ltr">
                    <Clock className="size-3.5" />
                    {liveElapsed}
                  </span>
                  {isActive && job.estimated_remaining && (
                    <span className="flex items-center gap-1.5">
                      <Timer className="size-3.5" />
                      {msg("auto.app.optimizations.id.page.3")}
                      {job.estimated_remaining}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <TooltipProvider>
                  <UiTooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8"
                        onClick={() => router.push(`/submit?clone=${job.optimization_id}`)}
                        aria-label={msg("auto.app.optimizations.id.page.literal.4")}
                      >
                        <CopyPlus className="size-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="bottom">
                      {msg("auto.app.optimizations.id.page.4")}
                    </TooltipContent>
                  </UiTooltip>
                </TooltipProvider>
                {isActive && (
                  <TooltipProvider>
                    <UiTooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-8 text-destructive hover:bg-destructive/10 hover:text-destructive focus-visible:ring-0 focus-visible:border-0"
                          onClick={handleCancel}
                          aria-label={msg("auto.app.optimizations.id.page.literal.5")}
                        >
                          <XCircle className="size-4" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">
                        {msg("auto.app.optimizations.id.page.5")}
                      </TooltipContent>
                    </UiTooltip>
                  </TooltipProvider>
                )}
                {isTerminal && (
                  <DeleteJobDialog
                    optimizationId={job.optimization_id}
                    onDeleted={() => router.push("/")}
                  />
                )}
              </div>
            </div>
          </div>
        </FadeIn>
      )}

      {job.status === "failed" && (job.message || (metrics.error as string)) && (
        <FadeIn delay={0.15}>
          <div className="p-5 rounded-xl border border-red-300/60 bg-gradient-to-br from-red-50 to-red-100/40 shadow-[0_0_15px_rgba(239,68,68,0.06)]">
            <div className="flex items-start gap-3">
              <XCircle className="size-5 text-red-500 shrink-0 mt-0.5" />
              <p className="text-sm font-semibold text-red-800">
                {msg("auto.app.optimizations.id.page.6")}
              </p>
            </div>
            <pre
              className="text-xs text-red-700 mt-3 whitespace-pre-wrap break-words font-mono leading-relaxed"
              dir="ltr"
            >
              {linkifyMessage(job.message ?? "", "underline hover:text-red-900 transition-colors")}
            </pre>
            {typeof metrics.error === "string" && !job.message?.includes(metrics.error) && (
              <pre
                className="text-xs text-red-700 mt-2 whitespace-pre-wrap break-words font-mono leading-relaxed border-t border-red-200 pt-2"
                dir="ltr"
              >
                {linkifyMessage(
                  String(metrics.error),
                  "underline hover:text-red-900 transition-colors",
                )}
              </pre>
            )}
          </div>
        </FadeIn>
      )}

      {job.status === "cancelled" && (
        <FadeIn>
          <div className="flex items-center gap-3 p-4 rounded-xl border border-stone-300 bg-stone-50 text-stone-700">
            <XCircle className="size-5 shrink-0" />
            <div>
              <p className="text-sm font-semibold">
                {msg("auto.app.optimizations.id.page.7")}
                {TERMS.optimization}
                {msg("auto.app.optimizations.id.page.8")}
              </p>
              <p className="text-xs text-stone-500 mt-0.5">
                {job.message ||
                  formatMsg("auto.app.optimizations.id.page.template.4", {
                    p1: TERMS.optimization,
                  })}
              </p>
            </div>
          </div>
        </FadeIn>
      )}

      {isTerminal &&
        job.status !== "cancelled" &&
        !(job.optimization_type === "grid_search" && activePairIndex !== null) &&
        (optimizedPrompt ||
          (job.logs && job.logs.length > 0) ||
          job.result?.program_artifact?.program_pickle_base64 ||
          job.grid_result?.best_pair?.program_artifact?.program_pickle_base64) && (
          <FadeIn delay={0.25}>
            <div className="flex items-center gap-3 p-5 rounded-xl border border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10 shadow-[0_0_20px_rgba(var(--primary),0.06)]">
              <div className="flex-1">
                <p className="text-sm font-medium">{msg("auto.app.optimizations.id.page.9")}</p>
              </div>
              <ExportMenu job={job} optimizedPrompt={optimizedPrompt} />
            </div>
          </FadeIn>
        )}

      {job.optimization_type === "grid_search" &&
        activePairIndex !== null &&
        (!activePair || !effectiveJob?.grid_result) && (
          <FadeIn>
            <div className="rounded-xl border border-border/50 bg-card/80 p-8 text-center space-y-3">
              <p className="text-sm font-medium">{msg("auto.app.optimizations.id.page.10")}</p>
              <p className="text-xs text-muted-foreground">
                {msg("auto.app.optimizations.id.page.11")}
                {TERMS.optimization}
                {msg("auto.app.optimizations.id.page.12")}
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => router.push(`/optimizations/${id}`)}
              >
                {msg("auto.app.optimizations.id.page.13")}
              </Button>
            </div>
          </FadeIn>
        )}

      {effectiveJob?.optimization_type === "grid_search" &&
        activePairIndex !== null &&
        activePair &&
        effectiveJob.grid_result && (
          <PairDetailView
            job={effectiveJob}
            activePair={activePair}
            activePairIndex={activePairIndex}
            pairCount={effectiveJob.grid_result.pair_results.length}
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
            onClone={() =>
              router.push(
                `/submit?clone=${effectiveJob.optimization_id}&pair=${activePair.pair_index}`,
              )
            }
            onCancel={handleCancel}
            onClearHistory={handleClearHistory}
            onStageClick={setStageModal}
            onDeleted={() => router.push(`/optimizations/${id}`)}
          />
        )}

      {!(job.optimization_type === "grid_search" && activePairIndex !== null) &&
        (() => {
          const tabCls =
            "relative px-2.5 sm:px-4 py-2.5 rounded-none border-b-2 border-transparent data-[state=active]:border-transparent data-[state=active]:border-b-primary data-[state=active]:text-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none transition-all duration-200 text-xs sm:text-sm";
          return (
            <Tabs value={detailTab} onValueChange={setDetailTab} dir="rtl">
              <TabsList
                variant="line"
                className="border-b border-border/50 pb-0 gap-0 overflow-x-auto no-scrollbar"
                data-tutorial="detail-tabs"
              >
                <TabsTrigger value="overview" className={tabCls}>
                  <TrendingUp className="size-3.5" />
                  {msg("auto.app.optimizations.id.page.14")}
                  {isActive && (
                    <span className="relative flex size-2 ms-1">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--warning)]/60" />
                      <span className="relative inline-flex rounded-full size-2 bg-[var(--warning)]" />
                    </span>
                  )}
                </TabsTrigger>
                {job.status === "success" &&
                  (job.optimization_type === "grid_search" || serveInfo) && (
                    <TabsTrigger
                      value="playground"
                      className={tabCls}
                      data-tutorial="playground-tab"
                    >
                      <Send className="size-3.5" />
                      {msg("auto.app.optimizations.id.page.15")}
                    </TabsTrigger>
                  )}
                {job.optimization_type !== "grid_search" && isTerminal && (
                  <TabsTrigger value="data" className={tabCls} data-tutorial="data-tab-trigger">
                    <Database className="size-3.5" />
                    {msg("auto.app.optimizations.id.page.16")}
                  </TabsTrigger>
                )}
                <TabsTrigger value="code" className={tabCls}>
                  <Code className="size-3.5" />
                  {msg("auto.app.optimizations.id.page.17")}
                </TabsTrigger>
                {job.optimization_type !== "grid_search" && (
                  <TabsTrigger value="logs" className={tabCls} data-tutorial="logs-tab-trigger">
                    <Terminal className="size-3.5" />
                    {msg("auto.app.optimizations.id.page.18")}
                    {isActive && (
                      <span className="relative flex size-2 ms-1">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--warning)]/60" />
                        <span className="relative inline-flex rounded-full size-2 bg-[var(--warning)]" />
                      </span>
                    )}
                  </TabsTrigger>
                )}
                <TabsTrigger value="config" className={tabCls} data-tutorial="config-tab-trigger">
                  <Settings className="size-3.5" />
                  {msg("auto.app.optimizations.id.page.19")}
                </TabsTrigger>
              </TabsList>

              <TabsContent value="overview" className="space-y-6 mt-4" data-tutorial="overview-tab">
                <OverviewTab
                  job={effectiveJob ?? job}
                  isActive={isActive}
                  scorePoints={scorePoints}
                  activePairIndex={activePairIndex}
                  onStageClick={setStageModal}
                  onPairSelect={(pi) => router.push(`/optimizations/${id}?pair=${pi}`)}
                  onPairDeleted={(pi) => {
                    try {
                      window.localStorage.removeItem(`grid-serve:pair:${id}`);
                    } catch {
                      /* localStorage unavailable — nothing to clean up */
                    }
                    if (activePairIndex === pi) {
                      router.replace(`/optimizations/${id}`);
                    }
                    void fetchJob();
                  }}
                />
              </TabsContent>

              {job.status === "success" && job.optimization_type === "grid_search" && (
                <TabsContent
                  value="playground"
                  className="space-y-4 mt-4"
                  data-tutorial="serve-playground"
                >
                  <GridServeTab job={job} />
                </TabsContent>
              )}
              {serveInfo && job.optimization_type !== "grid_search" && (
                <TabsContent
                  value="playground"
                  className="space-y-4 mt-4"
                  data-tutorial="serve-playground"
                >
                  <FadeIn>
                    <div className="flex items-center justify-between pb-3 border-b border-border/60">
                      <p className="text-sm text-muted-foreground">
                        {msg("auto.app.optimizations.id.page.20")}
                      </p>
                      {runHistory.length > 0 && (
                        <TooltipProvider>
                          <UiTooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="size-8"
                                onClick={handleClearHistory}
                                aria-label={msg("auto.app.optimizations.id.page.literal.6")}
                              >
                                <Trash2 className="size-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent side="bottom">
                              {msg("auto.app.optimizations.id.page.21")}
                            </TooltipContent>
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
                    demos={
                      job?.result?.program_artifact?.optimized_prompt?.demos ??
                      job?.grid_result?.best_pair?.program_artifact?.optimized_prompt?.demos ??
                      []
                    }
                  />

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">
                        <HelpTip text={tip("serve.section_run")}>
                          {msg("auto.app.optimizations.id.page.22")}
                        </HelpTip>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-1.5">
                        <p className="text-[0.625rem] text-muted-foreground uppercase tracking-wider">
                          <HelpTip text={tip("serve.api_url_run")}>
                            {msg("auto.app.optimizations.id.page.23")}
                          </HelpTip>
                        </p>
                        <div className="rounded-lg bg-muted/40 p-2.5 pe-8 relative group" dir="ltr">
                          <code className="text-xs font-mono break-all">
                            {msg("auto.app.optimizations.id.page.24")}
                            {getRuntimeEnv().apiUrl}
                            {msg("auto.app.optimizations.id.page.25")}
                            {id}
                          </code>
                          <CopyButton
                            text={`${getRuntimeEnv().apiUrl}/serve/${id}`}
                            className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100"
                          />
                        </div>
                      </div>

                      <Separator />

                      <div className="space-y-2">
                        <p className="text-[0.625rem] text-muted-foreground uppercase tracking-wider">
                          <HelpTip text={tip("serve.integration_code")}>
                            {msg("auto.app.optimizations.id.page.26")}
                          </HelpTip>
                        </p>
                        <ServeCodeSnippets serveInfo={serveInfo} optimizationId={id} />
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>
              )}

              <TabsContent value="data">
                <DataTab job={job} />
              </TabsContent>

              <TabsContent value="code" className="space-y-6 mt-4">
                <CodeTab
                  signatureCode={signatureCode}
                  metricCode={metricCode}
                  optimizedPrompt={optimizedPrompt}
                />
              </TabsContent>

              {job.optimization_type !== "grid_search" && (
                <TabsContent value="logs" data-tutorial="live-logs">
                  <LogsTab logs={job.logs} live={isActive} />
                </TabsContent>
              )}

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
