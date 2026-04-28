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
import { ChartTooltip, ChartEmptyState } from "./chart-utils";
import { TERMS } from "@/shared/lib/terms";
import { formatMsg, msg } from "@/shared/lib/messages";

interface ScoresChartProps {
  data: Array<{ name: string; baselineScore: number; optimizedScore: number; delta?: number }>;
  optimizationIds?: string[];
  onBarClick?: (optimizationId: string) => void;
}

export function ScoresChart({ data, optimizationIds, onBarClick }: ScoresChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [hiddenSeries, setHiddenSeries] = useState<Set<string>>(new Set());

  if (data.length === 0) {
    return (
      <ChartEmptyState
        message={formatMsg("auto.shared.charts.scores.chart.template.1", {
          p1: TERMS.optimizationPlural,
        })}
      />
    );
  }

  const handleClick = (index: number) => {
    if (onBarClick && optimizationIds?.[index]) onBarClick(optimizationIds[index]);
  };

  const toggleSeries = (key: string) => {
    setHiddenSeries((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
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
              label={{
                value: msg("auto.shared.charts.scores.chart.literal.1"),
                position: "insideBottom",
                offset: -5,
                fontSize: 11,
              }}
            />
            <YAxis type="category" dataKey="name" hide />
            <Tooltip content={<ChartTooltip />} />
            {!hiddenSeries.has(TERMS.baselineScore) && (
              <Bar
                dataKey="baselineScore"
                name={TERMS.baselineScore}
                fill="var(--color-chart-4)"
                radius={[0, 4, 4, 0]}
                barSize={16}
                animationDuration={300}
                cursor={onBarClick ? "pointer" : "default"}
                onClick={(_, index) => handleClick(index)}
              />
            )}
            {!hiddenSeries.has(TERMS.optimizedScore) && (
              <Bar
                dataKey="optimizedScore"
                name={TERMS.optimizedScore}
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
            )}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex justify-center gap-4 mt-2">
        {[
          { key: TERMS.baselineScore, color: "var(--color-chart-4)" },
          { key: TERMS.optimizedScore, color: "var(--color-chart-2)" },
        ].map(({ key, color }) => {
          const isHidden = hiddenSeries.has(key);
          return (
            <button
              key={key}
              type="button"
              onClick={() => toggleSeries(key)}
              className={`flex items-center gap-1.5 text-xs cursor-pointer transition-colors ${isHidden ? "text-muted-foreground/50" : "text-muted-foreground hover:text-foreground"}`}
              aria-pressed={!isHidden}
            >
              <span
                className="size-2.5 rounded-full transition-all"
                style={
                  isHidden
                    ? { backgroundColor: "transparent", boxShadow: `inset 0 0 0 1.5px ${color}` }
                    : { backgroundColor: color }
                }
              />
              {key}
            </button>
          );
        })}
      </div>
    </>
  );
}
