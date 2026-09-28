import { FunnelX, X } from "@/shared/ui/icons";
import { Button } from "@/shared/ui/primitives/button";
import { TooltipButton } from "@/shared/ui/tooltip-button";
import { getStatusLabel } from "@/shared/constants/job-status";
import { modelDisplayName, moduleLabel } from "@/shared/lib/formatters";
import { msg } from "@/shared/lib/messages";
import { getActiveIntlLocale } from "@/shared/lib/runtime-locale";
import { TERMS } from "@/shared/lib/terms";
import { jobTypeLabel } from "../lib/transform-chart-data";
import type { UseAnalyticsFiltersReturn } from "../hooks/use-analytics-filters";

export function AnalyticsFilterChips({
  filters,
  sessionUser,
}: {
  filters: UseAnalyticsFiltersReturn;
  sessionUser: string;
}) {
  const {
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
    setOwner,
    setAccess,
    setJobType,
    setModule,
    setImprovement,
    setRuntime,
    setDataset,
    hasFilters,
    clearAll,
  } = filters;
  if (!hasFilters) return null;

  const locale = getActiveIntlLocale();
  const dateFormat: Intl.DateTimeFormatOptions = {
    day: "numeric",
    month: "short",
    year: "numeric",
  };
  const dateLabel = date
    ? dateTo && dateTo !== date
      ? new Intl.DateTimeFormat(locale, dateFormat).formatRange(new Date(date), new Date(dateTo))
      : new Date(date).toLocaleDateString(locale, dateFormat)
    : "";
  const bucketClearLabel = msg("auto.features.dashboard.components.analyticstab.literal.2");
  const clearAllLabel = msg("auto.features.dashboard.components.analyticstab.3");

  const ownerIsMe = Boolean(owner) && owner!.toLowerCase() === sessionUser.toLowerCase();
  const accessLabels: Record<string, string> = {
    mine: msg("dashboard.role.mine"),
    owner: msg("dashboard.role_short.owner"),
    editor: msg("dashboard.role_short.editor"),
    viewer: msg("dashboard.role_short.viewer"),
  };

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {access && (
        <FilterChip
          label={accessLabels[access] ?? access}
          ariaLabel={msg("dashboard.analytics.access_filter_clear")}
          onClear={() => setAccess(null)}
        />
      )}
      {owner && (
        <FilterChip
          dir={ownerIsMe ? undefined : "ltr"}
          label={ownerIsMe ? msg("dashboard.owner.me") : owner}
          title={owner}
          truncate={!ownerIsMe}
          ariaLabel={msg("dashboard.analytics.owner_filter_clear")}
          onClear={() => setOwner(null)}
        />
      )}
      {range !== "all" && (
        <FilterChip
          label={msg(`usage.range.${range}`)}
          ariaLabel={msg("dashboard.analytics.range_filter_clear")}
          onClear={() => setRange("all")}
        />
      )}
      {optimizer !== "all" && (
        <FilterChip
          dir="ltr"
          label={optimizer}
          ariaLabel={msg("dashboard.analytics.optimizer_filter_clear")}
          onClear={() => setOptimizer("all")}
        />
      )}
      {date && (
        <FilterChip label={dateLabel} ariaLabel={bucketClearLabel} onClear={() => setDate(null)} />
      )}
      {jobType && (
        <FilterChip
          label={jobTypeLabel(jobType)}
          ariaLabel={bucketClearLabel}
          onClear={() => setJobType(null)}
        />
      )}
      {module && (
        <FilterChip
          label={moduleLabel(module)}
          title={module}
          truncate
          ariaLabel={bucketClearLabel}
          onClear={() => setModule(null)}
        />
      )}
      {improvement && (
        <FilterChip
          dir="ltr"
          label={`${improvement.label} ${msg("dashboard.analytics.axis_points")}`}
          ariaLabel={bucketClearLabel}
          onClear={() => setImprovement(null)}
        />
      )}
      {runtime && (
        <FilterChip
          dir="ltr"
          label={`${runtime.label} ${msg("dashboard.analytics.axis_minutes")}`}
          ariaLabel={bucketClearLabel}
          onClear={() => setRuntime(null)}
        />
      )}
      {dataset && (
        <FilterChip
          dir="ltr"
          label={`${dataset.label} ${TERMS.rowPlural}`}
          ariaLabel={bucketClearLabel}
          onClear={() => setDataset(null)}
        />
      )}
      {model !== "all" && (
        <FilterChip
          dir="ltr"
          label={modelDisplayName(model)}
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
      <TooltipButton tooltip={clearAllLabel}>
        <Button
          variant="ghost"
          size="icon-sm"
          type="button"
          onClick={clearAll}
          className="ms-0.5"
          aria-label={clearAllLabel}
        >
          <FunnelX className="size-4" aria-hidden="true" />
        </Button>
      </TooltipButton>
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
    <span className="group inline-flex items-center gap-1.5 rounded-lg border border-[#3D2E22]/10 bg-[#3D2E22]/[0.06] pe-1 ps-2.5 py-1 transition-all duration-150 hover:border-[#3D2E22]/20 hover:bg-[#3D2E22]/[0.1]">
      <span
        className={`text-[0.6875rem] font-medium text-[#3D2E22]/80 ${truncate ? "font-mono truncate max-w-[140px]" : ""}`}
        dir={dir}
        title={title}
      >
        {label}
      </span>
      <button
        type="button"
        onClick={onClear}
        className="close-button [--close-btn-size:20px] [--close-btn-radius:6px] [--close-btn-icon:12px]"
        aria-label={ariaLabel}
      >
        <X />
      </button>
    </span>
  );
}
