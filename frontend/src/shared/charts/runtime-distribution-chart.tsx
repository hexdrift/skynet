"use client";

import { useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { ChartTooltip } from "./chart-utils";
import { TERMS } from "@/shared/lib/terms";
import { formatMsg, msg } from "@/shared/lib/messages";
import { useLiteMode } from "@/features/settings";
import { ChartTable } from "@/shared/charts/chart-table";

interface RuntimeDistributionChartProps {
  data: Array<{ name: string; runtimeMinutes: number }>;
  optimizationIds?: string[];
  onBarClick?: (optimizationId: string) => void;
}

export function RuntimeDistributionChart({
  data,
  optimizationIds,
  onBarClick,
}: RuntimeDistributionChartProps) {
  const lite = useLiteMode();
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  if (data.length === 0) return null;

  if (lite) {
    return (
      <ChartTable
        rows={data}
        columns={[
          {
            key: "name",
            label: formatMsg("auto.shared.charts.runtime.distribution.chart.template.1", {
              p1: TERMS.optimization,
            }),
          },
          {
            key: "runtimeMinutes",
            label: msg("auto.shared.charts.runtime.distribution.chart.literal.2"),
            align: "end",
            format: (value) => (typeof value === "number" ? value.toFixed(1) : "—"),
          },
        ]}
        onRowClick={
          onBarClick
            ? (_, index) => {
                if (optimizationIds?.[index]) onBarClick(optimizationIds[index]);
              }
            : undefined
        }
      />
    );
  }

  return (
    <div className="h-[250px] min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ left: 10, right: 10, top: 10, bottom: 25 }}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-muted" />
          <XAxis
            dataKey="name"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 9, fill: "#A69585", fontFamily: "var(--font-mono, monospace)" }}
            label={{
              value: formatMsg("auto.shared.charts.runtime.distribution.chart.template.1", {
                p1: TERMS.optimization,
              }),
              position: "insideBottom",
              offset: -10,
              fontSize: 10,
            }}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 10 }}
            className="fill-muted-foreground"
            label={{
              value: msg("auto.shared.charts.runtime.distribution.chart.literal.1"),
              angle: -90,
              position: "center",
              dx: -15,
              fontSize: 10,
            }}
          />
          <Tooltip content={<ChartTooltip />} />
          <Bar
            dataKey="runtimeMinutes"
            name={msg("auto.shared.charts.runtime.distribution.chart.literal.2")}
            fill="var(--color-chart-3)"
            radius={[4, 4, 0, 0]}
            barSize={24}
            animationDuration={300}
            cursor={onBarClick ? "pointer" : "default"}
            onClick={(_, index) => {
              if (onBarClick && optimizationIds?.[index]) onBarClick(optimizationIds[index]);
            }}
            onMouseEnter={(_, index) => setHoveredIndex(index)}
            onMouseLeave={() => setHoveredIndex(null)}
          >
            {data.map((_, i) => (
              <Cell
                key={i}
                fill={hoveredIndex === i ? "var(--color-chart-1)" : "var(--color-chart-3)"}
                style={{ transition: "fill 200ms ease" }}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
