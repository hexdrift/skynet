"use client";

import dynamic from "next/dynamic";
import { Activity, Clock, Database, MessageSquare, Timer, TrendingUp, Zap } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/primitives/card";
import { FadeIn, StaggerContainer, StaggerItem, TiltCard } from "@/shared/ui/motion";
import { HelpTip } from "@/shared/ui/help-tip";
import type { OptimizationStatusResponse } from "@/shared/types/api";
import { type PipelineStage } from "../constants";
import { detectStage } from "../lib/detect-stage";
import { formatDuration, formatImprovement, formatPercent } from "@/shared/lib";
import { tip } from "@/shared/lib/tooltips";
import { TERMS } from "@/shared/lib/terms";
import type { ScorePoint } from "../lib/extract-scores";
import { GridOverview } from "./GridOverview";
import { GridLiveChart } from "./GridLiveChart";
import { InfoCard } from "./ui-primitives";
import { PipelineStages, computeStageTimestamps } from "./PipelineStages";
import { formatMsg, msg } from "@/shared/lib/messages";

const ScoreChart = dynamic(() => import("@/shared/ui/score-chart").then((m) => m.ScoreChart), {
  ssr: false,
  loading: () => <div className="h-full" />,
});

export function OverviewTab({
  job,
  isActive,
  scorePoints,
  activePairIndex,
  onStageClick,
  onPairSelect,
  onPairDeleted,
  onShowLMActivity,
}: {
  job: OptimizationStatusResponse;
  isActive: boolean;
  scorePoints: ScorePoint[];
  activePairIndex: number | null;
  onStageClick: (stage: PipelineStage) => void;
  onPairSelect: (pairIndex: number) => void;
  onPairDeleted?: (pairIndex: number) => void;
  onShowLMActivity?: () => void;
}) {
  const metrics = job.latest_metrics ?? {};

  return (
    <>
      <FadeIn>
        <p className="text-sm text-muted-foreground">
          {isActive
            ? formatMsg("auto.features.optimizations.components.overviewtab.template.1", {
                p1: TERMS.optimization,
              })
            : job.status === "cancelled"
              ? formatMsg("auto.features.optimizations.components.overviewtab.template.2", {
                  p1: TERMS.optimization,
                })
              : job.status === "failed"
                ? formatMsg("auto.features.optimizations.components.overviewtab.template.3", {
                    p1: TERMS.optimization,
                  })
                : formatMsg("auto.features.optimizations.components.overviewtab.template.4", {
                    p1: TERMS.optimization,
                  })}
        </p>
      </FadeIn>

      {isActive &&
        (() => {
          const tqdmPercent = metrics.tqdm_percent as number | undefined;
          const tqdmDesc = metrics.tqdm_desc as string | undefined;
          const tqdmN = metrics.tqdm_n as number | undefined;
          const tqdmTotal = metrics.tqdm_total as number | undefined;
          return tqdmPercent != null ? (
            <FadeIn>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{tqdmDesc || TERMS.optimization}</span>
                  <span className="font-mono tabular-nums">
                    {tqdmN ?? 0}/{tqdmTotal ?? "?"} ({tqdmPercent.toFixed(0)}%)
                  </span>
                </div>
                <div className="h-2 rounded-full bg-border/50 overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-full transition-all duration-500"
                    style={{ width: `${tqdmPercent}%` }}
                  />
                </div>
              </div>
            </FadeIn>
          ) : null;
        })()}

      {isActive &&
        (() => {
          const tqdmN = metrics.tqdm_n as number | undefined;
          const tqdmTotal = metrics.tqdm_total as number | undefined;
          const tqdmElapsed = metrics.tqdm_elapsed as number | undefined;
          const tqdmRemaining = metrics.tqdm_remaining as number | undefined;
          const tqdmRate = metrics.tqdm_rate as number | undefined;
          const baselineScore =
            job.optimization_type === "grid_search"
              ? undefined
              : (job.progress_events?.find((e) => e.event === "baseline_evaluated")?.metrics
                  ?.baseline_test_metric as number | undefined);
          const splitsEvent = job.progress_events?.find((e) => e.event === "dataset_splits_ready");
          const trainCount = (splitsEvent?.metrics?.train_examples ?? metrics.train_examples) as
            | number
            | undefined;
          const valCount = (splitsEvent?.metrics?.val_examples ?? metrics.val_examples) as
            | number
            | undefined;
          const testCount = (splitsEvent?.metrics?.test_examples ?? metrics.test_examples) as
            | number
            | undefined;
          const hasAny =
            tqdmN != null || tqdmElapsed != null || baselineScore != null || trainCount != null;
          if (!hasAny) return null;
          return (
            <div
              className="grid gap-2.5"
              style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(120px, 100%), 1fr))" }}
            >
              {tqdmN != null && tqdmTotal != null && (
                <InfoCard
                  label={msg("auto.features.optimizations.components.overviewtab.literal.1")}
                  value={`${tqdmN}/${tqdmTotal}`}
                  icon={<Activity className="size-3.5" />}
                />
              )}
              {tqdmElapsed != null && (
                <InfoCard
                  label={msg("auto.features.optimizations.components.overviewtab.literal.2")}
                  value={formatDuration(tqdmElapsed)}
                  icon={<Timer className="size-3.5" />}
                />
              )}
              {tqdmRemaining != null && (
                <InfoCard
                  label={msg("auto.features.optimizations.components.overviewtab.literal.3")}
                  value={formatDuration(Number(tqdmRemaining))}
                  icon={<Clock className="size-3.5" />}
                />
              )}
              {tqdmRate != null && (
                <InfoCard
                  label={msg("auto.features.optimizations.components.overviewtab.literal.4")}
                  value={formatMsg(
                    "auto.features.optimizations.components.overviewtab.template.5",
                    { p1: tqdmRate.toFixed(2) },
                  )}
                  icon={<Zap className="size-3.5" />}
                />
              )}
              {baselineScore != null && (
                <InfoCard
                  label={TERMS.baselineScore}
                  value={formatPercent(baselineScore)}
                  icon={<TrendingUp className="size-3.5" />}
                />
              )}
              {trainCount != null && (
                <InfoCard
                  label={msg("auto.features.optimizations.components.overviewtab.literal.5")}
                  value={`${trainCount}/${valCount}/${testCount}`}
                  icon={<Database className="size-3.5" />}
                />
              )}
            </div>
          );
        })()}

      {job.optimization_type !== "grid_search" && (
        <FadeIn delay={0.05}>
          <PipelineStages
            currentStage={job.status === "success" ? "done" : detectStage(job)}
            stageTs={computeStageTimestamps(
              job.progress_events ?? [],
              job.started_at,
              job.completed_at,
            )}
            isActive={isActive}
            isFailed={job.status === "failed" || job.status === "cancelled"}
            onStageClick={onStageClick}
            dataTutorial="pipeline-stages"
          />
        </FadeIn>
      )}

      {job.status === "success" &&
        job.optimization_type === "run" &&
        job.result &&
        (() => {
          const activity = job.result.lm_activity;
          // When the backend provided per-LM × per-stage activity, render a
          // compact 2x2 (Generation/Reflection × calls/avg) and link to the
          // dedicated tab. Otherwise fall back to the legacy 2-card summary
          // so older jobs (no ``lm_activity`` field) still render usefully.
          if (activity) {
            const sumStage = (
              perStage: Record<string, { calls: number; avg_response_time_ms?: number | null }>,
            ): { calls: number; avgMs: number | null } => {
              let totalCalls = 0;
              let weighted = 0;
              let weighted_n = 0;
              for (const cell of Object.values(perStage)) {
                const calls = cell?.calls ?? 0;
                totalCalls += calls;
                if (calls > 0 && typeof cell?.avg_response_time_ms === "number") {
                  weighted += cell.avg_response_time_ms * calls;
                  weighted_n += calls;
                }
              }
              return {
                calls: totalCalls,
                avgMs: weighted_n > 0 ? weighted / weighted_n : null,
              };
            };
            const gen = sumStage(activity.generation ?? {});
            const refl = sumStage(activity.reflection ?? {});
            const hasReflection = refl.calls > 0;
            const fmtAvg = (ms: number | null): string =>
              ms == null ? "—" : ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
            return (
              <FadeIn delay={0.1}>
                <div className="space-y-2">
                  <div
                    className={`grid gap-2.5 ${hasReflection ? "grid-cols-2 sm:grid-cols-4" : "grid-cols-2"}`}
                  >
                    <InfoCard
                      label={
                        <HelpTip text={tip("lm_activity.column.generation")}>
                          {msg("auto.features.optimizations.components.lmactivitytab.col_generation")}
                          {" — "}
                          {msg("auto.features.optimizations.components.lmactivitytab.cell_calls")}
                        </HelpTip>
                      }
                      value={gen.calls.toLocaleString("he-IL")}
                      icon={<MessageSquare className="size-3.5" />}
                    />
                    <InfoCard
                      label={
                        <HelpTip text={tip("lm_activity.column.generation")}>
                          {msg("auto.features.optimizations.components.lmactivitytab.col_generation")}
                          {" — "}
                          {msg("auto.features.optimizations.components.lmactivitytab.cell_avg_ms")}
                        </HelpTip>
                      }
                      value={fmtAvg(gen.avgMs)}
                      icon={<Timer className="size-3.5" />}
                    />
                    {hasReflection && (
                      <>
                        <InfoCard
                          label={
                            <HelpTip text={tip("lm_activity.column.reflection")}>
                              {msg(
                                "auto.features.optimizations.components.lmactivitytab.col_reflection",
                              )}
                              {" — "}
                              {msg(
                                "auto.features.optimizations.components.lmactivitytab.cell_calls",
                              )}
                            </HelpTip>
                          }
                          value={refl.calls.toLocaleString("he-IL")}
                          icon={<MessageSquare className="size-3.5" />}
                        />
                        <InfoCard
                          label={
                            <HelpTip text={tip("lm_activity.column.reflection")}>
                              {msg(
                                "auto.features.optimizations.components.lmactivitytab.col_reflection",
                              )}
                              {" — "}
                              {msg(
                                "auto.features.optimizations.components.lmactivitytab.cell_avg_ms",
                              )}
                            </HelpTip>
                          }
                          value={fmtAvg(refl.avgMs)}
                          icon={<Timer className="size-3.5" />}
                        />
                      </>
                    )}
                  </div>
                  {onShowLMActivity && (
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={onShowLMActivity}
                        className="text-xs text-[#7C6350] hover:text-[#3D2E22] transition-colors duration-150 underline-offset-2 hover:underline cursor-pointer"
                      >
                        {msg("auto.features.optimizations.components.overviewtab.lm_activity_link")}
                      </button>
                    </div>
                  )}
                </div>
              </FadeIn>
            );
          }
          if (!job.result.num_lm_calls && !job.result.avg_response_time_ms) return null;
          return (
            <FadeIn delay={0.1}>
              <div className="grid grid-cols-2 gap-2.5">
                {job.result.num_lm_calls != null && (
                  <InfoCard
                    label={
                      <HelpTip text={tip("lm.calls_count")}>
                        {msg("auto.features.optimizations.components.overviewtab.1")}
                      </HelpTip>
                    }
                    value={formatMsg(
                      "auto.features.optimizations.components.overviewtab.template.6",
                      { p1: job.result.num_lm_calls },
                    )}
                    icon={<MessageSquare className="size-3.5" />}
                  />
                )}
                {job.result.avg_response_time_ms != null && (
                  <InfoCard
                    label={
                      <HelpTip text={tip("lm.avg_response_time")}>
                        {msg("auto.features.optimizations.components.overviewtab.2")}
                      </HelpTip>
                    }
                    value={formatMsg(
                      "auto.features.optimizations.components.overviewtab.template.7",
                      { p1: (job.result.avg_response_time_ms / 1000).toFixed(1) },
                    )}
                    icon={<Timer className="size-3.5" />}
                  />
                )}
              </div>
            </FadeIn>
          );
        })()}

      {job.status === "success" && job.optimization_type === "run" && job.result && (
        <div data-tutorial="score-cards">
          <StaggerContainer className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <StaggerItem>
              <TiltCard className=" rounded-xl border border-border/50 bg-card p-6 text-center">
                <p className="text-[0.6875rem] text-muted-foreground mb-2 font-medium tracking-wide">
                  <HelpTip text={tip("score.baseline")}>{TERMS.baselineScore}</HelpTip>
                </p>
                <p className="text-3xl font-mono font-bold">
                  {formatPercent(job.result.baseline_test_metric)}
                </p>
              </TiltCard>
            </StaggerItem>
            <StaggerItem>
              <TiltCard className="rounded-xl border border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10 p-6 text-center shadow-[0_0_20px_rgba(var(--primary),0.08)]">
                <p className="text-[0.6875rem] text-muted-foreground mb-2 font-medium tracking-wide">
                  <HelpTip text={tip("score.optimized")}>{TERMS.optimizedScore}</HelpTip>
                </p>
                <p className="text-3xl font-mono font-bold text-primary">
                  {formatPercent(job.result.optimized_test_metric)}
                </p>
              </TiltCard>
            </StaggerItem>
            <StaggerItem>
              <TiltCard
                className={`rounded-xl border p-6 text-center ${(job.result.metric_improvement ?? 0) >= 0 ? "border-stone-400/50 bg-gradient-to-br from-stone-100/50 to-stone-200/30" : "border-red-300/50 bg-gradient-to-br from-red-50/50 to-red-100/30"}`}
              >
                <p className="text-[0.6875rem] text-muted-foreground mb-2 font-medium tracking-wide">
                  <HelpTip text={tip("score.improvement")}>
                    {msg("auto.features.optimizations.components.overviewtab.3")}
                  </HelpTip>
                </p>
                <p
                  className={`text-3xl font-mono font-bold ${(job.result.metric_improvement ?? 0) >= 0 ? "text-stone-600" : "text-red-600"}`}
                >
                  {formatImprovement(job.result.metric_improvement)}
                </p>
              </TiltCard>
            </StaggerItem>
          </StaggerContainer>
        </div>
      )}

      {job.optimization_type === "run" && scorePoints.length > 1 && (
        <FadeIn delay={0.1}>
          <Card
            className="relative overflow-hidden shadow-[0_1px_3px_rgba(28,22,18,0.04),inset_0_1px_0_rgba(255,255,255,0.5)]"
            data-tutorial="score-chart"
          >
            <div
              className="absolute inset-x-0 top-0 h-px bg-gradient-to-l from-transparent via-[#C8A882]/40 to-transparent"
              aria-hidden="true"
            />
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <TrendingUp className="size-4 text-[#7C6350]" aria-hidden="true" />
                <HelpTip text={tip("score.progression")}>
                  <span className="font-bold tracking-tight">
                    {msg("auto.features.optimizations.components.overviewtab.4")}
                  </span>
                </HelpTip>
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

      {job.optimization_type === "grid_search" && !job.grid_result && activePairIndex === null && (
        <FadeIn delay={0.1}>
          <GridLiveChart job={job} />
        </FadeIn>
      )}

      {job.optimization_type === "grid_search" && job.grid_result && activePairIndex === null && (
        <GridOverview job={job} onPairSelect={onPairSelect} onPairDeleted={onPairDeleted} />
      )}
    </>
  );
}
