"use client";

/**
 * Scores comparison chart
 * Displays baseline vs optimized scores for multiple jobs
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
import { ChartTooltip, ChartEmptyState } from "./chart-utils";

interface ScoresChartProps {
  data: Array<{ name: string; ציון_התחלתי: number; ציון_משופר: number; delta?: number }>;
  optimizationIds?: string[];
  onBarClick?: (optimizationId: string) => void;
}

export function ScoresChart({ data, optimizationIds, onBarClick }: ScoresChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  if (data.length === 0) {
    return <ChartEmptyState message="אין עדיין אופטימיזציות שהושלמו" />;
  }

  const handleClick = (index: number) => {
    if (onBarClick && optimizationIds?.[index]) onBarClick(optimizationIds[index]);
  };

  return (
    <>
      <div className="h-[300px] relative group">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ left: 0, right: 20, top: 20, bottom: 10 }}
          >
            <CartesianGrid horizontal={false} strokeDasharray="3 3" className="stroke-muted" />
            <XAxis
              type="number"
              domain={[0, 105]}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11 }}
              className="fill-muted-foreground"
              ticks={[0, 25, 50, 75, 100]}
              label={{ value: "ציון באחוזים", position: "insideBottom", offset: -5, fontSize: 11 }}
            />
            <YAxis type="category" dataKey="name" hide />
            <Tooltip content={<ChartTooltip />} />
            <Bar
              dataKey="ציון_התחלתי"
              name="ציון התחלתי"
              fill="var(--color-chart-4)"
              radius={[0, 4, 4, 0]}
              barSize={16}
              animationDuration={300}
              cursor={onBarClick ? "pointer" : "default"}
              onClick={(_, index) => handleClick(index)}
            />
            <Bar
              dataKey="ציון_משופר"
              name="ציון משופר"
              fill="var(--color-chart-2)"
              radius={[0, 4, 4, 0]}
              barSize={16}
              animationDuration={300}
              cursor={onBarClick ? "pointer" : "default"}
              onClick={(_, index) => handleClick(index)}
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
      <div className="flex justify-center gap-4 mt-2">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            className="size-2.5 rounded-full"
            style={{ backgroundColor: "var(--color-chart-4)" }}
          />
          ציון התחלתי
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            className="size-2.5 rounded-full"
            style={{ backgroundColor: "var(--color-chart-2)" }}
          />
          ציון משופר
        </div>
      </div>
    </>
  );
}
