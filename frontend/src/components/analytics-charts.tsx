"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ScatterChart,
  Scatter,
  ZAxis,
} from "recharts";
import { useState } from "react";

/* ── Chart tooltip ── */
function ChartTooltip({
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

/* ── Scores comparison chart ── */
export function ScoresChart({
  data,
  optimizationIds,
  onBarClick,
}: {
  data: Array<{ name: string; ציון_התחלתי: number; ציון_משופר: number; delta?: number }>;
  optimizationIds?: string[];
  onBarClick?: (optimizationId: string) => void;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  if (data.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center">
        <p className="text-sm text-muted-foreground">אין עדיין אופטימיזציות שהושלמו</p>
      </div>
    );
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

/* ── Optimizer performance chart ── */
export function OptimizerChart({
  data,
  onBarClick,
}: {
  data: Array<{ name: string; שיפור_ממוצע: number; count: number }>;
  onBarClick?: (optimizerName: string) => void;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  return (
    <>
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
              label={{ value: "אופטימייזר", position: "insideBottom", offset: -15, fontSize: 11 }}
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
    </>
  );
}

/* ── Runtime distribution chart ── */
export function RuntimeDistributionChart({
  data,
  optimizationIds,
  onBarClick,
}: {
  data: Array<{ name: string; זמן_דקות: number }>;
  optimizationIds?: string[];
  onBarClick?: (optimizationId: string) => void;
}) {
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
            label={{ value: "זמן בדקות", angle: -90, position: "center", dx: -15, fontSize: 10 }}
          />
          <Tooltip content={<ChartTooltip />} />
          <Bar
            dataKey="זמן_דקות"
            name="זמן בדקות"
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

/* ── Dataset size vs improvement scatter ── */
export function DatasetVsImprovementChart({
  data,
  optimizationIds,
  onDotClick,
}: {
  data: Array<{ שורות: number; שיפור: number; name: string }>;
  optimizationIds?: string[];
  onDotClick?: (optimizationId: string) => void;
}) {
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

/* ── Efficiency chart (improvement per minute) ── */
export function EfficiencyChart({
  data,
  optimizationIds,
  onBarClick,
}: {
  data: Array<{ name: string; יעילות: number }>;
  optimizationIds?: string[];
  onBarClick?: (optimizationId: string) => void;
}) {
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

/* ── Timeline chart (jobs per day) ── */
export function TimelineChart({
  data,
  dates,
  onBarClick,
}: {
  data: Array<{ name: string; אופטימיזציות: number }>;
  dates?: string[];
  onBarClick?: (date: string) => void;
}) {
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
              value: "מספר אופטימיזציות",
              angle: -90,
              position: "center",
              dx: -10,
              fontSize: 10,
            }}
          />
          <Tooltip content={<ChartTooltip />} />
          <Bar
            dataKey="אופטימיזציות"
            name="אופטימיזציות"
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
