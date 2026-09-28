import type { PairResult } from "@/shared/types/api";
import { formatMsg, msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";
import {
  CHART_TOOLTIP_CARD_CLASS,
  CHART_TOOLTIP_ROW_CLASS,
  CHART_TOOLTIP_SWATCH_CLASS,
  CHART_TOOLTIP_TITLE_CLASS,
  CHART_TOOLTIP_VALUE_CLASS,
} from "@/shared/charts/chart-utils";
import { getActiveDir } from "@/shared/lib/runtime-locale";
import { cn } from "@/shared/lib/utils";

export interface ScatterPoint {
  pair_index: number;
  name: string;
  quality: number;
  latency: number;
  isOverall: boolean;
  isQuality: boolean;
  isSpeed: boolean;
}

export function computePareto(points: ScatterPoint[]): {
  pareto: ScatterPoint[];
  dominated: ScatterPoint[];
} {
  const pareto: ScatterPoint[] = [];
  const dominated: ScatterPoint[] = [];
  for (const p of points) {
    const isDominated = points.some(
      (q) =>
        q !== p &&
        q.quality >= p.quality &&
        q.latency <= p.latency &&
        (q.quality > p.quality || q.latency < p.latency),
    );
    if (isDominated) dominated.push(p);
    else pareto.push(p);
  }
  pareto.sort((a, b) => a.latency - b.latency);
  return { pareto, dominated };
}

function shortEffort(value: string | null | undefined): string | null {
  if (!value) return null;
  const v = value.toLowerCase();
  if (v === "minimal") return "min";
  if (v === "medium") return "med";
  return v;
}

export function pairLabel(p: PairResult): string {
  const gen = p.generation_model.split("/").pop();
  const ref = p.reflection_model.split("/").pop();
  const genE = shortEffort(p.generation_reasoning_effort);
  const refE = shortEffort(p.reflection_reasoning_effort);
  const genStr = genE ? `${gen}·${genE}` : gen;
  const refStr = refE ? `${ref}·${refE}` : ref;
  return `${genStr} × ${refStr}`;
}

export function ScoreTip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; dataKey?: string; color?: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const nameMap: Record<string, string> = {
    baselineScore: formatMsg("auto.features.optimizations.components.gridoverview.template.1", {
      p1: TERMS.score,
      p2: TERMS.optimization,
    }),
    optimizedScore: formatMsg("auto.features.optimizations.components.gridoverview.template.2", {
      p1: TERMS.score,
      p2: TERMS.optimization,
    }),
  };
  return (
    <div className={CHART_TOOLTIP_CARD_CLASS} dir={getActiveDir()}>
      {label && <p className={CHART_TOOLTIP_TITLE_CLASS}>{label}</p>}
      <div className="space-y-1">
        {payload.map((p, i) => (
          <div key={i} className={CHART_TOOLTIP_ROW_CLASS}>
            {p.color && (
              <span className={CHART_TOOLTIP_SWATCH_CLASS} style={{ backgroundColor: p.color }} />
            )}
            <span className="text-xs">{nameMap[String(p.dataKey)] ?? String(p.dataKey)}</span>
            <span className={CHART_TOOLTIP_VALUE_CLASS} dir="ltr">
              {p.value}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function CombinedTip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; dataKey?: string; color?: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className={CHART_TOOLTIP_CARD_CLASS} dir={getActiveDir()}>
      {label && <p className={CHART_TOOLTIP_TITLE_CLASS}>{label}</p>}
      <div className="space-y-1">
        {payload.map((p, i) => (
          <div key={i} className={CHART_TOOLTIP_ROW_CLASS}>
            {p.color && (
              <span className={CHART_TOOLTIP_SWATCH_CLASS} style={{ backgroundColor: p.color }} />
            )}
            <span className="text-xs">{String(p.dataKey)}</span>
            <span className={CHART_TOOLTIP_VALUE_CLASS} dir="ltr">
              {p.value}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ScatterTip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: ScatterPoint }>;
}) {
  if (!active || !payload?.length) return null;
  const first = payload[0];
  if (!first) return null;
  const p = first.payload;
  return (
    <div className={CHART_TOOLTIP_CARD_CLASS} dir={getActiveDir()}>
      <p className={cn(CHART_TOOLTIP_TITLE_CLASS, "font-mono")} dir="ltr">
        {p.name}
      </p>
      <div className="text-[0.6875rem] text-muted-foreground space-y-0.5">
        <div className="flex gap-4 justify-between">
          <span>{msg("auto.features.optimizations.components.gridoverview.3")}</span>
          <span className="font-mono text-foreground tabular-nums">{p.quality}%</span>
        </div>
        <div className="flex gap-4 justify-between">
          <span>{msg("auto.features.optimizations.components.gridoverview.4")}</span>
          <span className="font-mono text-foreground tabular-nums">
            {p.latency}
            {msg("auto.features.optimizations.components.gridoverview.5")}
          </span>
        </div>
      </div>
    </div>
  );
}
