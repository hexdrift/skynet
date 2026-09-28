import type {
  DashboardAnalytics,
  DashboardAnalyticsGranularity,
  DashboardAnalyticsJob,
  DashboardAnalyticsRangeBucket,
} from "@/shared/lib/api";
import { getStatusLabel } from "@/shared/constants/job-status";
import { msg } from "@/shared/lib/messages";
import { getActiveIntlLocale } from "@/shared/lib/runtime-locale";
import { STATUS_COLORS } from "../constants";

export type ShareBar = { key: string; name: string; value: number; pct: number };

export type HistogramBar = {
  label: string;
  count: number;
  avgImprovement: number | null;
  /** Backend `[lower, upper)` edges (null = open end) so a bar can become a filter. */
  lower: number | null;
  upper: number | null;
};

export type OptimizerRow = {
  name: string;
  count: number;
  successRate: number;
  avgImprovement: number | null;
  avgRuntimeMinutes: number | null;
  share: number;
};

export type ModelRow = {
  name: string;
  count: number;
  successRate: number;
  avgImprovement: number | null;
  share: number;
};

export type TimelinePoint = {
  date: string;
  label: string;
  success: number;
  failed: number;
  other: number;
  total: number;
};

export type ChartData = {
  kpis: null | {
    total: number;
    successRate: number;
    successCount: number;
    terminalCount: number;
    runningCount: number;
    avgImprovement: number | null;
    medianImprovement: number | null;
    bestImprovement: number | null;
    avgRuntimeSeconds: number | null;
    totalRows: number;
  };
  status: ShareBar[];
  jobTypes: ShareBar[];
  modules: ShareBar[];
  optimizerStats: OptimizerRow[];
  modelStats: ModelRow[];
  ownerUsage: Array<{ name: string; count: number }>;
  accessUsage: Array<{ name: string; count: number }>;
  improvementHistogram: HistogramBar[];
  runtimeHistogram: HistogramBar[];
  datasetBuckets: HistogramBar[];
  timeline: TimelinePoint[];
  timelineGranularity: DashboardAnalyticsGranularity;
  topJobs: DashboardAnalyticsJob[];
  truncated: boolean;
};

const EMPTY_CHART_DATA: ChartData = {
  kpis: null,
  status: [],
  jobTypes: [],
  modules: [],
  optimizerStats: [],
  modelStats: [],
  ownerUsage: [],
  accessUsage: [],
  improvementHistogram: [],
  runtimeHistogram: [],
  datasetBuckets: [],
  timeline: [],
  timelineGranularity: "day",
  topJobs: [],
  truncated: false,
};

function shareBars(counts: Record<string, number>, label: (key: string) => string): ShareBar[] {
  const entries = Object.entries(counts);
  const total = entries.reduce((sum, [, value]) => sum + value, 0);
  return entries
    .map(([key, value]) => ({
      key,
      name: label(key),
      value,
      pct: total > 0 ? (value / total) * 100 : 0,
    }))
    .sort((a, b) => b.value - a.value);
}

export function jobTypeLabel(key: string): string {
  switch (key) {
    case "grid_search":
      return msg("auto.features.dashboard.lib.transform.chart.data.literal.1");
    case "workflow":
      return msg("dashboard.analytics.type_workflow");
    default:
      return msg("auto.features.dashboard.lib.transform.chart.data.literal.2");
  }
}

/**
 * Turn `[lower, upper)` edges into a compact axis label: "<5", "5–10", "30+".
 * Open ends come from the backend as `null`.
 */
function bucketLabel(bucket: DashboardAnalyticsRangeBucket, fmt: Intl.NumberFormat): string {
  if (bucket.lower == null && bucket.upper == null) return "—";
  if (bucket.lower == null) return `<${fmt.format(bucket.upper!)}`;
  if (bucket.upper == null) return `${fmt.format(bucket.lower)}+`;
  return `${fmt.format(bucket.lower)}–${fmt.format(bucket.upper)}`;
}

function histogram(buckets: DashboardAnalyticsRangeBucket[], fmt: Intl.NumberFormat): HistogramBar[] {
  // An all-zero histogram means no run had the measurement at all (e.g. no
  // successful run yet); the chart renders its empty state instead of flat bars.
  if (buckets.every((b) => b.count === 0)) return [];
  return buckets.map((b) => ({
    label: bucketLabel(b, fmt),
    count: b.count,
    avgImprovement: b.avg_improvement,
    lower: b.lower,
    upper: b.upper,
  }));
}

function timelineLabel(date: string, granularity: DashboardAnalyticsGranularity, locale: string) {
  // Bucket dates are calendar days; parsing at UTC midnight keeps the label
  // on that day regardless of the viewer's timezone.
  const d = new Date(`${date}T00:00:00Z`);
  if (granularity === "month") {
    return d.toLocaleDateString(locale, { month: "short", year: "2-digit", timeZone: "UTC" });
  }
  return d.toLocaleDateString(locale, { day: "numeric", month: "short", timeZone: "UTC" });
}

export function transformChartData(analyticsData: DashboardAnalytics | null): ChartData {
  if (!analyticsData) return EMPTY_CHART_DATA;

  const locale = getActiveIntlLocale();
  const fmt = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });

  const kpis = {
    total: analyticsData.filtered_total,
    successRate: analyticsData.success_rate * 100,
    successCount: analyticsData.success_count,
    terminalCount: analyticsData.terminal_count,
    runningCount: analyticsData.running_count,
    avgImprovement: analyticsData.avg_improvement,
    medianImprovement: analyticsData.median_improvement,
    bestImprovement: analyticsData.best_improvement,
    avgRuntimeSeconds: analyticsData.avg_runtime_seconds,
    totalRows: analyticsData.total_dataset_rows,
  };

  const status = Object.entries(analyticsData.status_counts)
    .map(([key, value]) => ({ key, value }))
    .sort((a, b) => b.value - a.value)
    .map(({ key, value }) => ({
      key,
      name: getStatusLabel(key),
      value,
      pct: kpis.total > 0 ? (value / kpis.total) * 100 : 0,
    }));

  const maxOptimizer = analyticsData.optimizer_stats[0]?.count ?? 0;
  const optimizerStats = analyticsData.optimizer_stats.map((o) => ({
    name: o.name,
    count: o.count,
    successRate: o.success_rate * 100,
    avgImprovement: o.avg_improvement,
    avgRuntimeMinutes: o.avg_runtime_minutes,
    share: maxOptimizer > 0 ? (o.count / maxOptimizer) * 100 : 0,
  }));

  const maxModel = analyticsData.model_stats[0]?.count ?? 0;
  const modelStats = analyticsData.model_stats.map((m) => ({
    name: m.name,
    count: m.count,
    successRate: m.success_rate * 100,
    avgImprovement: m.avg_improvement,
    share: maxModel > 0 ? (m.count / maxModel) * 100 : 0,
  }));

  const timeline = analyticsData.timeline.map((t) => ({
    date: t.date,
    label: timelineLabel(t.date, analyticsData.timeline_granularity, locale),
    success: t.success_count,
    failed: t.failed_count,
    other: Math.max(0, t.count - t.success_count - t.failed_count),
    total: t.count,
  }));

  return {
    kpis,
    status,
    jobTypes: shareBars(analyticsData.job_type_counts, jobTypeLabel),
    modules: shareBars(analyticsData.module_counts, (key) => key),
    optimizerStats,
    modelStats,
    ownerUsage: analyticsData.owner_usage.map((o) => ({ name: o.name, count: o.value })),
    accessUsage: analyticsData.access_usage.map((a) => ({ name: a.name, count: a.value })),
    improvementHistogram: histogram(analyticsData.improvement_histogram, fmt),
    runtimeHistogram: histogram(analyticsData.runtime_histogram, fmt),
    datasetBuckets: histogram(analyticsData.dataset_size_buckets, fmt),
    timeline,
    timelineGranularity: analyticsData.timeline_granularity,
    topJobs: analyticsData.top_jobs_by_improvement,
    truncated: analyticsData.truncated,
  };
}

