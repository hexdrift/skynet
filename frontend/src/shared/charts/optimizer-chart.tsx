"use client";

/**
 * Optimizer performance chart
 * Displays average improvement by optimizer type
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

interface OptimizerChartProps {
  data: Array<{ name: string; שיפור_ממוצע: number; count: number }>;
  onBarClick?: (optimizerName: string) => void;
}

export function OptimizerChart({ data, onBarClick }: OptimizerChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  return (
    <div className="h-[280px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ left: 10, right: 20, top: 20, bottom: 30 }}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-muted" />
          <XAxis
            dataKey="name"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 12 }}
            className="fill-muted-foreground"
            dy={10}
            label={{ value: TERMS.optimizer, position: "insideBottom", offset: -15, fontSize: 11 }}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11 }}
            className="fill-muted-foreground"
            dx={-5}
            label={{
              value: "שיפור ממוצע באחוזים",
              angle: -90,
              position: "center",
              dx: -20,
              fontSize: 11,
            }}
          />
          <Tooltip content={<ChartTooltip />} />
          <Bar
            dataKey="שיפור_ממוצע"
            name="שיפור ממוצע באחוזים"
            fill="var(--color-chart-2)"
            radius={[4, 4, 0, 0]}
            barSize={36}
            animationDuration={300}
            cursor={onBarClick ? "pointer" : "default"}
            onClick={(entry) => {
              if (onBarClick && entry?.name) onBarClick(String(entry.name));
            }}
            onMouseEnter={(_, index) => setHoveredIndex(index)}
            onMouseLeave={() => setHoveredIndex(null)}
          >
            {data.map((_, index) => (
              <Cell
                key={`cell-${index}`}
                fill={hoveredIndex === index ? "var(--color-chart-1)" : "var(--color-chart-2)"}
                style={{ transition: "fill 200ms ease" }}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
