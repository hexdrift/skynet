"use client";

import { ChartBar } from "@/shared/ui/icons";

import { msg } from "@/shared/lib/messages";
import { EmptyState } from "@/shared/ui/empty-state";
import { getActiveDir } from "@/shared/lib/runtime-locale";

// Shared Recharts tooltip chrome, reused by the bespoke tooltips that need their own row content.
export const CHART_TOOLTIP_CARD_CLASS =
  "rounded-xl border border-border/60 bg-background/95 p-3 text-sm shadow-lg backdrop-blur-sm";
export const CHART_TOOLTIP_TITLE_CLASS = "mb-2 font-semibold text-foreground";
export const CHART_TOOLTIP_ROW_CLASS = "flex items-center gap-2 text-muted-foreground";
export const CHART_TOOLTIP_SWATCH_CLASS = "size-2.5 shrink-0 rounded-full ring-1 ring-black/5";
export const CHART_TOOLTIP_VALUE_CLASS =
  "ms-auto font-mono font-semibold tabular-nums text-foreground";

export function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; name: string; color?: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className={CHART_TOOLTIP_CARD_CLASS} dir={getActiveDir()}>
      {label && <p className={CHART_TOOLTIP_TITLE_CLASS}>{label}</p>}
      <div className="space-y-1">
        {payload.map((p, i) => (
          <div key={i} className={CHART_TOOLTIP_ROW_CLASS}>
            {p.color && (
              <span className={CHART_TOOLTIP_SWATCH_CLASS} style={{ backgroundColor: p.color }} />
            )}
            <span className="text-xs">{p.name}:</span>
            <span className={CHART_TOOLTIP_VALUE_CLASS} dir="ltr">
              {p.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ChartEmptyState({ message }: { message?: string }) {
  return (
    <EmptyState
      variant="list"
      icon={ChartBar}
      title={message ?? msg("auto.shared.charts.chart.utils.literal.1")}
      className="h-[300px] justify-center"
    />
  );
}
