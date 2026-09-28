"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { formatMsg, msg } from "@/shared/lib/messages";
import { useLiteMode } from "@/features/settings";
import { ChartTable } from "@/shared/charts/chart-table";
import {
  CHART_TOOLTIP_CARD_CLASS,
  CHART_TOOLTIP_ROW_CLASS,
  CHART_TOOLTIP_SWATCH_CLASS,
  CHART_TOOLTIP_TITLE_CLASS,
  CHART_TOOLTIP_VALUE_CLASS,
} from "@/shared/charts/chart-utils";
import { getActiveDir } from "@/shared/lib/runtime-locale";

function formatScore(value: unknown): string {
  return typeof value === "number" ? value.toFixed(1) : "—";
}

function ScoreChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; name: string; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className={CHART_TOOLTIP_CARD_CLASS} dir={getActiveDir()}>
      <p className={CHART_TOOLTIP_TITLE_CLASS}>
        {formatMsg("shared.score_chart.prompt_version", { label: label ?? "" })}
      </p>
      <div className="space-y-1">
        {payload.map((p, i) => (
          <div key={i} className={CHART_TOOLTIP_ROW_CLASS}>
            <span className={CHART_TOOLTIP_SWATCH_CLASS} style={{ backgroundColor: p.color }} />
            <span className="text-xs">{p.name}:</span>
            <span className={CHART_TOOLTIP_VALUE_CLASS} dir="ltr">
              {typeof p.value === "number" ? p.value.toFixed(1) : "—"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ScoreChart({
  data,
}: {
  data: Array<{ trial: number; score: number; best: number }>;
}) {
  const lite = useLiteMode();
  if (lite) {
    return (
      <ChartTable
        rows={data}
        columns={[
          { key: "trial", label: msg("shared.score_chart.prompt_version_axis") },
          {
            key: "score",
            label: msg("shared.score_chart.version_score"),
            align: "end",
            format: formatScore,
          },
          {
            key: "best",
            label: msg("shared.score_chart.best"),
            align: "end",
            format: formatScore,
          },
        ]}
      />
    );
  }
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 5, right: 10, left: 5, bottom: 18 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis
          dataKey="trial"
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 10 }}
          className="fill-muted-foreground"
          label={{
            value: msg("shared.score_chart.prompt_version_axis"),
            position: "insideBottom",
            offset: -12,
            fontSize: 10,
            fill: "var(--muted-foreground)",
          }}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 10 }}
          className="fill-muted-foreground"
          label={{
            value: msg("shared.score_chart.score_axis"),
            angle: -90,
            position: "insideLeft",
            offset: 10,
            fontSize: 10,
            fill: "var(--muted-foreground)",
          }}
          domain={[0, "auto"]}
        />
        <Tooltip content={<ScoreChartTooltip />} />
        <Line
          type="monotone"
          dataKey="score"
          name={msg("shared.score_chart.version_score")}
          stroke="var(--color-chart-4)"
          strokeWidth={1.5}
          dot={{ r: 2 }}
          isAnimationActive={false}
        />
        <Line
          type="stepAfter"
          dataKey="best"
          name={msg("shared.score_chart.best")}
          stroke="var(--color-chart-2)"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
