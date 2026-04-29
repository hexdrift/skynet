"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronDown,
  XCircle,
  Trophy,
  Cpu,
  Database,
  Layers,
  ListChecks,
  Sparkles,
  Clipboard,
  Check,
  X,
  BarChart3,
  Clock,
  TrendingUp,
  GitCompareArrows,
} from "lucide-react";
import {
  Tooltip as UiTooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/shared/ui/primitives/tooltip";
import { Button } from "@/shared/ui/primitives/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/primitives/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/primitives/tabs";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartTooltip } from "@/shared/charts/chart-utils";
import { AnimatePresence, motion } from "framer-motion";
import { FadeIn } from "@/shared/ui/motion";
import {
  getJob,
  getTestResults,
  getPairTestResults,
  getOptimizationDataset,
} from "@/shared/lib/api";
import type {
  EvalExampleResult,
  OptimizationDatasetResponse,
  OptimizationStatusResponse,
  OptimizedPredictor,
} from "@/shared/types/api";
import { Skeleton } from "boneyard-js/react";
import { compareBones } from "../lib/bones";
import { HelpTip } from "@/shared/ui/help-tip";
import { tip } from "@/shared/lib/tooltips";
import {
  consumePendingCompareDemo,
  consumePendingCompareExamples,
  registerTutorialHook,
} from "@/features/tutorial";
import { formatMsg, msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";
import {
  RunChip,
  bestIndexOf,
  colorFor,
  deriveRunInfo,
  fmt,
  fmtElapsed,
  fmtImprovement,
  fmtLatency,
  isRowTie,
  runToken,
  winnerIndexOf,
  type RunInfo,
} from "./compare-model";

const WINNER_TINT = "rgba(61, 46, 34, 0.085)";
// Cubic-bezier matches the snappy curve in globals.css (`--ease-snappy`).
const EASE_SNAPPY = [0.2, 0.8, 0.2, 1] as const;

function VerdictBlock({ runs, winnerIdx }: { runs: RunInfo[]; winnerIdx: number | null }) {
  const winner = winnerIdx != null ? runs[winnerIdx] : null;

  if (!winner) {
    return (
      <FadeIn>
        <Card>
          <CardContent className="py-5">
            <p className="text-sm text-muted-foreground">{msg("auto.app.compare.page.1")}</p>
          </CardContent>
        </Card>
      </FadeIn>
    );
  }

  const stats: Array<{
    key: string;
    label: string;
    tooltip: string;
    icon: React.ReactNode;
    value: React.ReactNode;
    tone?: "primary";
  }> = [];
  if (winner.improvement != null) {
    stats.push({
      key: "improvement",
      label: msg("auto.app.compare.page.literal.3"),
      tooltip: tip("compare.winner_improvement"),
      icon: <TrendingUp className="size-3 text-primary/70 shrink-0" />,
      value: fmtImprovement(winner.improvement),
      tone: "primary",
    });
  }
  if (winner.runtime != null) {
    stats.push({
      key: "runtime",
      label: msg("auto.app.compare.page.literal.4"),
      tooltip: tip("compare.winner_runtime"),
      icon: <Clock className="size-3 text-muted-foreground/70 shrink-0" />,
      value: fmtElapsed(winner.runtime),
    });
  }
  const modelDisplay = winner.pairLabel ?? winner.modelName;
  if (modelDisplay) {
    stats.push({
      key: "models",
      label: winner.pairLabel
        ? msg("auto.app.compare.page.literal.5")
        : msg("auto.app.compare.page.literal.6"),
      tooltip: tip("compare.winner_models"),
      icon: <Cpu className="size-3 text-muted-foreground/70 shrink-0" />,
      value: (
        <span
          className="block truncate font-mono text-sm text-foreground/90"
          dir="ltr"
          title={modelDisplay}
        >
          {modelDisplay}
        </span>
      ),
    });
  }
  return (
    <FadeIn>
      <div className="space-y-3" data-tutorial="compare-verdict">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-5 rounded-xl border border-border/50 bg-card px-4 sm:px-5 py-3">
          <div className="flex items-center gap-2.5 min-w-0 flex-1">
            <Trophy className="size-4 text-primary shrink-0" />
            <span className="text-[0.625rem] font-semibold text-muted-foreground uppercase tracking-[0.14em] shrink-0">
              {msg("auto.app.compare.page.2")}
            </span>
            <RunChip index={winnerIdx!} label={winner.label} winner size="md" />
          </div>
          <UiTooltip>
            <TooltipTrigger asChild>
              <Button
                asChild
                size="icon-sm"
                variant="default"
                className="shrink-0 self-start sm:self-auto"
              >
                <Link
                  href={`/optimizations/${winner.job.optimization_id}`}
                  aria-label={formatMsg("auto.app.compare.page.template.1", {
                    p1: TERMS.optimization,
                  })}
                >
                  <ChevronLeft className="size-3.5" />
                </Link>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top" sideOffset={6}>
              {msg("auto.app.compare.page.3")}
              {TERMS.optimization}
            </TooltipContent>
          </UiTooltip>
        </div>

        {stats.length > 0 && (
          <div
            className="grid gap-3"
            style={{
              gridTemplateColumns: `repeat(auto-fit, minmax(${stats.length > 2 ? 160 : 200}px, 1fr))`,
            }}
          >
            {stats.map((stat) => (
              <div
                key={stat.key}
                className={`rounded-xl border px-4 py-3 ${
                  stat.tone === "primary"
                    ? "border-primary/25 bg-primary/[0.04]"
                    : "border-border/50 bg-card"
                }`}
              >
                <div className="flex items-center gap-1.5">
                  {stat.icon}
                  <HelpTip text={stat.tooltip}>
                    <span className="text-[0.625rem] font-semibold text-muted-foreground uppercase tracking-[0.14em]">
                      {stat.label}
                    </span>
                  </HelpTip>
                </div>
                <div
                  className={`mt-1 font-mono tabular-nums text-lg ${
                    stat.tone === "primary" ? "font-bold text-primary" : "text-foreground"
                  }`}
                >
                  {stat.value}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </FadeIn>
  );
}

function CopyBtn({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(() => {
    void navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [text]);
  return (
    <button
      type="button"
      onClick={copy}
      className="absolute top-2 right-2 p-1.5 rounded cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity duration-200 hover:bg-black/5"
      aria-label={msg("auto.app.compare.page.literal.8")}
    >
      {copied ? (
        <Check className="size-3.5 text-[var(--success)]" />
      ) : (
        <Clipboard className="size-3.5 text-muted-foreground" />
      )}
    </button>
  );
}

function PromptBlock({ prompt }: { prompt: OptimizedPredictor | null | undefined }) {
  if (!prompt) {
    return (
      <div className="flex items-center justify-center h-32 rounded-xl border border-dashed border-border/60 bg-muted/20">
        <p className="text-sm text-muted-foreground italic">{msg("auto.app.compare.page.4")}</p>
      </div>
    );
  }
  return (
    <div>
      <div className="relative group">
        <pre
          className="text-sm font-mono bg-muted/50 rounded-lg p-4 pe-10 overflow-x-auto whitespace-pre-wrap leading-relaxed"
          dir="ltr"
        >
          {prompt.formatted_prompt}
        </pre>
        <CopyBtn text={prompt.formatted_prompt} />
      </div>
      {prompt.demos && prompt.demos.length > 0 && (
        <div className="mt-4 pt-4 border-t border-border">
          <p className="text-xs text-muted-foreground mb-2">
            {prompt.demos.length}{" "}
            <HelpTip text={tip("prompt.demonstrations")}>{msg("auto.app.compare.page.5")}</HelpTip>
          </p>
          <div className="space-y-2">
            {prompt.demos.map((demo, i) => (
              <div key={i} className="text-xs font-mono bg-muted/50 rounded-lg p-3" dir="ltr">
                {Object.entries(demo.inputs).map(([k, v]) => (
                  <div key={k}>
                    <span className="text-muted-foreground">{k}:</span> {String(v)}
                  </div>
                ))}
                {Object.entries(demo.outputs).map(([k, v]) => (
                  <div key={k}>
                    <span className="text-stone-600">{k}:</span> {String(v)}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

type MetricRow = {
  key: string;
  label: React.ReactNode;
  values: Array<number | null>;
  format: (v: number | null) => string;
  prefer: "max" | "min" | "none";
};

function MetricCell({
  value,
  format,
  isBest,
}: {
  value: number | null;
  format: (v: number | null) => string;
  isBest: boolean;
}) {
  return (
    <div
      className={`flex items-center justify-center gap-1 rounded-md px-2 py-1 text-xs sm:text-sm font-mono tabular-nums transition-colors ${
        isBest
          ? "bg-primary/[0.08] border border-primary/20 text-primary font-bold"
          : value == null
            ? "text-muted-foreground"
            : "text-foreground"
      }`}
    >
      <span>{format(value)}</span>
      {isBest && <Trophy className="size-3 text-primary/70 shrink-0" />}
    </div>
  );
}

function RunsHeaderRow({
  runs,
  winnerIdx,
  stickyFirst,
  firstLabel,
}: {
  runs: RunInfo[];
  winnerIdx: number | null;
  stickyFirst: string;
  firstLabel: string;
}) {
  const winnerBg = (i: number) => (i === winnerIdx ? WINNER_TINT : undefined);
  return (
    <tr>
      <th
        className={`py-2.5 text-center text-[0.6875rem] font-semibold uppercase tracking-wider text-muted-foreground w-[180px] border-b border-border/40 ${stickyFirst}`}
      >
        {firstLabel}
      </th>
      {runs.map((run, i) => (
        <th
          key={run.job.optimization_id}
          className="py-2.5 px-2 border-b border-border/40"
          style={{ background: winnerBg(i) }}
        >
          <div className="flex flex-col items-center gap-1">
            <RunChip index={i} label={run.label} winner={i === winnerIdx} />
          </div>
        </th>
      ))}
    </tr>
  );
}

type ChartRow = {
  metric: string;
  [runKey: string]: string | number | null;
};

function PerformanceChart({ runs }: { runs: RunInfo[] }) {
  const [hiddenRuns, setHiddenRuns] = useState<Set<string>>(new Set());
  const toggleRun = useCallback(
    (id: string) => {
      setHiddenRuns((prev) => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        // Prevent hiding every single run — always keep at least one visible.
        if (next.size >= prev.size + 1 && next.size === runs.length) {
          return prev;
        }
        return next;
      });
    },
    [runs.length],
  );
  const chartData = useMemo(() => {
    const latencies = runs
      .map((r) => r.avgResponseMs)
      .filter((v): v is number => v != null && v > 0);
    const minLatency = latencies.length ? Math.min(...latencies) : null;
    const hasSpeed = minLatency != null;

    const quality = (r: RunInfo) => {
      const v = r.optimized;
      if (v == null) return null;
      return v > 1 ? v / 100 : v;
    };
    const speed = (r: RunInfo) => {
      if (!hasSpeed || r.avgResponseMs == null || r.avgResponseMs <= 0) return null;
      return minLatency! / r.avgResponseMs;
    };

    const toPct = (v: number | null) => (v == null ? null : Math.round(v * 1000) / 10);

    const qualityRow: ChartRow = { metric: msg("auto.app.compare.page.literal.9") };
    const speedRow: ChartRow = { metric: msg("auto.app.compare.page.literal.10") };
    runs.forEach((r, i) => {
      const key = runToken(i);
      qualityRow[key] = toPct(quality(r));
      speedRow[key] = toPct(speed(r));
    });

    const rows: ChartRow[] = [qualityRow];
    if (hasSpeed) {
      rows.push(speedRow);
    }
    return { rows, hasSpeed };
  }, [runs]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <BarChart3 className="size-4" />
          <HelpTip text={msg("auto.app.compare.page.literal.12")}>
            {msg("auto.app.compare.page.6")}
          </HelpTip>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-[280px]" dir="ltr">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData.rows}
              margin={{ top: 16, right: 16, bottom: 8, left: 0 }}
              barCategoryGap="20%"
              barGap={4}
            >
              <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-muted" />
              <XAxis
                dataKey="metric"
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 12 }}
                className="fill-muted-foreground"
                reversed
              />
              <YAxis
                domain={[0, 100]}
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11 }}
                className="fill-muted-foreground"
                ticks={[0, 25, 50, 75, 100]}
                tickFormatter={(v) => `${v}%`}
                orientation="right"
                width={40}
              />
              <RechartsTooltip
                content={<ChartTooltip />}
                cursor={{ fill: "var(--muted)", opacity: 0.3 }}
              />
              {runs.map((run, i) => {
                if (hiddenRuns.has(run.job.optimization_id)) return null;
                return (
                  <Bar
                    key={run.job.optimization_id}
                    dataKey={runToken(i)}
                    name={`${runToken(i)} · ${run.label}`}
                    radius={[4, 4, 0, 0]}
                    animationDuration={400}
                  >
                    {chartData.rows.map((_, idx) => (
                      <Cell key={idx} fill={colorFor(i)} />
                    ))}
                  </Bar>
                );
              })}
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap justify-center gap-4 mt-3" dir="rtl">
          {runs.map((run, i) => {
            const isHidden = hiddenRuns.has(run.job.optimization_id);
            const color = colorFor(i);
            return (
              <button
                key={run.job.optimization_id}
                type="button"
                onClick={() => toggleRun(run.job.optimization_id)}
                aria-pressed={!isHidden}
                className={`flex items-center gap-1.5 text-xs cursor-pointer transition-opacity ${
                  isHidden ? "opacity-45 hover:opacity-75" : "hover:opacity-80"
                }`}
              >
                <span
                  className="size-2.5 rounded-full shrink-0 transition-all"
                  style={
                    isHidden
                      ? { backgroundColor: "transparent", boxShadow: `inset 0 0 0 1.5px ${color}` }
                      : { backgroundColor: color }
                  }
                />
                <RunChip index={i} label={run.label} />
              </button>
            );
          })}
        </div>
        {!chartData.hasSpeed && (
          <p className="text-[0.6875rem] text-muted-foreground text-center mt-2">
            {msg("auto.app.compare.page.7")}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function ScoresTable({ runs, winnerIdx }: { runs: RunInfo[]; winnerIdx: number | null }) {
  const metricRows: MetricRow[] = [
    {
      key: "baseline",
      label: <HelpTip text={tip("score.baseline")}>{TERMS.baselineScore}</HelpTip>,
      values: runs.map((r) => r.baseline),
      format: fmt,
      prefer: "none",
    },
    {
      key: "optimized",
      label: <HelpTip text={tip("score.optimized")}>{TERMS.optimizedScore}</HelpTip>,
      values: runs.map((r) => r.optimized),
      format: fmt,
      prefer: "max",
    },
    {
      key: "improvement",
      label: <HelpTip text={tip("score.improvement")}>{msg("auto.app.compare.page.8")}</HelpTip>,
      values: runs.map((r) => r.improvement),
      format: fmtImprovement,
      prefer: "max",
    },
    {
      key: "runtime",
      label: msg("auto.app.compare.page.literal.13"),
      values: runs.map((r) => r.runtime),
      format: fmtElapsed,
      prefer: "min",
    },
    {
      key: "latency",
      label: <HelpTip text={tip("lm.avg_response_time")}>{msg("auto.app.compare.page.9")}</HelpTip>,
      values: runs.map((r) => r.avgResponseMs),
      format: fmtLatency,
      prefer: "min",
    },
  ];

  const winnerBg = (i: number) => (i === winnerIdx ? WINNER_TINT : undefined);
  const stickyFirst = "sticky start-0 bg-card z-10 border-e border-border/30";

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[500px] text-sm border-separate border-spacing-0">
            <thead>
              <RunsHeaderRow
                runs={runs}
                winnerIdx={winnerIdx}
                stickyFirst={stickyFirst}
                firstLabel={TERMS.metric}
              />
            </thead>
            <tbody>
              {metricRows.map((row, rowIdx) => {
                const tie = row.prefer !== "none" && isRowTie(row.values);
                const bestIdx =
                  row.prefer === "none" || tie ? null : bestIndexOf(row.values, row.prefer);
                const borderTop = rowIdx > 0 ? "border-t border-border/30" : "";
                return (
                  <tr key={row.key}>
                    <td
                      className={`py-2.5 px-3 text-xs text-muted-foreground ${borderTop} ${stickyFirst}`}
                    >
                      {row.label}
                    </td>
                    {row.values.map((v, i) => (
                      <td
                        key={i}
                        className={`py-2.5 px-2 ${borderTop}`}
                        style={{ background: winnerBg(i) }}
                      >
                        <MetricCell value={v} format={row.format} isBest={bestIdx === i} />
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function ConfigTable({ runs, winnerIdx }: { runs: RunInfo[]; winnerIdx: number | null }) {
  type ConfigRowDef = {
    key: string;
    icon: React.ElementType;
    label: string;
    values: string[];
  };
  const configRows: ConfigRowDef[] = [
    {
      key: "module",
      icon: Layers,
      label: msg("auto.app.compare.page.literal.14"),
      values: runs.map((r) => r.moduleName ?? "—"),
    },
    {
      key: "optimizer",
      icon: Cpu,
      label: TERMS.optimizer,
      values: runs.map((r) => r.optimizerName ?? "—"),
    },
    {
      key: "model",
      icon: Sparkles,
      label: msg("auto.app.compare.page.literal.15"),
      values: runs.map((r) => r.modelName ?? "—"),
    },
    {
      key: "dataset",
      icon: Database,
      label: formatMsg("auto.app.compare.page.template.2", { p1: TERMS.dataset }),
      values: runs.map((r) => String(r.datasetRows ?? "—")),
    },
  ];

  const stickyFirst = "sticky start-0 bg-card z-10 border-e border-border/30";

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[500px] text-sm border-separate border-spacing-0">
            <thead>
              <RunsHeaderRow
                runs={runs}
                winnerIdx={winnerIdx}
                stickyFirst={stickyFirst}
                firstLabel={msg("auto.app.compare.page.literal.16")}
              />
            </thead>
            <tbody>
              {configRows.map((row, rowIdx) => {
                const first = row.values[0];
                const allSame = first !== undefined && row.values.every((v) => v === first);
                const borderTop = rowIdx > 0 ? "border-t border-border/30" : "";
                return (
                  <tr key={row.key}>
                    <td
                      className={`py-2.5 px-3 text-xs text-muted-foreground ${borderTop} ${stickyFirst}`}
                    >
                      <span className="flex items-center gap-1.5">
                        <row.icon className="size-3 opacity-50" />
                        {row.label}
                      </span>
                    </td>
                    {allSame ? (
                      <td colSpan={runs.length} className={`py-2.5 px-2 text-center ${borderTop}`}>
                        <span className="font-mono text-xs tabular-nums text-foreground">
                          {first}
                        </span>
                        <span className="mx-2 text-muted-foreground/40">·</span>
                        <span className="text-[0.6875rem] text-muted-foreground">
                          {msg("auto.app.compare.page.10")}
                        </span>
                      </td>
                    ) : (
                      row.values.map((v, i) => (
                        <td
                          key={i}
                          className={`py-2.5 px-2 text-center font-mono text-xs tabular-nums truncate ${borderTop}`}
                          title={v}
                        >
                          {v}
                        </td>
                      ))
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function PromptsSection({ runs, winnerIdx }: { runs: RunInfo[]; winnerIdx: number | null }) {
  const initial = (winnerIdx != null ? runs[winnerIdx] : runs[0])!.job.optimization_id;
  const [activeValue, setActiveValue] = useState(initial);
  const activeIdx = Math.max(
    0,
    runs.findIndex((r) => r.job.optimization_id === activeValue),
  );
  const n = runs.length;
  const pad = 4;
  const gap = 4;
  const segmentWidth = `calc((100% - ${2 * pad + (n - 1) * gap}px) / ${n})`;
  const segmentOffset = `calc(${activeIdx} * ((100% - ${2 * pad + (n - 1) * gap}px) / ${n}) + ${pad + activeIdx * gap}px)`;

  return (
    <Card>
      <CardContent className="p-5 sm:p-6">
        <Tabs value={activeValue} onValueChange={setActiveValue} dir="rtl">
          <TabsList className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1 border-none shadow-none h-auto">
            {n >= 2 && (
              <div
                className="absolute top-1 bottom-1 rounded-md bg-[#3D2E22] shadow-sm transition-[inset-inline-start] duration-200 ease-out"
                style={{ width: segmentWidth, insetInlineStart: segmentOffset }}
              />
            )}
            {runs.map((run, i) => (
              <TabsTrigger
                key={run.job.optimization_id}
                value={run.job.optimization_id}
                className="flex-1 min-w-0 relative z-10 rounded-md px-3 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5"
              >
                <span
                  className="size-5 rounded-md flex items-center justify-center text-[0.625rem] font-bold text-white tabular-nums shrink-0"
                  style={{ background: colorFor(i) }}
                >
                  {runToken(i)}
                </span>
                <span className="font-mono tabular-nums truncate" dir="ltr">
                  {run.label}
                </span>
              </TabsTrigger>
            ))}
          </TabsList>
          {runs.map((run) => (
            <TabsContent
              key={run.job.optimization_id}
              value={run.job.optimization_id}
              className="mt-5"
            >
              <PromptBlock prompt={run.prompt} />
            </TabsContent>
          ))}
        </Tabs>
      </CardContent>
    </Card>
  );
}

async function fetchPerExample(run: RunInfo): Promise<EvalExampleResult[] | null> {
  try {
    const id = run.job.optimization_id;
    if (run.isGrid && run.winnerPairIndex != null) {
      const res = await getPairTestResults(id, run.winnerPairIndex);
      return res.optimized;
    }
    const res = await getTestResults(id);
    return res.optimized;
  } catch {
    return null;
  }
}

function PassBadge({ result }: { result: EvalExampleResult | undefined }) {
  if (!result) {
    return <span className="text-muted-foreground/50 text-xs">—</span>;
  }
  const scoreStr = fmt(result.score);
  if (result.pass) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-[var(--success-dim)] border border-[var(--success-border)] text-[var(--success)] px-2 py-0.5 text-xs font-mono tabular-nums">
        <Check className="size-3 shrink-0" aria-hidden="true" />
        {scoreStr}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-[var(--danger-dim)] border border-[var(--danger-border)] text-[var(--danger)] px-2 py-0.5 text-xs font-mono tabular-nums">
      <X className="size-3 shrink-0" aria-hidden="true" />
      {scoreStr}
    </span>
  );
}

function renderValue(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

function KVBlock({
  title,
  entries,
  accent,
}: {
  title: string;
  entries: Array<[string, unknown]>;
  accent?: "muted" | "primary";
}) {
  if (entries.length === 0) return null;
  const titleCls =
    accent === "primary" ? "text-primary font-semibold" : "text-muted-foreground font-medium";
  return (
    <div className="space-y-1.5">
      <p className={`text-[0.625rem] uppercase tracking-wider ${titleCls}`}>{title}</p>
      <div className="space-y-1">
        {entries.map(([k, v]) => (
          <div key={k} className="rounded-md border border-border/40 bg-muted/20 px-2.5 py-1.5">
            <div className="text-[0.625rem] text-muted-foreground/80 font-medium mb-0.5" dir="ltr">
              {k}
            </div>
            <pre
              className="text-xs font-mono whitespace-pre-wrap break-words leading-relaxed text-foreground/90"
              dir="auto"
            >
              {renderValue(v)}
            </pre>
          </div>
        ))}
      </div>
    </div>
  );
}

function ExampleDetailRow({
  runs,
  inputs,
  expected,
  outputsPerRun,
  colSpan,
}: {
  runs: RunInfo[];
  inputs: Array<[string, unknown]>;
  expected: Array<[string, unknown]>;
  outputsPerRun: Array<EvalExampleResult | undefined>;
  colSpan: number;
}) {
  return (
    <tr>
      <td colSpan={colSpan} className="p-0 bg-muted/10 border-t border-border/30">
        <div className="p-4 sm:p-5 space-y-5">
          {inputs.length > 0 && (
            <KVBlock
              title={msg("auto.app.compare.page.literal.17")}
              entries={inputs}
              accent="muted"
            />
          )}
          {expected.length > 0 && (
            <KVBlock
              title={msg("auto.app.compare.page.literal.18")}
              entries={expected}
              accent="primary"
            />
          )}
          <div className="space-y-2">
            <p className="text-[0.625rem] uppercase tracking-wider text-muted-foreground font-medium">
              {msg("auto.app.compare.page.11")}
            </p>
            <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(260px,1fr))]">
              {runs.map((run, i) => {
                const res = outputsPerRun[i];
                const tint = colorFor(i);
                return (
                  <div
                    key={run.job.optimization_id}
                    className="rounded-md border border-border/50 bg-card overflow-hidden flex flex-col"
                  >
                    <div
                      className="flex items-center justify-between px-2.5 py-1.5 gap-2 border-b border-border/40"
                      style={{ background: `color-mix(in oklch, ${tint} 10%, transparent)` }}
                    >
                      <RunChip index={i} label={run.label} />
                      <PassBadge result={res} />
                    </div>
                    <div className="px-2.5 py-2 flex-1">
                      {res ? (
                        <div className="space-y-1.5">
                          {Object.entries(res.outputs).map(([k, v]) => (
                            <div key={k}>
                              <div
                                className="text-[0.625rem] text-muted-foreground/80 mb-0.5"
                                dir="ltr"
                              >
                                {k}
                              </div>
                              <pre
                                className="text-xs font-mono whitespace-pre-wrap break-words leading-relaxed text-foreground/90"
                                dir="auto"
                              >
                                {renderValue(v)}
                              </pre>
                            </div>
                          ))}
                          {res.error && (
                            <p className="text-[0.6875rem] text-[var(--danger)] mt-1" dir="auto">
                              {msg("auto.app.compare.page.12")}
                              {res.error}
                            </p>
                          )}
                        </div>
                      ) : (
                        <p className="text-xs text-muted-foreground italic">
                          {msg("auto.app.compare.page.13")}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}

function PerExampleSection({ runs }: { runs: RunInfo[] }) {
  const [injectedDemo] = useState(() => consumePendingCompareExamples());
  const [byRun, setByRun] = useState<Record<string, Map<number, EvalExampleResult>> | null>(() => {
    if (!injectedDemo) return null;
    const next: Record<string, Map<number, EvalExampleResult>> = {};
    for (const run of runs) {
      const arr = injectedDemo.byJobId[run.job.optimization_id];
      if (!arr) continue;
      const m = new Map<number, EvalExampleResult>();
      arr.forEach((r) => m.set(r.index, r));
      next[run.job.optimization_id] = m;
    }
    return next;
  });
  const [dataset, setDataset] = useState<OptimizationDatasetResponse | null>(
    () => injectedDemo?.dataset ?? null,
  );
  const [loading, setLoading] = useState(() => !injectedDemo);
  const [onlyDisagreements, setOnlyDisagreements] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (injectedDemo) return;
    let alive = true;
    setLoading(true);

    const resultsPromise = Promise.all(runs.map(fetchPerExample));
    // Datasets are shared across compared runs (same task_fingerprint). Try each
    // run in order and use the first successful response.
    const datasetPromise = (async () => {
      for (const r of runs) {
        try {
          return await getOptimizationDataset(r.job.optimization_id);
        } catch {
          continue;
        }
      }
      return null;
    })();

    void Promise.all([resultsPromise, datasetPromise])
      .then(([list, ds]) => {
        if (!alive) return;
        const next: Record<string, Map<number, EvalExampleResult>> = {};
        list.forEach((arr, i) => {
          const run = runs[i];
          if (!run || !arr) return;
          const m = new Map<number, EvalExampleResult>();
          arr.forEach((r) => m.set(r.index, r));
          next[run.job.optimization_id] = m;
        });
        setByRun(next);
        setDataset(ds);
      })
      .catch((err) => {
        // resultsPromise/datasetPromise individually swallow errors, but a
        // future edit could surface a rejection here — leave the spinner
        // would-spin-forever bug behind.
        console.warn("PerExampleSection: failed to load examples", err);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [runs, injectedDemo]);

  const rowByIndex = useMemo(() => {
    const m = new Map<number, Record<string, unknown>>();
    if (!dataset) return m;
    const all = [...dataset.splits.test, ...dataset.splits.val, ...dataset.splits.train];
    all.forEach((r) => m.set(r.index, r.row));
    return m;
  }, [dataset]);

  const indices = useMemo(() => {
    if (!byRun) return [] as number[];
    const set = new Set<number>();
    Object.values(byRun).forEach((m) => m.forEach((_, idx) => set.add(idx)));
    return Array.from(set).sort((a, b) => a - b);
  }, [byRun]);

  const disagreementSet = useMemo(() => {
    if (!byRun) return new Set<number>();
    const s = new Set<number>();
    indices.forEach((idx) => {
      const passes: boolean[] = [];
      runs.forEach((r) => {
        const hit = byRun[r.job.optimization_id]?.get(idx);
        if (hit) passes.push(hit.pass);
      });
      if (passes.length < 2) return;
      if (passes.some((p) => p !== passes[0])) s.add(idx);
    });
    return s;
  }, [byRun, indices, runs]);

  const toggleRow = useCallback((idx: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }, []);

  if (loading) {
    return (
      <Card>
        <CardContent className="py-6">
          <p className="text-xs text-muted-foreground">{msg("auto.app.compare.page.14")}</p>
        </CardContent>
      </Card>
    );
  }

  if (!byRun || indices.length === 0) {
    return (
      <Card>
        <CardContent className="py-6">
          <p className="text-sm text-muted-foreground">{msg("auto.app.compare.page.15")}</p>
        </CardContent>
      </Card>
    );
  }

  const rows = onlyDisagreements ? indices.filter((i) => disagreementSet.has(i)) : indices;
  const inputFields = dataset ? Object.entries(dataset.column_mapping.inputs) : [];
  const outputFields = dataset ? Object.entries(dataset.column_mapping.outputs) : [];

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <div className="flex items-center justify-between gap-3 px-4 sm:px-5 py-3 border-b border-border/40">
          <div className="flex items-center gap-2 text-[0.6875rem] text-muted-foreground tabular-nums">
            <span>
              {indices.length === 1
                ? msg("auto.app.compare.page.literal.19")
                : formatMsg("auto.app.compare.page.template.3", { p1: indices.length })}
            </span>
          </div>
          <UiTooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => setOnlyDisagreements((v) => !v)}
                disabled={disagreementSet.size === 0}
                aria-pressed={onlyDisagreements}
                aria-label={
                  onlyDisagreements
                    ? msg("auto.app.compare.page.literal.20")
                    : msg("auto.app.compare.page.literal.21")
                }
                className={`flex size-8 items-center justify-center rounded-md transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-40 ${
                  onlyDisagreements
                    ? "bg-primary text-primary-foreground hover:bg-primary/90"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground"
                }`}
              >
                <GitCompareArrows className="size-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="top" dir="rtl">
              {disagreementSet.size === 0
                ? msg("auto.app.compare.page.literal.22")
                : onlyDisagreements
                  ? msg("auto.app.compare.page.literal.23")
                  : disagreementSet.size === 1
                    ? msg("auto.app.compare.page.literal.24")
                    : formatMsg("auto.app.compare.page.template.4", { p1: disagreementSet.size })}
            </TooltipContent>
          </UiTooltip>
        </div>

        {rows.length === 0 ? (
          <div className="py-6 text-center">
            <p className="text-sm text-muted-foreground">{msg("auto.app.compare.page.16")}</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-separate border-spacing-0">
              <thead>
                <tr>
                  <th className="py-2 w-10 border-b border-border/40 sticky start-0 bg-card z-10" />
                  <th className="py-2 px-3 text-start text-[0.6875rem] font-semibold uppercase tracking-wider text-muted-foreground w-[min(120px,30%)] border-b border-border/40 sticky start-10 bg-card z-10 border-e border-border/30">
                    {msg("auto.app.compare.page.17")}
                  </th>
                  {runs.map((run, i) => (
                    <th
                      key={run.job.optimization_id}
                      className="py-2.5 px-2 border-b border-border/40 text-center"
                    >
                      <div className="flex items-center justify-center">
                        <RunChip index={i} label={run.label} />
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((idx, rowIdx) => {
                  const borderTop = rowIdx > 0 ? "border-t border-border/30" : "";
                  const isDisagree = disagreementSet.has(idx);
                  const isExpanded = expanded.has(idx);
                  const row = rowByIndex.get(idx);
                  const inputEntries: Array<[string, unknown]> = row
                    ? inputFields.map(([field, col]) => [
                        field,
                        (row as Record<string, unknown>)[col],
                      ])
                    : [];
                  const expectedEntries: Array<[string, unknown]> = row
                    ? outputFields.map(([field, col]) => [
                        field,
                        (row as Record<string, unknown>)[col],
                      ])
                    : [];
                  const outputsPerRun = runs.map((r) => byRun[r.job.optimization_id]?.get(idx));

                  return (
                    <Fragment key={idx}>
                      <tr
                        className="hover:bg-muted/30 transition-colors cursor-pointer"
                        onClick={() => toggleRow(idx)}
                      >
                        <td className={`py-2 px-2 ${borderTop} sticky start-0 z-10 bg-card`}>
                          <div className="flex items-center gap-1.5">
                            <ChevronDown
                              className={`size-3.5 text-muted-foreground transition-transform ${isExpanded ? "rotate-180" : ""}`}
                            />
                            {isDisagree && (
                              <span
                                className="size-1.5 rounded-full bg-primary shrink-0"
                                aria-label={msg("auto.app.compare.page.literal.25")}
                                title={msg("auto.app.compare.page.literal.26")}
                              />
                            )}
                          </div>
                        </td>
                        <td
                          className={`py-2 px-3 ${borderTop} sticky start-10 z-10 bg-card border-e border-border/30`}
                        >
                          <span
                            className="text-xs font-mono tabular-nums text-muted-foreground"
                            dir="ltr"
                          >
                            #{idx}
                          </span>
                        </td>
                        {runs.map((run, i) => (
                          <td key={i} className={`py-2 px-2 ${borderTop} text-center`}>
                            <PassBadge result={outputsPerRun[i]} />
                          </td>
                        ))}
                      </tr>
                      {isExpanded && (
                        <ExampleDetailRow
                          runs={runs}
                          inputs={inputEntries}
                          expected={expectedEntries}
                          outputsPerRun={outputsPerRun}
                          colSpan={runs.length + 2}
                        />
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function CompareView() {
  const searchParams = useSearchParams();
  const optimizationIds = useMemo(
    () => (searchParams.get("jobs") ?? "").split(",").filter(Boolean),
    [searchParams],
  );

  // Consume the tutorial's one-shot demo via a useState initializer because
  // `consumePendingCompareDemo` mutates module-level state (see
  // features/tutorial/lib/bridge.ts) — calling it from an effect would race
  // with the real-API fallback and could miss the injected payload entirely.
  const [injectedDemo] = useState(() => consumePendingCompareDemo());
  const [jobs, setJobs] = useState<OptimizationStatusResponse[] | null>(() =>
    injectedDemo && injectedDemo.length >= 2 ? injectedDemo : null,
  );
  const [loading, setLoading] = useState(() => !(injectedDemo && injectedDemo.length >= 2));
  const [error, setError] = useState<string | null>(null);
  const [failedIds, setFailedIds] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState("overview");

  useEffect(() => registerTutorialHook("setCompareTab", setActiveTab), []);

  useEffect(() => {
    if (injectedDemo && injectedDemo.length >= 2) return;
    if (optimizationIds.length < 2) {
      setError(formatMsg("auto.app.compare.page.template.5", { p1: TERMS.optimizationPlural }));
      setLoading(false);
      return;
    }
    setLoading(true);
    void Promise.allSettled(optimizationIds.map((id) => getJob(id)))
      .then((results) => {
        const ok: OptimizationStatusResponse[] = [];
        const failed: string[] = [];
        results.forEach((r, i) => {
          if (r.status === "fulfilled") ok.push(r.value);
          else failed.push(optimizationIds[i] ?? "unknown");
        });
        if (ok.length < 2) {
          setError(msg("compare.load_error"));
          setJobs(null);
        } else {
          setJobs(ok);
          setError(null);
        }
        setFailedIds(failed);
      })
      .finally(() => setLoading(false));
  }, [optimizationIds, injectedDemo]);

  const runs = useMemo(() => (jobs ? jobs.map(deriveRunInfo) : []), [jobs]);
  const winnerIdx = useMemo(() => winnerIndexOf(runs), [runs]);

  if (loading) {
    return (
      <Skeleton
        name="compare"
        loading
        initialBones={compareBones}
        color="var(--muted)"
        animate="shimmer"
      >
        <div className="min-h-[60vh]" />
      </Skeleton>
    );
  }

  if (error || !jobs || runs.length < 2) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <XCircle className="size-12 text-destructive" />
        <p className="text-lg text-muted-foreground">
          {error ?? formatMsg("auto.app.compare.page.template.6", { p1: TERMS.optimizationPlural })}
        </p>
        <Button variant="outline" asChild>
          <Link href="/">{msg("auto.app.compare.page.18")}</Link>
        </Button>
      </div>
    );
  }

  const tabCls =
    "relative flex-1 min-w-0 justify-center py-2.5 rounded-none border-b-2 border-transparent data-[state=active]:border-transparent data-[state=active]:border-b-primary data-[state=active]:text-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none transition-all duration-200 text-xs sm:text-sm";

  const panelMotion = {
    initial: { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -8 },
    transition: { duration: 0.2, ease: EASE_SNAPPY },
  };

  return (
    <motion.div
      className="space-y-6 pb-16"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: EASE_SNAPPY }}
    >
      <FadeIn>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Link href="/" className="hover:text-foreground transition-colors">
            {msg("auto.app.compare.page.19")}
          </Link>
          <ChevronLeft className="h-3 w-3" />
          <span className="text-foreground font-medium">
            {msg("auto.app.compare.page.20")}
            {TERMS.optimizationPlural}
          </span>
        </div>
      </FadeIn>

      {failedIds.length > 0 && (
        <FadeIn>
          <div
            className="flex items-start gap-3 rounded-xl border border-amber-400/30 bg-amber-50 px-4 py-3 text-sm text-amber-900"
            role="status"
          >
            <AlertTriangle className="size-4 mt-0.5 shrink-0 text-amber-600" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{msg("compare.partial_load")}</p>
              <p className="mt-0.5 text-xs text-amber-900/75 break-all" dir="ltr">
                {failedIds.join(", ")}
              </p>
            </div>
          </div>
        </FadeIn>
      )}

      <VerdictBlock runs={runs} winnerIdx={winnerIdx} />

      <FadeIn delay={0.15}>
        <Tabs value={activeTab} onValueChange={setActiveTab} dir="rtl">
          <TabsList variant="line" className="w-full border-b border-border/50 pb-0 gap-0">
            <TabsTrigger value="overview" className={tabCls}>
              <BarChart3 className="size-3.5" />
              {msg("auto.app.compare.page.21")}
            </TabsTrigger>
            <TabsTrigger value="config" className={tabCls}>
              <Cpu className="size-3.5" />
              {msg("auto.app.compare.page.22")}
            </TabsTrigger>
            <TabsTrigger value="prompts" className={tabCls}>
              <Sparkles className="size-3.5" />
              {msg("auto.app.compare.page.23")}
            </TabsTrigger>
            <TabsTrigger value="examples" className={tabCls}>
              <ListChecks className="size-3.5" />
              {msg("auto.app.compare.page.24")}
            </TabsTrigger>
          </TabsList>

          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={activeTab}
              initial={panelMotion.initial}
              animate={panelMotion.animate}
              exit={panelMotion.exit}
              transition={panelMotion.transition}
              className="space-y-4 mt-4"
            >
              {activeTab === "overview" && (
                <div data-tutorial="compare-scores" className="space-y-4">
                  <PerformanceChart runs={runs} />
                  <ScoresTable runs={runs} winnerIdx={winnerIdx} />
                </div>
              )}
              {activeTab === "config" && (
                <div data-tutorial="compare-config">
                  <ConfigTable runs={runs} winnerIdx={winnerIdx} />
                </div>
              )}
              {activeTab === "prompts" && (
                <div data-tutorial="compare-prompts">
                  <PromptsSection runs={runs} winnerIdx={winnerIdx} />
                </div>
              )}
              {activeTab === "examples" && (
                <div data-tutorial="compare-examples">
                  <PerExampleSection runs={runs} />
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </Tabs>
      </FadeIn>
    </motion.div>
  );
}
