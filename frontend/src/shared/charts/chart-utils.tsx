"use client";

/**
 * Shared chart utilities
 * Common tooltip and formatting functions for Recharts components
 * Preserves exact RTL layout and Hebrew text
 */

/* ── Chart colors ── */
export const chartColors = {
  primary: "var(--color-chart-1)",
  secondary: "var(--color-chart-2)",
  tertiary: "var(--color-chart-3)",
  quaternary: "var(--color-chart-4)",
  quinary: "var(--color-chart-5)",
};

/* ── Shared chart tooltip ── */
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
    <div
      className="rounded-xl border border-border/60 bg-background/95 backdrop-blur-sm p-3 shadow-lg text-sm"
      dir="rtl"
    >
      {label && <p className="font-semibold mb-2 text-foreground">{label}</p>}
      <div className="space-y-1">
        {payload.map((p, i) => (
          <div key={i} className="flex items-center gap-2 text-muted-foreground">
            {p.color && (
              <span
                className="size-2.5 rounded-full shrink-0 ring-1 ring-black/5"
                style={{ backgroundColor: p.color }}
              />
            )}
            <span className="text-xs">{p.name}:</span>
            <span
              className="font-mono font-semibold text-foreground ms-auto tabular-nums"
              dir="ltr"
            >
              {p.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Format axis labels ── */
export const formatAxisLabel = {
  percent: (value: number) => `${value}%`,
  minutes: (value: number) => `${value}m`,
  count: (value: number) => value.toString(),
};

/* ── Empty state ── */
export function ChartEmptyState({ message }: { message?: string }) {
  return (
    <div className="flex h-[300px] items-center justify-center">
      <p className="text-sm text-muted-foreground">{message ?? "אין עדיין נתונים"}</p>
    </div>
  );
}
