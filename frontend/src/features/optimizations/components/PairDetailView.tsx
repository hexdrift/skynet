"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import {
  ArrowLeft,
  ArrowRight,
  ChevronRight,
  Clock,
  Code2,
  CopyPlus,
  Cpu,
  Crown,
  Database,
  Lightbulb,
  Loader2,
  MessageSquare,
  Send,
  Terminal,
  Timer,
  Trash2,
  TrendingUp,
  XCircle,
} from "lucide-react";
import { Button } from "@/shared/ui/primitives/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/primitives/card";
import { Dialog, DialogContent, DialogFooter } from "@/shared/ui/primitives/dialog";
import { DialogTitleRow } from "@/shared/ui/dialog-title-row";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/primitives/tabs";
import { TooltipButton } from "@/shared/ui/tooltip-button";
import { FadeIn, StaggerContainer, StaggerItem, TiltCard } from "@/shared/ui/motion";
import { HelpTip } from "@/shared/ui/help-tip";
import type {
  PairResult,
  OptimizationLogEntry,
  OptimizationStatusResponse,
  ServeInfoResponse,
} from "@/shared/types/api";
import { DataTab } from "./DataTab";
import { LogsTab } from "./LogsTab";
import { ExportMenu } from "./ExportMenu";
import { ServeChat, type ServeChatProps } from "./ServeChat";
import { CopyButton, InfoCard, ReasoningPill } from "./ui-primitives";
import { LMActivityTab } from "./LMActivityTab";
import { PipelineStages, computeStageTimestamps } from "./PipelineStages";
import { detectPairStage } from "../lib/detect-stage";
import type { PipelineStage } from "../constants";
import { formatDuration, formatImprovement, formatPercent } from "@/shared/lib";
import { deleteGridPair } from "@/shared/lib/api";
import { tip } from "@/shared/lib/tooltips";
import { msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";
import type { ScorePoint } from "../lib/extract-scores";
import { ACTIVE_STATUSES, TERMINAL_STATUSES } from "@/shared/constants/job-status";
import { pairLabel } from "./grid-overview-helpers";
import { toast } from "react-toastify";

const ScoreChart = dynamic(() => import("@/shared/ui/score-chart").then((m) => m.ScoreChart), {
  ssr: false,
  loading: () => <div className="h-full" />,
});

export interface PairDetailViewProps {
  job: OptimizationStatusResponse;
  activePair: PairResult;
  activePairIndex: number;
  pairCount: number;
  pairFilteredLogs: OptimizationLogEntry[];
  pairScorePoints: ScorePoint[];
  initialTab: string;
  serveInfo: ServeInfoResponse | null;
  runHistory: ServeChatProps["runHistory"];
  setRunHistory: ServeChatProps["setRunHistory"];
  streamingRun: ServeChatProps["streamingRun"];
  serveLoading: boolean;
  serveError: string | null;
  setServeError: ServeChatProps["setServeError"];
  textareaRefs: ServeChatProps["textareaRefs"];
  chatScrollRef: ServeChatProps["chatScrollRef"];
  handleServe: ServeChatProps["handleServe"];
  onBack: () => void;
  onPrev: () => void;
  onNext: () => void;
  onClone: () => void;
  onCancel: () => void;
  onClearHistory: () => void;
  onStageClick: (stage: PipelineStage) => void;
  onDeleted: () => void;
}

export function PairDetailView({
  job,
  activePair,
  activePairIndex,
  pairCount,
  pairFilteredLogs,
  pairScorePoints,
  initialTab,
  serveInfo,
  runHistory,
  setRunHistory,
  streamingRun,
  serveLoading,
  serveError,
  setServeError,
  textareaRefs,
  chatScrollRef,
  handleServe,
  onBack,
  onPrev,
  onNext,
  onClone,
  onCancel,
  onClearHistory,
  onStageClick,
  onDeleted,
}: PairDetailViewProps) {
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const isBest = job.grid_result?.best_pair?.pair_index === activePair.pair_index;
  const pairPrompt = activePair.program_artifact?.optimized_prompt;
  const pairStage = detectPairStage(job, activePair.pair_index);
  const pairEvents = (job.progress_events ?? []).filter(
    (e) => e.metrics?.pair_index === activePair.pair_index,
  );
  const baselineFromEvents = pairEvents.find((e) => e.event === "baseline_evaluated")?.metrics
    ?.baseline_test_metric as number | undefined;
  const optimizedFromEvents = pairEvents.find((e) => e.event === "optimized_evaluated")?.metrics
    ?.optimized_test_metric as number | undefined;
  const pairBaseline = activePair.baseline_test_metric ?? baselineFromEvents;
  const pairOptimized = activePair.optimized_test_metric ?? optimizedFromEvents;
  const pairImprovement =
    activePair.metric_improvement ??
    (pairBaseline != null && pairOptimized != null ? pairOptimized - pairBaseline : undefined);
  const pairStageTs = computeStageTimestamps(
    job.progress_events ?? [],
    job.started_at,
    job.completed_at,
    activePair.pair_index,
  );
  const jobActive = ACTIVE_STATUSES.has(job.status);
  const jobTerminal = TERMINAL_STATUSES.has(job.status);
  const pairActive = jobActive && pairStage !== "done" && !activePair.error;
  const pairFailed = !!activePair.error || (!jobActive && pairStage !== "done");
  const tabCls =
    "relative px-4 py-2.5 rounded-none border-b-2 border-transparent data-[state=active]:border-transparent data-[state=active]:border-b-primary data-[state=active]:text-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none transition-all duration-200";
  const handleDeletePair = async () => {
    setDeleting(true);
    try {
      await deleteGridPair(job.optimization_id, activePair.pair_index);
      setDeleteOpen(false);
      window.dispatchEvent(new Event("optimizations-changed"));
      onDeleted();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("optimization.delete.failed"));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-4" data-tutorial="pair-detail">
      <FadeIn>
        <div className="flex items-center justify-between rounded-xl border border-[#C8A882]/30 bg-gradient-to-l from-[#FAF8F5] to-[#F5F1EC] p-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onBack}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-[#3D2E22] hover:text-[#3D2E22]/80 transition-colors cursor-pointer"
            >
              <ChevronRight className="size-4" />
              <span>{msg("auto.features.optimizations.components.pairdetailview.1")}</span>
            </button>
            <span className="text-[0.6875rem] text-muted-foreground/60">|</span>
            <div className="flex items-center gap-1.5 flex-wrap">
              {isBest && <Crown className="size-3.5 text-[#C8A882]" />}
              <span className="text-sm font-semibold text-foreground">
                {activePair.generation_model.split("/").pop()}
              </span>
              <ReasoningPill value={activePair.generation_reasoning_effort} size="sm" />
              <span className="text-[0.6875rem] text-muted-foreground/50">×</span>
              <span className="text-sm font-semibold text-foreground">
                {activePair.reflection_model.split("/").pop()}
              </span>
              <ReasoningPill value={activePair.reflection_reasoning_effort} size="sm" />
            </div>
          </div>
          <div className="flex items-center gap-1">
            <TooltipButton tooltip={msg("auto.app.optimizations.id.page.4")}>
              <Button
                variant="ghost"
                size="icon"
                className="size-8"
                onClick={onClone}
                aria-label={msg("auto.app.optimizations.id.page.literal.4")}
              >
                <CopyPlus className="size-4" />
              </Button>
            </TooltipButton>
            {jobActive && (
              <TooltipButton tooltip={msg("auto.app.optimizations.id.page.5")}>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-8 text-destructive hover:bg-destructive/10 hover:text-destructive focus-visible:ring-0 focus-visible:border-0"
                  onClick={onCancel}
                  aria-label={msg("auto.app.optimizations.id.page.literal.5")}
                >
                  <XCircle className="size-4" />
                </Button>
              </TooltipButton>
            )}
            {jobTerminal && (
              <TooltipButton tooltip={msg("auto.features.optimizations.components.gridoverview.18")}>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-8 text-muted-foreground hover:text-red-600"
                  onClick={() => setDeleteOpen(true)}
                  aria-label={msg("auto.features.optimizations.components.gridoverview.literal.29")}
                >
                  <Trash2 className="size-4" />
                </Button>
              </TooltipButton>
            )}
            <span className="mx-1 h-5 w-px bg-[#C8A882]/30" />
            <button
              type="button"
              disabled={activePairIndex <= 0}
              onClick={onPrev}
              className="p-1.5 rounded-lg hover:bg-[#3D2E22]/5 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
              title={msg("auto.features.optimizations.components.pairdetailview.literal.1")}
            >
              <ArrowRight className="size-4 text-[#3D2E22]" />
            </button>
            <span className="text-[0.6875rem] text-muted-foreground tabular-nums font-mono">
              {activePairIndex + 1}/{pairCount}
            </span>
            <button
              type="button"
              disabled={activePairIndex >= pairCount - 1}
              onClick={onNext}
              className="p-1.5 rounded-lg hover:bg-[#3D2E22]/5 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
              title={msg("auto.features.optimizations.components.pairdetailview.literal.2")}
            >
              <ArrowLeft className="size-4 text-[#3D2E22]" />
            </button>
          </div>
        </div>
      </FadeIn>

      <Dialog open={deleteOpen} onOpenChange={(open) => !open && setDeleteOpen(false)}>
        <DialogContent className="max-w-sm">
          <DialogTitleRow
            title={msg("auto.features.optimizations.components.gridoverview.19")}
            description={
              <>
                {msg("auto.features.optimizations.components.gridoverview.20")}{" "}
                <span className="font-mono font-medium text-foreground break-all">
                  {pairLabel(activePair)}
                </span>
                {msg("auto.features.optimizations.components.gridoverview.21")}
              </>
            }
          />
          <DialogFooter className="grid grid-cols-2 gap-2">
            <Button
              variant="outline"
              onClick={() => setDeleteOpen(false)}
              disabled={deleting}
              className="w-full justify-center"
            >
              {msg("auto.features.optimizations.components.gridoverview.22")}
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeletePair}
              disabled={deleting}
              className="w-full justify-center"
            >
              {deleting ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                msg("auto.features.optimizations.components.gridoverview.literal.30")
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {!activePair.error && activePair.program_artifact && (
        <FadeIn delay={0.05}>
          <div className="flex items-center gap-3 p-4 rounded-xl border border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10">
            <div className="flex-1">
              <p className="text-sm font-medium">
                {msg("auto.features.optimizations.components.pairdetailview.2")}
              </p>
            </div>
            <ExportMenu job={job} optimizedPrompt={pairPrompt ?? null} />
          </div>
        </FadeIn>
      )}

      {activePair.error && (
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

      <Tabs defaultValue={initialTab} dir="rtl">
        <TabsList variant="line" className="border-b border-border/50 pb-0 gap-0">
          <TabsTrigger value="overview" className={tabCls}>
            <TrendingUp className="size-3.5" />
            {msg("auto.features.optimizations.components.pairdetailview.4")}
          </TabsTrigger>
          {pairPrompt?.formatted_prompt && (
            <TabsTrigger value="prompt" className={tabCls}>
              <Code2 className="size-3.5" />
              {msg("auto.features.optimizations.components.pairdetailview.5")}
            </TabsTrigger>
          )}
          {serveInfo && (
            <TabsTrigger value="playground" className={tabCls}>
              <Send className="size-3.5" />
              {msg("auto.features.optimizations.components.pairdetailview.6")}
            </TabsTrigger>
          )}
          <TabsTrigger value="data" className={tabCls}>
            <Database className="size-3.5" />
            {msg("auto.features.optimizations.components.pairdetailview.7")}
          </TabsTrigger>
          <TabsTrigger value="logs" className={tabCls}>
            <Terminal className="size-3.5" />
            {msg("auto.features.optimizations.components.pairdetailview.8")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6 mt-4">
          <FadeIn delay={0.05}>
            <PipelineStages
              currentStage={pairStage}
              stageTs={pairStageTs}
              isActive={pairActive}
              isFailed={pairFailed}
              onStageClick={onStageClick}
            />
          </FadeIn>

          <div data-tutorial="pair-detail-summary" className="space-y-6">
            {!activePair.error && (
              <StaggerContainer className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <StaggerItem>
                  <TiltCard className="rounded-xl border border-border/50 bg-card p-6 text-center">
                    <p className="text-[0.6875rem] text-muted-foreground mb-2 font-medium tracking-wide">
                      <HelpTip text={tip("score.baseline")}>{TERMS.baselineScore}</HelpTip>
                    </p>
                    <p className="text-3xl font-mono font-bold tabular-nums">
                      {formatPercent(pairBaseline)}
                    </p>
                  </TiltCard>
                </StaggerItem>
                <StaggerItem>
                  <TiltCard className="rounded-xl border border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10 p-6 text-center shadow-[0_0_20px_rgba(var(--primary),0.08)]">
                    <p className="text-[0.6875rem] text-muted-foreground mb-2 font-medium tracking-wide">
                      <HelpTip text={tip("score.optimized")}>{TERMS.optimizedScore}</HelpTip>
                    </p>
                    <p className="text-3xl font-mono font-bold text-primary tabular-nums">
                      {formatPercent(pairOptimized)}
                    </p>
                  </TiltCard>
                </StaggerItem>
                <StaggerItem>
                  <TiltCard
                    className={`rounded-xl border p-6 text-center ${(pairImprovement ?? 0) >= 0 ? "border-stone-400/50 bg-gradient-to-br from-stone-100/50 to-stone-200/30" : "border-red-300/50 bg-gradient-to-br from-red-50/50 to-red-100/30"}`}
                  >
                    <p className="text-[0.6875rem] text-muted-foreground mb-2 font-medium tracking-wide">
                      <HelpTip text={tip("score.improvement")}>
                        {msg("auto.features.optimizations.components.pairdetailview.9")}
                      </HelpTip>
                    </p>
                    <p
                      className={`text-3xl font-mono font-bold tabular-nums ${(pairImprovement ?? 0) >= 0 ? "text-stone-600" : "text-red-600"}`}
                    >
                      {formatImprovement(pairImprovement)}
                    </p>
                  </TiltCard>
                </StaggerItem>
              </StaggerContainer>
            )}

            <FadeIn delay={0.1}>
              <div className="space-y-2.5">
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-2.5">
                  <InfoCard
                    label={
                      <HelpTip text={tip("model.generation")}>
                        {msg("model.generation.label")}
                      </HelpTip>
                    }
                    value={
                      <span className="inline-flex items-center gap-1.5">
                        <span className="truncate">
                          {activePair.generation_model.split("/").pop()}
                        </span>
                        <ReasoningPill value={activePair.generation_reasoning_effort} />
                      </span>
                    }
                    icon={<Cpu className="size-3.5" />}
                  />
                  <InfoCard
                    label={<HelpTip text={tip("model.reflection")}>{TERMS.reflectionModel}</HelpTip>}
                    value={
                      <span className="inline-flex items-center gap-1.5">
                        <span className="truncate">
                          {activePair.reflection_model.split("/").pop()}
                        </span>
                        <ReasoningPill value={activePair.reflection_reasoning_effort} />
                      </span>
                    }
                    icon={<Lightbulb className="size-3.5" />}
                  />
                  {activePair.runtime_seconds != null && (
                    <InfoCard
                      label={
                        <HelpTip text={tip("pair.runtime")}>
                          {msg("auto.features.optimizations.components.pairdetailview.10")}
                        </HelpTip>
                      }
                      value={formatDuration(activePair.runtime_seconds)}
                      icon={<Clock className="size-3.5" />}
                    />
                  )}
                </div>
                {(activePair.num_lm_calls != null || activePair.avg_response_time_ms != null) && (
                  <div className="grid grid-cols-2 gap-2.5">
                    {activePair.num_lm_calls != null && (
                      <InfoCard
                        label={
                          <HelpTip text={tip("lm.calls_count")}>
                            {msg("auto.features.optimizations.components.pairdetailview.11")}
                          </HelpTip>
                        }
                        value={String(activePair.num_lm_calls)}
                        icon={<MessageSquare className="size-3.5" />}
                      />
                    )}
                    {activePair.avg_response_time_ms != null && (
                      <InfoCard
                        label={
                          <HelpTip text={tip("lm.avg_response_time")}>
                            {msg("auto.features.optimizations.components.pairdetailview.12")}
                          </HelpTip>
                        }
                        value={`${(activePair.avg_response_time_ms / 1000).toFixed(1)}s`}
                        icon={<Timer className="size-3.5" />}
                      />
                    )}
                  </div>
                )}
              </div>
            </FadeIn>
          </div>

          {activePair.lm_activity && (
            <LMActivityTab lmActivity={activePair.lm_activity} />
          )}

          {pairScorePoints.length > 1 && (
            <FadeIn delay={0.1}>
              <Card className="relative overflow-hidden shadow-[0_1px_3px_rgba(28,22,18,0.04),inset_0_1px_0_rgba(255,255,255,0.5)]">
                <div
                  className="absolute inset-x-0 top-0 h-px bg-gradient-to-l from-transparent via-[#C8A882]/40 to-transparent"
                  aria-hidden="true"
                />
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <TrendingUp className="size-4 text-[#7C6350]" aria-hidden="true" />
                    <HelpTip text={tip("score.progression")}>
                      <span className="font-bold tracking-tight">
                        {msg("auto.features.optimizations.components.pairdetailview.13")}
                      </span>
                    </HelpTip>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="h-[220px]">
                    <ScoreChart data={pairScorePoints} />
                  </div>
                </CardContent>
              </Card>
            </FadeIn>
          )}
        </TabsContent>

        {pairPrompt?.formatted_prompt && (
          <TabsContent value="prompt" className="space-y-4 mt-4">
            <FadeIn>
              {pairPrompt.demos && pairPrompt.demos.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base font-medium">
                      <HelpTip text={tip("prompt.demonstrations")}>
                        {pairPrompt.demos.length}
                        {msg("auto.features.optimizations.components.pairdetailview.14")}
                      </HelpTip>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {pairPrompt.demos.map((demo, di) => (
                      <div
                        key={di}
                        className="rounded-lg border border-border/40 bg-muted/30 p-3 text-xs font-mono space-y-1"
                        dir="ltr"
                      >
                        {Object.entries(demo).map(([k, v]) => (
                          <div key={k}>
                            <span className="text-muted-foreground">{k}:</span> {String(v)}
                          </div>
                        ))}
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base font-medium">
                    <HelpTip text={tip("prompt.optimized")}>
                      {msg("auto.features.optimizations.components.pairdetailview.15")}
                    </HelpTip>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="relative group">
                    <pre
                      className="text-sm font-mono bg-muted/50 rounded-lg p-4 pe-10 overflow-x-auto whitespace-pre-wrap leading-relaxed"
                      dir="ltr"
                    >
                      {pairPrompt.formatted_prompt}
                    </pre>
                    <CopyButton
                      text={pairPrompt.formatted_prompt}
                      className="absolute top-2 right-2 opacity-0 group-hover:opacity-100"
                    />
                  </div>
                </CardContent>
              </Card>
            </FadeIn>
          </TabsContent>
        )}

        {serveInfo && (
          <TabsContent value="playground" className="space-y-4 mt-4">
            <FadeIn>
              <div className="flex items-center justify-between pb-3 border-b border-border/60">
                <p className="text-sm text-muted-foreground">
                  {msg("auto.features.optimizations.components.pairdetailview.16")}
                </p>
                {runHistory.length > 0 && (
                  <TooltipButton
                    tooltip={msg("auto.features.optimizations.components.pairdetailview.17")}
                  >
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8"
                      onClick={onClearHistory}
                      aria-label={msg(
                        "auto.features.optimizations.components.pairdetailview.literal.3",
                      )}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </TooltipButton>
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
              demos={activePair.program_artifact?.optimized_prompt?.demos ?? []}
            />
          </TabsContent>
        )}

        <TabsContent value="data">
          <DataTab job={job} pairIndex={activePairIndex} />
        </TabsContent>

        <TabsContent value="logs">
          <LogsTab logs={pairFilteredLogs} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
