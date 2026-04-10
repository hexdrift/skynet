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
import {
  Activity,
  CheckCircle2,
  Circle,
  Clock,
  Database,
  Loader2,
  MessageSquare,
  Timer,
  TrendingUp,
  XCircle,
  Zap,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FadeIn, StaggerContainer, StaggerItem, TiltCard } from "@/components/motion";
import { HelpTip } from "@/components/help-tip";
import type { OptimizationStatusResponse } from "@/lib/types";
import { PIPELINE_STAGES, type PipelineStage } from "../constants";
import { detectStage } from "../lib/detect-stage";
import { formatDuration, formatImprovement, formatPercent } from "../lib/formatters";
import type { ScorePoint } from "../lib/extract-scores";
import { GridOverview } from "./GridOverview";
import { InfoCard } from "./ui-primitives";

const ScoreChart = dynamic(() => import("@/components/score-chart").then((m) => m.ScoreChart), {
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
}: {
  job: OptimizationStatusResponse;
  isActive: boolean;
  scorePoints: ScorePoint[];
  activePairIndex: number | null;
  onStageClick: (stage: PipelineStage) => void;
  onPairSelect: (pairIndex: number) => void;
}) {
  const metrics = job.latest_metrics ?? {};

  return (
    <>
      <FadeIn>
        <p className="text-sm text-muted-foreground">
          {isActive
            ? "האופטימיזציה רצה כעת — ניתן לעקוב אחר ההתקדמות בזמן אמת."
            : job.status === "cancelled"
              ? "האופטימיזציה בוטלה — להלן מצב התהליך בעת הביטול."
              : job.status === "failed"
                ? "האופטימיזציה נכשלה."
                : "תוצאות האופטימיזציה, ציונים ומטריקות ביצוע."}
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
                  <span>{tqdmDesc || "אופטימיזציה"}</span>
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
          const baselineEvent = job.progress_events?.find((e) => e.event === "baseline_evaluated");
          const baselineScore = baselineEvent?.metrics?.baseline_test_metric as number | undefined;
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
                  label="ציון התחלתי"
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
          {(() => {
            const completedStageIdx =
              job.status === "success"
                ? PIPELINE_STAGES.length
                : detectStage(job) === "done"
                  ? PIPELINE_STAGES.length
                  : PIPELINE_STAGES.findIndex((s) => s.key === detectStage(job));
            const eventToStage: Record<string, PipelineStage> = {
              validation_passed: "validating",
              dataset_splits_ready: "splitting",
              baseline_evaluated: "baseline",
              grid_pair_started: "baseline",
              optimizer_progress: "optimizing",
              optimized_evaluated: "evaluating",
              grid_pair_completed: "evaluating",
            };
            const stageTs: Partial<Record<PipelineStage, string>> = {};
            for (const ev of job.progress_events ?? []) {
              const sk = ev.event ? eventToStage[ev.event] : undefined;
              if (sk && ev.timestamp) {
                const d = new Date(ev.timestamp);
                stageTs[sk] =
                  `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })}|${d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}`;
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
              <div
                className="relative flex items-start justify-between"
                dir="rtl"
                data-tutorial="pipeline-stages"
              >
                <div className="absolute top-[14px] right-[14px] left-[14px] h-[2px] bg-border/50 rounded-full" />
                <div
                  className={`absolute top-[14px] right-[14px] h-[2px] rounded-full transition-all duration-700 ease-out ${isFailed ? "bg-destructive/60" : "bg-[#3D2E22]"}`}
                  style={{
                    width: `calc(${(Math.min(completedStageIdx, PIPELINE_STAGES.length - 1) / (PIPELINE_STAGES.length - 1)) * 100}% - 28px)`,
                  }}
                />
                {PIPELINE_STAGES.map((s, i) => {
                  const isDone = i < completedStageIdx;
                  const isCurrent = isActive && i === completedStageIdx;
                  const isStopped = isFailed && i === completedStageIdx;
                  const ts = stageTs[s.key];
                  return (
                    <div
                      key={s.key}
                      className="relative z-10 flex flex-col items-center gap-2 min-w-0 group/node cursor-pointer"
                      onClick={() => onStageClick(s.key)}
                    >
                      <div
                        className={`size-7 rounded-full flex items-center justify-center transition-all duration-300 group-hover/node:scale-125 group-hover/node:shadow-[0_0_0_6px_rgba(61,46,34,0.1)] ${
                          isStopped
                            ? "bg-destructive text-white shadow-[0_0_0_4px_rgba(176,64,48,0.15)]"
                            : isCurrent
                              ? "bg-[#3D2E22] text-white shadow-[0_0_0_4px_rgba(61,46,34,0.15)]"
                              : isDone
                                ? "bg-[#3D2E22] text-white"
                                : "bg-[#E5DDD4] text-[#8C7A6B]"
                        }`}
                      >
                        {isDone ? (
                          <CheckCircle2 className="size-3.5" />
                        ) : isCurrent ? (
                          <Loader2 className="size-3.5 animate-spin" />
                        ) : isStopped ? (
                          <XCircle className="size-3.5" />
                        ) : (
                          <Circle className="size-3" />
                        )}
                      </div>
                      <span
                        className={`text-[11px] whitespace-nowrap transition-colors duration-200 group-hover/node:text-[#3D2E22] ${
                          isCurrent
                            ? "text-[#3D2E22] font-semibold"
                            : isStopped
                              ? "text-destructive font-semibold"
                              : isDone
                                ? "text-[#3D2E22]/80"
                                : "text-muted-foreground/40"
                        }`}
                      >
                        {s.label}
                      </span>
                      {ts &&
                        isDone &&
                        (() => {
                          const [date, time] = ts.split("|");
                          return (
                            <div className="flex flex-col items-center -mt-0.5" dir="ltr">
                              <span className="text-[10px] text-muted-foreground/50 tracking-wide uppercase">
                                {date}
                              </span>
                              <span className="text-[11px] text-muted-foreground/70 font-mono tabular-nums">
                                {time}
                              </span>
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

      {job.status === "success" &&
        job.optimization_type === "run" &&
        job.result &&
        (job.result.num_lm_calls || job.result.avg_response_time_ms) && (
          <FadeIn delay={0.1}>
            <div className="grid grid-cols-2 gap-2.5">
              {job.result.num_lm_calls != null && (
                <InfoCard
                  label={
                    <HelpTip text="מספר הפעמים שהמערכת פנתה למודל השפה במהלך האופטימיזציה">
                      קריאות למודל שפה
                    </HelpTip>
                  }
                  value={`${job.result.num_lm_calls} קריאות`}
                  icon={<MessageSquare className="size-3.5" />}
                />
              )}
              {job.result.avg_response_time_ms != null && (
                <InfoCard
                  label={
                    <HelpTip text="משך זמן ממוצע לכל קריאה בודדת למודל השפה">
                      זמן תגובה ממוצע לקריאה
                    </HelpTip>
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
                <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide">
                  <HelpTip text="ציון המדידה לפני אופטימיזציה — התוכנית רצה ללא הנחיות או דוגמאות">
                    ציון התחלתי
                  </HelpTip>
                </p>
                <p className="text-3xl font-mono font-bold">
                  {formatPercent(job.result.baseline_test_metric)}
                </p>
              </TiltCard>
            </StaggerItem>
            <StaggerItem>
              <TiltCard className="rounded-xl border border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10 p-6 text-center shadow-[0_0_20px_rgba(var(--primary),0.08)]">
                <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide">
                  <HelpTip text="ציון המדידה אחרי אופטימיזציה — התוכנית רצה עם ההנחיות והדוגמאות שנבחרו">
                    ציון משופר
                  </HelpTip>
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
                <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide">
                  <HelpTip text="ההפרש בין הציון המשופר לציון ההתחלתי — ככל שגבוה יותר, האופטימיזציה הועילה יותר">
                    שיפור
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
                <HelpTip text="שינוי הציון לאורך הניסיונות השונים של האופטימייזר">
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

      {job.status === "success" &&
        job.optimization_type === "grid_search" &&
        job.grid_result &&
        activePairIndex === null && <GridOverview job={job} onPairSelect={onPairSelect} />}
    </>
  );
}
