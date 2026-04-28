import { X } from "lucide-react";
import { getStatusLabel } from "@/shared/constants/job-status";
import { msg } from "@/shared/lib/messages";
import type { UseAnalyticsFiltersReturn } from "../hooks/use-analytics-filters";

export function AnalyticsFilterChips({
  filters,
}: {
  filters: Pick<
    UseAnalyticsFiltersReturn,
    | "optimizer"
    | "model"
    | "status"
    | "jobId"
    | "date"
    | "setOptimizer"
    | "setModel"
    | "setStatus"
    | "setJobId"
    | "setDate"
  >;
}) {
  const {
    optimizer,
    model,
    status,
    jobId,
    date,
    setOptimizer,
    setModel,
    setStatus,
    setJobId,
    setDate,
  } = filters;
  const hasFilters = jobId || date || optimizer !== "all" || model !== "all" || status !== "all";
  if (!hasFilters) return null;

  const clearAllFilters = () => {
    setJobId(null);
    setDate(null);
    setOptimizer("all");
    setModel("all");
    setStatus("all");
  };

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {jobId && (
        <FilterChip
          dir="ltr"
          label={`${jobId.slice(0, 8)}...`}
          ariaLabel={msg("auto.features.dashboard.components.analyticstab.literal.1")}
          onClear={() => setJobId(null)}
        />
      )}
      {date && (
        <FilterChip
          label={new Date(date).toLocaleDateString("he-IL", {
            day: "numeric",
            month: "short",
            year: "numeric",
          })}
          ariaLabel={msg("auto.features.dashboard.components.analyticstab.literal.2")}
          onClear={() => setDate(null)}
        />
      )}
      {optimizer !== "all" && (
        <FilterChip
          dir="ltr"
          label={optimizer}
          ariaLabel={msg("auto.features.dashboard.components.analyticstab.literal.3")}
          onClear={() => setOptimizer("all")}
        />
      )}
      {model !== "all" && (
        <FilterChip
          dir="ltr"
          label={model}
          title={model}
          truncate
          ariaLabel={msg("auto.features.dashboard.components.analyticstab.literal.4")}
          onClear={() => setModel("all")}
        />
      )}
      {status !== "all" && (
        <FilterChip
          label={getStatusLabel(status)}
          ariaLabel={msg("auto.features.dashboard.components.analyticstab.literal.5")}
          onClear={() => setStatus("all")}
        />
      )}
      <button
        onClick={clearAllFilters}
        className="text-[0.625rem] text-[#3D2E22]/40 hover:text-[#3D2E22]/70 transition-colors cursor-pointer ms-0.5"
      >
        {msg("auto.features.dashboard.components.analyticstab.3")}
      </button>
    </div>
  );
}

function FilterChip({
  label,
  ariaLabel,
  onClear,
  dir,
  title,
  truncate,
}: {
  label: string;
  ariaLabel: string;
  onClear: () => void;
  dir?: "ltr" | "rtl";
  title?: string;
  truncate?: boolean;
}) {
  return (
    <span className="group inline-flex items-center gap-1.5 rounded-lg bg-[#3D2E22]/[0.06] border border-[#3D2E22]/10 pe-1 ps-2.5 py-1 transition-all duration-150 hover:bg-[#3D2E22]/[0.1] hover:border-[#3D2E22]/20">
      <span
        className={`text-[0.6875rem] font-medium text-[#3D2E22]/80 ${truncate ? "font-mono truncate max-w-[140px]" : ""}`}
        dir={dir}
        title={title}
      >
        {label}
      </span>
      <button
        onClick={onClear}
        className="size-5 rounded-md flex items-center justify-center text-[#3D2E22]/40 hover:text-[#3D2E22] hover:bg-[#3D2E22]/10 transition-colors cursor-pointer"
        aria-label={ariaLabel}
      >
        <X className="size-3" />
      </button>
    </span>
  );
}
