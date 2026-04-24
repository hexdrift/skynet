"use client";

/**
 * Overview tab body — the live progress block, completed pipeline
 * timeline, single-run results, score progression chart, and the
 * grid-overview hand-off.
 *
 * Extracted from app/optimizations/[id]/page.tsx. Takes the job plus
 * the derived score points and two callbacks (stage click, pair
 * select); internal state lives in the parent page.
 */

import dynamic from "next/dynamic";
import { Activity, Clock, Database, MessageSquare, Timer, TrendingUp, Zap } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
}: {
  job: OptimizationStatusResponse;
  isActive: boolean;
  scorePoints: ScorePoint[];
  activePairIndex: number | null;
  onStageClick: (stage: PipelineStage) => void;
  onPairSelect: (pairIndex: number) => void;
  onPairDeleted?: (pairIndex: number) => void;
}) {
  const metrics = job.latest_metrics ?? {};

  return (
    <>
      <FadeIn>
        <p className="text-sm text-muted-foreground">
          {isActive
            ? `ה${TERMS.optimization} רצה כעת — ניתן לעקוב אחר ההתקדמות בזמן אמת.`
            : job.status === "cancelled"
              ? `ה${TERMS.optimization} בוטלה — זה המצב שהיה ברגע הביטול.`
              : job.status === "failed"
                ? `ה${TERMS.optimization} נכשלה.`
                : `תוצאות ה${TERMS.optimization} וציוני הביצוע.`}
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
                  label="צעד"
                  value={`${tqdmN}/${tqdmTotal}`}
                  icon={<Activity className="size-3.5" />}
                />
              )}
              {tqdmElapsed != null && (
                <InfoCard
                  label="זמן שעבר"
                  value={formatDuration(tqdmElapsed)}
                  icon={<Timer className="size-3.5" />}
                />
              )}
              {tqdmRemaining != null && (
                <InfoCard
                  label="נותר"
                  value={formatDuration(Number(tqdmRemaining))}
                  icon={<Clock className="size-3.5" />}
                />
              )}
              {tqdmRate != null && (
                <InfoCard
                  label="קצב"
                  value={`${tqdmRate.toFixed(2)}/שנ׳`}
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
                  label="נתונים"
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
        (job.result.num_lm_calls || job.result.avg_response_time_ms) && (
          <FadeIn delay={0.1}>
            <div className="grid grid-cols-2 gap-2.5">
              {job.result.num_lm_calls != null && (
                <InfoCard
                  label={<HelpTip text={tip("lm.calls_count")}>קריאות למודל שפה</HelpTip>}
                  value={`${job.result.num_lm_calls} קריאות`}
                  icon={<MessageSquare className="size-3.5" />}
                />
              )}
              {job.result.avg_response_time_ms != null && (
                <InfoCard
                  label={
                    <HelpTip text={tip("lm.avg_response_time")}>זמן תגובה ממוצע לקריאה</HelpTip>
                  }
                  value={`${(job.result.avg_response_time_ms / 1000).toFixed(1)} שניות לקריאה`}
                  icon={<Timer className="size-3.5" />}
                />
              )}
            </div>
          </FadeIn>
        )}

      {job.status === "success" && job.optimization_type === "run" && job.result && (
        <div data-tutorial="score-cards">
          <StaggerContainer className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
                  <HelpTip text={tip("score.improvement")}>שיפור</HelpTip>
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
                  <span className="font-bold tracking-tight">מהלך הציונים</span>
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
