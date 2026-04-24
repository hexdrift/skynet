import type { DashboardAnalytics } from "@/shared/lib/api";
import { getStatusLabel } from "@/shared/constants/job-status";
import { TERMS } from "@/shared/lib/terms";
import type { OptimizationSummaryResponse } from "@/shared/types/api";
import { STATUS_COLORS } from "../constants";

export type ChartData = {
  status: { key: string; name: string; value: number; fill: string }[];
  improvement: {
    name: string;
    ציון_משופר: number;
    ציון_התחלתי: number;
    delta: number | undefined;
  }[];
  improvementJobIds: string[];
  optimizer: { name: string; value: number }[];
  kpis: null | {
    successRate: number;
    avgImprovement: number;
    avgRuntime: number;
    totalRows: number;
    successCount: number;
    terminalCount: number;
    totalPairsRun: number;
    gridSearchCount: number;
    singleRunCount: number;
    bestImprovement: number;
  };
  avgByOptimizer: { name: string; שיפור_ממוצע: number; count: number }[];
  runtimeByOptimizer: { name: string; זמן_ממוצע: number; count: number }[];
  modelUsage: { name: string; count: number }[];
  topJobs: OptimizationSummaryResponse[];
  jobTypeData: { name: string; value: number }[];
  runtimeDistribution: { name: string; זמן_דקות: number }[];
  runtimeDistributionJobIds: string[];
  datasetVsImprovement: { שורות: number; שיפור: number; name: string }[];
  datasetVsImprovementIds: string[];
  efficiencyData: { name: string; יעילות: number }[];
  efficiencyJobIds: string[];
  timelineData: Array<{ name: string; [valueKey: string]: string | number }>;
  timelineDates: string[];
};

const EMPTY_CHART_DATA: ChartData = {
  status: [],
  improvement: [],
  improvementJobIds: [],
  optimizer: [],
  kpis: null,
  avgByOptimizer: [],
  runtimeByOptimizer: [],
  modelUsage: [],
  topJobs: [],
  jobTypeData: [],
  runtimeDistribution: [],
  runtimeDistributionJobIds: [],
  datasetVsImprovement: [],
  datasetVsImprovementIds: [],
  efficiencyData: [],
  efficiencyJobIds: [],
  timelineData: [],
  timelineDates: [],
};

// Raw metric deltas < 1 in magnitude are treated as 0-1 ratios and
// scaled to percentage; larger values pass through unchanged.
const toPct = (v: number) => (Math.abs(v) > 1 ? v : v * 100);

const shortId = (id: string) => id.slice(0, 8) + "…";

export function transformChartData(analyticsData: DashboardAnalytics | null): ChartData {
  if (!analyticsData) return EMPTY_CHART_DATA;

  const status = Object.entries(analyticsData.status_counts).map(([key, count]) => ({
    key,
    name: getStatusLabel(key),
    value: count,
    fill: STATUS_COLORS[key] ?? "var(--color-chart-5)",
  }));

  const improvement = analyticsData.top_improvement.map((j) => {
    const opt = j.optimized_test_metric ?? 0;
    const bl = j.baseline_test_metric ?? 0;
    return {
      name: shortId(j.optimization_id),
      ציון_משופר: Math.round(opt > 1 ? opt : opt * 100),
      ציון_התחלתי: Math.round(bl > 1 ? bl : bl * 100),
      delta: j.metric_improvement != null ? toPct(j.metric_improvement) : undefined,
    };
  });
  const improvementJobIds = analyticsData.top_improvement.map((j) => j.optimization_id);

  const optimizer = Object.entries(analyticsData.optimizer_counts).map(([name, value]) => ({
    name,
    value,
  }));

  const kpis = {
    successRate: analyticsData.success_rate * 100,
    avgImprovement:
      analyticsData.avg_improvement != null ? toPct(analyticsData.avg_improvement) : 0,
    avgRuntime: analyticsData.avg_runtime_seconds ?? 0,
    totalRows: analyticsData.total_dataset_rows,
    successCount: analyticsData.success_count,
    terminalCount: analyticsData.terminal_count,
    totalPairsRun: analyticsData.total_pairs_run,
    gridSearchCount: analyticsData.grid_search_count,
    singleRunCount: analyticsData.single_run_count,
    bestImprovement:
      analyticsData.best_improvement != null ? toPct(analyticsData.best_improvement) : 0,
  };

  const avgByOptimizer = analyticsData.improvement_by_optimizer.map((o) => ({
    name: o.name,
    שיפור_ממוצע: +toPct(o.average).toFixed(1),
    count: o.count,
  }));

  const runtimeByOptimizer = analyticsData.runtime_minutes_by_optimizer.map((o) => ({
    name: o.name,
    זמן_ממוצע: o.average,
    count: o.count,
  }));

  const modelUsage = analyticsData.model_usage.map((m) => ({
    name: m.name,
    count: m.value,
  }));

  const topJobs = analyticsData.top_jobs_by_improvement as unknown as OptimizationSummaryResponse[];

  const jobTypeData = Object.entries(analyticsData.job_type_counts).map(([key, value]) => ({
    name: key === "grid_search" ? "סריקה" : "ריצה",
    value,
  }));

  const runtimeDistribution = analyticsData.runtime_distribution.map((j) => ({
    name: shortId(j.optimization_id),
    זמן_דקות: +((j.elapsed_seconds ?? 0) / 60).toFixed(1),
  }));
  const runtimeDistributionJobIds = analyticsData.runtime_distribution.map(
    (j) => j.optimization_id,
  );

  const datasetVsImprovement = analyticsData.dataset_vs_improvement.map((j) => ({
    שורות: j.dataset_rows ?? 0,
    שיפור: +toPct(j.metric_improvement ?? 0).toFixed(1),
    name: shortId(j.optimization_id),
  }));
  const datasetVsImprovementIds = analyticsData.dataset_vs_improvement.map(
    (j) => j.optimization_id,
  );

  const efficiencyData = analyticsData.efficiency.map((j) => {
    const delta = j.metric_improvement ?? 0;
    const elapsed = j.elapsed_seconds ?? 0;
    const יעילות = elapsed > 0 ? +((toPct(delta) / elapsed) * 60).toFixed(2) : 0;
    return { name: shortId(j.optimization_id), יעילות };
  });
  const efficiencyJobIds = analyticsData.efficiency.map((j) => j.optimization_id);

  const timelineData = analyticsData.timeline.map((t) => ({
    name: new Date(t.date).toLocaleDateString("he-IL", {
      day: "numeric",
      month: "short",
    }),
    [TERMS.optimizationPlural]: t.count,
  }));
  const timelineDates = analyticsData.timeline.map((t) => t.date);

  return {
    status,
    improvement,
    improvementJobIds,
    optimizer,
    kpis,
    avgByOptimizer,
    runtimeByOptimizer,
    modelUsage,
    topJobs,
    jobTypeData,
    runtimeDistribution,
    runtimeDistributionJobIds,
    datasetVsImprovement,
    datasetVsImprovementIds,
    efficiencyData,
    efficiencyJobIds,
    timelineData,
    timelineDates,
  };
}
