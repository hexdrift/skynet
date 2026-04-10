"use client";

/**
 * Per-pair full view shown when ?pair=N is set on a grid-search
 * optimization. Contains its own Tabs (overview/prompt/playground/
 * data/logs) scoped to the selected pair.
 *
 * Extracted from app/optimizations/[id]/page.tsx. State for the serve
 * playground lives in the parent — this component just forwards it.
 */

import dynamic from "next/dynamic";
import {
  ArrowLeft,
  ArrowRight,
  ChevronRight,
  Clock,
  Code2,
  Cpu,
  Crown,
  Database,
  Lightbulb,
  MessageSquare,
  Send,
  Terminal,
  Timer,
  Trash2,
  TrendingUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip as UiTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { FadeIn, StaggerContainer, StaggerItem, TiltCard } from "@/components/motion";
import { HelpTip } from "@/components/help-tip";
import type {
  PairResult,
  OptimizationLogEntry,
  OptimizationStatusResponse,
  ServeInfoResponse,
} from "@/lib/types";
import { DataTab } from "./DataTab";
import { LogsTab } from "./LogsTab";
import { ExportMenu } from "./ExportMenu";
import { ServeChat, type ServeChatProps } from "./ServeChat";
import { CopyButton, InfoCard } from "./ui-primitives";
import { formatDuration, formatImprovement, formatPercent } from "../lib/formatters";
import type { ScorePoint } from "../lib/extract-scores";

const ScoreChart = dynamic(() => import("@/components/score-chart").then((m) => m.ScoreChart), {
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
  onClearHistory: () => void;
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
  onClearHistory,
}: PairDetailViewProps) {
  const isBest = job.grid_result?.best_pair?.pair_index === activePair.pair_index;
  const pairPrompt = activePair.program_artifact?.optimized_prompt;
  const tabCls =
    "relative px-4 py-2.5 rounded-none border-b-2 border-transparent data-[state=active]:border-transparent data-[state=active]:border-b-primary data-[state=active]:text-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none transition-all duration-200";

  return (
    <div className="space-y-4">
      <FadeIn>
        <div className="flex items-center justify-between rounded-xl border border-[#C8A882]/30 bg-gradient-to-l from-[#FAF8F5] to-[#F5F1EC] p-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onBack}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-[#3D2E22] hover:text-[#3D2E22]/80 transition-colors cursor-pointer"
            >
              <ChevronRight className="size-4" />
              <span>חזרה לסקירת הסריקה</span>
            </button>
            <span className="text-[11px] text-muted-foreground/60">|</span>
            <div className="flex items-center gap-1.5">
              {isBest && <Crown className="size-3.5 text-[#C8A882]" />}
              <span className="text-sm font-semibold text-foreground">
                {activePair.generation_model.split("/").pop()} ×{" "}
                {activePair.reflection_model.split("/").pop()}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              disabled={activePairIndex <= 0}
              onClick={onPrev}
              className="p-1.5 rounded-lg hover:bg-[#3D2E22]/5 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
              title="זוג קודם"
            >
              <ArrowRight className="size-4 text-[#3D2E22]" />
            </button>
            <span className="text-[11px] text-muted-foreground tabular-nums font-mono">
              {activePairIndex + 1}/{pairCount}
            </span>
            <button
              type="button"
              disabled={activePairIndex >= pairCount - 1}
              onClick={onNext}
              className="p-1.5 rounded-lg hover:bg-[#3D2E22]/5 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
              title="זוג הבא"
            >
              <ArrowLeft className="size-4 text-[#3D2E22]" />
            </button>
          </div>
        </div>
      </FadeIn>

      {!activePair.error && activePair.program_artifact && (
        <FadeIn delay={0.05}>
          <div className="flex items-center gap-3 p-4 rounded-xl border border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10">
            <div className="flex-1">
              <p className="text-sm font-medium">ייצוא תוצאות</p>
            </div>
            <ExportMenu job={job} optimizedPrompt={pairPrompt ?? null} />
          </div>
        </FadeIn>
      )}

      {activePair.error && (
        <FadeIn delay={0.05}>
          <div className="rounded-xl border border-[#B04030]/30 bg-[#B04030]/5 p-4">
            <div className="text-sm font-medium text-[#B04030] mb-1">שגיאה</div>
            <pre className="text-xs font-mono text-[#B04030]/80 whitespace-pre-wrap" dir="ltr">
              {activePair.error}
            </pre>
          </div>
        </FadeIn>
      )}

      <Tabs defaultValue={initialTab} dir="rtl">
        <TabsList variant="line" className="border-b border-border/50 pb-0 gap-0">
          <TabsTrigger value="overview" className={tabCls}>
            <TrendingUp className="size-3.5" /> סקירה
          </TabsTrigger>
          {pairPrompt?.formatted_prompt && (
            <TabsTrigger value="prompt" className={tabCls}>
              <Code2 className="size-3.5" /> פרומפט
            </TabsTrigger>
          )}
          {serveInfo && (
            <TabsTrigger value="playground" className={tabCls}>
              <Send className="size-3.5" /> שימוש
            </TabsTrigger>
          )}
          <TabsTrigger value="data" className={tabCls}>
            <Database className="size-3.5" /> נתונים
          </TabsTrigger>
          <TabsTrigger value="logs" className={tabCls}>
            <Terminal className="size-3.5" /> לוגים
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6 mt-4">
          {!activePair.error && (
            <StaggerContainer className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <StaggerItem>
                <TiltCard className="rounded-xl border border-border/50 bg-card p-6 text-center">
                  <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide">
                    <HelpTip text="ציון המדידה לפני אופטימיזציה — התוכנית רצה ללא הנחיות או דוגמאות">
                      ציון התחלתי
                    </HelpTip>
                  </p>
                  <p className="text-3xl font-mono font-bold tabular-nums">
                    {formatPercent(activePair.baseline_test_metric)}
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
                  <p className="text-3xl font-mono font-bold text-primary tabular-nums">
                    {formatPercent(activePair.optimized_test_metric)}
                  </p>
                </TiltCard>
              </StaggerItem>
              <StaggerItem>
                <TiltCard
                  className={`rounded-xl border p-6 text-center ${(activePair.metric_improvement ?? 0) >= 0 ? "border-stone-400/50 bg-gradient-to-br from-stone-100/50 to-stone-200/30" : "border-red-300/50 bg-gradient-to-br from-red-50/50 to-red-100/30"}`}
                >
                  <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide">
                    <HelpTip text="ההפרש בין הציון המשופר לציון ההתחלתי — ככל שגבוה יותר, האופטימיזציה הועילה יותר">
                      שיפור
                    </HelpTip>
                  </p>
                  <p
                    className={`text-3xl font-mono font-bold tabular-nums ${(activePair.metric_improvement ?? 0) >= 0 ? "text-stone-600" : "text-red-600"}`}
                  >
                    {formatImprovement(activePair.metric_improvement)}
                  </p>
                </TiltCard>
              </StaggerItem>
            </StaggerContainer>
          )}

          <FadeIn delay={0.1}>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
              <InfoCard
                label="מודל יצירה"
                value={activePair.generation_model.split("/").pop()}
                icon={<Cpu className="size-3.5" />}
              />
              <InfoCard
                label="מודל רפלקציה"
                value={activePair.reflection_model.split("/").pop()}
                icon={<Lightbulb className="size-3.5" />}
              />
              {activePair.runtime_seconds != null && (
                <InfoCard
                  label="זמן ריצה"
                  value={formatDuration(activePair.runtime_seconds)}
                  icon={<Clock className="size-3.5" />}
                />
              )}
              {activePair.num_lm_calls != null && (
                <InfoCard
                  label="קריאות למודל"
                  value={String(activePair.num_lm_calls)}
                  icon={<MessageSquare className="size-3.5" />}
                />
              )}
              {activePair.avg_response_time_ms != null && (
                <InfoCard
                  label="זמן תגובה ממוצע"
                  value={`${(activePair.avg_response_time_ms / 1000).toFixed(1)}s`}
                  icon={<Timer className="size-3.5" />}
                />
              )}
            </div>
          </FadeIn>

          {pairScorePoints.length > 1 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-medium">
                  <HelpTip text="שינוי הציון לאורך הניסיונות השונים של האופטימייזר">
                    מהלך הציונים
                  </HelpTip>
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="h-[260px]" dir="ltr">
                  <ScoreChart data={pairScorePoints} />
                </div>
                <div className="flex flex-wrap justify-center gap-x-5 gap-y-1 mt-2">
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span
                      className="inline-block w-3 h-0.5 rounded-full"
                      style={{ backgroundColor: "var(--color-chart-4)" }}
                    />
                    <span>ציון הניסיון</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span
                      className="inline-block w-3 h-[2px] rounded-full"
                      style={{ backgroundColor: "var(--color-chart-2)" }}
                    />
                    <span>הציון הגבוה ביותר</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {pairPrompt?.formatted_prompt && (
          <TabsContent value="prompt" className="space-y-4 mt-4">
            <FadeIn>
              {pairPrompt.demos && pairPrompt.demos.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base font-medium">
                      <HelpTip text="דוגמאות קלט-פלט שנבחרו מהדאטאסט ומוצגות למודל כהדגמה">
                        {pairPrompt.demos.length} דוגמאות
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
                    <HelpTip text="הפרומפט המלא שהאופטימייזר בנה — כולל הנחיות ודוגמאות שנבחרו">
                      הפרומפט המאומן
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
                  הרצת התוכנית המאומנת של זוג זה — הזן קלט וקבל תשובה.
                </p>
                {runHistory.length > 0 && (
                  <TooltipProvider>
                    <UiTooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-8"
                          onClick={onClearHistory}
                          aria-label="נקה היסטוריה"
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">נקה היסטוריה</TooltipContent>
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
