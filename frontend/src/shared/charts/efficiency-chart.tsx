"use client";

/**
 * Efficiency chart (improvement per minute)
 * Shows optimization efficiency as improvement per minute of runtime
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

interface EfficiencyChartProps {
  data: Array<{ name: string; יעילות: number }>;
  optimizationIds?: string[];
  onBarClick?: (optimizationId: string) => void;
}

export function EfficiencyChart({ data, optimizationIds, onBarClick }: EfficiencyChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  
  if (data.length === 0) return null;
  
  return (
    <div className="h-[250px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ left: 10, right: 10, top: 10, bottom: 25 }}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-muted" />
          <XAxis
            dataKey="name"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 9, fill: "#A69585", fontFamily: "var(--font-mono, monospace)" }}
            label={{
              value: "מזהה אופטימיזציה",
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
            label={{ value: "שיפור לדקה", angle: -90, position: "center", dx: -15, fontSize: 10 }}
          />
          <Tooltip content={<ChartTooltip />} />
          <Bar
            dataKey="יעילות"
            name="שיפור לדקה"
            fill="var(--color-chart-1)"
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
                fill={hoveredIndex === i ? "var(--color-chart-2)" : "var(--color-chart-1)"}
                style={{ transition: "fill 200ms ease" }}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
