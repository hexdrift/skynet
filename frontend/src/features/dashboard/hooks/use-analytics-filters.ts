import { useCallback, useMemo, useState } from "react";

export type AnalyticsRange = "7d" | "30d" | "90d" | "all";

/**
 * One histogram bar echoed back as a filter: the backend's `[lower, upper)`
 * edges (null = open end) plus the bar's axis label for the filter chip.
 */
export type AnalyticsBucket = {
  lower: number | null;
  upper: number | null;
  label: string;
};

type AnalyticsFilters = {
  range: AnalyticsRange;
  optimizer: string;
  model: string;
  status: string;
  date: string | null;
  /** Inclusive end of a `date`-anchored range (timeline week/month buckets). */
  dateTo: string | null;
  owner: string | null;
  access: string | null;
  jobType: string | null;
  module: string | null;
  improvement: AnalyticsBucket | null;
  runtime: AnalyticsBucket | null;
  dataset: AnalyticsBucket | null;
};

export type UseAnalyticsFiltersReturn = AnalyticsFilters & {
  setRange: (v: AnalyticsRange) => void;
  setOptimizer: (v: string) => void;
  setModel: (v: string) => void;
  setStatus: (v: string) => void;
  setDate: (v: string | null) => void;
  setDateRange: (from: string | null, to: string | null) => void;
  setOwner: (v: string | null) => void;
  setAccess: (v: string | null) => void;
  setJobType: (v: string | null) => void;
  setModule: (v: string | null) => void;
  setImprovement: (v: AnalyticsBucket | null) => void;
  setRuntime: (v: AnalyticsBucket | null) => void;
  setDataset: (v: AnalyticsBucket | null) => void;
  /** True when any filter narrows the dashboard beyond the full history. */
  hasFilters: boolean;
  clearAll: () => void;
  /** Stable identity of the active filter set, for remount/animation keys. */
  key: string;
};

export function useAnalyticsFilters(): UseAnalyticsFiltersReturn {
  const [range, setRange] = useState<AnalyticsRange>("all");
  const [optimizer, setOptimizer] = useState<string>("all");
  const [model, setModel] = useState<string>("all");
  const [status, setStatus] = useState<string>("all");
  const [date, setDateOnly] = useState<string | null>(null);
  const [dateTo, setDateTo] = useState<string | null>(null);
  const [owner, setOwner] = useState<string | null>(null);
  const [access, setAccess] = useState<string | null>(null);
  const [jobType, setJobType] = useState<string | null>(null);
  const [module, setModule] = useState<string | null>(null);
  const [improvement, setImprovement] = useState<AnalyticsBucket | null>(null);
  const [runtime, setRuntime] = useState<AnalyticsBucket | null>(null);
  const [dataset, setDataset] = useState<AnalyticsBucket | null>(null);

  const setDate = useCallback((v: string | null) => {
    setDateOnly(v);
    setDateTo(null);
  }, []);

  const setDateRange = useCallback((from: string | null, to: string | null) => {
    setDateOnly(from);
    setDateTo(from ? to : null);
  }, []);

  const clearAll = useCallback(() => {
    setRange("all");
    setOptimizer("all");
    setModel("all");
    setStatus("all");
    setDateOnly(null);
    setDateTo(null);
    setOwner(null);
    setAccess(null);
    setJobType(null);
    setModule(null);
    setImprovement(null);
    setRuntime(null);
    setDataset(null);
  }, []);

  const hasFilters =
    range !== "all" ||
    optimizer !== "all" ||
    model !== "all" ||
    status !== "all" ||
    date != null ||
    owner != null ||
    access != null ||
    jobType != null ||
    module != null ||
    improvement != null ||
    runtime != null ||
    dataset != null;

  const key = useMemo(
    () =>
      [
        range,
        optimizer,
        model,
        status,
        date ?? "",
        dateTo ?? "",
        owner ?? "",
        access ?? "",
        jobType ?? "",
        module ?? "",
        improvement?.label ?? "",
        runtime?.label ?? "",
        dataset?.label ?? "",
      ].join("|"),
    [range, optimizer, model, status, date, dateTo, owner, access, jobType, module, improvement, runtime, dataset],
  );

  return {
    range,
    optimizer,
    model,
    status,
    date,
    dateTo,
    owner,
    access,
    jobType,
    module,
    improvement,
    runtime,
    dataset,
    setRange,
    setOptimizer,
    setModel,
    setStatus,
    setDate,
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
    key,
  };
}
