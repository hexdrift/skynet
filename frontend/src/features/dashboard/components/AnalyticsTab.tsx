import { memo, useMemo } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { toast } from "react-toastify";
import dynamic from "next/dynamic";
import { AnimatePresence, motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { AnimatedNumber, StaggerContainer, StaggerItem } from "@/shared/ui/motion";
import { HelpTip } from "@/shared/ui/help-tip";
import { formatElapsed } from "@/shared/lib";
import type { DashboardAnalytics } from "@/shared/lib/api";
import { msg } from "@/shared/lib/messages";
import { tip } from "@/shared/lib/tooltips";
import { TERMS } from "@/shared/lib/terms";
import { AnalyticsEmpty } from "./AnalyticsEmpty";
import { AnalyticsFilterChips } from "./AnalyticsFilterChips";
import { AnalyticsSection } from "./AnalyticsSection";
import type { ChartData } from "../lib/transform-chart-data";
import type { UseAnalyticsFiltersReturn } from "../hooks/use-analytics-filters";

const ScoresChart = dynamic(() => import("@/shared/charts").then((m) => m.ScoresChart), {
  ssr: false,
  loading: () => (
    <div className="h-[300px] flex items-center justify-center">
      <span className="text-sm text-muted-foreground">
        {msg("auto.features.dashboard.components.analyticstab.1")}
      </span>
    </div>
  ),
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

type KpiAccent = "default" | "success" | "warning" | "danger";

const KPI_DOT: Record<KpiAccent, string> = {
  default: "bg-foreground/25",
  success: "bg-emerald-500",
  warning: "bg-[var(--warning)]",
  danger: "bg-red-500",
};

const KPI_TEXT: Record<KpiAccent, string> = {
  default: "text-foreground",
  success: "text-emerald-600",
  warning: "text-[var(--warning)]",
  danger: "text-red-600",
};

function KpiCard({
  label,
  value,
  accent,
  valueDir,
}: {
  label: string;
  value: ReactNode;
  accent: KpiAccent;
  valueDir?: "ltr" | "rtl";
}) {
  return (
    <div className="flex h-full flex-col gap-5 rounded-2xl border border-border/40 bg-card/60 p-6 transition-colors duration-300 hover:border-border/70 sm:p-7">
      <div className="flex items-center gap-2">
        <span className={`size-1.5 rounded-full ${KPI_DOT[accent]}`} aria-hidden />
        <p className="text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground/70">
          {label}
        </p>
      </div>
      <div className="flex flex-1 items-center justify-center">
        <p
          dir={valueDir}
          className={`text-center text-[2.75rem] sm:text-[3.25rem] font-bold leading-[0.9] tracking-tight tabular-nums ${KPI_TEXT[accent]}`}
        >
          {value}
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

function fmtPct(n: number | undefined | null): string {
  if (n == null) return "—";
  return `${(n > 1 ? n : n * 100).toFixed(1)}%`;
}

function toPctScale(n: number): number {
  return Math.abs(n) > 1 ? n : n * 100;
}

function copyToClipboard(text: string) {
  void navigator.clipboard
    .writeText(text)
    .then(() => toast.success(msg("clipboard.copied_short"), { autoClose: 1000 }))
    .catch(() => {});
}

function AnalyticsTabImpl({
  analyticsLoading,
  analyticsData,
  chartData,
  filters,
}: AnalyticsTabProps) {
  const {
    model,
    status,
    jobId,
    date,
    leaderboardLimit,
    setModel,
    setStatus,
    setJobId,
    setDate,
  } = filters;

  const statusBars = useMemo(() => {
    const total = chartData.status.reduce((a, b) => a + b.value, 0);
    return chartData.status.map((s) => ({
      ...s,
      pct: total > 0 ? (s.value / total) * 100 : 0,
    }));
  }, [chartData.status]);

  const jobTypeBars = useMemo(() => {
    const total = chartData.jobTypeData.reduce((a, b) => a + b.value, 0);
    return chartData.jobTypeData.map((d) => ({
      ...d,
      pct: total > 0 ? (d.value / total) * 100 : 0,
    }));
  }, [chartData.jobTypeData]);

  const modelUsageBars = useMemo(() => {
    const maxCount = chartData.modelUsage[0]?.count ?? 1;
    return chartData.modelUsage.map((m) => ({
      ...m,
      pct: maxCount > 0 ? (m.count / maxCount) * 100 : 0,
    }));
  }, [chartData.modelUsage]);

  if (analyticsLoading && analyticsData === null) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-24">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          {msg("auto.features.dashboard.components.analyticstab.2")}
        </p>
      </div>
    );
  }

  if ((analyticsData?.filtered_total ?? 0) === 0) {
    const hasFilters = Boolean(jobId || date || model !== "all" || status !== "all");
    if (hasFilters) {
      return (
        <AnalyticsEmpty
          variant="no-results"
          onClearFilters={() => {
            setModel("all");
            setStatus("all");
          }}
        />
      );
    }
    return <AnalyticsEmpty variant="no-data" />;
  }

  return (
    <div className="space-y-6">
      <AnalyticsFilterChips filters={filters} />

      <AnimatePresence mode="wait">
        <motion.div
          key={`${jobId ?? "all"}-${date ?? "all"}-${model}-${status}`}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.3, ease: [0.2, 0.8, 0.2, 1] }}
        >
          <StaggerContainer className="space-y-6" staggerDelay={0.03}>
            {chartData.kpis && (
              <StaggerItem>
                <div
                  data-tutorial="dashboard-stats"
                  className="grid gap-3 sm:gap-4"
                  style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(200px, 100%), 1fr))" }}
                >
                  <KpiCard
                    label={msg("auto.features.dashboard.components.analyticstab.4")}
                    accent="default"
                    value={
                      <AnimatedNumber
                        value={Math.round(chartData.kpis.successRate)}
                        suffix="%"
                      />
                    }
                  />
                  <KpiCard
                    label={msg("auto.features.dashboard.components.analyticstab.8")}
                    accent={
                      chartData.kpis.avgImprovement > 0
                        ? "success"
                        : chartData.kpis.avgImprovement < 0
                          ? "danger"
                          : "default"
                    }
                    value={
                      <AnimatedNumber
                        value={parseFloat(chartData.kpis.avgImprovement.toFixed(1))}
                        decimals={1}
                        prefix={chartData.kpis.avgImprovement >= 0 ? "+" : ""}
                        suffix="%"
                      />
                    }
                  />
                  <KpiCard
                    label={msg("auto.features.dashboard.components.analyticstab.11")}
                    accent="default"
                    valueDir="ltr"
                    value={formatElapsed(chartData.kpis.avgRuntime)}
                  />
                  <KpiCard
                    label={msg("auto.features.dashboard.components.analyticstab.15")}
                    accent="warning"
                    value={
                      <AnimatedNumber
                        value={parseFloat(chartData.kpis.bestImprovement.toFixed(1))}
                        decimals={1}
                        prefix="+"
                        suffix="%"
                      />
                    }
                  />
                </div>
              </StaggerItem>
            )}

            <StaggerItem>
              <AnalyticsSection
                title={
                  <HelpTip text={tip("analytics.score_comparison")}>
                    {msg("auto.features.dashboard.components.analyticstab.20")}
                  </HelpTip>
                }
                defaultOpen={true}
                className="border-border/60"
              >
                <div className="grid gap-5 lg:grid-cols-7">
                  <div className="lg:col-span-4">
                    <div className="mb-3">
                      <h4 className="text-sm font-semibold">
                        {msg("auto.features.dashboard.components.analyticstab.21")}
                        {TERMS.optimization}
                      </h4>
                    </div>
                    <ScoresChart
                      data={chartData.improvement}
                      optimizationIds={chartData.improvementJobIds}
                      onBarClick={(optimizationId) => setJobId(optimizationId)}
                    />
                  </div>

                  <div className="lg:col-span-3 space-y-6">
                    <div className="space-y-3">
                      <p className="text-[0.6875rem] font-semibold text-muted-foreground uppercase tracking-widest">
                        {msg("auto.features.dashboard.components.analyticstab.22")}
                      </p>
                      {statusBars.map((s) => (
                        <div
                          key={s.key}
                          role="button"
                          tabIndex={0}
                          className="space-y-1.5 cursor-pointer hover:opacity-80 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 rounded-md"
                          onClick={() => setStatus(s.key)}
                          onKeyDown={(e) => activateOnKey(e, () => setStatus(s.key))}
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
                                width: `${s.pct}%`,
                                backgroundColor: s.fill,
                              }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>

                    {chartData.jobTypeData.length > 0 && (
                      <>
                        <div className="border-t border-border" />
                        <div className="space-y-3">
                          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                            {msg("auto.features.dashboard.components.analyticstab.24")}
                            {TERMS.optimization}
                          </p>
                          {jobTypeBars.map((d) => (
                            <div key={d.name} className="space-y-1">
                              <div className="flex items-center justify-between text-sm">
                                <span>{d.name}</span>
                                <span className="tabular-nums font-medium">{d.value}</span>
                              </div>
                              <div className="h-2 rounded-full bg-muted overflow-hidden">
                                <div
                                  className="h-full rounded-full bg-primary/70 transition-all"
                                  style={{
                                    width: `${d.pct}%`,
                                  }}
                                />
                              </div>
                            </div>
                          ))}
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
                    <HelpTip text={tip("analytics.runtime_vs_gain")}>
                      {msg("auto.features.dashboard.components.analyticstab.25")}
                    </HelpTip>
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
                              {msg("auto.features.dashboard.components.analyticstab.26")}
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
                              {msg("auto.features.dashboard.components.analyticstab.27")}
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
                            {msg("auto.features.dashboard.components.analyticstab.28")}
                            {TERMS.dataset}
                            {msg("auto.features.dashboard.components.analyticstab.29")}
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
                  title={
                    <HelpTip text={tip("analytics.submissions_per_day")}>
                      {msg("auto.features.dashboard.components.analyticstab.30")}
                    </HelpTip>
                  }
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

            {chartData.modelUsage.length > 0 && (
              <StaggerItem>
                <AnalyticsSection
                  title={msg("auto.features.dashboard.components.analyticstab.33")}
                  defaultOpen={true}
                  className="border-border/60"
                >
                  <div className="space-y-3">
                    {modelUsageBars.map((m) => (
                      <div
                        key={m.name}
                        role="button"
                        tabIndex={0}
                        className="space-y-1.5 cursor-pointer hover:opacity-80 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 rounded-md"
                        onClick={() => setModel(m.name)}
                        onKeyDown={(e) => activateOnKey(e, () => setModel(m.name))}
                      >
                        <div className="flex items-center justify-between text-sm" dir="ltr">
                          <span className="font-mono truncate max-w-[200px]" title={m.name}>
                            {m.name}
                          </span>
                          <span className="tabular-nums font-medium">{m.count}</span>
                        </div>
                        <div className="h-2 rounded-full bg-muted overflow-hidden" dir="ltr">
                          <div
                            className="h-full rounded-full bg-primary/60 transition-all"
                            style={{
                              width: `${m.pct}%`,
                            }}
                          />
                        </div>
                      </div>
                    ))}
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

export const AnalyticsTab = memo(AnalyticsTabImpl);
