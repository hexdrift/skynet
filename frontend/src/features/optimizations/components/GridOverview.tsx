"use client";

/**
 * Grid-search overview — aggregated KPIs, comparison charts, and pair
 * cards for a completed grid-search job.
 *
 * Extracted from app/optimizations/[id]/page.tsx. Pure display component
 * that takes the job + a pair-selection callback.
 */

import { useMemo, useState } from "react";
import {
  ChevronLeft,
  Crown,
  Gauge,
  Loader2,
  Target,
  Trash2,
  Trophy,
  X,
  XCircle,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { toast } from "react-toastify";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ScatterChart,
  Scatter,
  ZAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip as UiTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { FadeIn, StaggerContainer, StaggerItem, TiltCard } from "@/shared/ui/motion";
import { HelpTip } from "@/shared/ui/help-tip";
import type { OptimizationStatusResponse, PairResult } from "@/shared/types/api";
import { formatPercent } from "@/shared/lib";
import { deleteGridPair } from "@/shared/lib/api";
import { msg } from "@/shared/lib/messages";
import { tip } from "@/shared/lib/tooltips";
import { TERMS } from "@/shared/lib/terms";
import { computePairScores, type PairScores } from "../lib/pair-scores";
import { ReasoningPill } from "./ui-primitives";

function HarmonicCalc({
  scores,
  className = "",
}: {
  scores: PairScores | null;
  className?: string;
}) {
  if (!scores || scores.harmonic == null || scores.speed == null) return null;
  const q = scores.quality.toFixed(2);
  const s = scores.speed.toFixed(2);
  const h = Math.round(scores.harmonic * 100);
  return (
    <div className={`mt-1.5 text-[0.5625rem] leading-tight ${className}`}>
      <div className="mb-0.5" dir="rtl">
        ממוצע הרמוני של איכות ומהירות:
      </div>
      <div className="font-mono tabular-nums" dir="ltr">
        (2 × {q} × {s}) / ({q} + {s}) = <span className="font-semibold">{h}%</span>
      </div>
    </div>
  );
}

interface ScatterPoint {
  pair_index: number;
  name: string;
  quality: number;
  latency: number;
  combined: number | null;
  isOverall: boolean;
  isQuality: boolean;
  isSpeed: boolean;
}

function computePareto(points: ScatterPoint[]): {
  pareto: ScatterPoint[];
  dominated: ScatterPoint[];
} {
  const pareto: ScatterPoint[] = [];
  const dominated: ScatterPoint[] = [];
  for (const p of points) {
    const isDominated = points.some(
      (q) =>
        q !== p &&
        q.quality >= p.quality &&
        q.latency <= p.latency &&
        (q.quality > p.quality || q.latency < p.latency),
    );
    if (isDominated) dominated.push(p);
    else pareto.push(p);
  }
  pareto.sort((a, b) => a.latency - b.latency);
  return { pareto, dominated };
}

function shortEffort(value: string | null | undefined): string | null {
  if (!value) return null;
  const v = value.toLowerCase();
  if (v === "minimal") return "min";
  if (v === "medium") return "med";
  return v;
}

function pairLabel(p: PairResult): string {
  const gen = p.generation_model.split("/").pop();
  const ref = p.reflection_model.split("/").pop();
  const genE = shortEffort(p.generation_reasoning_effort);
  const refE = shortEffort(p.reflection_reasoning_effort);
  const genStr = genE ? `${gen}·${genE}` : gen;
  const refStr = refE ? `${ref}·${refE}` : ref;
  return `${genStr} × ${refStr}`;
}

export function GridOverview({
  job,
  onPairSelect,
  onPairDeleted,
}: {
  job: OptimizationStatusResponse;
  onPairSelect: (pairIndex: number) => void;
  onPairDeleted?: (pairIndex: number) => void;
}) {
  const [pendingDelete, setPendingDelete] = useState<PairResult | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [pairFilter, setPairFilter] = useState<number | null>(null);
  const [hiddenPairSeries, setHiddenPairSeries] = useState<Set<string>>(new Set());
  const [hiddenCombinedSeries, setHiddenCombinedSeries] = useState<Set<string>>(new Set());
  const [hiddenScatterSeries, setHiddenScatterSeries] = useState<Set<string>>(new Set());
  const togglePairSeries = (key: string) => {
    setHiddenPairSeries((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  const toggleCombinedSeries = (key: string) => {
    setHiddenCombinedSeries((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  const toggleScatterSeries = (key: string) => {
    setHiddenScatterSeries((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  const handleBarClick = (data: unknown) => {
    const pi = (data as { pair_index?: number }).pair_index;
    if (typeof pi === "number") setPairFilter(pi);
  };
  const handleConfirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await deleteGridPair(job.optimization_id, pendingDelete.pair_index);
      onPairDeleted?.(pendingDelete.pair_index);
      setPendingDelete(null);
      window.dispatchEvent(new Event("optimizations-changed"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("optimization.delete.failed"));
    } finally {
      setDeleting(false);
    }
  };
  if (!job.grid_result) return null;
  const prs = job.grid_result.pair_results;
  const completedPrs = prs.filter((p) => !p.error);
  const scoring = computePairScores(prs);
  const byIdx = (i: number | null | undefined) =>
    i == null ? null : (prs.find((p) => p.pair_index === i) ?? null);
  const qualityPair = byIdx(scoring.qualityWinner);
  const speedPair = byIdx(scoring.speedWinner);
  const overallPair = byIdx(scoring.overallWinner);
  const qualityScores =
    scoring.qualityWinner != null ? (scoring.byIndex[scoring.qualityWinner] ?? null) : null;
  const speedScores =
    scoring.speedWinner != null ? (scoring.byIndex[scoring.speedWinner] ?? null) : null;
  const overallScores =
    scoring.overallWinner != null ? (scoring.byIndex[scoring.overallWinner] ?? null) : null;
  const overallScore = overallScores?.harmonic ?? overallScores?.quality ?? null;

  const pairScoresData = completedPrs.map((p) => ({
    pair_index: p.pair_index,
    name: pairLabel(p),
    התחלתי: Math.round(
      (p.baseline_test_metric ?? 0) > 1
        ? (p.baseline_test_metric ?? 0)
        : (p.baseline_test_metric ?? 0) * 100,
    ),
    משופר: Math.round(
      (p.optimized_test_metric ?? 0) > 1
        ? (p.optimized_test_metric ?? 0)
        : (p.optimized_test_metric ?? 0) * 100,
    ),
    isBest: scoring.overallWinner === p.pair_index,
  }));
  const combinedScoresData = completedPrs
    .map((p) => {
      const s = scoring.byIndex[p.pair_index];
      if (!s) return null;
      return {
        pair_index: p.pair_index,
        name: pairLabel(p),
        איכות: Math.round(s.quality * 100),
        מהירות: s.speed != null ? Math.round(s.speed * 100) : 0,
        משולב: s.harmonic != null ? Math.round(s.harmonic * 100) : 0,
        isBest: scoring.overallWinner === p.pair_index,
      };
    })
    .filter((r): r is NonNullable<typeof r> => r != null);
  const pairRespTimeData = completedPrs
    .filter((p) => p.avg_response_time_ms)
    .map((p) => ({
      pair_index: p.pair_index,
      name: pairLabel(p),
      זמן_תגובה: +(p.avg_response_time_ms! / 1000).toFixed(1),
      isBest: scoring.speedWinner === p.pair_index,
    }));

  const scatterPoints: ScatterPoint[] = completedPrs
    .filter((p) => p.avg_response_time_ms != null && p.optimized_test_metric != null)
    .map((p) => {
      const raw = p.optimized_test_metric!;
      const qPct = raw > 1 ? raw : raw * 100;
      const harmonic = scoring.byIndex[p.pair_index]?.harmonic;
      return {
        pair_index: p.pair_index,
        name: pairLabel(p),
        quality: +qPct.toFixed(1),
        latency: +(p.avg_response_time_ms! / 1000).toFixed(2),
        combined: harmonic != null ? Math.round(harmonic * 100) : null,
        isOverall: scoring.overallWinner === p.pair_index,
        isQuality: scoring.qualityWinner === p.pair_index,
        isSpeed: scoring.speedWinner === p.pair_index,
      };
    });
  const { pareto: paretoPoints, dominated: dominatedPoints } = computePareto(scatterPoints);

  const matchesFilter = (pi: number) => pairFilter == null || pi === pairFilter;
  const pairScoresFiltered = pairScoresData.filter((r) => matchesFilter(r.pair_index));
  const combinedScoresFiltered = combinedScoresData.filter((r) => matchesFilter(r.pair_index));
  const pairRespTimeFiltered = pairRespTimeData.filter((r) => matchesFilter(r.pair_index));
  const paretoFiltered = paretoPoints.filter((p) => matchesFilter(p.pair_index));
  const dominatedFiltered = dominatedPoints.filter((p) => matchesFilter(p.pair_index));
  const visiblePrs = useMemo(() => {
    const filtered = pairFilter != null ? prs.filter((p) => p.pair_index === pairFilter) : prs;
    const winnerId = scoring.overallWinner;
    if (winnerId == null) return filtered;
    const winner = filtered.find((p) => p.pair_index === winnerId);
    if (!winner || filtered[0]?.pair_index === winnerId) return filtered;
    return [winner, ...filtered.filter((p) => p.pair_index !== winnerId)];
  }, [prs, pairFilter, scoring.overallWinner]);
  const selectedPair =
    pairFilter != null ? (prs.find((p) => p.pair_index === pairFilter) ?? null) : null;

  const ScoreTip = ({
    active,
    payload,
    label,
  }: {
    active?: boolean;
    payload?: Array<{ value: number; dataKey?: string; color?: string }>;
    label?: string;
  }) => {
    if (!active || !payload?.length) return null;
    const nameMap: Record<string, string> = {
      התחלתי: `${TERMS.score} לפני ${TERMS.optimization}`,
      משופר: `${TERMS.score} אחרי ${TERMS.optimization}`,
    };
    return (
      <div
        className="rounded-xl border border-border/60 bg-background/95 backdrop-blur-sm p-3 shadow-lg"
        dir="rtl"
      >
        {label && <p className="font-semibold mb-1.5 text-foreground text-xs">{label}</p>}
        {payload.map((p, i) => (
          <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
            {p.color && (
              <span className="size-2 rounded-full shrink-0" style={{ backgroundColor: p.color }} />
            )}
            <span>{nameMap[String(p.dataKey)] ?? String(p.dataKey)}</span>
            <span className="font-mono font-semibold text-foreground ms-auto">{p.value}%</span>
          </div>
        ))}
      </div>
    );
  };

  const CombinedTip = ({
    active,
    payload,
    label,
  }: {
    active?: boolean;
    payload?: Array<{ value: number; dataKey?: string; color?: string }>;
    label?: string;
  }) => {
    if (!active || !payload?.length) return null;
    return (
      <div
        className="rounded-xl border border-border/60 bg-background/95 backdrop-blur-sm p-3 shadow-lg"
        dir="rtl"
      >
        {label && <p className="font-semibold mb-1.5 text-foreground text-xs">{label}</p>}
        {payload.map((p, i) => (
          <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
            {p.color && (
              <span className="size-2 rounded-full shrink-0" style={{ backgroundColor: p.color }} />
            )}
            <span>{String(p.dataKey)}</span>
            <span className="font-mono font-semibold text-foreground ms-auto">{p.value}%</span>
          </div>
        ))}
      </div>
    );
  };

  const ScatterTip = ({
    active,
    payload,
  }: {
    active?: boolean;
    payload?: Array<{ payload: ScatterPoint }>;
  }) => {
    if (!active || !payload?.length) return null;
    const first = payload[0];
    if (!first) return null;
    const p = first.payload;
    return (
      <div className="rounded-xl border border-border/60 bg-background/95 backdrop-blur-sm p-2.5 shadow-lg">
        <p className="font-mono font-semibold text-xs text-foreground mb-1" dir="ltr">
          {p.name}
        </p>
        <div className="text-[0.6875rem] text-muted-foreground space-y-0.5" dir="rtl">
          <div className="flex gap-4 justify-between">
            <span>איכות</span>
            <span className="font-mono text-foreground tabular-nums">{p.quality}%</span>
          </div>
          <div className="flex gap-4 justify-between">
            <span>זמן תגובה</span>
            <span className="font-mono text-foreground tabular-nums">{p.latency}s</span>
          </div>
          {p.combined != null && (
            <div className="flex gap-4 justify-between">
              <span>משולב</span>
              <span className="font-mono text-foreground tabular-nums">{p.combined}%</span>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4" data-tutorial="grid-search">
      <StaggerContainer className="grid grid-cols-3 gap-3">
        <StaggerItem>
          <TiltCard
            className="rounded-xl border border-border/50 bg-card/80 p-4 text-center"
            onClick={qualityPair ? () => setPairFilter(qualityPair.pair_index) : undefined}
          >
            <div className="flex items-center justify-center gap-1.5 mb-1">
              <Trophy className="size-3 text-[#C8A882]" />
              <p className="text-[0.625rem] text-muted-foreground">איכות</p>
            </div>
            <p
              className="font-mono text-[0.6875rem] font-semibold truncate text-foreground"
              title={qualityPair ? pairLabel(qualityPair) : undefined}
              dir="ltr"
            >
              {qualityPair ? pairLabel(qualityPair) : "—"}
            </p>
            <p className="text-sm font-mono font-bold tabular-nums text-foreground mt-0.5">
              {formatPercent(qualityPair?.optimized_test_metric)}
            </p>
            <HarmonicCalc scores={qualityScores} className="text-muted-foreground/70" />
          </TiltCard>
        </StaggerItem>
        <StaggerItem>
          <TiltCard
            className="rounded-xl border border-border/50 bg-card/80 p-4 text-center"
            onClick={speedPair ? () => setPairFilter(speedPair.pair_index) : undefined}
          >
            <div className="flex items-center justify-center gap-1.5 mb-1">
              <Gauge className="size-3 text-[#3D2E22]" />
              <p className="text-[0.625rem] text-muted-foreground">מהירות</p>
            </div>
            <p
              className="font-mono text-[0.6875rem] font-semibold truncate text-foreground"
              title={speedPair ? pairLabel(speedPair) : undefined}
              dir="ltr"
            >
              {speedPair ? pairLabel(speedPair) : "—"}
            </p>
            <p className="text-sm font-mono font-bold tabular-nums text-foreground mt-0.5">
              {speedPair?.avg_response_time_ms != null
                ? `${(speedPair.avg_response_time_ms / 1000).toFixed(1)}s`
                : "—"}
            </p>
            <HarmonicCalc scores={speedScores} className="text-muted-foreground/70" />
          </TiltCard>
        </StaggerItem>
        <StaggerItem>
          <TiltCard
            className="rounded-xl border border-[#3D2E22]/40 bg-[#3D2E22]/5 p-4 text-center"
            onClick={overallPair ? () => setPairFilter(overallPair.pair_index) : undefined}
          >
            <div className="flex items-center justify-center gap-1.5 mb-1">
              <Target className="size-3 text-[#3D2E22]" />
              <p className="text-[0.625rem] text-[#3D2E22]">{TERMS.optimizedScore}</p>
            </div>
            <p
              className="font-mono text-[0.6875rem] font-semibold truncate text-[#3D2E22]"
              title={overallPair ? pairLabel(overallPair) : undefined}
              dir="ltr"
            >
              {overallPair ? pairLabel(overallPair) : "—"}
            </p>
            <p className="text-sm font-mono font-bold tabular-nums text-[#3D2E22] mt-0.5">
              {overallScore != null ? `${Math.round(overallScore * 100)}%` : "—"}
            </p>
            <HarmonicCalc scores={overallScores} className="text-[#3D2E22]/60" />
          </TiltCard>
        </StaggerItem>
      </StaggerContainer>

      {completedPrs.length > 0 && (
        <FadeIn delay={0.1}>
          {pairFilter != null && (
            <div className="flex items-center gap-2 flex-wrap mb-3">
              <span className="group inline-flex items-center gap-1.5 rounded-lg bg-[#3D2E22]/[0.06] border border-[#3D2E22]/10 pe-1 ps-2.5 py-1 transition-all duration-150 hover:bg-[#3D2E22]/[0.1] hover:border-[#3D2E22]/20">
                <span
                  className="font-mono text-[0.6875rem] font-medium text-[#3D2E22]/80"
                  dir="ltr"
                >
                  {selectedPair ? pairLabel(selectedPair) : "—"}
                </span>
                <button
                  onClick={() => setPairFilter(null)}
                  className="size-5 rounded-md flex items-center justify-center text-[#3D2E22]/40 hover:text-[#3D2E22] hover:bg-[#3D2E22]/10 transition-colors cursor-pointer"
                  aria-label="הסר סינון"
                >
                  <X className="size-3" />
                </button>
              </span>
            </div>
          )}
          {scatterPoints.length > 0 && (
            <Card className="mb-4">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">
                  <HelpTip text="כל נקודה = זוג מודלים. נקודות בולטות (חומות) הן על חזית פארטו — אין זוג אחר שמנצח אותן גם באיכות וגם במהירות. נקודות שקופות נשלטות ע״י פשרה טובה יותר. לחצו על נקודה כדי לסנן.">
                    חזית פארטו — איכות לעומת מהירות
                  </HelpTip>
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="h-[280px]" dir="ltr">
                  <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart margin={{ top: 10, right: 30, bottom: 35, left: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                      <XAxis
                        type="number"
                        dataKey="latency"
                        name="latency"
                        unit="s"
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 10 }}
                        className="fill-muted-foreground"
                        label={{
                          value: "זמן תגובה בשניות — נמוך יותר טוב יותר",
                          position: "insideBottom",
                          offset: -15,
                          fontSize: 10,
                        }}
                      />
                      <YAxis
                        type="number"
                        dataKey="quality"
                        name="quality"
                        unit="%"
                        domain={[0, 100]}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 10 }}
                        className="fill-muted-foreground"
                        label={{
                          value: "איכות באחוזים — גבוה יותר טוב יותר",
                          angle: -90,
                          position: "center",
                          dx: -15,
                          fontSize: 10,
                        }}
                      />
                      <ZAxis range={[70, 70]} />
                      <Tooltip content={<ScatterTip />} cursor={{ strokeDasharray: "3 3" }} />
                      {!hiddenScatterSeries.has("dominated") && (
                        <Scatter
                          data={dominatedFiltered}
                          fill="var(--color-muted-foreground)"
                          fillOpacity={0.35}
                          cursor="pointer"
                          onClick={handleBarClick}
                        />
                      )}
                      {!hiddenScatterSeries.has("pareto") && (
                        <Scatter
                          data={paretoFiltered}
                          fill="#3D2E22"
                          cursor="pointer"
                          onClick={handleBarClick}
                        />
                      )}
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
                <div
                  className="mt-2 flex items-center justify-center gap-4 text-[0.6875rem]"
                  dir="rtl"
                >
                  {[
                    {
                      key: "pareto",
                      label: "חזית פארטו — בחירה מיטבית",
                      color: "#3D2E22",
                    },
                    {
                      key: "dominated",
                      label: "נשלט — יש זוג טוב יותר בשני הצירים",
                      color: "var(--color-muted-foreground)",
                    },
                  ].map(({ key, label, color }) => {
                    const isHidden = hiddenScatterSeries.has(key);
                    return (
                      <button
                        key={key}
                        type="button"
                        onClick={() => toggleScatterSeries(key)}
                        className={`inline-flex items-center gap-1.5 cursor-pointer transition-colors ${isHidden ? "text-muted-foreground/50" : "text-muted-foreground hover:text-foreground"}`}
                        aria-pressed={!isHidden}
                      >
                        <span
                          className="size-2 rounded-full transition-all"
                          style={
                            isHidden
                              ? {
                                  backgroundColor: "transparent",
                                  boxShadow: `inset 0 0 0 1.5px ${color}`,
                                }
                              : { backgroundColor: color }
                          }
                        />
                        {label}
                      </button>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          )}
          <AnimatePresence mode="wait">
            <motion.div
              key={pairFilter ?? "all"}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.3, ease: [0.2, 0.8, 0.2, 1] }}
            >
              <div className="grid gap-4 md:grid-cols-2">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-semibold">
                      <HelpTip text={tip("grid.score_comparison")}>ציונים לפי זוג</HelpTip>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="pt-0">
                    <div className="h-[220px]" dir="ltr">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={pairScoresFiltered}
                          layout="vertical"
                          margin={{ left: 10, right: 20, top: 5, bottom: 5 }}
                        >
                          <CartesianGrid
                            horizontal={false}
                            strokeDasharray="3 3"
                            className="stroke-muted"
                          />
                          <XAxis
                            type="number"
                            domain={[0, 105]}
                            tickLine={false}
                            axisLine={false}
                            tick={{ fontSize: 10 }}
                            className="fill-muted-foreground"
                            label={{
                              value: "ציון באחוזים",
                              position: "insideBottom",
                              offset: -2,
                              fontSize: 10,
                            }}
                          />
                          <YAxis
                            type="category"
                            dataKey="name"
                            tick={{ fontSize: 10 }}
                            width={100}
                            className="fill-muted-foreground"
                            tickLine={false}
                            axisLine={false}
                            label={{
                              value: "זוג מודלים",
                              angle: -90,
                              position: "insideLeft",
                              offset: 15,
                              fontSize: 10,
                            }}
                          />
                          <Tooltip content={<ScoreTip />} />
                          {!hiddenPairSeries.has("התחלתי") && (
                            <Bar
                              dataKey="התחלתי"
                              name="התחלתי"
                              fill="var(--color-chart-4)"
                              radius={[0, 3, 3, 0]}
                              barSize={12}
                              animationDuration={400}
                              cursor="pointer"
                              onClick={handleBarClick}
                            />
                          )}
                          {!hiddenPairSeries.has("משופר") && (
                            <Bar
                              dataKey="משופר"
                              name="משופר"
                              fill="var(--color-chart-2)"
                              radius={[0, 3, 3, 0]}
                              barSize={12}
                              animationDuration={400}
                              cursor="pointer"
                              onClick={handleBarClick}
                            />
                          )}
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="flex justify-center gap-4 mt-1">
                      {[
                        { key: "התחלתי", color: "var(--color-chart-4)" },
                        { key: "משופר", color: "var(--color-chart-2)" },
                      ].map(({ key, color }) => {
                        const isHidden = hiddenPairSeries.has(key);
                        return (
                          <button
                            key={key}
                            type="button"
                            onClick={() => togglePairSeries(key)}
                            className={`flex items-center gap-1.5 text-[0.625rem] cursor-pointer transition-colors ${isHidden ? "text-muted-foreground/50" : "text-muted-foreground hover:text-foreground"}`}
                            aria-pressed={!isHidden}
                          >
                            <span
                              className="size-2 rounded-full transition-all"
                              style={
                                isHidden
                                  ? {
                                      backgroundColor: "transparent",
                                      boxShadow: `inset 0 0 0 1.5px ${color}`,
                                    }
                                  : { backgroundColor: color }
                              }
                            />
                            {key}
                          </button>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-semibold">
                      <HelpTip text={tip("grid.quality_speed_combined")}>
                        ציונים משולבים לפי זוג
                      </HelpTip>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="pt-0">
                    <div className="h-[220px]" dir="ltr">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={combinedScoresFiltered}
                          layout="vertical"
                          margin={{ left: 10, right: 20, top: 5, bottom: 5 }}
                        >
                          <CartesianGrid
                            horizontal={false}
                            strokeDasharray="3 3"
                            className="stroke-muted"
                          />
                          <XAxis
                            type="number"
                            domain={[0, 100]}
                            tickLine={false}
                            axisLine={false}
                            tick={{ fontSize: 10 }}
                            className="fill-muted-foreground"
                            label={{
                              value: "ציון באחוזים",
                              position: "insideBottom",
                              offset: -2,
                              fontSize: 10,
                            }}
                          />
                          <YAxis
                            type="category"
                            dataKey="name"
                            tick={{ fontSize: 10 }}
                            width={100}
                            className="fill-muted-foreground"
                            tickLine={false}
                            axisLine={false}
                            label={{
                              value: "זוג מודלים",
                              angle: -90,
                              position: "insideLeft",
                              offset: 15,
                              fontSize: 10,
                            }}
                          />
                          <Tooltip content={<CombinedTip />} />
                          {!hiddenCombinedSeries.has("איכות") && (
                            <Bar
                              dataKey="איכות"
                              name="איכות"
                              fill="var(--color-chart-2)"
                              radius={[0, 3, 3, 0]}
                              barSize={8}
                              animationDuration={400}
                              cursor="pointer"
                              onClick={handleBarClick}
                            />
                          )}
                          {!hiddenCombinedSeries.has("מהירות") && (
                            <Bar
                              dataKey="מהירות"
                              name="מהירות"
                              fill="var(--color-chart-4)"
                              radius={[0, 3, 3, 0]}
                              barSize={8}
                              animationDuration={400}
                              cursor="pointer"
                              onClick={handleBarClick}
                            />
                          )}
                          {!hiddenCombinedSeries.has("משולב") && (
                            <Bar
                              dataKey="משולב"
                              name="משולב"
                              radius={[0, 3, 3, 0]}
                              barSize={8}
                              animationDuration={400}
                              cursor="pointer"
                              onClick={handleBarClick}
                            >
                              {combinedScoresFiltered.map((entry, i) => (
                                <Cell key={i} fill={entry.isBest ? "#3D2E22" : "#8C7A6B"} />
                              ))}
                            </Bar>
                          )}
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="flex flex-wrap justify-center gap-3 mt-1">
                      {[
                        { key: "איכות", color: "var(--color-chart-2)" },
                        { key: "מהירות", color: "var(--color-chart-4)" },
                        { key: "משולב", color: "#3D2E22" },
                      ].map(({ key, color }) => {
                        const isHidden = hiddenCombinedSeries.has(key);
                        return (
                          <button
                            key={key}
                            type="button"
                            onClick={() => toggleCombinedSeries(key)}
                            className={`flex items-center gap-1.5 text-[0.625rem] cursor-pointer transition-colors ${isHidden ? "text-muted-foreground/50" : "text-muted-foreground hover:text-foreground"}`}
                            aria-pressed={!isHidden}
                          >
                            <span
                              className="size-2 rounded-full transition-all"
                              style={
                                isHidden
                                  ? {
                                      backgroundColor: "transparent",
                                      boxShadow: `inset 0 0 0 1.5px ${color}`,
                                    }
                                  : { backgroundColor: color }
                              }
                            />
                            {key}
                          </button>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>
              </div>

              {pairRespTimeFiltered.length > 0 && (
                <Card className="mt-4">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-semibold">
                      <HelpTip text={tip("grid.avg_response_time_per_pair")}>
                        זמן תגובה ממוצע לפי זוג
                      </HelpTip>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="pt-0">
                    <div className="h-[220px]" dir="ltr">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={pairRespTimeFiltered}
                          layout="vertical"
                          margin={{ left: 10, right: 20, top: 5, bottom: 5 }}
                        >
                          <CartesianGrid
                            horizontal={false}
                            strokeDasharray="3 3"
                            className="stroke-muted"
                          />
                          <XAxis
                            type="number"
                            tickLine={false}
                            axisLine={false}
                            tick={{ fontSize: 10 }}
                            className="fill-muted-foreground"
                            label={{
                              value: "זמן תגובה בשניות",
                              position: "insideBottom",
                              offset: -2,
                              fontSize: 10,
                            }}
                          />
                          <YAxis
                            type="category"
                            dataKey="name"
                            tick={{ fontSize: 10 }}
                            width={100}
                            className="fill-muted-foreground"
                            tickLine={false}
                            axisLine={false}
                            label={{
                              value: "זוג מודלים",
                              angle: -90,
                              position: "insideLeft",
                              offset: 15,
                              fontSize: 10,
                            }}
                          />
                          <Tooltip
                            content={({ active, payload, label }) => {
                              if (!active || !payload?.length) return null;
                              return (
                                <div
                                  className="rounded-xl border border-border/60 bg-background/95 backdrop-blur-sm p-3 shadow-lg"
                                  dir="rtl"
                                >
                                  {label && (
                                    <p className="font-semibold mb-1.5 text-foreground text-xs">
                                      {label}
                                    </p>
                                  )}
                                  <div className="flex items-center gap-2 text-xs">
                                    <span className="text-muted-foreground">
                                      זמן תגובה ממוצע לקריאה:
                                    </span>
                                    <span className="font-mono font-semibold text-foreground ms-auto">
                                      {payload[0]!.value}s
                                    </span>
                                  </div>
                                </div>
                              );
                            }}
                          />
                          <Bar
                            dataKey="זמן_תגובה"
                            name="זמן תגובה בשניות"
                            radius={[0, 3, 3, 0]}
                            barSize={14}
                            animationDuration={400}
                            cursor="pointer"
                            onClick={handleBarClick}
                          >
                            {pairRespTimeFiltered.map((entry, i) => (
                              <Cell
                                key={i}
                                fill={entry.isBest ? "#C8A882" : "var(--color-chart-4)"}
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>
              )}
            </motion.div>
          </AnimatePresence>
        </FadeIn>
      )}

      <div className="space-y-2" data-tutorial="grid-pair-list">
        {visiblePrs.map((pr) => {
          const isOverall = scoring.overallWinner === pr.pair_index;
          const isQuality = scoring.qualityWinner === pr.pair_index;
          const isSpeed = scoring.speedWinner === pr.pair_index;
          const s = scoring.byIndex[pr.pair_index];
          const barRatio = s?.harmonic ?? s?.quality ?? 0;
          return (
            <div
              key={pr.pair_index}
              className={`group rounded-xl border p-4 transition-all duration-200 cursor-pointer hover:shadow-sm ${
                pr.error
                  ? "border-[#B04030]/30 bg-[#B04030]/[0.02] hover:border-[#B04030]/50"
                  : isOverall
                    ? "border-[#3D2E22]/40 bg-[#3D2E22]/[0.03] hover:border-[#3D2E22]/60"
                    : "border-border/50 bg-card/80 hover:border-border"
              }`}
              onClick={() => onPairSelect(pr.pair_index)}
            >
              <div className="flex items-center gap-3">
                {isOverall && <Crown className="size-4 text-[#C8A882] shrink-0" />}
                {pr.error && <XCircle className="size-4 text-[#B04030] shrink-0" />}

                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <div className="flex items-center gap-1 min-w-0">
                    <span className="font-mono text-xs truncate" title={pr.generation_model}>
                      {pr.generation_model.split("/").pop()}
                    </span>
                    {pr.generation_reasoning_effort && (
                      <ReasoningPill value={pr.generation_reasoning_effort} />
                    )}
                  </div>
                  <span className="text-[0.625rem] text-muted-foreground/50">×</span>
                  <div className="flex items-center gap-1 min-w-0">
                    <span className="font-mono text-xs truncate" title={pr.reflection_model}>
                      {pr.reflection_model.split("/").pop()}
                    </span>
                    {pr.reflection_reasoning_effort && (
                      <ReasoningPill value={pr.reflection_reasoning_effort} />
                    )}
                  </div>
                </div>

                {!pr.error ? (
                  <div
                    className="flex items-center gap-4 shrink-0 tabular-nums font-mono text-xs"
                    dir="rtl"
                  >
                    <div className="text-center min-w-[44px]">
                      <div className="text-[9px] text-foreground/50 mb-0.5 flex items-center justify-center gap-1">
                        <Trophy className="size-2.5" />
                        איכות
                      </div>
                      <div className={isQuality ? "font-bold text-[#3D2E22]" : "text-foreground"}>
                        {s ? `${Math.round(s.quality * 100)}%` : "—"}
                      </div>
                    </div>
                    <div className="text-center min-w-[44px]">
                      <div className="text-[9px] text-foreground/50 mb-0.5 flex items-center justify-center gap-1">
                        <Gauge className="size-2.5" />
                        זמן תגובה
                      </div>
                      <div className={isSpeed ? "font-bold text-[#3D2E22]" : "text-foreground"}>
                        {pr.avg_response_time_ms != null
                          ? `${(pr.avg_response_time_ms / 1000).toFixed(1)}s`
                          : "—"}
                      </div>
                    </div>
                    <div className="text-center min-w-[44px]">
                      <div className="text-[9px] text-foreground/50 mb-0.5 flex items-center justify-center gap-1">
                        <Target className="size-2.5" />
                        משולב
                      </div>
                      <div className={isOverall ? "font-bold text-[#3D2E22]" : "text-foreground"}>
                        {s?.harmonic != null
                          ? `${Math.round(s.harmonic * 100)}%`
                          : s
                            ? `${Math.round(s.quality * 100)}%`
                            : "—"}
                      </div>
                    </div>
                  </div>
                ) : (
                  <span
                    className="text-[0.6875rem] text-[#B04030] truncate max-w-[280px]"
                    title={pr.error}
                  >
                    {pr.error}
                  </span>
                )}

                <TooltipProvider>
                  <UiTooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-7 text-muted-foreground/50 hover:text-red-600 shrink-0"
                        aria-label="מחיקת זוג"
                        onClick={(e) => {
                          e.stopPropagation();
                          setPendingDelete(pr);
                        }}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="bottom">מחיקת זוג</TooltipContent>
                  </UiTooltip>
                </TooltipProvider>

                <ChevronLeft className="size-4 text-muted-foreground/30 group-hover:text-muted-foreground transition-colors shrink-0" />
              </div>

              {!pr.error && (
                <div className="mt-2.5 h-1 rounded-full bg-border/30 overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${barRatio * 100}%`,
                      background: isOverall ? "#3D2E22" : "#C8A882",
                      opacity: isOverall ? 0.6 : 0.3,
                    }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <Dialog open={pendingDelete !== null} onOpenChange={(o) => !o && setPendingDelete(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>מחיקת זוג</DialogTitle>
            <DialogDescription>
              האם למחוק את הזוג{" "}
              <span className="font-mono font-medium text-foreground break-all">
                {pendingDelete ? pairLabel(pendingDelete) : ""}
              </span>
              ? פעולה זו אינה הפיכה.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="grid grid-cols-2 gap-2">
            <Button
              variant="outline"
              onClick={() => setPendingDelete(null)}
              disabled={deleting}
              className="w-full justify-center"
            >
              ביטול
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmDelete}
              disabled={deleting}
              className="w-full justify-center"
            >
              {deleting ? <Loader2 className="size-4 animate-spin" /> : "מחיקה"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
