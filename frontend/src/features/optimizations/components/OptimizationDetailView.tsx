"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import {
  XCircle,
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
  Activity,
} from "lucide-react";
import { toast } from "react-toastify";

import { Button } from "@/shared/ui/primitives/button";
import { Badge } from "@/shared/ui/primitives/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/primitives/tabs";
import { PingDot } from "@/shared/ui/ping-dot";
import { FadeIn } from "@/shared/ui/motion";
import { TooltipButton } from "@/shared/ui/tooltip-button";
import {
  getJob,
  cancelJob,
  getOptimizationPayload,
  getServeInfo,
  getPairServeInfo,
  serveProgramStream,
  servePairProgramStream,
} from "@/shared/lib/api";
import type { LMActivity, ServeInfoResponse } from "@/shared/types/api";
import {
  DEMO_OPTIMIZATION_ID,
  DEMO_GRID_OPTIMIZATION_ID,
  DEMO_TRAJECTORY_PREVIEW_LAYOUT,
  buildGridDemoJob,
  resetDemoSimulation,
  startDemoSimulation,
} from "@/features/tutorial";
import { OptimizationDetailSkeleton } from "./OptimizationDetailSkeleton";
import { formatMsg, msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";
import { getRuntimeEnv } from "@/shared/lib/runtime-env";
import { ACTIVE_STATUSES, TERMINAL_STATUSES } from "@/shared/constants/job-status";
import { registerTutorialHook } from "@/features/tutorial";
import type { OptimizationStatusResponse, OptimizationPayloadResponse } from "@/shared/types/api";
import type { PipelineStage } from "../constants";
import { extractScoresFromLogs } from "../lib/extract-scores";
import { reconstructGridResult } from "../lib/reconstruct-grid";
import { DataTab } from "./DataTab";
import { LogsTab } from "./LogsTab";
import { ExportMenu } from "./ExportMenu";
import { DeleteJobDialog } from "./DeleteJobDialog";
import { StatusBadge } from "@/shared/ui/status-badge";
import { ConfigTab } from "./ConfigTab";
import { CodeTab } from "./CodeTab";
import { StageInfoModal } from "./StageInfoModal";
import { PairSelectionStrip } from "./PairSelectionStrip";
import { OverviewTab } from "./OverviewTab";
import { GridServeTab } from "./GridServeTab";
import { LMActivityTab } from "./LMActivityTab";
import { RunPlayground } from "./RunPlayground";
import { linkifyMessage } from "@/shared/lib/linkify";
import { useStreamWithPollFallback } from "@/shared/hooks/use-stream-with-poll-fallback";

// Treat naive ISO timestamps (no trailing tz marker) as UTC — that matches the
// backend, which stores UTC datetimes that Pydantic emits without a suffix.
// Without this, browsers in a positive UTC offset parse them as local time
// and the elapsed clock either jumps backward or stays at 00:00:00.
function parseTimestampMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value);
  const ms = Date.parse(hasTz ? value : `${value}Z`);
  return Number.isFinite(ms) ? ms : null;
}

function formatElapsed(seconds: number): string {
  const h = String(Math.floor(seconds / 3600)).padStart(2, "0");
  const m = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
  const s = String(seconds % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
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

  // The NextAuth session resolves asynchronously on the client. Without this
  // gate the first getJob() fires before setApiAuthToken() runs, returns 401,
  // and flashes the "not found" UI until SSE/poll refetches a few seconds
  // later with the token now in place.
  const { status: sessionStatus } = useSession();
  const authReady = isAnyDemoMode || sessionStatus === "authenticated";

  const [job, setJob] = useState<OptimizationStatusResponse | null>(null);
  const [payload, setPayload] = useState<OptimizationPayloadResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Bump to replay the demo optimization simulation. The deep-dive tour
  // triggers this when reaching the trajectory step so users watch the tree
  // grow live instead of seeing the already-completed final state.
  const [demoReplayKey, setDemoReplayKey] = useState(0);

  useEffect(
    () =>
      registerTutorialHook("replayDemoSimulation", () => {
        resetDemoSimulation();
        setDemoReplayKey((k) => k + 1);
      }),
    [],
  );

  useEffect(() => {
    if (!isDemoMode) return;
    const fromTrajectory = demoReplayKey > 0;
    return startDemoSimulation(
      { setJob: (fn) => setJob(fn), setLoading },
      { fromTrajectory },
    );
  }, [isDemoMode, demoReplayKey]);

  useEffect(() => {
    if (!isGridDemoMode) return;
    setJob(buildGridDemoJob());
    setLoading(false);
  }, [isGridDemoMode]);

  const [serveInfo, setServeInfo] = useState<ServeInfoResponse | null>(null);
  const [serveInfoError, setServeInfoError] = useState<string | null>(null);
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
  const isPairContext = activePair != null;

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
    if (!authReady) return;
    getOptimizationPayload(id)
      .then(setPayload)
      .catch(() => {});
  }, [id, isAnyDemoMode, authReady]);

  const jobRef = useRef(job);
  useEffect(() => {
    jobRef.current = job;
  }, [job]);
  const lastCountsRef = useRef({ logs: 0, progress: 0 });

  useEffect(() => {
    if (isAnyDemoMode) return;
    if (!authReady) return;
    void fetchJob();
  }, [id, isAnyDemoMode, authReady, fetchJob]);

  const API = getRuntimeEnv().apiUrl;
  useStreamWithPollFallback({
    url: isAnyDemoMode ? "" : `${API}/optimizations/${encodeURIComponent(id)}/stream`,
    enabled: !isAnyDemoMode && authReady,
    onMessage: (event) => {
      try {
        const sseData = JSON.parse(event.data);
        const logCount = sseData.log_count ?? 0;
        const progressCount = sseData.progress_count ?? 0;
        const prev = lastCountsRef.current;
        if (
          logCount > prev.logs ||
          progressCount > prev.progress ||
          sseData.status !== jobRef.current?.status
        ) {
          lastCountsRef.current = { logs: logCount, progress: progressCount };
          void fetchJob();
        } else {
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
    },
    events: { done: () => void fetchJob() },
    closeOnEvents: ["done"],
    poll: () => void fetchJob(),
    pollIntervalMs: 5000,
    shouldStopPolling: () =>
      !!jobRef.current && TERMINAL_STATUSES.has(jobRef.current.status),
    // Stream auth failed even after a token refresh — re-fetch through the
    // self-healing request() path so a still-bad token surfaces the existing
    // error banner instead of the page silently freezing on stale data.
    onAuthError: () => void fetchJob(),
  });

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
    // A failure here used to be swallowed as `setServeInfo(null)`, which
    // silently blanked the Usage tab (e.g. when an expired bearer 401'd).
    // request() now self-heals a stale token; a persistent failure surfaces.
    const onFail = (err: unknown) => {
      setServeInfo(null);
      setServeInfoError(
        err instanceof Error
          ? err.message
          : formatMsg("auto.app.optimizations.id.page.template.1", { p1: TERMS.optimization }),
      );
    };
    const isGrid = job.optimization_type === "grid_search";
    const loader =
      isGrid && activePairIndex != null
        ? getPairServeInfo(id, activePairIndex)
        : getServeInfo(id);
    loader
      .then((info) => {
        setServeInfo(info);
        setServeInfoError(null);
      })
      .catch(onFail);
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
    setServeInfoError(null);
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

  // Optimized prompt picks the pair's artifact in pair view, otherwise falls
  // back to the run's artifact, otherwise to the grid's best pair (for the
  // grid-root overview banner/code tab).
  const optimizedPrompt = isPairContext
    ? (activePair.program_artifact?.optimized_prompt ?? null)
    : (job?.result?.program_artifact?.optimized_prompt ??
       job?.grid_result?.best_pair?.program_artifact?.optimized_prompt ??
       null);

  // Demos passed to the serve playground — pair-scoped in pair view.
  const playgroundDemos = isPairContext
    ? (activePair.program_artifact?.optimized_prompt?.demos ?? [])
    : (job?.result?.program_artifact?.optimized_prompt?.demos ??
       job?.grid_result?.best_pair?.program_artifact?.optimized_prompt?.demos ??
       []);

  // LM activity is pair-scoped in pair view, otherwise the run's.
  const viewLmActivity: LMActivity | null = isPairContext
    ? ((activePair.lm_activity as LMActivity | undefined) ?? null)
    : ((job?.result?.lm_activity as LMActivity | undefined) ?? null);

  const isActive = job ? ACTIVE_STATUSES.has(job.status) : false;
  const startedAt = job?.started_at ?? null;
  const createdAt = job?.created_at ?? null;
  const completedAt = job?.completed_at ?? null;
  const elapsedSeconds = job?.elapsed_seconds ?? null;
  // `now` ticks once per second only while the job is active, driving the
  // elapsed-time derivation in `liveElapsed`. Decoupling the tick from the
  // timestamp deps keeps the interval alive across polling refreshes that
  // replace identical timestamp strings.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!isActive) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [isActive]);
  // Anchor on the server-computed elapsed_seconds so the live counter is
  // immune to client/server clock skew — wall-clock derivation alone can go
  // negative and stall the badge at 00:00:00.
  const [elapsedAnchor, setElapsedAnchor] = useState<{ ms: number; sec: number } | null>(null);
  useEffect(() => {
    if (elapsedSeconds != null && Number.isFinite(elapsedSeconds) && elapsedSeconds >= 0) {
      setElapsedAnchor({ ms: Date.now(), sec: elapsedSeconds });
    }
  }, [elapsedSeconds]);
  const liveElapsed = useMemo(() => {
    if (!isActive) {
      if (elapsedSeconds != null && elapsedSeconds > 0) {
        return formatElapsed(Math.floor(elapsedSeconds));
      }
      const start = parseTimestampMs(startedAt ?? createdAt);
      const end = parseTimestampMs(completedAt);
      if (start !== null && end !== null) {
        return formatElapsed(Math.max(0, Math.floor((end - start) / 1000)));
      }
      return "00:00:00";
    }
    // Take the larger of wallclock (now - started_at) and the server anchor so
    // a stale upstream `elapsed_seconds` (e.g. cached 0) doesn't reset the
    // header counter back to zero on every page reload.
    const start = parseTimestampMs(startedAt ?? createdAt);
    const wall = start !== null ? Math.max(0, (now - start) / 1000) : 0;
    const anchored = elapsedAnchor
      ? elapsedAnchor.sec + Math.max(0, (now - elapsedAnchor.ms) / 1000)
      : 0;
    return formatElapsed(Math.floor(Math.max(wall, anchored)));
  }, [now, isActive, startedAt, createdAt, completedAt, elapsedSeconds, elapsedAnchor]);

  if (loading || !authReady) {
    return <OptimizationDetailSkeleton />;
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
  // Pair-aware terminal: a pair is considered "available for data export" once
  // it has either a program artifact or an error recorded. This mirrors the
  // standalone job's "isTerminal" gate so the data/export surfaces appear
  // identically in both contexts.
  const isPairTerminal = isPairContext
    ? !!(activePair.error || activePair.program_artifact || activePair.optimized_test_metric != null)
    : false;

  // Tab gating uniform across run and pair contexts.
  const showPlaygroundTab =
    job.status === "success" && (job.optimization_type === "grid_search" || !!serveInfo);
  const showDataTab = isPairContext
    ? isPairTerminal
    : isTerminal && job.optimization_type !== "grid_search";
  const showLogsTab = job.optimization_type !== "grid_search" || isPairContext;
  const showLmActivityTab = viewLmActivity != null;

  // Export-ready banner — pair-aware. Pair shows when it has its own artifact
  // (no error). Standalone shows when the run terminated successfully with any
  // artifact/log data to export.
  const showExportBanner = isPairContext
    ? !activePair.error && !!activePair.program_artifact
    : isTerminal &&
      job.status !== "cancelled" &&
      !!(
        optimizedPrompt ||
        (job.logs && job.logs.length > 0) ||
        job.result?.program_artifact?.program_pickle_base64 ||
        job.grid_result?.best_pair?.program_artifact?.program_pickle_base64
      );

  const pairCount = effectiveJob?.grid_result?.pair_results.length ?? 0;
  const isBestPair =
    isPairContext &&
    effectiveJob?.grid_result?.best_pair?.pair_index === activePair.pair_index;

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

      <FadeIn delay={0.1}>
        <div
          className=" rounded-xl border border-border/40 bg-gradient-to-br from-card to-card/80 p-5"
          data-tutorial="detail-header"
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-2 min-w-0">
              <div className="flex items-center gap-3 flex-wrap">
                <StatusBadge status={job.status} />
                {job.name && (
                  <h2 className="text-lg sm:text-xl font-bold tracking-tight" dir="auto">
                    {job.name}
                  </h2>
                )}
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
              <TooltipButton tooltip={msg("auto.app.optimizations.id.page.4")}>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-8"
                  onClick={() => router.push(`/submit?clone=${job.optimization_id}`)}
                  aria-label={msg("auto.app.optimizations.id.page.literal.4")}
                >
                  <CopyPlus className="size-4" />
                </Button>
              </TooltipButton>
              {isActive && (
                <TooltipButton tooltip={msg("auto.app.optimizations.id.page.5")}>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-8 text-destructive hover:bg-destructive/10 hover:text-destructive focus-visible:ring-0 focus-visible:border-0"
                    onClick={handleCancel}
                    aria-label={msg("auto.app.optimizations.id.page.literal.5")}
                  >
                    <XCircle className="size-4" />
                  </Button>
                </TooltipButton>
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

      {isPairContext && effectiveJob?.grid_result && (
        <PairSelectionStrip
          job={effectiveJob}
          activePair={activePair}
          activePairIndex={activePair.pair_index}
          pairCount={pairCount}
          isBest={isBestPair}
          jobActive={isActive}
          jobTerminal={isTerminal}
          onBack={() => router.push(`/optimizations/${id}`)}
          onPrev={() => router.push(`/optimizations/${id}?pair=${activePair.pair_index - 1}`)}
          onNext={() => router.push(`/optimizations/${id}?pair=${activePair.pair_index + 1}`)}
          onClone={() =>
            router.push(`/submit?clone=${effectiveJob.optimization_id}&pair=${activePair.pair_index}`)
          }
          onCancel={handleCancel}
          onDeleted={() => router.push(`/optimizations/${id}`)}
        />
      )}

      {job.status === "failed" && !isPairContext && (job.message || (metrics.error as string)) && (
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

      {isPairContext && activePair.error && (
        <FadeIn delay={0.05}>
          <div className="rounded-xl border border-[#B04030]/30 bg-[#B04030]/5 p-4">
            <div className="text-sm font-medium text-[#B04030] mb-1">
              {msg("auto.features.optimizations.components.pairdetailview.3")}
            </div>
            <pre className="text-xs font-mono text-[#B04030]/80 whitespace-pre-wrap" dir="ltr">
              {activePair.error}
            </pre>
          </div>
        </FadeIn>
      )}

      {job.status === "cancelled" && !isPairContext && (
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

      {showExportBanner && (
        <FadeIn delay={0.25}>
          <div className="flex items-center gap-3 p-5 rounded-xl border border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10 shadow-[0_0_20px_rgba(var(--primary),0.06)]">
            <div className="flex-1">
              <p className="text-sm font-medium">
                {isPairContext
                  ? msg("auto.features.optimizations.components.pairdetailview.2")
                  : msg("auto.app.optimizations.id.page.9")}
              </p>
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

      {(() => {
        const tabCls =
          "relative px-2.5 sm:px-4 py-2.5 rounded-none border-b-2 border-transparent data-[state=active]:border-transparent data-[state=active]:border-b-primary data-[state=active]:text-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none transition-all duration-200 text-xs sm:text-sm";
        // Pair view pings the trajectory/logs tabs only while the pair itself
        // is still running, matching the standalone run's behaviour exactly.
        const pingActive = isPairContext
          ? isActive &&
            !activePair.error &&
            !(activePair.program_artifact || activePair.optimized_test_metric != null)
          : isActive;
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
                {pingActive && <PingDot className="ms-1" />}
              </TabsTrigger>
              {showPlaygroundTab && (
                <TabsTrigger
                  value="playground"
                  className={tabCls}
                  data-tutorial="playground-tab"
                >
                  <Send className="size-3.5" />
                  {msg("auto.app.optimizations.id.page.15")}
                </TabsTrigger>
              )}
              {showDataTab && (
                <TabsTrigger value="data" className={tabCls} data-tutorial="data-tab-trigger">
                  <Database className="size-3.5" />
                  {msg("auto.app.optimizations.id.page.16")}
                </TabsTrigger>
              )}
              <TabsTrigger value="code" className={tabCls}>
                <Code className="size-3.5" />
                {msg("auto.app.optimizations.id.page.17")}
              </TabsTrigger>
              {showLogsTab && (
                <TabsTrigger value="logs" className={tabCls} data-tutorial="logs-tab-trigger">
                  <Terminal className="size-3.5" />
                  {msg("auto.app.optimizations.id.page.18")}
                  {pingActive && <PingDot className="ms-1" />}
                </TabsTrigger>
              )}
              {showLmActivityTab && (
                <TabsTrigger value="lm-activity" className={tabCls}>
                  <Activity className="size-3.5" />
                  {msg("auto.app.optimizations.id.page.lm_activity")}
                </TabsTrigger>
              )}
              <TabsTrigger value="config" className={tabCls} data-tutorial="config-tab-trigger">
                <Settings className="size-3.5" />
                {msg("auto.app.optimizations.id.page.19")}
              </TabsTrigger>
            </TabsList>

            <TabsContent
              value="overview"
              className="space-y-6 mt-4"
              data-tutorial={isPairContext ? "pair-detail" : "overview-tab"}
            >
              <OverviewTab
                job={effectiveJob ?? job}
                isActive={isActive}
                scorePoints={isPairContext ? pairScorePoints : scorePoints}
                activePairIndex={activePairIndex}
                activePair={activePair}
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
                trajectoryPreviewLayout={
                  isDemoMode && !isPairContext ? DEMO_TRAJECTORY_PREVIEW_LAYOUT : undefined
                }
              />
            </TabsContent>

            {showPlaygroundTab && (
              <TabsContent
                value="playground"
                className="space-y-4 mt-4"
                data-tutorial="serve-playground"
              >
                {job.optimization_type === "grid_search" && !isPairContext ? (
                  <GridServeTab job={job} />
                ) : serveInfo ? (
                  <RunPlayground
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
                    demos={playgroundDemos}
                    optimizationId={job.optimization_id}
                    pairIndex={isPairContext ? activePair.pair_index : undefined}
                    onClearHistory={handleClearHistory}
                  />
                ) : null}
              </TabsContent>
            )}

            {showDataTab && (
              <TabsContent value="data">
                <DataTab job={job} pairIndex={isPairContext ? activePair.pair_index : undefined} />
              </TabsContent>
            )}

            <TabsContent value="code" className="space-y-6 mt-4">
              <CodeTab
                signatureCode={signatureCode ?? ""}
                metricCode={metricCode ?? ""}
                optimizedPrompt={optimizedPrompt}
              />
            </TabsContent>

            {showLogsTab && (
              <TabsContent value="logs" data-tutorial="live-logs">
                <LogsTab
                  logs={isPairContext ? pairFilteredLogs : (job.logs ?? [])}
                  live={isActive}
                />
              </TabsContent>
            )}

            {showLmActivityTab && viewLmActivity && (
              <TabsContent value="lm-activity" className="mt-4">
                <LMActivityTab lmActivity={viewLmActivity} />
              </TabsContent>
            )}

            <TabsContent value="config" className="mt-4" data-tutorial="config-section">
              <ConfigTab job={job} payload={payload} activePair={activePair ?? undefined} />
            </TabsContent>
          </Tabs>
        );
      })()}

      <StageInfoModal stage={stageModal} job={job} onClose={() => setStageModal(null)} />
    </div>
  );
}
