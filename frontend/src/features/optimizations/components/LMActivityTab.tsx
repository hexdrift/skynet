"use client";

import { Activity } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/primitives/card";
import { FadeIn } from "@/shared/ui/motion";
import { HelpTip } from "@/shared/ui/help-tip";
import { msg } from "@/shared/lib/messages";
import { tip } from "@/shared/lib/tooltips";
import type { LMActivity, LMStageStats } from "@/shared/types/api";

const STAGE_KEYS = ["baseline", "training", "evaluation"] as const;
type StageKey = (typeof STAGE_KEYS)[number];

const STAGE_MESSAGE_KEYS: Record<
  StageKey,
  "auto.features.optimizations.components.lmactivitytab.stage_baseline"
  | "auto.features.optimizations.components.lmactivitytab.stage_training"
  | "auto.features.optimizations.components.lmactivitytab.stage_evaluation"
> = {
  baseline: "auto.features.optimizations.components.lmactivitytab.stage_baseline",
  training: "auto.features.optimizations.components.lmactivitytab.stage_training",
  evaluation: "auto.features.optimizations.components.lmactivitytab.stage_evaluation",
};

const STAGE_TIP_KEYS: Record<
  StageKey,
  "lm_activity.stage.baseline" | "lm_activity.stage.training" | "lm_activity.stage.evaluation"
> = {
  baseline: "lm_activity.stage.baseline",
  training: "lm_activity.stage.training",
  evaluation: "lm_activity.stage.evaluation",
};

function aggregateColumn(
  perStage: Record<string, LMStageStats>,
): { calls: number; avg_response_time_ms: number | null } {
  // Weighted mean across stages: ``avg_ms`` per stage is itself a mean, so
  // multiply by per-stage call count before reducing.
  let totalCalls = 0;
  let weighted = 0;
  let weighted_n = 0;
  for (const cell of Object.values(perStage)) {
    const calls = cell?.calls ?? 0;
    totalCalls += calls;
    if (calls > 0 && typeof cell?.avg_response_time_ms === "number") {
      weighted += cell.avg_response_time_ms * calls;
      weighted_n += calls;
    }
  }
  return {
    calls: totalCalls,
    avg_response_time_ms: weighted_n > 0 ? weighted / weighted_n : null,
  };
}

function formatCalls(n: number): string {
  return n.toLocaleString("he-IL");
}

function formatAvgMs(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

function Cell({
  value,
  ariaLabel,
}: {
  value: string;
  ariaLabel?: string;
}) {
  return (
    <span
      aria-label={ariaLabel}
      className="inline-block font-mono tabular-nums text-sm text-[#1C1612]"
    >
      {value}
    </span>
  );
}

function StageRow({
  stage,
  generation,
  reflection,
  hasReflection,
}: {
  stage: StageKey;
  generation: LMStageStats | undefined;
  reflection: LMStageStats | undefined;
  hasReflection: boolean;
}) {
  const genCalls = generation?.calls ?? 0;
  const reflCalls = reflection?.calls ?? 0;
  return (
    <tr className="border-t border-[#E3DCD0]/70">
      <th
        scope="row"
        className="px-3 py-2.5 text-start text-xs font-semibold text-[#7C6350] whitespace-nowrap"
      >
        <HelpTip text={tip(STAGE_TIP_KEYS[stage])}>{msg(STAGE_MESSAGE_KEYS[stage])}</HelpTip>
      </th>
      <td className="px-3 py-2.5 text-start">
        {genCalls > 0 ? (
          <div className="flex flex-col gap-0.5">
            <Cell value={formatCalls(genCalls)} />
            <span className="text-[10px] text-[#A89680] font-mono tabular-nums">
              {formatAvgMs(generation?.avg_response_time_ms)}
            </span>
          </div>
        ) : (
          <span className="text-[#BFB3A3] font-mono">—</span>
        )}
      </td>
      {hasReflection && (
        <td className="px-3 py-2.5 text-start">
          {reflCalls > 0 ? (
            <div className="flex flex-col gap-0.5">
              <Cell value={formatCalls(reflCalls)} />
              <span className="text-[10px] text-[#A89680] font-mono tabular-nums">
                {formatAvgMs(reflection?.avg_response_time_ms)}
              </span>
            </div>
          ) : (
            <span className="text-[#BFB3A3] font-mono">—</span>
          )}
        </td>
      )}
    </tr>
  );
}

function TotalRow({
  generation,
  reflection,
  hasReflection,
}: {
  generation: { calls: number; avg_response_time_ms: number | null };
  reflection: { calls: number; avg_response_time_ms: number | null };
  hasReflection: boolean;
}) {
  return (
    <tr className="border-t-2 border-[#C8A882]/40 bg-[#FAF6F0]/70">
      <th
        scope="row"
        className="px-3 py-2.5 text-start text-xs font-bold text-[#1C1612] whitespace-nowrap"
      >
        <HelpTip text={tip("lm_activity.total_row")}>
          {msg("auto.features.optimizations.components.lmactivitytab.row_total")}
        </HelpTip>
      </th>
      <td className="px-3 py-2.5 text-start">
        {generation.calls > 0 ? (
          <div className="flex flex-col gap-0.5">
            <Cell value={formatCalls(generation.calls)} />
            <span className="text-[10px] text-[#7C6350] font-mono tabular-nums font-semibold">
              {formatAvgMs(generation.avg_response_time_ms)}
            </span>
          </div>
        ) : (
          <span className="text-[#BFB3A3] font-mono">—</span>
        )}
      </td>
      {hasReflection && (
        <td className="px-3 py-2.5 text-start">
          {reflection.calls > 0 ? (
            <div className="flex flex-col gap-0.5">
              <Cell value={formatCalls(reflection.calls)} />
              <span className="text-[10px] text-[#7C6350] font-mono tabular-nums font-semibold">
                {formatAvgMs(reflection.avg_response_time_ms)}
              </span>
            </div>
          ) : (
            <span className="text-[#BFB3A3] font-mono">—</span>
          )}
        </td>
      )}
    </tr>
  );
}

export function LMActivityTab({ lmActivity }: { lmActivity: LMActivity | null | undefined }) {
  const generation = lmActivity?.generation ?? {};
  const reflection = lmActivity?.reflection ?? {};
  // Hide the reflection column entirely when no reflection traffic was recorded —
  // unoptimized runs and grid pairs that didn't reach reflection should not show
  // a column full of em-dashes.
  const hasReflection = Object.values(reflection).some((c) => (c?.calls ?? 0) > 0);
  const hasAnyCalls =
    hasReflection || Object.values(generation).some((c) => (c?.calls ?? 0) > 0);

  const genTotal = aggregateColumn(generation);
  const reflTotal = aggregateColumn(reflection);

  return (
    <FadeIn>
      <Card className="relative overflow-hidden shadow-[0_1px_3px_rgba(28,22,18,0.04),inset_0_1px_0_rgba(255,255,255,0.5)]">
        <div
          className="absolute inset-x-0 top-0 h-px bg-gradient-to-l from-transparent via-[#C8A882]/40 to-transparent"
          aria-hidden="true"
        />
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Activity className="size-4 text-[#7C6350]" aria-hidden="true" />
            <HelpTip text={tip("lm_activity.section")}>
              <span className="font-bold tracking-tight">
                {msg("auto.features.optimizations.components.lmactivitytab.title")}
              </span>
            </HelpTip>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!hasAnyCalls ? (
            <p className="text-sm text-[#A89680] py-2">
              {msg("auto.features.optimizations.components.lmactivitytab.no_data")}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table
                className="w-full text-sm border-collapse"
                dir="rtl"
              >
                <thead>
                  <tr>
                    <th
                      scope="col"
                      className="px-3 py-2 text-start text-[0.625rem] font-semibold tracking-[0.08em] uppercase text-[#A89680]"
                    >
                      {msg("auto.features.optimizations.components.lmactivitytab.col_stage")}
                    </th>
                    <th
                      scope="col"
                      className="px-3 py-2 text-start text-[0.625rem] font-semibold tracking-[0.08em] uppercase text-[#A89680]"
                    >
                      <HelpTip text={tip("lm_activity.column.generation")}>
                        {msg("auto.features.optimizations.components.lmactivitytab.col_generation")}
                      </HelpTip>
                    </th>
                    {hasReflection && (
                      <th
                        scope="col"
                        className="px-3 py-2 text-start text-[0.625rem] font-semibold tracking-[0.08em] uppercase text-[#A89680]"
                      >
                        <HelpTip text={tip("lm_activity.column.reflection")}>
                          {msg(
                            "auto.features.optimizations.components.lmactivitytab.col_reflection",
                          )}
                        </HelpTip>
                      </th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {STAGE_KEYS.map((stage) => (
                    <StageRow
                      key={stage}
                      stage={stage}
                      generation={generation[stage]}
                      reflection={reflection[stage]}
                      hasReflection={hasReflection}
                    />
                  ))}
                  <TotalRow
                    generation={genTotal}
                    reflection={reflTotal}
                    hasReflection={hasReflection}
                  />
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </FadeIn>
  );
}
