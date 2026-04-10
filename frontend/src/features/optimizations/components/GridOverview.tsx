"use client";

/**
 * Grid-search overview — aggregated KPIs, comparison charts, and pair
 * cards for a completed grid-search job.
 *
 * Extracted from app/optimizations/[id]/page.tsx. Pure display component
 * that takes the job + a pair-selection callback.
 */

import { ChevronLeft, Crown, XCircle } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FadeIn, StaggerContainer, StaggerItem, TiltCard } from "@/components/motion";
import { HelpTip } from "@/components/help-tip";
import type { OptimizationStatusResponse } from "@/lib/types";
import { formatPercent, formatImprovement } from "../lib/formatters";

export function GridOverview({
  job,
  onPairSelect,
}: {
  job: OptimizationStatusResponse;
  onPairSelect: (pairIndex: number) => void;
}) {
  if (!job.grid_result) return null;
  const prs = job.grid_result.pair_results;
  const best = job.grid_result.best_pair;
  const completedPrs = prs.filter((p) => !p.error);
  const maxScore = Math.max(...completedPrs.map((p) => p.optimized_test_metric ?? 0), 0.01);

  const scores = completedPrs.map((p) => p.optimized_test_metric ?? 0);
  const improvements = completedPrs.map((p) => p.metric_improvement ?? 0);

  const avg = (arr: number[]) => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0);
  const bestScore = scores.length ? Math.max(...scores) : 0;
  const avgImprovement = avg(improvements);

  const pairScoresData = completedPrs.map((p) => ({
    name: `${p.generation_model.split("/").pop()} × ${p.reflection_model.split("/").pop()}`,
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
    isBest: best?.pair_index === p.pair_index,
  }));
  const pairImprovData = completedPrs.map((p) => ({
    name: `${p.generation_model.split("/").pop()} × ${p.reflection_model.split("/").pop()}`,
    שיפור: +(
      (p.metric_improvement ?? 0) > 1
        ? (p.metric_improvement ?? 0)
        : (p.metric_improvement ?? 0) * 100
    ).toFixed(1),
    isBest: best?.pair_index === p.pair_index,
  }));
  const pairRespTimeData = completedPrs
    .filter((p) => p.avg_response_time_ms)
    .map((p) => ({
      name: `${p.generation_model.split("/").pop()} × ${p.reflection_model.split("/").pop()}`,
      זמן_תגובה: +(p.avg_response_time_ms! / 1000).toFixed(1),
      isBest: best?.pair_index === p.pair_index,
    }));

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
      התחלתי: "ציון לפני אופטימיזציה",
      משופר: "ציון אחרי אופטימיזציה",
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

  const ImprovTip = ({
    active,
    payload,
    label,
  }: {
    active?: boolean;
    payload?: Array<{ value: number; color?: string }>;
    label?: string;
  }) => {
    if (!active || !payload?.length) return null;
    const val = payload[0]!.value;
    return (
      <div
        className="rounded-xl border border-border/60 bg-background/95 backdrop-blur-sm p-3 shadow-lg"
        dir="rtl"
      >
        {label && <p className="font-semibold mb-1.5 text-foreground text-xs">{label}</p>}
        <div className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">שיפור ביצועים:</span>
          <span
            className={`font-mono font-semibold ms-auto ${val > 0 ? "text-[#5C7A52]" : val < 0 ? "text-[#B04030]" : "text-foreground"}`}
          >
            {val > 0 ? "+" : ""}
            {val}%
          </span>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4" data-tutorial="grid-search">
      <StaggerContainer className="grid grid-cols-2 gap-3">
        <StaggerItem>
          <TiltCard className="rounded-xl border border-[#5C7A52]/30 bg-[#5C7A52]/5 p-4 text-center">
            <p className="text-[10px] text-[#5C7A52] mb-1">ציון מנצח</p>
            <p className="text-2xl font-mono font-bold tabular-nums text-[#5C7A52]">
              {formatPercent(bestScore)}
            </p>
          </TiltCard>
        </StaggerItem>
        <StaggerItem>
          <TiltCard className="rounded-xl border border-border/50 bg-card/80 p-4 text-center">
            <p className="text-[10px] text-muted-foreground mb-1">שיפור ממוצע</p>
            <p
              className={`text-2xl font-mono font-bold tabular-nums ${avgImprovement > 0 ? "text-[#5C7A52]" : avgImprovement < 0 ? "text-[#B04030]" : ""}`}
            >
              {formatImprovement(avgImprovement)}
            </p>
          </TiltCard>
        </StaggerItem>
      </StaggerContainer>

      {completedPrs.length > 0 && (
        <FadeIn delay={0.1}>
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">
                  <HelpTip text="השוואת ציוני הבסיס והציון המשופר לכל זוג מודלים">
                    ציונים לפי זוג
                  </HelpTip>
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="h-[220px]" dir="ltr">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={pairScoresData}
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
                      <Bar
                        dataKey="התחלתי"
                        name="התחלתי"
                        fill="var(--color-chart-4)"
                        radius={[0, 3, 3, 0]}
                        barSize={12}
                        animationDuration={400}
                      />
                      <Bar
                        dataKey="משופר"
                        name="משופר"
                        fill="var(--color-chart-2)"
                        radius={[0, 3, 3, 0]}
                        barSize={12}
                        animationDuration={400}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex justify-center gap-4 mt-1">
                  <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                    <span
                      className="size-2 rounded-full"
                      style={{ backgroundColor: "var(--color-chart-4)" }}
                    />{" "}
                    התחלתי
                  </div>
                  <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                    <span
                      className="size-2 rounded-full"
                      style={{ backgroundColor: "var(--color-chart-2)" }}
                    />{" "}
                    משופר
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">
                  <HelpTip text="אחוז השיפור שכל זוג מודלים השיג ביחס לציון ההתחלתי">
                    שיפור לפי זוג
                  </HelpTip>
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="h-[220px]" dir="ltr">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={pairImprovData}
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
                          value: "שיפור באחוזים",
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
                      <Tooltip content={<ImprovTip />} />
                      <Bar
                        dataKey="שיפור"
                        name="שיפור"
                        radius={[0, 3, 3, 0]}
                        barSize={14}
                        animationDuration={400}
                      >
                        {pairImprovData.map((entry, i) => (
                          <Cell
                            key={i}
                            fill={
                              entry.isBest
                                ? "#5C7A52"
                                : entry.שיפור >= 0
                                  ? "var(--color-chart-2)"
                                  : "#B04030"
                            }
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          </div>

          {pairRespTimeData.length > 0 && (
            <Card className="mt-4">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">
                  <HelpTip text="משך זמן ממוצע לכל קריאה למודל שפה, לפי זוג מודלים">
                    זמן תגובה ממוצע לפי זוג
                  </HelpTip>
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="h-[220px]" dir="ltr">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={pairRespTimeData}
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
                      >
                        {pairRespTimeData.map((entry, i) => (
                          <Cell key={i} fill={entry.isBest ? "#C8A882" : "var(--color-chart-4)"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}
        </FadeIn>
      )}

      <div className="space-y-2">
        {prs.map((pr) => {
          const isBest = best?.pair_index === pr.pair_index;
          const scoreRatio = (pr.optimized_test_metric ?? 0) / maxScore;
          const improv = pr.metric_improvement ?? 0;
          return (
            <div
              key={pr.pair_index}
              className={`group rounded-xl border p-4 transition-all duration-200 cursor-pointer hover:shadow-sm ${
                pr.error
                  ? "border-[#B04030]/30 bg-[#B04030]/[0.02] hover:border-[#B04030]/50"
                  : isBest
                    ? "border-[#5C7A52]/40 bg-[#5C7A52]/[0.03] hover:border-[#5C7A52]/60"
                    : "border-border/50 bg-card/80 hover:border-border"
              }`}
              onClick={() => onPairSelect(pr.pair_index)}
            >
              <div className="flex items-center gap-3">
                {isBest && <Crown className="size-4 text-[#C8A882] shrink-0" />}
                {pr.error && <XCircle className="size-4 text-[#B04030] shrink-0" />}

                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <span className="font-mono text-xs truncate" title={pr.generation_model}>
                    {pr.generation_model.split("/").pop()}
                  </span>
                  <span className="text-[10px] text-muted-foreground/50">×</span>
                  <span className="font-mono text-xs truncate" title={pr.reflection_model}>
                    {pr.reflection_model.split("/").pop()}
                  </span>
                </div>

                {!pr.error ? (
                  <div
                    className="flex items-center gap-4 shrink-0 tabular-nums font-mono text-xs"
                    dir="rtl"
                  >
                    <div className="text-center">
                      <div className="text-[9px] text-foreground/50 mb-0.5">התחלתי</div>
                      <div className="text-foreground">
                        {formatPercent(pr.baseline_test_metric)}
                      </div>
                    </div>
                    <div className="text-center">
                      <div className="text-[9px] text-foreground/50 mb-0.5">משופר</div>
                      <div className={isBest ? "font-bold text-[#5C7A52]" : "text-foreground"}>
                        {formatPercent(pr.optimized_test_metric)}
                      </div>
                    </div>
                    <div
                      className={`text-center min-w-[48px] ${improv > 0 ? "text-[#5C7A52]" : improv < 0 ? "text-[#B04030]" : "text-foreground"}`}
                    >
                      <div className="text-[9px] text-foreground/50 mb-0.5">שיפור</div>
                      <div>{formatImprovement(improv)}</div>
                    </div>
                  </div>
                ) : (
                  <span
                    className="text-[11px] text-[#B04030] truncate max-w-[280px]"
                    title={pr.error}
                  >
                    {pr.error}
                  </span>
                )}

                <ChevronLeft className="size-4 text-muted-foreground/30 group-hover:text-muted-foreground transition-colors shrink-0" />
              </div>

              {!pr.error && (
                <div className="mt-2.5 h-1 rounded-full bg-border/30 overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${scoreRatio * 100}%`,
                      background: isBest ? "#5C7A52" : "#C8A882",
                      opacity: isBest ? 0.6 : 0.3,
                    }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
