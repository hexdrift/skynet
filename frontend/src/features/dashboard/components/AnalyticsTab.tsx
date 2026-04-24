import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "react-toastify";
import dynamic from "next/dynamic";
import { AnimatePresence, motion } from "framer-motion";
import {
  CheckCircle2,
  Clock,
  ExternalLink,
  Loader2,
  Medal,
  TrendingUp,
  X,
  Zap,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip as UiTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { AnimatedNumber, StaggerContainer, StaggerItem, TiltCard } from "@/shared/ui/motion";
import { HelpTip } from "@/shared/ui/help-tip";
import { formatElapsed } from "@/shared/lib";
import { getStatusLabel } from "@/shared/constants/job-status";
import type { DashboardAnalytics } from "@/shared/lib/api";
import { msg } from "@/shared/lib/messages";
import { tip } from "@/shared/lib/tooltips";
import { TERMS } from "@/shared/lib/terms";
import { AnalyticsEmpty } from "./AnalyticsEmpty";
import { AnalyticsSection } from "./AnalyticsSection";
import type { ChartData } from "../lib/transform-chart-data";
import type { UseAnalyticsFiltersReturn } from "../hooks/use-analytics-filters";

const ScoresChart = dynamic(() => import("@/shared/charts").then((m) => m.ScoresChart), {
  ssr: false,
  loading: () => (
    <div className="h-[300px] flex items-center justify-center">
      <span className="text-sm text-muted-foreground">טוען גרפים...</span>
    </div>
  ),
});
const OptimizerChart = dynamic(() => import("@/shared/charts").then((m) => m.OptimizerChart), {
  ssr: false,
  loading: () => <div className="h-[280px]" />,
});
const RuntimeDistributionChart = dynamic(
  () => import("@/shared/charts").then((m) => m.RuntimeDistributionChart),
  { ssr: false, loading: () => <div className="h-[250px]" /> },
);
const DatasetVsImprovementChart = dynamic(
  () => import("@/shared/charts").then((m) => m.DatasetVsImprovementChart),
  { ssr: false, loading: () => <div className="h-[250px]" /> },
);
const EfficiencyChart = dynamic(() => import("@/shared/charts").then((m) => m.EfficiencyChart), {
  ssr: false,
  loading: () => <div className="h-[250px]" />,
});
const TimelineChart = dynamic(() => import("@/shared/charts").then((m) => m.TimelineChart), {
  ssr: false,
  loading: () => <div className="h-[160px]" />,
});

type AnalyticsTabProps = {
  analyticsLoading: boolean;
  analyticsData: DashboardAnalytics | null;
  chartData: ChartData;
  filters: UseAnalyticsFiltersReturn;
};

export function AnalyticsTab({
  analyticsLoading,
  analyticsData,
  chartData,
  filters,
}: AnalyticsTabProps) {
  const router = useRouter();
  const {
    optimizer,
    model,
    status,
    jobId,
    date,
    leaderboardLimit,
    setOptimizer,
    setModel,
    setStatus,
    setJobId,
    setDate,
  } = filters;

  if (analyticsLoading && analyticsData === null) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-24">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">טוען נתוני אנליטיקה...</p>
      </div>
    );
  }

  if ((analyticsData?.filtered_total ?? 0) === 0) {
    const hasFilters = jobId || date || optimizer !== "all" || model !== "all" || status !== "all";
    if (hasFilters) {
      return (
        <AnalyticsEmpty
          variant="no-results"
          onClearFilters={() => {
            setOptimizer("all");
            setModel("all");
            setStatus("all");
          }}
        />
      );
    }
    return <AnalyticsEmpty variant="no-data" />;
  }

  const hasFilters = jobId || date || optimizer !== "all" || model !== "all" || status !== "all";
  const clearAllFilters = () => {
    setJobId(null);
    setDate(null);
    setOptimizer("all");
    setModel("all");
    setStatus("all");
  };

  return (
    <div className="space-y-6">
      {hasFilters && (
        <div className="flex items-center gap-2 flex-wrap">
          {jobId && (
            <span className="group inline-flex items-center gap-1.5 rounded-lg bg-[#3D2E22]/[0.06] border border-[#3D2E22]/10 pe-1 ps-2.5 py-1 transition-all duration-150 hover:bg-[#3D2E22]/[0.1] hover:border-[#3D2E22]/20">
              <span className="font-mono text-[0.6875rem] font-medium text-[#3D2E22]/80" dir="ltr">
                {jobId.slice(0, 8)}…
              </span>
              <button
                onClick={() => setJobId(null)}
                className="size-5 rounded-md flex items-center justify-center text-[#3D2E22]/40 hover:text-[#3D2E22] hover:bg-[#3D2E22]/10 transition-colors cursor-pointer"
                aria-label="הסר סינון"
              >
                <X className="size-3" />
              </button>
            </span>
          )}
          {date && (
            <span className="group inline-flex items-center gap-1.5 rounded-lg bg-[#3D2E22]/[0.06] border border-[#3D2E22]/10 pe-1 ps-2.5 py-1 transition-all duration-150 hover:bg-[#3D2E22]/[0.1] hover:border-[#3D2E22]/20">
              <span className="text-[0.6875rem] font-medium text-[#3D2E22]/80">
                {new Date(date).toLocaleDateString("he-IL", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </span>
              <button
                onClick={() => setDate(null)}
                className="size-5 rounded-md flex items-center justify-center text-[#3D2E22]/40 hover:text-[#3D2E22] hover:bg-[#3D2E22]/10 transition-colors cursor-pointer"
                aria-label="הסר סינון"
              >
                <X className="size-3" />
              </button>
            </span>
          )}
          {optimizer !== "all" && (
            <span className="group inline-flex items-center gap-1.5 rounded-lg bg-[#3D2E22]/[0.06] border border-[#3D2E22]/10 pe-1 ps-2.5 py-1 transition-all duration-150 hover:bg-[#3D2E22]/[0.1] hover:border-[#3D2E22]/20">
              <span className="text-[0.6875rem] font-medium text-[#3D2E22]/80" dir="ltr">
                {optimizer}
              </span>
              <button
                onClick={() => setOptimizer("all")}
                className="size-5 rounded-md flex items-center justify-center text-[#3D2E22]/40 hover:text-[#3D2E22] hover:bg-[#3D2E22]/10 transition-colors cursor-pointer"
                aria-label="הסר סינון"
              >
                <X className="size-3" />
              </button>
            </span>
          )}
          {model !== "all" && (
            <span className="group inline-flex items-center gap-1.5 rounded-lg bg-[#3D2E22]/[0.06] border border-[#3D2E22]/10 pe-1 ps-2.5 py-1 transition-all duration-150 hover:bg-[#3D2E22]/[0.1] hover:border-[#3D2E22]/20">
              <span
                className="font-mono text-[0.6875rem] font-medium text-[#3D2E22]/80 truncate max-w-[140px]"
                dir="ltr"
                title={model}
              >
                {model}
              </span>
              <button
                onClick={() => setModel("all")}
                className="size-5 rounded-md flex items-center justify-center text-[#3D2E22]/40 hover:text-[#3D2E22] hover:bg-[#3D2E22]/10 transition-colors cursor-pointer"
                aria-label="הסר סינון"
              >
                <X className="size-3" />
              </button>
            </span>
          )}
          {status !== "all" && (
            <span className="group inline-flex items-center gap-1.5 rounded-lg bg-[#3D2E22]/[0.06] border border-[#3D2E22]/10 pe-1 ps-2.5 py-1 transition-all duration-150 hover:bg-[#3D2E22]/[0.1] hover:border-[#3D2E22]/20">
              <span className="text-[0.6875rem] font-medium text-[#3D2E22]/80">
                {getStatusLabel(status)}
              </span>
              <button
                onClick={() => setStatus("all")}
                className="size-5 rounded-md flex items-center justify-center text-[#3D2E22]/40 hover:text-[#3D2E22] hover:bg-[#3D2E22]/10 transition-colors cursor-pointer"
                aria-label="הסר סינון"
              >
                <X className="size-3" />
              </button>
            </span>
          )}
          <button
            onClick={clearAllFilters}
            className="text-[0.625rem] text-[#3D2E22]/40 hover:text-[#3D2E22]/70 transition-colors cursor-pointer ms-0.5"
          >
            נקה הכל
          </button>
        </div>
      )}

      <AnimatePresence mode="wait">
        <motion.div
          key={`${jobId ?? "all"}-${date ?? "all"}-${optimizer}-${model}-${status}`}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.3, ease: [0.2, 0.8, 0.2, 1] }}
        >
          <StaggerContainer className="space-y-6" staggerDelay={0.03}>
            {chartData.kpis && (
              <StaggerItem>
                <div
                  className="grid gap-3 sm:gap-4"
                  style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(200px, 100%), 1fr))" }}
                >
                  <TooltipProvider>
                    <UiTooltip>
                      <TooltipTrigger asChild>
                        <TiltCard>
                          <Card className="relative overflow-hidden group/kpi border-border/40 hover:border-border/70 transition-colors duration-300">
                            <CardContent className="p-5 sm:p-6 relative">
                              <div className="flex items-start justify-between">
                                <div className="space-y-3">
                                  <p className="text-[0.75rem] font-medium text-muted-foreground/80 tracking-wide">
                                    אחוז הצלחה
                                  </p>
                                  <p className="text-2xl sm:text-4xl font-bold tracking-tighter tabular-nums">
                                    <AnimatedNumber
                                      value={Math.round(chartData.kpis.successRate)}
                                      suffix="%"
                                    />
                                  </p>
                                </div>
                                <div className="size-9 rounded-lg bg-stone-500/[0.07] flex items-center justify-center">
                                  <CheckCircle2 className="size-4 text-stone-500" />
                                </div>
                              </div>
                              <div className="mt-3 flex items-center gap-2">
                                <div className="flex-1 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                                  <div
                                    className="h-full rounded-full bg-stone-500/40 transition-all duration-700"
                                    style={{
                                      width: `${chartData.kpis.successRate}%`,
                                    }}
                                  />
                                </div>
                                <span className="text-[0.625rem] tabular-nums text-muted-foreground/60 shrink-0">
                                  <AnimatedNumber value={chartData.kpis.successCount} />
                                  /
                                  <AnimatedNumber value={chartData.kpis.terminalCount} />
                                </span>
                              </div>
                            </CardContent>
                          </Card>
                        </TiltCard>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="max-w-xs">
                        <div className="space-y-1.5 text-xs">
                          <p className="font-semibold">פרוט נוסף:</p>
                          <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                            <span className="text-muted-foreground">הצליחו:</span>
                            <span className="font-mono tabular-nums">
                              {chartData.kpis.successCount}
                            </span>
                            <span className="text-muted-foreground">סה"כ הסתיימו:</span>
                            <span className="font-mono tabular-nums">
                              {chartData.kpis.terminalCount}
                            </span>
                          </div>
                        </div>
                      </TooltipContent>
                    </UiTooltip>
                  </TooltipProvider>
                  <TooltipProvider>
                    <UiTooltip>
                      <TooltipTrigger asChild>
                        <TiltCard>
                          <Card className="relative overflow-hidden group/kpi border-border/40 hover:border-border/70 transition-colors duration-300">
                            <CardContent className="p-5 sm:p-6 relative">
                              <div className="flex items-start justify-between">
                                <div className="space-y-3">
                                  <p className="text-[0.75rem] font-medium text-muted-foreground/80 tracking-wide">
                                    שיפור ממוצע
                                  </p>
                                  <p
                                    className={`text-2xl sm:text-4xl font-bold tracking-tighter tabular-nums ${chartData.kpis.avgImprovement > 0 ? "text-emerald-700" : chartData.kpis.avgImprovement < 0 ? "text-red-600" : ""}`}
                                  >
                                    <AnimatedNumber
                                      value={parseFloat(chartData.kpis.avgImprovement.toFixed(1))}
                                      decimals={1}
                                      prefix={chartData.kpis.avgImprovement >= 0 ? "+" : ""}
                                      suffix="%"
                                    />
                                  </p>
                                </div>
                                <div
                                  className={`size-9 rounded-lg flex items-center justify-center ${chartData.kpis.avgImprovement > 0 ? "bg-emerald-500/[0.07]" : chartData.kpis.avgImprovement < 0 ? "bg-red-500/[0.07]" : "bg-stone-500/[0.07]"}`}
                                >
                                  <TrendingUp
                                    className={`size-4 ${chartData.kpis.avgImprovement > 0 ? "text-emerald-600" : chartData.kpis.avgImprovement < 0 ? "text-red-500" : "text-stone-500"}`}
                                  />
                                </div>
                              </div>
                              <div className="mt-3 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                                <div
                                  className={`h-full rounded-full transition-all duration-700 ${chartData.kpis.avgImprovement > 0 ? "bg-emerald-500/40" : chartData.kpis.avgImprovement < 0 ? "bg-red-500/40" : "bg-stone-400/40"}`}
                                  style={{
                                    width: `${Math.min(Math.abs(chartData.kpis.avgImprovement), 100)}%`,
                                  }}
                                />
                              </div>
                            </CardContent>
                          </Card>
                        </TiltCard>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="max-w-xs">
                        <div className="space-y-1.5 text-xs">
                          <p className="font-semibold">פרוט נוסף:</p>
                          <p className="text-muted-foreground">
                            שיפור ממוצע בציון הבדיקה לאחר {TERMS.optimization}
                          </p>
                        </div>
                      </TooltipContent>
                    </UiTooltip>
                  </TooltipProvider>
                  <TooltipProvider>
                    <UiTooltip>
                      <TooltipTrigger asChild>
                        <TiltCard>
                          <Card className="relative overflow-hidden group/kpi border-border/40 hover:border-border/70 transition-colors duration-300">
                            <CardContent className="p-5 sm:p-6 relative">
                              <div className="flex items-start justify-between">
                                <div className="space-y-3">
                                  <p className="text-[0.75rem] font-medium text-muted-foreground/80 tracking-wide">
                                    זמן ריצה ממוצע
                                  </p>
                                  <p
                                    className="text-2xl sm:text-4xl font-bold tracking-tighter tabular-nums"
                                    dir="ltr"
                                  >
                                    {formatElapsed(chartData.kpis.avgRuntime)}
                                  </p>
                                </div>
                                <div className="size-9 rounded-lg bg-stone-500/[0.07] flex items-center justify-center">
                                  <Clock className="size-4 text-stone-500" />
                                </div>
                              </div>
                              <p className="mt-3 text-[0.625rem] text-muted-foreground/50">
                                לכל {TERMS.optimization}
                              </p>
                            </CardContent>
                          </Card>
                        </TiltCard>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="max-w-xs">
                        <div className="space-y-1.5 text-xs">
                          <p className="font-semibold">פרוט נוסף:</p>
                          <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                            <span className="text-muted-foreground">זוגות שרצו:</span>
                            <span className="font-mono tabular-nums">
                              {chartData.kpis.totalPairsRun}
                            </span>
                          </div>
                        </div>
                      </TooltipContent>
                    </UiTooltip>
                  </TooltipProvider>
                  <TooltipProvider>
                    <UiTooltip>
                      <TooltipTrigger asChild>
                        <TiltCard>
                          <Card className="relative overflow-hidden group/kpi border-border/40 hover:border-border/70 transition-colors duration-300">
                            <CardContent className="p-5 sm:p-6 relative">
                              <div className="flex items-start justify-between">
                                <div className="space-y-3">
                                  <p className="text-[0.75rem] font-medium text-muted-foreground/80 tracking-wide">
                                    שיפור מקסימלי
                                  </p>
                                  <p className="text-2xl sm:text-4xl font-bold tracking-tighter tabular-nums text-amber-700">
                                    <AnimatedNumber
                                      value={parseFloat(chartData.kpis.bestImprovement.toFixed(1))}
                                      decimals={1}
                                      prefix="+"
                                      suffix="%"
                                    />
                                  </p>
                                </div>
                                <div className="size-9 rounded-lg bg-amber-500/[0.07] flex items-center justify-center">
                                  <Zap className="size-4 text-amber-600" />
                                </div>
                              </div>
                              <div className="mt-3 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                                <div
                                  className="h-full rounded-full bg-amber-500/40 transition-all duration-700"
                                  style={{
                                    width: `${Math.min(chartData.kpis.bestImprovement, 100)}%`,
                                  }}
                                />
                              </div>
                            </CardContent>
                          </Card>
                        </TiltCard>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="max-w-xs">
                        <div className="space-y-1.5 text-xs">
                          <p className="font-semibold">פרוט נוסף:</p>
                          <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                            <span className="text-muted-foreground">שורות שנותחו:</span>
                            <span className="font-mono tabular-nums">
                              {chartData.kpis.totalRows.toLocaleString("he-IL")}
                            </span>
                            <span className="text-muted-foreground">סריקות:</span>
                            <span className="font-mono tabular-nums">
                              {chartData.kpis.gridSearchCount}
                            </span>
                            <span className="text-muted-foreground">ריצות בודדות:</span>
                            <span className="font-mono tabular-nums">
                              {chartData.kpis.singleRunCount}
                            </span>
                          </div>
                        </div>
                      </TooltipContent>
                    </UiTooltip>
                  </TooltipProvider>
                </div>
              </StaggerItem>
            )}

            <StaggerItem>
              <AnalyticsSection
                title={<HelpTip text={tip("analytics.score_comparison")}>סקירת ביצועים</HelpTip>}
                defaultOpen={true}
                className="border-border/60"
              >
                <div className="grid gap-5 md:grid-cols-7">
                  <div className="md:col-span-4">
                    <div className="mb-3">
                      <h4 className="text-sm font-semibold">ציונים לפי {TERMS.optimization}</h4>
                    </div>
                    <ScoresChart
                      data={chartData.improvement}
                      optimizationIds={chartData.improvementJobIds}
                      onBarClick={(optimizationId) => setJobId(optimizationId)}
                    />
                  </div>

                  <div className="md:col-span-3 space-y-6">
                    <div className="space-y-3">
                      <p className="text-[0.6875rem] font-semibold text-muted-foreground uppercase tracking-widest">
                        סטטוסים
                      </p>
                      {chartData.status.map((s, i) => {
                        const total = chartData.status.reduce((a, b) => a + b.value, 0);
                        return (
                          <div
                            key={i}
                            className="space-y-1.5 cursor-pointer hover:opacity-80 transition-opacity"
                            onClick={() => setStatus(s.key)}
                          >
                            <div className="flex items-center justify-between text-sm">
                              <span className="flex items-center gap-2">
                                <span
                                  className=" size-2.5 rounded-full shrink-0 ring-1 ring-black/5"
                                  style={{ backgroundColor: s.fill }}
                                />
                                <span className="text-[0.8125rem]">{s.name}</span>
                              </span>
                              <span className="tabular-nums font-semibold text-[0.8125rem]">
                                {s.value}
                              </span>
                            </div>
                            <div className="h-2 rounded-full bg-muted/60 overflow-hidden">
                              <div
                                className="h-full rounded-full transition-all duration-500"
                                style={{
                                  width: `${(s.value / total) * 100}%`,
                                  backgroundColor: s.fill,
                                }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    <div className="border-t border-border" />

                    <div className="space-y-3">
                      <p className="text-[0.6875rem] font-semibold text-muted-foreground uppercase tracking-widest">
                        {TERMS.optimizer}ים
                      </p>
                      {chartData.optimizer.map((o, i) => {
                        const total = chartData.optimizer.reduce((a, b) => a + b.value, 0);
                        return (
                          <div
                            key={i}
                            className="space-y-1.5 cursor-pointer hover:opacity-80 transition-opacity"
                            dir="ltr"
                            onClick={() => setOptimizer(o.name)}
                          >
                            <div className="flex items-center justify-between text-sm">
                              <span className="flex items-center gap-2">
                                <span
                                  className="size-2.5 rounded-full shrink-0 ring-1 ring-black/5"
                                  style={{
                                    backgroundColor: `var(--color-chart-${(i % 5) + 1})`,
                                  }}
                                />
                                <span className="text-[0.8125rem]">{o.name}</span>
                              </span>
                              <span className="tabular-nums font-semibold text-[0.8125rem]">
                                {o.value}
                              </span>
                            </div>
                            <div className="h-2 rounded-full bg-muted/60 overflow-hidden">
                              <div
                                className="h-full rounded-full transition-all duration-500"
                                style={{
                                  width: `${(o.value / total) * 100}%`,
                                  backgroundColor: `var(--color-chart-${(i % 5) + 1})`,
                                }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {chartData.jobTypeData.length > 0 && (
                      <>
                        <div className="border-t border-border" />
                        <div className="space-y-3">
                          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                            סוג {TERMS.optimization}
                          </p>
                          {chartData.jobTypeData.map((d, i) => {
                            const total = chartData.jobTypeData.reduce((a, b) => a + b.value, 0);
                            return (
                              <div key={i} className="space-y-1">
                                <div className="flex items-center justify-between text-sm">
                                  <span>{d.name}</span>
                                  <span className="tabular-nums font-medium">{d.value}</span>
                                </div>
                                <div className="h-2 rounded-full bg-muted overflow-hidden">
                                  <div
                                    className="h-full rounded-full bg-primary/70 transition-all"
                                    style={{
                                      width: `${(d.value / total) * 100}%`,
                                    }}
                                  />
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </AnalyticsSection>
            </StaggerItem>

            {(chartData.runtimeDistribution.length > 0 || chartData.efficiencyData.length > 0) && (
              <StaggerItem>
                <AnalyticsSection
                  title={
                    <HelpTip text={tip("analytics.runtime_vs_gain")}>יעילות וזמני ריצה</HelpTip>
                  }
                  defaultOpen={true}
                  className="border-border/60"
                >
                  <div className="grid gap-5 md:grid-cols-2">
                    {chartData.runtimeDistribution.length > 0 && (
                      <div>
                        <div className="mb-3">
                          <h4 className="text-sm font-semibold">
                            <HelpTip text={tip("analytics.runtime_minutes")}>
                              התפלגות זמני ריצה
                            </HelpTip>
                          </h4>
                        </div>
                        <RuntimeDistributionChart
                          data={chartData.runtimeDistribution}
                          optimizationIds={chartData.runtimeDistributionJobIds}
                          onBarClick={(optimizationId) => setJobId(optimizationId)}
                        />
                      </div>
                    )}
                    {chartData.efficiencyData.length > 0 && (
                      <div>
                        <div className="mb-3">
                          <h4 className="text-sm font-semibold">
                            <HelpTip text={tip("analytics.improvement_per_minute")}>
                              יעילות: שיפור לדקה
                            </HelpTip>
                          </h4>
                        </div>
                        <EfficiencyChart
                          data={chartData.efficiencyData}
                          optimizationIds={chartData.efficiencyJobIds}
                          onBarClick={(optimizationId) => setJobId(optimizationId)}
                        />
                      </div>
                    )}
                  </div>
                  {chartData.datasetVsImprovement.length > 0 && (
                    <div className="mt-5">
                      <div className="mb-3">
                        <h4 className="text-sm font-semibold">
                          <HelpTip text={tip("analytics.dataset_size_vs_improvement")}>
                            גודל {TERMS.dataset} מול שיפור
                          </HelpTip>
                        </h4>
                      </div>
                      <DatasetVsImprovementChart
                        data={chartData.datasetVsImprovement}
                        optimizationIds={chartData.datasetVsImprovementIds}
                        onDotClick={(id) => setJobId(id)}
                      />
                    </div>
                  )}
                </AnalyticsSection>
              </StaggerItem>
            )}

            {chartData.timelineData.length > 0 && (
              <StaggerItem>
                <AnalyticsSection
                  title={<HelpTip text={tip("analytics.submissions_per_day")}>ציר זמן</HelpTip>}
                  defaultOpen={true}
                  className="border-border/60"
                >
                  <TimelineChart
                    data={chartData.timelineData}
                    dates={chartData.timelineDates}
                    onBarClick={(d) => setDate(d)}
                  />
                </AnalyticsSection>
              </StaggerItem>
            )}

            {chartData.avgByOptimizer.length > 0 && (
              <StaggerItem>
                <AnalyticsSection
                  title={
                    <HelpTip text={tip("analytics.optimizer_avg_improvement")}>
                      השוואת {TERMS.optimizer}ים
                    </HelpTip>
                  }
                  defaultOpen={true}
                  className="border-border/60"
                >
                  <div className="grid gap-5 md:grid-cols-7">
                    <div className="md:col-span-4">
                      <OptimizerChart
                        data={chartData.avgByOptimizer}
                        onBarClick={(name) => setOptimizer(name)}
                      />
                    </div>
                    <div className="md:col-span-3">
                      <div className="mb-3">
                        <h4 className="text-sm font-semibold">מודלים פופולריים</h4>
                      </div>
                      {chartData.modelUsage.length > 0 ? (
                        <div className="space-y-3">
                          {chartData.modelUsage.map((m, i) => {
                            const maxCount = chartData.modelUsage[0]?.count ?? 1;
                            return (
                              <div
                                key={i}
                                className="space-y-1.5 cursor-pointer hover:opacity-80 transition-opacity"
                                onClick={() => setModel(m.name)}
                              >
                                <div
                                  className="flex items-center justify-between text-sm"
                                  dir="ltr"
                                >
                                  <span className="font-mono truncate max-w-[200px]" title={m.name}>
                                    {m.name}
                                  </span>
                                  <span className="tabular-nums font-medium">{m.count}</span>
                                </div>
                                <div
                                  className="h-2 rounded-full bg-muted overflow-hidden"
                                  dir="ltr"
                                >
                                  <div
                                    className="h-full rounded-full bg-primary/60 transition-all"
                                    style={{
                                      width: `${(m.count / maxCount) * 100}%`,
                                    }}
                                  />
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="flex h-[150px] items-center justify-center">
                          <p className="text-sm text-muted-foreground">אין מידע על מודלים</p>
                        </div>
                      )}
                    </div>
                  </div>
                </AnalyticsSection>
              </StaggerItem>
            )}

            {chartData.topJobs.length > 0 && (
              <StaggerItem>
                <AnalyticsSection
                  title={
                    <div className="flex items-center gap-2">
                      <span className="size-5 rounded-md bg-gradient-to-br from-stone-400/20 to-stone-500/10 flex items-center justify-center ring-1 ring-stone-400/10">
                        <TrendingUp className="size-3 text-stone-600" />
                      </span>
                      <HelpTip text={tip("analytics.top_improvements")}>
                        השיפורים הגדולים ביותר
                      </HelpTip>
                    </div>
                  }
                  defaultOpen={true}
                  className="border-border/60"
                >
                  <div className="pt-0">
                    <div className="hidden sm:block overflow-x-auto" dir="rtl">
                      <Table className="min-w-[500px]">
                        <TableHeader>
                          <TableRow className="border-b-0">
                            <TableHead className="text-center w-10 text-[0.6875rem] uppercase tracking-wider text-stone-400">
                              #
                            </TableHead>
                            <TableHead className="text-start text-[0.6875rem] uppercase tracking-wider text-stone-400">
                              מזהה {TERMS.optimization}
                            </TableHead>
                            <TableHead className="text-start text-[0.6875rem] uppercase tracking-wider text-stone-400">
                              {TERMS.optimizer}
                            </TableHead>
                            <TableHead className="text-center text-[0.6875rem] uppercase tracking-wider text-stone-400">
                              לפני
                            </TableHead>
                            <TableHead className="text-center text-[0.6875rem] uppercase tracking-wider text-stone-400">
                              אחרי
                            </TableHead>
                            <TableHead className="text-center text-[0.6875rem] uppercase tracking-wider text-stone-400">
                              שיפור
                            </TableHead>
                            <TableHead className="w-10"></TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {chartData.topJobs.slice(0, leaderboardLimit).map((j, i) => {
                            const fmt = (n: number | undefined | null) => {
                              if (n == null) return "\u2014";
                              return (n > 1 ? n : n * 100).toFixed(1) + "%";
                            };
                            const imp = j.metric_improvement!;
                            const impPct = Math.abs(imp) > 1 ? imp : imp * 100;
                            const baseline =
                              j.baseline_test_metric != null
                                ? j.baseline_test_metric > 1
                                  ? j.baseline_test_metric
                                  : j.baseline_test_metric * 100
                                : null;
                            const optimized =
                              j.optimized_test_metric != null
                                ? j.optimized_test_metric > 1
                                  ? j.optimized_test_metric
                                  : j.optimized_test_metric * 100
                                : null;

                            const copyCell = (text: string) => (e: React.MouseEvent) => {
                              e.stopPropagation();
                              navigator.clipboard.writeText(text);
                              toast.success(msg("clipboard.copied_short"), {
                                autoClose: 1000,
                              });
                            };
                            const copyCls =
                              "cursor-pointer hover:bg-stone-500/[0.04] transition-colors";
                            return (
                              <TableRow
                                key={j.optimization_id}
                                className="group/row border-border/40 hover:bg-stone-500/[0.03]"
                              >
                                <TableCell className="text-center py-3">
                                  <Medal
                                    className={`size-4 mx-auto ${i === 0 ? "text-yellow-500" : i === 1 ? "text-slate-400" : "text-amber-700"}`}
                                  />
                                </TableCell>
                                <TableCell className="py-3 text-start">
                                  <Link
                                    href={`/optimizations/${j.optimization_id}`}
                                    className="font-mono text-[0.6875rem] text-primary hover:text-primary/80 transition-colors underline-offset-4 hover:underline"
                                    dir="ltr"
                                    title={j.optimization_id}
                                  >
                                    {j.optimization_id.slice(0, 8)}…
                                  </Link>
                                </TableCell>
                                <TableCell
                                  className={`py-3 text-start ${copyCls}`}
                                  onClick={copyCell(j.optimizer_name ?? "")}
                                >
                                  <span
                                    className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-stone-500/[0.06] text-[0.75rem] font-medium text-stone-700"
                                    dir="ltr"
                                  >
                                    {j.optimizer_name}
                                  </span>
                                </TableCell>
                                <TableCell
                                  className={`text-center py-3 ${copyCls}`}
                                  onClick={copyCell(fmt(j.baseline_test_metric))}
                                >
                                  <div className="flex flex-col items-center gap-1">
                                    <span className="font-mono tabular-nums text-[0.75rem] text-stone-400">
                                      {fmt(j.baseline_test_metric)}
                                    </span>
                                    <div className="w-14 h-1 rounded-full bg-stone-200/60 overflow-hidden">
                                      <div
                                        className="h-full rounded-full bg-stone-400/40 transition-all"
                                        style={{
                                          width: `${baseline != null ? (baseline / 100) * 100 : 0}%`,
                                        }}
                                      />
                                    </div>
                                  </div>
                                </TableCell>
                                <TableCell
                                  className={`text-center py-3 ${copyCls}`}
                                  onClick={copyCell(fmt(j.optimized_test_metric))}
                                >
                                  <div className="flex flex-col items-center gap-1">
                                    <span className="font-mono tabular-nums text-[0.75rem] font-semibold text-stone-700">
                                      {fmt(j.optimized_test_metric)}
                                    </span>
                                    <div className="w-14 h-1 rounded-full bg-stone-200/60 overflow-hidden">
                                      <div
                                        className="h-full rounded-full bg-stone-600/50 transition-all"
                                        style={{
                                          width: `${optimized != null ? (optimized / 100) * 100 : 0}%`,
                                        }}
                                      />
                                    </div>
                                  </div>
                                </TableCell>
                                <TableCell
                                  className={`text-center py-3 ${copyCls}`}
                                  onClick={copyCell(
                                    `${impPct >= 0 ? "+" : ""}${impPct.toFixed(1)}%`,
                                  )}
                                >
                                  <div className="flex flex-col items-center gap-1">
                                    <span
                                      className={`font-mono tabular-nums text-[0.75rem] font-semibold ${impPct > 0 ? "text-emerald-700" : impPct < 0 ? "text-red-600" : "text-stone-500"}`}
                                    >
                                      {impPct >= 0 ? "+" : ""}
                                      {impPct.toFixed(1)}%
                                    </span>
                                    <div className="w-14 h-1 rounded-full bg-stone-200/60 overflow-hidden">
                                      <div
                                        className={`h-full rounded-full transition-all ${impPct > 0 ? "bg-emerald-500/50" : impPct < 0 ? "bg-red-500/50" : "bg-stone-400/40"}`}
                                        style={{
                                          width: `${Math.min(Math.abs(impPct), 100)}%`,
                                        }}
                                      />
                                    </div>
                                  </div>
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </div>

                    <div className="sm:hidden space-y-3">
                      {chartData.topJobs.slice(0, leaderboardLimit).map((j, i) => {
                        const fmt = (n: number | undefined | null) => {
                          if (n == null) return "—";
                          return (n > 1 ? n : n * 100).toFixed(1) + "%";
                        };
                        const imp = j.metric_improvement!;
                        const impPct = Math.abs(imp) > 1 ? imp : imp * 100;

                        return (
                          <Card
                            key={j.optimization_id}
                            className="border-border/40 hover:border-border/60 transition-colors"
                          >
                            <CardContent className="p-4 space-y-3">
                              <div className="flex items-start justify-between gap-3">
                                <div className="flex items-center gap-2">
                                  <Medal
                                    className={`size-5 shrink-0 ${i === 0 ? "text-yellow-500" : i === 1 ? "text-slate-400" : "text-amber-700"}`}
                                  />
                                  <div className="min-w-0">
                                    <Link
                                      href={`/optimizations/${j.optimization_id}`}
                                      className="font-mono text-xs text-primary hover:text-primary/80 transition-colors underline-offset-4 hover:underline block truncate"
                                      dir="ltr"
                                      title={j.optimization_id}
                                    >
                                      {j.optimization_id.slice(0, 12)}…
                                    </Link>
                                    <span className="text-xs text-muted-foreground" dir="ltr">
                                      {j.optimizer_name}
                                    </span>
                                  </div>
                                </div>
                                <button
                                  onClick={() => router.push(`/optimizations/${j.optimization_id}`)}
                                  className="p-1.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-all shrink-0"
                                >
                                  <ExternalLink className="size-3.5" />
                                </button>
                              </div>
                              <div className="grid grid-cols-3 gap-3 text-center">
                                <div>
                                  <p className="text-[0.625rem] text-muted-foreground mb-1">לפני</p>
                                  <p className="font-mono text-sm text-stone-500">
                                    {fmt(j.baseline_test_metric)}
                                  </p>
                                </div>
                                <div>
                                  <p className="text-[0.625rem] text-muted-foreground mb-1">אחרי</p>
                                  <p className="font-mono text-sm font-semibold">
                                    {fmt(j.optimized_test_metric)}
                                  </p>
                                </div>
                                <div>
                                  <p className="text-[0.625rem] text-muted-foreground mb-1">
                                    שיפור
                                  </p>
                                  <p
                                    className={`font-mono text-sm font-bold ${impPct > 0 ? "text-emerald-700" : impPct < 0 ? "text-red-600" : "text-stone-500"}`}
                                  >
                                    {impPct >= 0 ? "+" : ""}
                                    {impPct.toFixed(1)}%
                                  </p>
                                </div>
                              </div>
                            </CardContent>
                          </Card>
                        );
                      })}
                    </div>
                  </div>
                </AnalyticsSection>
              </StaggerItem>
            )}
          </StaggerContainer>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
