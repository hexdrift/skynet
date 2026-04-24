"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { HelpTip } from "@/shared/ui/help-tip";
import { tip } from "@/shared/lib/tooltips";
import { TERMS } from "@/shared/lib/terms";
import type { OptimizationStatusResponse } from "@/shared/types/api";

type PairSnapshot = {
  pair_index: number;
  name: string;
  התחלתי: number | null;
  משופר: number | null;
};

function shortName(model: unknown): string {
  if (typeof model !== "string") return "?";
  return model.split("/").pop() ?? model;
}

function toPct(v: unknown): number | null {
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  return Math.round(v > 1 ? v : v * 100);
}

function buildPairs(job: OptimizationStatusResponse): PairSnapshot[] {
  const events = job.progress_events ?? [];
  const byIndex = new Map<number, PairSnapshot>();
  const ensure = (pair_index: number, gen?: unknown, ref?: unknown) => {
    const existing = byIndex.get(pair_index);
    if (existing) return existing;
    const entry: PairSnapshot = {
      pair_index,
      name: `${shortName(gen)} × ${shortName(ref)}`,
      התחלתי: null,
      משופר: null,
    };
    byIndex.set(pair_index, entry);
    return entry;
  };
  for (const e of events) {
    const m = e.metrics ?? {};
    const pi = m.pair_index;
    if (typeof pi !== "number") continue;
    if (e.event === "baseline_evaluated") {
      const entry = ensure(pi);
      entry.התחלתי = toPct(m.baseline_test_metric);
    } else if (e.event === "optimized_evaluated") {
      const entry = ensure(pi);
      entry.משופר = toPct(m.optimized_test_metric);
    } else if (e.event === "grid_pair_completed") {
      const entry = ensure(pi, m.generation_model, m.reflection_model);
      if (entry.התחלתי == null) entry.התחלתי = toPct(m.baseline_test_metric);
      if (entry.משופר == null) entry.משופר = toPct(m.optimized_test_metric);
      if (entry.name.startsWith("?")) {
        entry.name = `${shortName(m.generation_model)} × ${shortName(m.reflection_model)}`;
      }
    }
  }
  return Array.from(byIndex.values())
    .filter((p) => p.התחלתי != null || p.משופר != null)
    .sort((a, b) => a.pair_index - b.pair_index);
}

type TipPayload = Array<{ value: number; dataKey?: string; color?: string }>;

function LiveTip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TipPayload;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const nameMap: Record<string, string> = {
    התחלתי: `${TERMS.score} לפני ${TERMS.optimization}`,
    משופר: `${TERMS.score} אחרי ${TERMS.optimization}`,
  };
  return (
    <div
      className="rounded-xl border border-border/60 bg-background/95 backdrop-blur-sm p-3 shadow-lg"
      dir="rtl"
    >
      {label && <p className="font-semibold mb-1.5 text-foreground text-xs">{label}</p>}
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
          {p.color && (
            <span className="size-2 rounded-full shrink-0" style={{ backgroundColor: p.color }} />
          )}
          <span>{nameMap[String(p.dataKey)] ?? String(p.dataKey)}</span>
          <span className="font-mono font-semibold text-foreground ms-auto">{p.value}%</span>
        </div>
      ))}
    </div>
  );
}

export function GridLiveChart({ job }: { job: OptimizationStatusResponse }) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const pairs = buildPairs(job);
  if (pairs.length === 0) return null;
  const toggle = (key: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  const totalPairs = (() => {
    const events = job.progress_events ?? [];
    for (let i = events.length - 1; i >= 0; i--) {
      const t = events[i]?.metrics?.total_pairs;
      if (typeof t === "number") return t;
    }
    return null;
  })();
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold flex items-center justify-between gap-2">
          <HelpTip text={tip("grid.score_comparison")}>ציונים לפי זוג</HelpTip>
          {totalPairs != null && (
            <span className="text-[0.6875rem] font-normal text-muted-foreground tabular-nums">
              {pairs.length}/{totalPairs} הושלמו
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="h-[220px]" dir="ltr">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={pairs}
              layout="vertical"
              margin={{ left: 10, right: 20, top: 5, bottom: 5 }}
            >
              <CartesianGrid horizontal={false} strokeDasharray="3 3" className="stroke-muted" />
              <XAxis
                type="number"
                domain={[0, 105]}
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 10 }}
                className="fill-muted-foreground"
                label={{
                  value: "ציון באחוזים",
                  position: "insideBottom",
                  offset: -2,
                  fontSize: 10,
                }}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fontSize: 10 }}
                width={100}
                className="fill-muted-foreground"
                tickLine={false}
                axisLine={false}
              />
              <Tooltip content={<LiveTip />} />
              {!hidden.has("התחלתי") && (
                <Bar
                  dataKey="התחלתי"
                  name="התחלתי"
                  fill="var(--color-chart-4)"
                  radius={[0, 3, 3, 0]}
                  barSize={12}
                  animationDuration={400}
                />
              )}
              {!hidden.has("משופר") && (
                <Bar
                  dataKey="משופר"
                  name="משופר"
                  fill="var(--color-chart-2)"
                  radius={[0, 3, 3, 0]}
                  barSize={12}
                  animationDuration={400}
                />
              )}
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="flex justify-center gap-4 mt-1">
          {[
            { key: "התחלתי", color: "var(--color-chart-4)" },
            { key: "משופר", color: "var(--color-chart-2)" },
          ].map(({ key, color }) => {
            const isHidden = hidden.has(key);
            return (
              <button
                key={key}
                type="button"
                onClick={() => toggle(key)}
                className={`flex items-center gap-1.5 text-[0.625rem] cursor-pointer transition-colors ${isHidden ? "text-muted-foreground/50" : "text-muted-foreground hover:text-foreground"}`}
                aria-pressed={!isHidden}
              >
                <span
                  className="size-2 rounded-full transition-all"
                  style={
                    isHidden
                      ? {
                          backgroundColor: "transparent",
                          boxShadow: `inset 0 0 0 1.5px ${color}`,
                        }
                      : { backgroundColor: color }
                  }
                />
                {key}
              </button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
