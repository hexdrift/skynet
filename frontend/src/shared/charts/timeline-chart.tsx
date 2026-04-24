"use client";

/**
 * Timeline chart (jobs per day)
 * Displays number of optimization jobs completed per day
 * Preserves exact styling, RTL layout, and hover interactions
 */

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

interface TimelineChartProps {
  data: Array<{ name: string; [valueKey: string]: string | number }>;
  dates?: string[];
  onBarClick?: (date: string) => void;
}

export function TimelineChart({ data, dates, onBarClick }: TimelineChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  if (data.length === 0) return null;

  return (
    <div className="h-[160px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ left: 10, right: 5, top: 10, bottom: 20 }}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-muted" />
          <XAxis
            dataKey="name"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 9 }}
            className="fill-muted-foreground"
            label={{ value: "תאריך", position: "insideBottom", offset: -8, fontSize: 10 }}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 9 }}
            className="fill-muted-foreground"
            allowDecimals={false}
            label={{
              value: `מספר ${TERMS.optimizationPlural}`,
              angle: -90,
              position: "center",
              dx: -10,
              fontSize: 10,
            }}
          />
          <Tooltip content={<ChartTooltip />} />
          <Bar
            dataKey={TERMS.optimizationPlural}
            name={TERMS.optimizationPlural}
            fill="var(--color-chart-5)"
            radius={[3, 3, 0, 0]}
            barSize={16}
            animationDuration={300}
            cursor={onBarClick ? "pointer" : "default"}
            onClick={(_, index) => {
              if (onBarClick && dates?.[index]) onBarClick(dates[index]);
            }}
            onMouseEnter={(_, index) => setHoveredIndex(index)}
            onMouseLeave={() => setHoveredIndex(null)}
          >
            {data.map((_, i) => (
              <Cell
                key={i}
                fill={hoveredIndex === i ? "var(--color-chart-3)" : "var(--color-chart-5)"}
                style={{ transition: "fill 200ms ease" }}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
