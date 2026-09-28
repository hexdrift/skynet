import { memo } from "react";
import { InlineWarningRow } from "@/shared/ui/inline-warning-row";
import { ProgressBar } from "@/shared/ui/progress-bar";
import type { KeyboardEvent, ReactNode } from "react";
import dynamic from "next/dynamic";
import { AnimatePresence, motion } from "framer-motion";
import { AnimatedNumber, StaggerContainer, StaggerItem } from "@/shared/ui/motion";
import { Segmented } from "@/shared/ui/segmented";
import { PanelHeading } from "@/shared/ui/panel-heading";
import { HelpTip } from "@/shared/ui/help-tip";
import { formatElapsed, modelDisplayName } from "@/shared/lib";
import type { DashboardAnalytics } from "@/shared/lib/api";
import { formatMsg, msg } from "@/shared/lib/messages";
import { tip } from "@/shared/lib/tooltips";
import { TERMS } from "@/shared/lib/terms";
import { cn } from "@/shared/lib/utils";
import { ACCENT_DOT, ACCENT_TEXT, STATUS_COLORS, type StatAccent } from "../constants";
import { AnalyticsEmpty } from "./AnalyticsEmpty";
import { AnalyticsFilterChips } from "./AnalyticsFilterChips";
import { AnalyticsSection } from "./AnalyticsSection";
import { AnalyticsTabSkeleton } from "./AnalyticsTabSkeleton";
import { Leaderboard, OptimizerTable } from "./AnalyticsTables";
import type { ChartData, HistogramBar, ShareBar } from "../lib/transform-chart-data";
import type {
  AnalyticsBucket,
  AnalyticsRange,
  UseAnalyticsFiltersReturn,
} from "../hooks/use-analytics-filters";

const chartFallback = (height: number) => (
  <div className="flex items-center justify-center" style={{ height }}>
    <span className="text-sm text-muted-foreground">
      {msg("auto.features.dashboard.components.analyticstab.1")}
    </span>
  </div>
);

const RangeHistogram = dynamic(() => import("./AnalyticsCharts").then((m) => m.RangeHistogram), {
  ssr: false,
  loading: () => chartFallback(240),
});
const StackedTimeline = dynamic(() => import("./AnalyticsCharts").then((m) => m.StackedTimeline), {
  ssr: false,
  loading: () => chartFallback(220),
});
const SharingBreakdown = dynamic(() => import("./UsageCharts"), {
  ssr: false,
  loading: () => <div className="h-[260px]" />,
});

type AnalyticsTabProps = {
  analyticsLoading: boolean;
  analyticsData: DashboardAnalytics | null;
  chartData: ChartData;
  filters: UseAnalyticsFiltersReturn;
  sessionUser: string;
  onOpenJob: (optimizationId: string) => void;
};

const RANGE_OPTIONS: readonly AnalyticsRange[] = ["7d", "30d", "90d", "all"];

function KpiCard({
  label,
  value,
  detail,
  accent,
  valueDir,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  accent: StatAccent;
  valueDir?: "ltr" | "rtl";
}) {
  return (
    <div className="flex h-full min-h-[9.5rem] min-w-0 flex-col gap-4 rounded-2xl border border-border/40 bg-card/60 p-5 transition-colors duration-300 hover:border-border/70 sm:p-6">
      <div className="flex items-center gap-2">
        <span className={`size-1.5 rounded-full ${ACCENT_DOT[accent]}`} aria-hidden />
        <p className="text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground/70">
          {label}
        </p>
      </div>
      <div className="flex flex-1 flex-col items-center justify-center gap-2">
        <p
          dir={valueDir}
          className={`text-center text-[2.5rem] font-bold leading-[0.9] tracking-tight tabular-nums sm:text-[3rem] ${ACCENT_TEXT[accent]}`}
        >
          {value}
        </p>
        <p className="min-h-[1rem] text-center text-[0.6875rem] tabular-nums text-muted-foreground">
          {detail}
        </p>
      </div>
    </div>
  );
}

function activateOnKey(e: KeyboardEvent, action: () => void) {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    action();
  }
}

function pointsValue(value: number | null): ReactNode {
  if (value == null) return "—";
  return (
    <AnimatedNumber
      value={parseFloat(value.toFixed(1))}
      decimals={1}
      prefix={value > 0 ? "+" : ""}
      suffix="%"
    />
  );
}

function pointsText(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function pointsAccent(value: number | null): StatAccent {
  if (value == null || value === 0) return "default";
  return value > 0 ? "success" : "danger";
}

/** Sliding segmented control for the date range, matching the wallet usage tab. */
function RangeControl({
  value,
  onChange,
}: {
  value: AnalyticsRange;
  onChange: (next: AnalyticsRange) => void;
}) {
  return (
    <Segmented
      size="sm"
      label={msg("usage.range.label")}
      value={value}
      onChange={onChange}
      options={RANGE_OPTIONS.map((option) => ({
        value: option,
        label: msg(`usage.range.${option}`),
      }))}
    />
  );
}

/** Horizontal share bars (status, type, module); the bar is a share of all runs. */
function ShareBars({
  bars,
  color,
  onSelect,
}: {
  bars: ShareBar[];
  color?: (bar: ShareBar) => string;
  onSelect?: (key: string) => void;
}) {
  return (
    <div className="space-y-2.5">
      {bars.map((bar) => {
        const fill = color?.(bar) ?? "var(--color-chart-3)";
        const interactive = onSelect != null;
        return (
          <div
            key={bar.key}
            role={interactive ? "button" : undefined}
            tabIndex={interactive ? 0 : undefined}
            className={cn(
              "space-y-1.5 rounded-md py-1",
              interactive &&
                "min-h-[44px] cursor-pointer transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 lg:min-h-0",
            )}
            onClick={interactive ? () => onSelect(bar.key) : undefined}
            onKeyDown={interactive ? (e) => activateOnKey(e, () => onSelect(bar.key)) : undefined}
          >
            <div className="flex items-center justify-between gap-3 text-[0.8125rem]">
              <span className="flex min-w-0 items-center gap-2">
                <span
                  className="size-2.5 shrink-0 rounded-full ring-1 ring-black/5"
                  style={{ backgroundColor: fill }}
                />
                <span className="truncate" title={bar.name}>
                  {bar.name}
                </span>
              </span>
              <span className="shrink-0 tabular-nums font-semibold">
                {bar.value}
                <span className="ms-1.5 text-[0.6875rem] font-normal text-muted-foreground">
                  {Math.round(bar.pct)}%
                </span>
              </span>
            </div>
            <ProgressBar value={bar.pct} color={fill} />
          </div>
        );
      })}
    </div>
  );
}

// Rank-shaded ramp for the model list: the most-used model is darkest and
// lighter steps follow, so the list reads as a ranking. Clamps past rank 5.
const MODEL_RAMP = [
  "var(--color-chart-1)",
  "var(--color-chart-2)",
  "var(--color-chart-3)",
  "var(--color-chart-4)",
  "var(--color-chart-5)",
];

function AnalyticsTabImpl({
  analyticsLoading,
  analyticsData,
  chartData,
  filters,
  sessionUser,
  onOpenJob,
}: AnalyticsTabProps) {
  const {
    range,
    owner,
    access,
    setRange,
    setOptimizer,
    setModel,
    setStatus,
    setDateRange,
    setOwner,
    setAccess,
    setJobType,
    setModule,
    setImprovement,
    setRuntime,
    setDataset,
    hasFilters,
    clearAll,
    key: filterKey,
  } = filters;

  const bucketFilter = (setter: (bucket: AnalyticsBucket | null) => void) => (bar: HistogramBar) =>
    setter({ lower: bar.lower, upper: bar.upper, label: bar.label });

  const showOwners = chartData.ownerUsage.length > 1 || Boolean(owner);
  const showAccess = chartData.accessUsage.length > 1 || Boolean(access);

  if (analyticsLoading && analyticsData === null) {
    return <AnalyticsTabSkeleton />;
  }

  const toolbar = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <RangeControl value={range} onChange={setRange} />
      <AnalyticsFilterChips filters={filters} sessionUser={sessionUser} />
    </div>
  );

  if ((analyticsData?.filtered_total ?? 0) === 0) {
    if (hasFilters) {
      return (
        <div data-tutorial="analytics-content" className="space-y-6">
          {toolbar}
          <AnalyticsEmpty variant="no-results" onClearFilters={clearAll} />
        </div>
      );
    }
    return <AnalyticsEmpty variant="no-data" />;
  }

  const kpis = chartData.kpis;
  const granularityLabel = msg(`dashboard.analytics.timeline_by_${chartData.timelineGranularity}`);
  const noSuccessMessage = msg("dashboard.analytics.no_successful_runs");

  return (
    <div data-tutorial="analytics-content" className="space-y-6">
      {toolbar}

      {chartData.truncated && <InlineWarningRow message={msg("dashboard.analytics.truncated")} />}

      <AnimatePresence mode="wait">
        <motion.div
          key={filterKey}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.3, ease: [0.2, 0.8, 0.2, 1] }}
        >
          <StaggerContainer className="space-y-6" staggerDelay={0.03}>
            {kpis && (
              <StaggerItem>
                <div
                  data-tutorial="dashboard-stats"
                  className="grid auto-rows-fr grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 xl:grid-cols-5"
                >
                  <KpiCard
                    label={msg("dashboard.analytics.kpi_total")}
                    accent="default"
                    value={<AnimatedNumber value={kpis.total} />}
                    detail={
                      kpis.runningCount > 0
                        ? formatMsg("dashboard.analytics.kpi_running_detail", {
                            p1: kpis.runningCount,
                          })
                        : undefined
                    }
                  />
                  <KpiCard
                    label={msg("auto.features.dashboard.components.analyticstab.4")}
                    accent="default"
                    value={<AnimatedNumber value={Math.round(kpis.successRate)} suffix="%" />}
                    detail={formatMsg("dashboard.analytics.kpi_success_detail", {
                      p1: kpis.successCount,
                      p2: kpis.terminalCount,
                    })}
                  />
                  <KpiCard
                    label={msg("auto.features.dashboard.components.analyticstab.8")}
                    accent={pointsAccent(kpis.avgImprovement)}
                    value={pointsValue(kpis.avgImprovement)}
                    detail={
                      kpis.medianImprovement != null
                        ? formatMsg("dashboard.analytics.kpi_median_detail", {
                            p1: pointsText(kpis.medianImprovement),
                          })
                        : undefined
                    }
                  />
                  <KpiCard
                    label={msg("auto.features.dashboard.components.analyticstab.11")}
                    accent="default"
                    valueDir="ltr"
                    value={
                      kpis.avgRuntimeSeconds == null ? "—" : formatElapsed(kpis.avgRuntimeSeconds)
                    }
                  />
                  <KpiCard
                    label={msg("auto.features.dashboard.components.analyticstab.15")}
                    accent={kpis.bestImprovement == null ? "default" : "warning"}
                    value={pointsValue(kpis.bestImprovement)}
                  />
                </div>
              </StaggerItem>
            )}

            <StaggerItem>
              <AnalyticsSection
                title={
                  <HelpTip text={tip("analytics.improvement_histogram")}>
                    {msg("dashboard.analytics.section_distributions")}
                  </HelpTip>
                }
                defaultOpen={true}
                className="border-border/60"
              >
                <div className="grid gap-6 md:grid-cols-2">
                  <div className="min-w-0">
                    <PanelHeading>{msg("dashboard.analytics.improvement_histogram")}</PanelHeading>
                    <RangeHistogram
                      data={chartData.improvementHistogram}
                      unitLabel={msg("dashboard.analytics.axis_points")}
                      emptyMessage={noSuccessMessage}
                      onBucketClick={bucketFilter(setImprovement)}
                    />
                  </div>
                  <div className="min-w-0">
                    <PanelHeading>
                      <HelpTip text={tip("analytics.runtime_histogram")}>
                        {msg("auto.features.dashboard.components.analyticstab.26")}
                      </HelpTip>
                    </PanelHeading>
                    <RangeHistogram
                      data={chartData.runtimeHistogram}
                      unitLabel={msg("dashboard.analytics.axis_minutes")}
                      onBucketClick={bucketFilter(setRuntime)}
                    />
                  </div>
                </div>
                <div className="mt-6 min-w-0">
                  <PanelHeading>
                    <HelpTip text={tip("analytics.dataset_buckets")}>
                      {msg("auto.features.dashboard.components.analyticstab.28")}
                      {TERMS.dataset}
                      {msg("auto.features.dashboard.components.analyticstab.29")}
                    </HelpTip>
                  </PanelHeading>
                  <RangeHistogram
                    data={chartData.datasetBuckets}
                    unitLabel={TERMS.rowPlural}
                    withAverage
                    onBucketClick={bucketFilter(setDataset)}
                  />
                </div>
              </AnalyticsSection>
            </StaggerItem>

            <StaggerItem>
              <AnalyticsSection
                title={
                  <HelpTip text={tip("analytics.submissions_per_day")}>
                    {msg("auto.features.dashboard.components.analyticstab.30")}
                    <span className="ms-2 text-xs font-normal text-muted-foreground">
                      {granularityLabel}
                    </span>
                  </HelpTip>
                }
                defaultOpen={true}
                className="border-border/60"
              >
                <StackedTimeline
                  data={chartData.timeline}
                  granularity={chartData.timelineGranularity}
                  onSelect={setDateRange}
                />
              </AnalyticsSection>
            </StaggerItem>

            {chartData.optimizerStats.length > 0 && (
              <StaggerItem>
                <AnalyticsSection
                  title={
                    <HelpTip text={tip("analytics.optimizer_comparison")}>
                      {msg("dashboard.analytics.optimizer_comparison")}
                    </HelpTip>
                  }
                  defaultOpen={true}
                  className="border-border/60"
                >
                  <OptimizerTable rows={chartData.optimizerStats} onSelect={setOptimizer} />
                </AnalyticsSection>
              </StaggerItem>
            )}

            <StaggerItem>
              <AnalyticsSection
                title={msg("dashboard.analytics.section_breakdown")}
                defaultOpen={true}
                className="border-border/60"
              >
                <div className="grid gap-6 md:grid-cols-3">
                  <div className="min-w-0">
                    <PanelHeading>
                      {msg("auto.features.dashboard.components.analyticstab.22")}
                    </PanelHeading>
                    <ShareBars
                      bars={chartData.status}
                      color={(bar) => STATUS_COLORS[bar.key] ?? "var(--color-chart-5)"}
                      onSelect={setStatus}
                    />
                  </div>
                  <div className="min-w-0">
                    <PanelHeading>
                      {msg("auto.features.dashboard.components.analyticstab.24")}
                      {TERMS.optimization}
                    </PanelHeading>
                    <ShareBars bars={chartData.jobTypes} onSelect={setJobType} />
                  </div>
                  <div className="min-w-0">
                    <PanelHeading>{msg("dashboard.analytics.by_module")}</PanelHeading>
                    {chartData.modules.length > 0 ? (
                      <ShareBars
                        bars={chartData.modules}
                        color={() => "var(--color-chart-4)"}
                        onSelect={setModule}
                      />
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        {msg("auto.shared.charts.chart.utils.literal.1")}
                      </p>
                    )}
                  </div>
                </div>
              </AnalyticsSection>
            </StaggerItem>

            {chartData.modelStats.length > 0 && (
              <StaggerItem>
                <AnalyticsSection
                  title={msg("auto.features.dashboard.components.analyticstab.33")}
                  defaultOpen={true}
                  className="border-border/60"
                >
                  <div className="space-y-3">
                    {chartData.modelStats.map((m, i) => (
                      <div
                        key={m.name}
                        role="button"
                        tabIndex={0}
                        className="min-h-[44px] cursor-pointer space-y-1.5 rounded-md py-1 transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 lg:min-h-0"
                        onClick={() => setModel(m.name)}
                        onKeyDown={(e) => activateOnKey(e, () => setModel(m.name))}
                      >
                        <div className="flex items-center gap-2 text-sm" dir="ltr">
                          <span className="w-4 shrink-0 text-end tabular-nums text-[0.6875rem] text-muted-foreground/70">
                            {i + 1}
                          </span>
                          <span className="min-w-0 truncate font-mono" title={m.name}>
                            {modelDisplayName(m.name)}
                          </span>
                          <span className="ms-auto flex shrink-0 items-center gap-3 tabular-nums">
                            <span className="hidden text-[0.6875rem] text-muted-foreground sm:inline">
                              {Math.round(m.successRate)}%
                            </span>
                            <span
                              className={cn(
                                "hidden text-[0.6875rem] sm:inline",
                                m.avgImprovement != null && m.avgImprovement > 0
                                  ? "text-[var(--success)]"
                                  : "text-muted-foreground",
                              )}
                            >
                              {pointsText(m.avgImprovement)}
                            </span>
                            <span className="font-medium">{m.count}</span>
                          </span>
                        </div>
                        <ProgressBar
                          dir="ltr"
                          value={m.share}
                          color={MODEL_RAMP[Math.min(i, MODEL_RAMP.length - 1)]}
                          className="ms-6 w-auto"
                        />
                      </div>
                    ))}
                  </div>
                </AnalyticsSection>
              </StaggerItem>
            )}

            {chartData.topJobs.length > 0 && (
              <StaggerItem>
                <AnalyticsSection
                  title={
                    <HelpTip text={tip("analytics.leaderboard")}>
                      {msg("dashboard.analytics.leaderboard")}
                    </HelpTip>
                  }
                  defaultOpen={true}
                  className="border-border/60"
                >
                  <Leaderboard jobs={chartData.topJobs} onOpenJob={onOpenJob} />
                </AnalyticsSection>
              </StaggerItem>
            )}

            {(showOwners || showAccess) && (
              <StaggerItem>
                <AnalyticsSection
                  title={msg("dashboard.analytics.sharing_breakdown")}
                  defaultOpen={true}
                  className="border-border/60"
                >
                  <SharingBreakdown
                    owners={chartData.ownerUsage}
                    access={chartData.accessUsage}
                    showOwners={showOwners}
                    showAccess={showAccess}
                    sessionUser={sessionUser}
                    onOwnerSelect={setOwner}
                    onAccessSelect={setAccess}
                  />
                </AnalyticsSection>
              </StaggerItem>
            )}
          </StaggerContainer>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

export const AnalyticsTab = memo(AnalyticsTabImpl);
