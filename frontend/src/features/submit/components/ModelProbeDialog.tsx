"use client";

import * as React from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  Check,
  ChevronDown,
  Circle,
  Crown,
  Info,
  Loader2,
  Medal,
  Play,
  Search,
  Sparkles,
  Timer,
  TrendingUp,
  Trash2,
  Trophy,
  X,
  XCircle,
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line as RLine,
  XAxis,
  YAxis,
  CartesianGrid,
  ReferenceLine,
  Tooltip as RechartsTooltip,
} from "recharts";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { toast } from "react-toastify";
import { cn } from "@/shared/lib/utils";
import { formatLogTimestamp, logTimeBucket } from "@/shared/lib";
import { msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";
import { probeModels, type ModelProbeRequest, type ProbeScalingFit } from "@/shared/lib/api";
import {
  ColumnHeader,
  useColumnFilters,
  useColumnResize,
  type SortDir,
} from "@/shared/ui/excel-filter";
import { AnimatedNumber, FadeIn, TiltCard } from "@/shared/ui/motion";
import type { CatalogModel, ColumnMapping } from "@/shared/types/api";

import type { SubmitWizardContext } from "../hooks/use-submit-wizard";

interface ModelProbeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  w: SubmitWizardContext;
  onSelect: (modelValue: string) => void;
  onRunningChange?: (running: boolean) => void;
  onHasResultsChange?: (has: boolean) => void;
}

type RowStatus = "pending" | "running" | "done" | "error";

interface TrajectoryPoint {
  step: number;
  score: number;
}

interface ProbeLogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
}

interface ModelRow {
  position: number;
  model: string;
  label: string;
  provider: string;
  status: RowStatus;
  logs: ProbeLogEntry[];
  score: number | null;
  scaling: ProbeScalingFit | null;
  trajectory: TrajectoryPoint[];
  durationMs: number | null;
  errorMessage: string | null;
  startedAt: number | null;
}

function rowAsymptote(row: ModelRow): number | null {
  const signal = row.scaling?.signal;
  if ((signal === "strong" || signal === "observed") && row.scaling?.asymptote != null) {
    return row.scaling.asymptote;
  }
  return null;
}

function rowIsPredicted(row: ModelRow): boolean {
  return row.scaling?.signal === "strong";
}

function rowIsObserved(row: ModelRow): boolean {
  return row.scaling?.signal === "observed";
}

function rowRankingScore(row: ModelRow): number {
  return rowAsymptote(row) ?? row.score ?? -Infinity;
}

const MIN_ROWS = 16;
const MAX_LOG_LINES = 60;
const MODEL_COLORS = [
  "#3D2E22",
  "#C8A882",
  "#8C7A6B",
  "#5B7B7A",
  "#A85A4A",
  "#6B8E23",
  "#7A6B8C",
  "#B8860B",
];

function rowColor(row: ModelRow): string {
  return MODEL_COLORS[row.position % MODEL_COLORS.length]!;
}

function bestSoFar(points: TrajectoryPoint[]): TrajectoryPoint[] {
  const out: TrajectoryPoint[] = [];
  let max = -Infinity;
  for (const p of points) {
    max = Math.max(max, p.score);
    out.push({ step: p.step, score: max });
  }
  return out;
}
const EXCLUDE_PATTERN =
  /preview|audio|realtime|search|embedding|tts|dall-?e|image|whisper|vision|container|chatgpt|-latest$/i;
const DEPRECATED_PATTERN = /gpt-3\.5|gpt-4$|gpt-4-(\d{4}|turbo)|claude-(1|2|instant)|gemini-1/i;
const TINY_PATTERN = /nano|tiny/i;
const SMALL_PATTERN = /mini|small|haiku|flash/i;

function scoreModel(value: string): number {
  const v = value.toLowerCase();
  let score = 0;
  const versionMatch = v.match(/[-/](\d+(?:\.\d+)?)/);
  if (versionMatch && versionMatch[1]) score += parseFloat(versionMatch[1]) * 100;
  if (TINY_PATTERN.test(v)) score -= 60;
  else if (SMALL_PATTERN.test(v)) score -= 40;
  if (/opus/.test(v)) score += 10;
  else if (/sonnet/.test(v)) score += 5;
  if (/-(chat|instruct|api)(-|$)/.test(v)) score -= 5;
  return score;
}

function smartDefaults(models: CatalogModel[]): Set<string> {
  const eligible = models
    .filter((m) => !EXCLUDE_PATTERN.test(m.value) && !DEPRECATED_PATTERN.test(m.value))
    .sort((a, b) => scoreModel(b.value) - scoreModel(a.value));
  const seen = new Set<string>();
  const picks = new Set<string>();
  for (const m of eligible) {
    if (picks.size >= 5) break;
    if (seen.has(m.provider)) continue;
    seen.add(m.provider);
    picks.add(m.value);
  }
  return picks;
}

function groupByProvider(models: CatalogModel[]): Map<string, CatalogModel[]> {
  const out = new Map<string, CatalogModel[]>();
  for (const m of models) {
    const list = out.get(m.provider) ?? [];
    list.push(m);
    out.set(m.provider, list);
  }
  return out;
}

export function ModelProbeDialog({
  open,
  onOpenChange,
  w,
  onSelect,
  onRunningChange,
  onHasResultsChange,
}: ModelProbeDialogProps) {
  const {
    signatureCode,
    metricCode,
    parsedDataset,
    columnRoles,
    moduleName,
    optimizerName,
    seed,
    shuffle,
    catalog,
  } = w;

  const catalogModels = React.useMemo(() => catalog?.models ?? [], [catalog]);
  const groupedModels = React.useMemo(() => groupByProvider(catalogModels), [catalogModels]);

  const [search, setSearch] = React.useState("");
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [reflectionModel, setReflectionModel] = React.useState<string | null>(null);
  const [reflectionPickerOpen, setReflectionPickerOpen] = React.useState(false);
  const [reflectionSearch, setReflectionSearch] = React.useState("");
  const reflectionPickerRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!reflectionPickerOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (!reflectionPickerRef.current?.contains(e.target as Node)) {
        setReflectionPickerOpen(false);
        setReflectionSearch("");
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [reflectionPickerOpen]);

  React.useEffect(() => {
    if (reflectionModel !== null) return;
    const first = catalogModels[0];
    if (!first) return;
    const ranked = [...catalogModels]
      .filter((m) => !EXCLUDE_PATTERN.test(m.value) && !DEPRECATED_PATTERN.test(m.value))
      .sort((a, b) => scoreModel(b.value) - scoreModel(a.value));
    setReflectionModel((ranked[0] ?? first).value);
  }, [catalogModels, reflectionModel]);

  const selectedReflectionModel = React.useMemo(
    () => catalogModels.find((m) => m.value === reflectionModel) ?? null,
    [catalogModels, reflectionModel],
  );

  const filteredReflectionModels = React.useMemo(() => {
    const q = reflectionSearch.trim().toLowerCase();
    if (!q) return catalogModels;
    return catalogModels.filter(
      (m) => m.label.toLowerCase().includes(q) || m.value.toLowerCase().includes(q),
    );
  }, [catalogModels, reflectionSearch]);

  const groupedFilteredReflection = React.useMemo(
    () => groupByProvider(filteredReflectionModels),
    [filteredReflectionModels],
  );

  const [phase, setPhase] = React.useState<"idle" | "running" | "done" | "error">("idle");
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [total, setTotal] = React.useState<number>(0);
  const [modelRows, setModelRows] = React.useState<Record<string, ModelRow>>({});
  const [expandedModel, setExpandedModel] = React.useState<string | null>(null);
  const [now, setNow] = React.useState<number>(() => Date.now());
  const abortRef = React.useRef<AbortController | null>(null);

  React.useEffect(() => {
    if (phase !== "running") return;
    const id = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(id);
  }, [phase]);

  const columnMapping = React.useMemo<ColumnMapping>(() => {
    const inputs: Record<string, string> = {};
    const outputs: Record<string, string> = {};
    Object.entries(columnRoles).forEach(([col, role]) => {
      if (role === "input") inputs[col] = col;
      else if (role === "output") outputs[col] = col;
    });
    return { inputs, outputs };
  }, [columnRoles]);

  const dataset = parsedDataset?.rows as Record<string, unknown>[] | undefined;
  const datasetRows = dataset?.length ?? 0;

  const hasEnoughRows = datasetRows >= MIN_ROWS;
  const hasInputs = Object.keys(columnMapping.inputs).length > 0;
  const hasOutputs = Object.keys(columnMapping.outputs).length > 0;
  const hasSignature = signatureCode.trim().length > 0;
  const hasMetric = metricCode.trim().length > 0;
  const hasCatalog = catalogModels.length > 0;

  const modelsToRun = React.useMemo<CatalogModel[]>(
    () => catalogModels.filter((m) => selected.has(m.value)),
    [catalogModels, selected],
  );

  const canStart =
    phase !== "running" &&
    hasSignature &&
    hasMetric &&
    hasEnoughRows &&
    hasInputs &&
    hasOutputs &&
    hasCatalog &&
    !!reflectionModel &&
    modelsToRun.length > 0;

  const prerequisiteMessages: string[] = [];
  if (!hasSignature) prerequisiteMessages.push("חסר קוד פרומפט התחלתי");
  if (!hasMetric) prerequisiteMessages.push(`חסר קוד ${TERMS.metric}`);
  if (!hasInputs || !hasOutputs) prerequisiteMessages.push("הגדר עמודות קלט ופלט");
  if (!hasEnoughRows) {
    prerequisiteMessages.push(`נדרשות לפחות ${MIN_ROWS} שורות (יש ${datasetRows})`);
  }
  if (!hasCatalog) prerequisiteMessages.push("אין מודלים זמינים בקטלוג");

  const reset = React.useCallback(() => {
    setPhase("idle");
    setErrorMessage(null);
    setTotal(0);
    setModelRows({});
    setExpandedModel(null);
  }, []);

  React.useEffect(() => {
    onRunningChange?.(phase === "running");
    onHasResultsChange?.(phase === "done" || phase === "error");
  }, [phase, onRunningChange, onHasResultsChange]);

  // When the dialog closes, only reset if we have no results to preserve.
  // Results (phase "done"/"error") persist so the user can reopen and see them.
  // Only the abort button (stop) resets everything.
  React.useEffect(() => {
    if (open) return;
    if (phase === "running") return;
    // If we have results, keep them — just clean up UI state
    if (phase === "done" || phase === "error") {
      setExpandedModel(null);
      return;
    }
    abortRef.current?.abort();
    abortRef.current = null;
    setSearch("");
    setSelected(new Set());
    setReflectionPickerOpen(false);
    setReflectionSearch("");
  }, [open, phase]);

  const toggleOne = (value: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  };

  const filteredModels = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = catalogModels.filter((m) => {
      if (q && !m.label.toLowerCase().includes(q) && !m.value.toLowerCase().includes(q))
        return false;
      return true;
    });
    return filtered.sort((a, b) => {
      const aS = selected.has(a.value) ? 0 : 1;
      const bS = selected.has(b.value) ? 0 : 1;
      return aS - bS;
    });
  }, [catalogModels, search, selected]);

  const selectAllVisible = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const m of filteredModels) next.add(m.value);
      return next;
    });
  };
  const clearAllSelection = () => setSelected(new Set());

  const start = async () => {
    if (!dataset || !canStart) return;
    setExpandedModel(null);
    const initialRows: Record<string, ModelRow> = {};
    modelsToRun.forEach((m, idx) => {
      initialRows[m.value] = {
        position: idx,
        model: m.value,
        label: m.label,
        provider: m.provider,
        status: "pending",
        logs: [],
        score: null,
        scaling: null,
        trajectory: [],
        durationMs: null,
        errorMessage: null,
        startedAt: null,
      };
    });
    setPhase("running");
    setErrorMessage(null);
    setTotal(modelsToRun.length);
    setModelRows(initialRows);
    setNow(Date.now());

    const controller = new AbortController();
    abortRef.current = controller;

    const payload: ModelProbeRequest = {
      signature_code: signatureCode,
      metric_code: metricCode,
      module_name: moduleName,
      optimizer_name: optimizerName,
      dataset,
      column_mapping: columnMapping,
      train_count: 12,
      eval_count: 4,
      shuffle,
      seed: seed ?? null,
      model_ids: modelsToRun.map((m) => m.value),
      reflection_model_name: reflectionModel,
    };

    await probeModels(payload, {
      signal: controller.signal,
      onStart: (e) => setTotal(e.total),
      onModelStart: (e) =>
        setModelRows((prev) => {
          const existing = prev[e.model];
          const base: ModelRow = existing ?? {
            position: e.position,
            model: e.model,
            label: e.label,
            provider: e.provider,
            status: "running",
            logs: [],
            score: null,
            scaling: null,
            trajectory: [],
            durationMs: null,
            errorMessage: null,
            startedAt: Date.now(),
          };
          return {
            ...prev,
            [e.model]: {
              ...base,
              position: e.position,
              label: e.label,
              provider: e.provider,
              status: "running",
              startedAt: Date.now(),
            },
          };
        }),
      onLog: (e) =>
        setModelRows((prev) => {
          const entry = Object.values(prev).find((r) => r.position === e.position);
          if (!entry) return prev;
          const logEntry: ProbeLogEntry = {
            timestamp: e.timestamp,
            level: e.level,
            logger: e.logger,
            message: e.message,
          };
          const nextLogs = entry.logs.concat(logEntry);
          if (nextLogs.length > MAX_LOG_LINES) {
            nextLogs.splice(0, nextLogs.length - MAX_LOG_LINES);
          }
          return { ...prev, [entry.model]: { ...entry, logs: nextLogs } };
        }),
      onTrajectory: (e) =>
        setModelRows((prev) => {
          const entry = Object.values(prev).find((r) => r.position === e.position);
          if (!entry) return prev;
          const nextTrajectory = entry.trajectory.concat({
            step: e.point.step,
            score: e.point.score,
          });
          return {
            ...prev,
            [entry.model]: {
              ...entry,
              trajectory: nextTrajectory,
              scaling: e.scaling,
            },
          };
        }),
      onResult: (e) =>
        setModelRows((prev) => {
          const existing = prev[e.model];
          const base: ModelRow = existing ?? {
            position: e.position,
            model: e.model,
            label: e.label,
            provider: e.provider,
            status: "pending",
            logs: [],
            score: null,
            scaling: null,
            trajectory: [],
            durationMs: null,
            errorMessage: null,
            startedAt: null,
          };
          return {
            ...prev,
            [e.model]: {
              ...base,
              status: e.status === "ok" ? "done" : "error",
              score: e.score,
              scaling: e.scaling,
              durationMs: e.duration_ms,
              errorMessage: e.message ?? null,
            },
          };
        }),
      onComplete: () => setPhase("done"),
      onError: (message) => {
        setPhase("error");
        setErrorMessage(message);
      },
    });
  };

  const stop = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    reset();
  };

  const allRows = React.useMemo(() => Object.values(modelRows), [modelRows]);
  const completedCount = React.useMemo(
    () => allRows.filter((r) => r.status === "done" || r.status === "error").length,
    [allRows],
  );
  const sortedRows = React.useMemo(() => {
    const rank = (r: ModelRow): number => {
      if (r.status === "running") return 0;
      if (r.status === "done") return 1;
      if (r.status === "pending") return 2;
      return 3;
    };
    return [...allRows].sort((a, b) => {
      const da = rank(a);
      const db = rank(b);
      if (da !== db) return da - db;
      if (a.status === "done" && b.status === "done") {
        return rowRankingScore(b) - rowRankingScore(a);
      }
      return a.position - b.position;
    });
  }, [allRows]);

  const podiumRows = React.useMemo(
    () =>
      [...allRows]
        .filter((r) => r.status === "done" && (r.score !== null || rowAsymptote(r) !== null))
        .sort((a, b) => rowRankingScore(b) - rowRankingScore(a))
        .slice(0, 3),
    [allRows],
  );

  const progressPct = total > 0 ? (completedCount / total) * 100 : 0;
  const expandedRow = expandedModel ? (modelRows[expandedModel] ?? null) : null;

  const tabCls =
    "relative px-2.5 sm:px-4 py-2.5 rounded-none border-b-2 border-transparent " +
    "data-[state=active]:border-transparent data-[state=active]:border-b-primary " +
    "data-[state=active]:text-foreground data-[state=active]:bg-transparent " +
    "data-[state=active]:shadow-none transition-all duration-200 text-xs sm:text-sm";

  const handleSelect = (value: string) => {
    onSelect(value);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[82vh] max-h-[82vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-[min(90vw,1060px)]">
        <DialogHeader className="sr-only">
          <DialogTitle>בדיקת מודלים</DialogTitle>
          <DialogDescription>מריץ אימון קצר על מודלים נבחרים</DialogDescription>
        </DialogHeader>
        {errorMessage && (
          <div className="mx-6 mt-4 flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-[0.75rem] text-destructive">
            <XCircle className="size-4 shrink-0 mt-0.5" />
            <div className="min-w-0 flex-1">
              <p className="font-semibold">שגיאת בדיקה</p>
              <p className="mt-0.5 break-all" dir="ltr">
                {errorMessage}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setErrorMessage(null)}
              className="shrink-0 rounded-md p-0.5 text-destructive/60 hover:text-destructive transition-colors cursor-pointer"
            >
              <X className="size-3.5" />
            </button>
          </div>
        )}
        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-4">
          {phase === "idle" && hasCatalog && (
            <div className="space-y-2 pt-4">
              <div className="flex items-center">
                <Label className="text-xs font-semibold">{TERMS.reflectionModel} משותף</Label>
              </div>
              <div ref={reflectionPickerRef} className="relative">
                <button
                  type="button"
                  onClick={() => setReflectionPickerOpen((o) => !o)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-lg border border-border/50 bg-card/80 px-3 py-2 text-start transition-colors cursor-pointer",
                    "hover:border-primary/40 hover:shadow-sm",
                    reflectionPickerOpen && "border-primary/40 shadow-sm",
                  )}
                  aria-haspopup="listbox"
                  aria-expanded={reflectionPickerOpen}
                >
                  <span className="flex min-w-0 flex-1 flex-col items-start gap-0.5">
                    {selectedReflectionModel ? (
                      <span
                        className="truncate text-sm font-mono font-medium text-foreground"
                        dir="ltr"
                      >
                        {selectedReflectionModel.label}
                      </span>
                    ) : (
                      <span className="truncate text-sm text-muted-foreground" dir="ltr">
                        Select model...
                      </span>
                    )}
                  </span>
                  <ChevronDown
                    className={cn(
                      "size-4 shrink-0 text-muted-foreground transition-transform duration-150",
                      reflectionPickerOpen && "rotate-180",
                    )}
                  />
                </button>
                {reflectionPickerOpen && (
                  <div
                    role="listbox"
                    className="absolute z-50 mt-1 w-full rounded-xl border border-border/70 bg-popover shadow-lg animate-in fade-in-0 zoom-in-95 slide-in-from-top-1"
                  >
                    <div className="sticky top-0 z-10 border-b border-border/40 bg-popover p-2">
                      <div className="relative">
                        <Search className="pointer-events-none absolute top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground left-2.5" />
                        <input
                          value={reflectionSearch}
                          onChange={(e) => setReflectionSearch(e.target.value)}
                          placeholder="Search models..."
                          dir="ltr"
                          className="w-full rounded-md border border-border/60 bg-background py-1.5 pl-8 pr-3 text-xs outline-none placeholder:text-muted-foreground focus:border-primary/40"
                          autoFocus
                          onMouseDown={(e) => e.stopPropagation()}
                        />
                      </div>
                    </div>
                    <div className="max-h-[40vh] overflow-y-auto">
                      {filteredReflectionModels.length === 0 ? (
                        <div className="p-4 text-center text-xs text-muted-foreground">
                          No matching models
                        </div>
                      ) : (
                        Array.from(groupedFilteredReflection.entries()).map(([provider, list]) => (
                          <div key={provider} className="border-b border-border/40 last:border-b-0">
                            <div className="bg-muted/40 px-3 py-1.5 text-[0.6875rem] font-semibold uppercase tracking-wide text-muted-foreground">
                              {provider}
                            </div>
                            {list.map((m) => {
                              const isActive = m.value === reflectionModel;
                              return (
                                <button
                                  key={m.value}
                                  type="button"
                                  onClick={() => {
                                    setReflectionModel(m.value);
                                    setReflectionPickerOpen(false);
                                    setReflectionSearch("");
                                  }}
                                  role="option"
                                  aria-selected={isActive}
                                  className={cn(
                                    "flex w-full items-center gap-2 px-3 py-2 text-start transition-colors cursor-pointer",
                                    isActive ? "bg-primary/10" : "hover:bg-accent/60",
                                  )}
                                >
                                  <Check
                                    className={cn(
                                      "size-3.5 shrink-0 text-primary",
                                      isActive ? "opacity-100" : "opacity-0",
                                    )}
                                  />
                                  <span
                                    className="min-w-0 flex-1 truncate font-mono text-xs"
                                    dir="ltr"
                                  >
                                    {m.label}
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {phase === "idle" && (
            <div className="space-y-3">
              {prerequisiteMessages.length > 0 && (
                <ul className="space-y-1 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-[0.75rem] text-amber-700 dark:text-amber-400">
                  {prerequisiteMessages.map((msg) => (
                    <li key={msg}>• {msg}</li>
                  ))}
                </ul>
              )}

              {hasCatalog && (
                <div className="space-y-3">
                  <div className="relative">
                    <Search className="pointer-events-none absolute top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground start-3" />
                    <Input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Search models..."
                      className="ps-9"
                      dir="ltr"
                    />
                  </div>

                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-semibold">מודלים להרצה</Label>
                    <div className="flex items-center gap-2 text-[0.6875rem]">
                      <span className="text-muted-foreground tabular-nums">
                        {selected.size}/{catalogModels.length}
                      </span>
                      <button
                        type="button"
                        onClick={() => setSelected(smartDefaults(catalogModels))}
                        className="text-primary hover:underline cursor-pointer"
                      >
                        מומלצים
                      </button>
                      <span className="text-muted-foreground/50">·</span>
                      <button
                        type="button"
                        onClick={selectAllVisible}
                        className="text-primary hover:underline cursor-pointer"
                      >
                        בחר הכל
                      </button>
                      <span className="text-muted-foreground/50">·</span>
                      <button
                        type="button"
                        onClick={clearAllSelection}
                        className="text-muted-foreground hover:text-destructive hover:underline cursor-pointer"
                      >
                        נקה
                      </button>
                    </div>
                  </div>

                  <div className="max-h-[min(30vh,280px)] overflow-y-auto rounded-lg border border-border/60 bg-card/50">
                    {filteredModels.length === 0 ? (
                      <div className="p-6 text-center text-xs text-muted-foreground">
                        לא נמצאו מודלים תואמים
                      </div>
                    ) : (
                      <div className="divide-y divide-border/30">
                        {filteredModels.map((m) => {
                          const isSelected = selected.has(m.value);
                          return (
                            <label
                              key={m.value}
                              className={cn(
                                "flex items-center gap-3 px-3 py-2 text-sm cursor-pointer transition-colors",
                                isSelected ? "bg-primary/5" : "hover:bg-accent/40",
                              )}
                            >
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={() => toggleOne(m.value)}
                                className="size-4 shrink-0 cursor-pointer accent-primary"
                              />
                              <span className="min-w-0 flex-1 truncate font-mono text-xs" dir="ltr">
                                {m.label}
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {phase !== "idle" && (
            <div className="space-y-4 pt-8">
              {expandedRow ? (
                <div className="space-y-3">
                  <motion.button
                    type="button"
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    onClick={() => setExpandedModel(null)}
                    className="flex items-center gap-1.5 text-[0.75rem] text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
                  >
                    <ArrowRight className="size-3.5" />
                    חזרה לכל המודלים
                  </motion.button>

                  <div className="flex items-center gap-3 pb-1">
                    <StatusIcon status={expandedRow.status} />
                    <div className="min-w-0 flex-1">
                      <span className="truncate font-mono text-sm font-semibold" dir="ltr">
                        {expandedRow.label}
                      </span>
                    </div>
                  </div>

                  <ModelDetailPanel row={expandedRow} now={now} tabCls={tabCls} />
                </div>
              ) : (
                <>
                  <div className="flex items-center gap-3" dir="rtl">
                    <span className="flex shrink-0 items-center gap-1.5 text-[0.6875rem] text-muted-foreground">
                      {phase === "running" ? (
                        <Loader2 className="size-3 animate-spin text-primary" />
                      ) : phase === "done" ? (
                        <Check className="size-3 text-primary" />
                      ) : phase === "error" ? (
                        <XCircle className="size-3 text-destructive" />
                      ) : null}
                      <span className="font-semibold tabular-nums text-foreground" dir="ltr">
                        {completedCount}/{total || "?"}
                      </span>
                      <span>מודלים</span>
                    </span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted" dir="ltr">
                      <motion.div
                        className="h-full bg-gradient-to-r from-primary/60 to-primary"
                        initial={{ width: 0 }}
                        animate={{ width: `${progressPct}%` }}
                        transition={{ duration: 0.4, ease: [0.2, 0.8, 0.2, 1] }}
                      />
                    </div>
                  </div>

                  <AnimatePresence>
                    {phase === "done" && podiumRows.length > 0 && (
                      <motion.div
                        key="podium"
                        initial={{ opacity: 0, y: -12 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                        transition={{ duration: 0.4, ease: [0.2, 0.8, 0.2, 1] }}
                        className="space-y-2"
                      >
                        <Label className="flex items-center gap-1.5 text-[0.6875rem] font-semibold uppercase tracking-wide text-muted-foreground">
                          <Trophy className="size-3 text-primary" />
                          שלושת המובילים
                        </Label>
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                          {podiumRows.map((row, idx) => (
                            <PodiumCard
                              key={row.model}
                              row={row}
                              rank={idx + 1}
                              onSelect={handleSelect}
                            />
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  <div className="max-h-[min(40vh,360px)] overflow-y-auto">
                    <motion.ul layout className="space-y-2">
                      <AnimatePresence initial={false}>
                        {sortedRows.map((row) => (
                          <RaceRow
                            key={row.model}
                            row={row}
                            now={now}
                            onNavigate={() => setExpandedModel(row.model)}
                            onSelect={handleSelect}
                          />
                        ))}
                      </AnimatePresence>
                    </motion.ul>
                  </div>

                  {allRows.filter((r) => r.trajectory.length > 0).length >= 2 && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Label className="flex items-center gap-1.5 text-[0.6875rem] font-semibold uppercase tracking-wide text-muted-foreground">
                          <Sparkles className="size-3 text-primary" />
                          השוואה בין מודלים
                        </Label>
                      </div>
                      <div className="rounded-lg border border-border/60 bg-card/50 p-3">
                        <TrajectoryCompareChart rows={allRows} />
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        <div className="border-t border-border/60 bg-card/80 px-6 py-3">
          {phase === "running" ? (
            <Button variant="destructive" onClick={stop} className="w-full gap-1.5">
              <XCircle className="size-4" />
              בטל ונקה
            </Button>
          ) : phase === "done" || phase === "error" ? (
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={() => reset()} className="flex-1 gap-1.5">
                <Play className="size-4 fill-current" />
                הרץ שוב
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  reset();
                  onOpenChange(false);
                }}
                className="gap-1.5 text-muted-foreground"
              >
                <Trash2 className="size-3.5" />
                נקה
              </Button>
            </div>
          ) : (
            <Button onClick={start} disabled={!canStart} className="w-full gap-1.5">
              <Play className="size-4 fill-current" />
              התחל בדיקה
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function TrajectorySparkline({
  points,
  asymptote,
  width = 120,
  height = 32,
  color = "currentColor",
}: {
  points: TrajectoryPoint[];
  asymptote: number | null;
  width?: number;
  height?: number;
  color?: string;
}) {
  if (points.length === 0) return null;
  const w = width;
  const h = height;
  const pad = 4;
  const scores = points.map((p) => p.score);
  const minY = Math.min(...scores, asymptote ?? Infinity);
  const maxY = Math.max(...scores, asymptote ?? -Infinity);
  const range = maxY - minY || 1;
  const n = points.length;
  const xAt = (i: number) => (n <= 1 ? w / 2 : pad + (i / (n - 1)) * (w - 2 * pad));
  const yAt = (v: number) => h - pad - ((v - minY) / range) * (h - 2 * pad);
  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xAt(i).toFixed(1)} ${yAt(p.score).toFixed(1)}`)
    .join(" ");
  const last = points[points.length - 1]!;
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      width={w}
      height={h}
      className="overflow-visible"
      aria-hidden="true"
    >
      {asymptote !== null && (
        <line
          x1={pad}
          x2={w - pad}
          y1={yAt(asymptote)}
          y2={yAt(asymptote)}
          stroke={color}
          strokeWidth={1}
          strokeDasharray="2 3"
          opacity={0.45}
        />
      )}
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {points.map((p, i) => (
        <circle key={i} cx={xAt(i)} cy={yAt(p.score)} r={i === n - 1 ? 2.5 : 1.5} fill={color} />
      ))}
    </svg>
  );
}

function ProbeChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; name: string; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-background p-3 shadow-md text-sm" dir="rtl">
      <p className="font-medium mb-1.5">
        צעד{" "}
        <span dir="ltr" className="font-mono">
          #{label}
        </span>
      </p>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="size-2.5 rounded-full shrink-0" style={{ backgroundColor: p.color }} />
          <span className="text-muted-foreground">{p.name}:</span>
          <span className="font-mono font-bold ms-auto" dir="ltr">
            {p.value.toFixed(1)}
          </span>
        </div>
      ))}
    </div>
  );
}

function TrajectoryDetailChart({
  points,
  asymptote,
}: {
  points: TrajectoryPoint[];
  asymptote: number | null;
  color?: string;
}) {
  const bsf = bestSoFar(points);
  const data = points.map((p, i) => ({
    step: p.step,
    score: p.score,
    best: bsf[i]?.score ?? p.score,
  }));

  return (
    <div dir="ltr" className="h-[340px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 10, left: 5, bottom: 18 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
          <XAxis
            dataKey="step"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 10 }}
            className="fill-muted-foreground"
            label={{
              value: "צעד",
              position: "insideBottom",
              offset: -12,
              fontSize: 10,
              fill: "var(--muted-foreground)",
            }}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 10 }}
            className="fill-muted-foreground"
            label={{
              value: "ציון",
              angle: -90,
              position: "insideLeft",
              offset: 10,
              fontSize: 10,
              fill: "var(--muted-foreground)",
            }}
            domain={[0, "auto"]}
          />
          <RechartsTooltip content={<ProbeChartTooltip />} />
          {asymptote !== null && (
            <ReferenceLine
              y={asymptote}
              stroke="var(--color-chart-2)"
              strokeDasharray="4 3"
              strokeOpacity={0.55}
            />
          )}
          <RLine
            type="monotone"
            dataKey="score"
            name="ציון"
            stroke="var(--color-chart-4)"
            strokeWidth={1.5}
            dot={{
              r: 3.5,
              strokeWidth: 1.5,
              stroke: "var(--color-chart-4)",
              fill: "var(--background, #fff)",
            }}
            activeDot={{
              r: 5,
              strokeWidth: 2,
              stroke: "var(--color-chart-4)",
              fill: "var(--background, #fff)",
            }}
            isAnimationActive={false}
          />
          <RLine
            type="stepAfter"
            dataKey="best"
            name="שיא"
            stroke="var(--color-chart-2)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function TrajectoryCompareChart({ rows }: { rows: ModelRow[] }) {
  const [soloModel, setSoloModel] = React.useState<string | null>(null);
  const [hovered, setHovered] = React.useState<{
    label: string;
    step: number;
    score: number;
    x: number;
    y: number;
  } | null>(null);
  const svgRef = React.useRef<SVGSVGElement>(null);

  const allSeries = rows
    .filter((r) => r.trajectory.length > 0)
    .map((r) => ({
      model: r.model,
      label: r.label,
      color: rowColor(r),
      points: bestSoFar(r.trajectory),
      raw: r.trajectory,
      asymptote:
        r.scaling?.signal === "strong" || r.scaling?.signal === "observed"
          ? (r.scaling?.asymptote ?? null)
          : null,
    }));
  if (allSeries.length === 0) return null;

  const toggleSolo = (model: string) => setSoloModel((prev) => (prev === model ? null : model));

  const series = soloModel ? allSeries.filter((s) => s.model === soloModel) : allSeries;

  const w = 800;
  const h = 240;
  const padX = 46;
  const padTop = 16;
  const padBottom = 44;
  const innerW = w - padX * 2;
  const innerH = h - padTop - padBottom;

  const allScores = series.flatMap((s) => s.points.map((p) => p.score));
  const allAsymptotes = series.map((s) => s.asymptote).filter((v): v is number => v !== null);
  const minY = Math.min(...allScores, ...allAsymptotes);
  const maxY = Math.max(...allScores, ...allAsymptotes);
  const yRange = maxY - minY || 1;
  const maxLen = Math.max(...series.map((s) => s.points.length));
  const yAt = (v: number) => padTop + innerH - ((v - minY) / yRange) * innerH;
  const xAt = (i: number) => (maxLen <= 1 ? w / 2 : padX + (i / (maxLen - 1)) * innerW);

  const tickCount = 4;
  const ticks = Array.from({ length: tickCount + 1 }, (_, i) => minY + (yRange * i) / tickCount);

  return (
    <div dir="ltr" className="space-y-2">
      <div className="relative">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${w} ${h}`}
          className="h-[240px] w-full"
          preserveAspectRatio="xMidYMid meet"
          aria-hidden="true"
          onMouseLeave={() => setHovered(null)}
        >
          {ticks.map((t, i) => (
            <g key={i}>
              <line
                x1={padX}
                x2={w - padX}
                y1={yAt(t)}
                y2={yAt(t)}
                stroke="currentColor"
                strokeWidth={0.5}
                strokeDasharray="2 4"
                className="text-muted-foreground/30"
              />
              <text
                x={padX - 6}
                y={yAt(t) + 3}
                textAnchor="end"
                className="fill-muted-foreground text-[9px] font-mono tabular-nums"
              >
                {t.toFixed(1)}
              </text>
            </g>
          ))}

          {Array.from({ length: Math.min(maxLen, 12) }, (_, i) => {
            const step = maxLen <= 12 ? i : Math.round((i / 11) * (maxLen - 1));
            return (
              <text
                key={step}
                x={xAt(step)}
                y={h - 22}
                textAnchor="middle"
                className="fill-muted-foreground text-[9px] font-mono tabular-nums"
              >
                {step}
              </text>
            );
          })}

          <text
            x={w / 2}
            y={h - 4}
            textAnchor="middle"
            className="fill-muted-foreground text-[10px]"
          >
            צעד
          </text>
          <text
            x={12}
            y={padTop + innerH / 2}
            textAnchor="middle"
            transform={`rotate(-90, 12, ${padTop + innerH / 2})`}
            className="fill-muted-foreground text-[10px]"
          >
            ציון
          </text>

          {series.map((s) => {
            if (s.points.length === 0) return null;
            const path = s.points
              .map(
                (p, i) => `${i === 0 ? "M" : "L"} ${xAt(i).toFixed(1)} ${yAt(p.score).toFixed(1)}`,
              )
              .join(" ");
            const last = s.points[s.points.length - 1]!;
            return (
              <g key={s.model}>
                {s.asymptote !== null && (
                  <line
                    x1={padX}
                    x2={w - padX}
                    y1={yAt(s.asymptote)}
                    y2={yAt(s.asymptote)}
                    stroke={s.color}
                    strokeWidth={0.75}
                    strokeDasharray="3 3"
                    opacity={0.4}
                  />
                )}
                <path
                  d={path}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                {s.points.map((p, i) => {
                  const isLast = i === s.points.length - 1;
                  return (
                    <g key={i}>
                      <circle
                        cx={xAt(i)}
                        cy={yAt(p.score)}
                        r={isLast ? 3.5 : 2}
                        fill={s.color}
                        opacity={isLast ? 1 : 0.5}
                        stroke={isLast ? "var(--background, #fff)" : undefined}
                        strokeWidth={isLast ? 1.5 : undefined}
                      />
                      <circle
                        cx={xAt(i)}
                        cy={yAt(p.score)}
                        r={isLast ? 10 : 8}
                        fill="transparent"
                        className="cursor-pointer"
                        onClick={() => toggleSolo(s.model)}
                        onMouseEnter={() => {
                          const svg = svgRef.current;
                          if (!svg) return;
                          const rect = svg.getBoundingClientRect();
                          const px = (xAt(i) / w) * rect.width;
                          const py = (yAt(p.score) / h) * rect.height;
                          setHovered({
                            label: s.label,
                            step: p.step,
                            score: p.score,
                            x: px,
                            y: py,
                          });
                        }}
                        onMouseLeave={() => setHovered(null)}
                      />
                    </g>
                  );
                })}
              </g>
            );
          })}
        </svg>
        {hovered &&
          (() => {
            const flipBelow = hovered.y < 40;
            return (
              <div
                className="pointer-events-none absolute z-10 max-w-[180px] rounded-md border border-border/60 bg-popover px-2.5 py-1.5 text-xs shadow-md"
                style={{
                  left: `clamp(70px, ${hovered.x}px, calc(100% - 70px))`,
                  top: hovered.y,
                  transform: flipBelow
                    ? "translate(-50%, 16px)"
                    : "translate(-50%, calc(-100% - 10px))",
                }}
              >
                <div className="truncate font-mono font-semibold" dir="ltr">
                  {hovered.label}
                </div>
                <div className="text-muted-foreground tabular-nums" dir="rtl">
                  צעד <span dir="ltr">{hovered.step}</span> ·{" "}
                  <span className="font-semibold text-foreground" dir="ltr">
                    {hovered.score.toFixed(1)}
                  </span>
                </div>
              </div>
            );
          })()}
      </div>

      <div
        dir="rtl"
        className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-[0.6875rem]"
      >
        {allSeries.map((s) => {
          const dimmed = soloModel !== null && soloModel !== s.model;
          return (
            <div
              key={s.model}
              className={cn(
                "flex items-center gap-1.5 cursor-pointer transition-opacity select-none",
                dimmed && "opacity-30",
              )}
              onClick={() => toggleSolo(s.model)}
              title={s.label}
            >
              <span
                className="inline-block h-2 w-2 shrink-0 self-start mt-1 rounded-full"
                style={{ backgroundColor: s.color }}
              />
              <span className="flex flex-col items-center min-w-0">
                <span className="max-w-[120px] truncate font-mono text-muted-foreground" dir="ltr">
                  {s.label}
                </span>
                {s.asymptote !== null && (
                  <span
                    className="font-mono text-[0.625rem] tabular-nums text-foreground"
                    dir="ltr"
                  >
                    {s.asymptote.toFixed(1)}
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ModelDetailPanel({ row, now, tabCls }: { row: ModelRow; now: number; tabCls: string }) {
  const elapsed =
    row.status === "running" && row.startedAt !== null
      ? now - row.startedAt
      : (row.durationMs ?? 0);

  const logScrollRef = React.useRef<HTMLDivElement>(null);
  const logFilters = useColumnFilters();
  const logResize = useColumnResize();
  const [logSortKey, setLogSortKey] = React.useState<string>("timestamp");
  const [logSortDir, setLogSortDir] = React.useState<SortDir>("desc");
  const toggleLogSort = (key: string) => {
    if (logSortKey === key) setLogSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setLogSortKey(key);
      setLogSortDir("asc");
    }
  };

  const filteredLogs = React.useMemo(() => {
    let result = row.logs.filter((l) => {
      for (const [col, allowed] of Object.entries(logFilters.filters)) {
        if (allowed.size === 0) continue;
        const val =
          col === "timestamp"
            ? logTimeBucket(l.timestamp)
            : String((l as unknown as Record<string, unknown>)[col] ?? "");
        if (!allowed.has(val)) return false;
      }
      return true;
    });
    result = [...result].sort((a, b) => {
      const av = String((a as unknown as Record<string, unknown>)[logSortKey] ?? "");
      const bv = String((b as unknown as Record<string, unknown>)[logSortKey] ?? "");
      const cmp = av.localeCompare(bv, "he", { numeric: true });
      return logSortDir === "asc" ? cmp : -cmp;
    });
    return result;
  }, [row.logs, logFilters.filters, logSortKey, logSortDir]);

  const logFilterOptions = React.useMemo(() => {
    const unique = (key: keyof ProbeLogEntry) =>
      [...new Set(row.logs.map((l) => l[key]))]
        .filter(Boolean)
        .sort()
        .map((v) => ({ value: v, label: v }));
    const timestampBuckets = [...new Set(row.logs.map((l) => logTimeBucket(l.timestamp)))]
      .filter(Boolean)
      .sort()
      .map((v) => ({ value: v, label: v }));
    return { timestamp: timestampBuckets, level: unique("level"), logger: unique("logger") };
  }, [row.logs]);

  const liveAsymptote =
    (row.scaling?.signal === "strong" || row.scaling?.signal === "observed") &&
    row.scaling?.asymptote != null
      ? row.scaling.asymptote
      : null;
  const liveLast = row.trajectory.length ? row.trajectory[row.trajectory.length - 1]!.score : null;
  const livePrediction = liveAsymptote ?? liveLast;

  const signalLabel =
    row.scaling?.signal === "strong"
      ? msg("submit.probe.asymptote_label")
      : row.scaling?.signal === "observed"
        ? msg("submit.probe.observed_label")
        : msg("submit.probe.signal_weak");

  React.useEffect(() => {
    const el = logScrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [row.logs.length]);

  return (
    <Tabs defaultValue="overview" className="gap-3" dir="rtl">
      <TabsList variant="line" className="w-full border-b border-border/50 pb-0 gap-0">
        <TabsTrigger value="overview" className={cn(tabCls, "flex-1")}>
          {msg("submit.probe.details.title")}
        </TabsTrigger>
        <TabsTrigger value="logs" className={cn(tabCls, "flex-1")}>
          {msg("submit.probe.details.logs")}
        </TabsTrigger>
      </TabsList>

      <TabsContent value="overview" className="space-y-4 mt-4">
        <FadeIn>
          <div
            className="grid gap-2.5"
            style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(120px, 100%), 1fr))" }}
          >
            <ProbeInfoCard
              icon={<TrendingUp className="size-3.5" />}
              label={signalLabel}
              value={
                livePrediction !== null ? (
                  <span className="font-mono tabular-nums" dir="ltr">
                    {livePrediction.toFixed(1)}
                  </span>
                ) : (
                  "—"
                )
              }
            />
            <ProbeInfoCard
              icon={<Activity className="size-3.5" />}
              label={msg("submit.probe.details.points_count")}
              value={row.trajectory.length.toString()}
            />
            <ProbeInfoCard
              icon={<Timer className="size-3.5" />}
              label="זמן ריצה"
              value={
                <span className="font-mono tabular-nums" dir="ltr">
                  {(elapsed / 1000).toFixed(1)}s
                </span>
              }
            />
          </div>
          {row.trajectory.length > 0 ? (
            <>
              <TrajectoryDetailChart points={row.trajectory} asymptote={liveAsymptote} />
            </>
          ) : null}
        </FadeIn>
      </TabsContent>

      <TabsContent value="logs" className="mt-4">
        <FadeIn>
          {row.logs.length > 0 ? (
            <Card>
              <CardContent className="p-0">
                <div ref={logScrollRef} dir="ltr" className="max-h-[400px] overflow-auto">
                  <Table className="table-fixed w-full">
                    <colgroup>
                      <col style={{ width: logResize.widths["timestamp"] ?? "15%" }} />
                      <col style={{ width: logResize.widths["level"] ?? "12%" }} />
                      <col style={{ width: logResize.widths["logger"] ?? "17%" }} />
                      <col />
                    </colgroup>
                    <TableHeader>
                      <TableRow>
                        <ColumnHeader
                          label="זמן"
                          sortKey="timestamp"
                          currentSort={logSortKey}
                          sortDir={logSortDir}
                          onSort={toggleLogSort}
                          filterCol="timestamp"
                          filterOptions={logFilterOptions.timestamp}
                          filters={logFilters.filters}
                          onFilter={logFilters.setColumnFilter}
                          openFilter={logFilters.openFilter}
                          setOpenFilter={logFilters.setOpenFilter}
                          width={logResize.widths["timestamp"]}
                          onResize={logResize.setColumnWidth}
                        />
                        <ColumnHeader
                          label="רמה"
                          sortKey="level"
                          currentSort={logSortKey}
                          sortDir={logSortDir}
                          onSort={toggleLogSort}
                          filterCol="level"
                          filterOptions={logFilterOptions.level}
                          filters={logFilters.filters}
                          onFilter={logFilters.setColumnFilter}
                          openFilter={logFilters.openFilter}
                          setOpenFilter={logFilters.setOpenFilter}
                          width={logResize.widths["level"]}
                          onResize={logResize.setColumnWidth}
                        />
                        <ColumnHeader
                          label="לוגר"
                          sortKey="logger"
                          currentSort={logSortKey}
                          sortDir={logSortDir}
                          onSort={toggleLogSort}
                          filterCol="logger"
                          filterOptions={logFilterOptions.logger}
                          filters={logFilters.filters}
                          onFilter={logFilters.setColumnFilter}
                          openFilter={logFilters.openFilter}
                          setOpenFilter={logFilters.setOpenFilter}
                          width={logResize.widths["logger"]}
                          onResize={logResize.setColumnWidth}
                        />
                        <ColumnHeader
                          label="הודעה"
                          sortKey="message"
                          currentSort={logSortKey}
                          sortDir={logSortDir}
                          onSort={toggleLogSort}
                          width={logResize.widths["message"]}
                          onResize={logResize.setColumnWidth}
                        />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredLogs.slice(0, 300).map((log, i) => (
                        <TableRow
                          key={i}
                          className="cursor-pointer"
                          onClick={(e) => {
                            const td = (e.target as HTMLElement).closest("td");
                            if (!td) return;
                            const text = td.textContent?.trim();
                            if (text) {
                              navigator.clipboard.writeText(text);
                              toast.success(msg("clipboard.copied"));
                            }
                          }}
                        >
                          <TableCell
                            className="text-xs font-mono text-muted-foreground truncate overflow-hidden"
                            style={
                              logResize.widths["timestamp"]
                                ? {
                                    width: logResize.widths["timestamp"],
                                    maxWidth: logResize.widths["timestamp"],
                                  }
                                : undefined
                            }
                            dir="ltr"
                          >
                            {formatLogTimestamp(log.timestamp)}
                          </TableCell>
                          <TableCell
                            className="truncate overflow-hidden"
                            style={
                              logResize.widths["level"]
                                ? {
                                    width: logResize.widths["level"],
                                    maxWidth: logResize.widths["level"],
                                  }
                                : undefined
                            }
                          >
                            <Badge
                              variant={
                                log.level === "ERROR"
                                  ? "destructive"
                                  : log.level === "WARNING"
                                    ? "outline"
                                    : "secondary"
                              }
                              className="text-[0.625rem] font-mono"
                            >
                              {log.level}
                            </Badge>
                          </TableCell>
                          <TableCell
                            className="text-xs font-mono text-muted-foreground truncate overflow-hidden"
                            style={
                              logResize.widths["logger"]
                                ? {
                                    width: logResize.widths["logger"],
                                    maxWidth: logResize.widths["logger"],
                                  }
                                : undefined
                            }
                            title={log.logger}
                          >
                            {log.logger}
                          </TableCell>
                          <TableCell
                            className="text-xs font-mono whitespace-pre-wrap break-all overflow-hidden hover:underline"
                            style={
                              logResize.widths["message"]
                                ? {
                                    width: logResize.widths["message"],
                                    maxWidth: logResize.widths["message"],
                                  }
                                : undefined
                            }
                            title={log.message}
                          >
                            {log.message}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                    {filteredLogs.length > 300 && (
                      <tfoot>
                        <tr>
                          <td
                            colSpan={4}
                            className="text-center py-3 text-[0.625rem] text-muted-foreground"
                          >
                            מוצגות 300 מתוך {filteredLogs.length} רשומות
                          </td>
                        </tr>
                      </tfoot>
                    )}
                  </Table>
                </div>
              </CardContent>
            </Card>
          ) : (
            <div className="flex h-[80px] items-center justify-center rounded-md border border-dashed border-border/40 text-[0.6875rem] text-muted-foreground">
              עדיין אין לוגים
            </div>
          )}
        </FadeIn>
      </TabsContent>
    </Tabs>
  );
}

function RaceRow({
  row,
  now,
  onNavigate,
  onSelect,
}: {
  row: ModelRow;
  now: number;
  onNavigate: () => void;
  onSelect: (value: string) => void;
}) {
  const elapsed =
    row.status === "running" && row.startedAt !== null
      ? now - row.startedAt
      : (row.durationMs ?? 0);

  const color = rowColor(row);
  const isNavigable =
    (row.status === "running" || row.status === "done") &&
    row.trajectory.length + row.logs.length > 0;

  const liveAsymptote =
    (row.scaling?.signal === "strong" || row.scaling?.signal === "observed") &&
    row.scaling?.asymptote != null
      ? row.scaling.asymptote
      : null;
  const liveLast = row.trajectory.length ? row.trajectory[row.trajectory.length - 1]!.score : null;
  const livePrediction = liveAsymptote ?? liveLast;

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25, ease: [0.2, 0.8, 0.2, 1] }}
      className={cn(
        "rounded-lg border bg-card/60 ps-3 pe-3 py-2.5 transition-colors",
        row.status === "running" && "border-primary/40 shadow-sm",
        row.status === "done" && "border-border/60",
        row.status === "error" && "border-destructive/30 bg-destructive/5",
        row.status === "pending" && "border-border/40 opacity-70",
        isNavigable && "cursor-pointer hover:bg-accent/40",
      )}
      style={
        row.status === "done"
          ? { borderInlineStartColor: color, borderInlineStartWidth: 3 }
          : undefined
      }
      onClick={isNavigable ? onNavigate : undefined}
      role={isNavigable ? "button" : undefined}
      tabIndex={isNavigable ? 0 : undefined}
      onKeyDown={
        isNavigable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onNavigate();
              }
            }
          : undefined
      }
    >
      <div className="flex items-center gap-3">
        <StatusIcon status={row.status} />
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-center gap-3">
            <div className="min-w-0 flex-1 flex items-center gap-2">
              <span className="truncate font-mono text-xs font-semibold" dir="ltr">
                {row.label}
              </span>
              {row.status === "error" && row.errorMessage && (
                <span className="truncate text-[0.6875rem] text-destructive" dir="ltr">
                  {row.errorMessage}
                </span>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-3 text-xs">
              {(row.status === "running" || row.status === "done") && row.trajectory.length > 0 && (
                <div className={cn(row.status === "running" && "opacity-80")}>
                  <TrajectorySparkline
                    points={row.trajectory}
                    asymptote={liveAsymptote}
                    width={72}
                    height={22}
                    color={color}
                  />
                </div>
              )}
              {row.status === "done" && <RowScoreDisplay row={row} />}
              {row.status === "running" && livePrediction !== null && (
                <span
                  className="font-mono text-[0.6875rem] tabular-nums text-foreground/80"
                  dir="ltr"
                >
                  ≈{livePrediction.toFixed(1)}
                </span>
              )}
              {(row.status === "running" || row.status === "done") && (
                <span
                  className={cn(
                    "font-mono text-[0.6875rem] tabular-nums",
                    row.status === "running" ? "text-primary" : "text-muted-foreground",
                  )}
                  dir="ltr"
                >
                  {(elapsed / 1000).toFixed(1)}s
                </span>
              )}
              {row.status === "done" && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 px-2 text-[0.6875rem]"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelect(row.model);
                  }}
                >
                  בחר
                </Button>
              )}
              {row.status === "error" && (
                <span className="font-mono text-[0.6875rem] text-destructive">שגיאה</span>
              )}
              {row.status === "pending" && (
                <span className="font-mono text-[0.6875rem] text-muted-foreground">ממתינה</span>
              )}
              {isNavigable && (
                <ArrowRight
                  className="size-3.5 shrink-0 text-muted-foreground/60 rtl:rotate-180"
                  aria-hidden="true"
                />
              )}
            </div>
          </div>
          {row.status === "running" && (
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <motion.div
                className="h-full bg-gradient-to-l from-primary/60 to-primary"
                initial={{ width: 0 }}
                animate={{
                  width:
                    row.trajectory.length > 0
                      ? `${Math.min((row.trajectory.length / 10) * 100, 95)}%`
                      : "15%",
                }}
                transition={{ duration: 0.4, ease: [0.2, 0.8, 0.2, 1] }}
              />
            </div>
          )}
        </div>
      </div>
    </motion.li>
  );
}

function ProbeInfoCard({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="group rounded-lg border border-[#E3DCD0] bg-[#FBF9F4] px-3.5 py-3 transition-[border-color,box-shadow] duration-200 hover:border-[#C8A882]/55 hover:shadow-[0_2px_8px_-2px_rgba(124,99,80,0.1)]">
      <div className="flex items-center gap-1.5 mb-1.5">
        <span
          className="shrink-0 inline-flex items-center justify-center size-3.5 text-[#A89680] transition-colors duration-200 group-hover:text-[#7C6350]"
          aria-hidden="true"
        >
          {icon}
        </span>
        <p className="text-[0.625rem] font-semibold tracking-[0.08em] uppercase text-[#A89680] truncate">
          {label}
        </p>
      </div>
      <p className="text-sm font-semibold text-[#1C1612] truncate">
        {value ?? <span className="text-[#BFB3A3] font-normal">—</span>}
      </p>
    </div>
  );
}

function RowScoreDisplay({ row }: { row: ModelRow }) {
  const value = rowAsymptote(row) ?? row.score;
  if (value === null)
    return <span className="font-mono font-bold tabular-nums text-foreground">—</span>;
  return (
    <span className="font-mono font-bold tabular-nums text-foreground">
      <AnimatedNumber value={value} decimals={1} duration={0.5} />
    </span>
  );
}

function PodiumScore({ row }: { row: ModelRow }) {
  const displayValue = rowAsymptote(row) ?? row.score;
  return (
    <span className="font-mono text-lg font-bold tabular-nums text-foreground">
      {displayValue !== null ? (
        <AnimatedNumber value={displayValue} decimals={1} duration={0.8} />
      ) : (
        "—"
      )}
    </span>
  );
}

function StatusIcon({ status }: { status: RowStatus }) {
  if (status === "running")
    return (
      <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Loader2 className="size-3.5 animate-spin" />
      </span>
    );
  if (status === "done")
    return (
      <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
        <Check className="size-3.5" />
      </span>
    );
  if (status === "error")
    return (
      <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-destructive/15 text-destructive">
        <XCircle className="size-3.5" />
      </span>
    );
  return (
    <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
      <Circle className="size-3.5" />
    </span>
  );
}

/* ── Podium card (top-3 with medal + AnimatedNumber) ── */
function PodiumCard({
  row,
  rank,
  onSelect,
}: {
  row: ModelRow;
  rank: number;
  onSelect: (value: string) => void;
}) {
  const palette: Record<number, { badge: string; icon: React.ReactNode }> = {
    1: { badge: "bg-amber-500 text-white", icon: <Crown className="size-3" /> },
    2: { badge: "bg-slate-400 text-white", icon: <Medal className="size-3" /> },
    3: { badge: "bg-orange-400 text-white", icon: <Medal className="size-3" /> },
  };
  const p = palette[rank] ?? palette[3]!;

  return (
    <TiltCard className="rounded-xl border border-border/60 bg-card/50 p-3">
      <div className="flex items-start justify-between gap-2">
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.625rem] font-bold",
            p.badge,
          )}
        >
          {p.icon}
          <span dir="ltr">#{rank}</span>
        </span>
      </div>
      <div className="mt-2 truncate font-mono text-xs font-semibold" dir="ltr">
        {row.label}
      </div>
      {row.trajectory.length > 0 && (
        <div className="mt-1.5 flex justify-center opacity-70">
          <TrajectorySparkline
            points={row.trajectory}
            asymptote={rowAsymptote(row)}
            width={100}
            height={24}
            color={rowColor(row)}
          />
        </div>
      )}
      <div className="mt-1.5 flex items-baseline justify-between">
        <PodiumScore row={row} />
        {row.durationMs !== null && (
          <span className="font-mono text-[0.625rem] tabular-nums text-muted-foreground">
            {(row.durationMs / 1000).toFixed(1)}s
          </span>
        )}
      </div>
      <Separator className="my-2" />
      <Button
        size="sm"
        variant="outline"
        className="h-7 w-full text-[0.6875rem]"
        onClick={() => onSelect(row.model)}
      >
        בחר
      </Button>
    </TiltCard>
  );
}
