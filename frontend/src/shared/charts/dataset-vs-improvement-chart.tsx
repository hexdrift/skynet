"use client";

/**
 * Dataset size vs improvement scatter chart
 * Shows correlation between dataset size and optimization improvement
 * Preserves exact styling, RTL layout, and hover interactions
 */

import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface DatasetVsImprovementChartProps {
  data: Array<{ שורות: number; שיפור: number; name: string }>;
  optimizationIds?: string[];
  onDotClick?: (optimizationId: string) => void;
}

export function DatasetVsImprovementChart({ data, optimizationIds, onDotClick }: DatasetVsImprovementChartProps) {
  if (data.length === 0) return null;
  
  return (
    <div className="h-[250px]">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ left: 10, right: 20, top: 10, bottom: 25 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
          <XAxis
            type="number"
            dataKey="שורות"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 10 }}
            className="fill-muted-foreground"
            label={{ value: "שורות בדאטאסט", position: "insideBottom", offset: -10, fontSize: 10 }}
          />
          <YAxis
            type="number"
            dataKey="שיפור"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 10 }}
            className="fill-muted-foreground"
            label={{
              value: "שיפור באחוזים",
              angle: -90,
              position: "center",
              dx: -15,
              fontSize: 10,
            }}
          />
          <ZAxis range={[40, 40]} />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0]?.payload as
                | { name?: string; שורות?: number; שיפור?: number }
                | undefined;
              return (
                <div
                  className="rounded-xl border border-border/60 bg-background/95 backdrop-blur-sm p-3 shadow-lg text-sm"
                  dir="rtl"
                >
                  {d?.name && (
                    <p className="font-semibold mb-1 text-foreground font-mono" dir="ltr">
                      {d.name}
                    </p>
                  )}
                  <div className="space-y-0.5 text-xs text-muted-foreground">
                    <div>
                      שורות:{" "}
                      <span className="font-mono font-semibold text-foreground">{d?.שורות}</span>
                    </div>
                    <div>
                      שיפור:{" "}
                      <span className="font-mono font-semibold text-foreground">{d?.שיפור}</span>
                    </div>
                  </div>
                </div>
              );
            }}
          />
          <Scatter
            data={data}
            fill="var(--color-chart-2)"
            cursor={onDotClick ? "pointer" : "default"}
            onClick={(_entry, index) => {
              if (
                onDotClick &&
                optimizationIds &&
                typeof index === "number" &&
                optimizationIds[index]
              )
                onDotClick(optimizationIds[index]);
            }}
          />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
