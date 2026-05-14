"use client";

import { Activity } from "lucide-react";
import { FadeIn } from "@/shared/ui/motion";
import { HelpTip } from "@/shared/ui/help-tip";
import { msg } from "@/shared/lib/messages";
import { tip } from "@/shared/lib/tooltips";
import type { LMActivity, LMStageStats } from "@/shared/types/api";

const STAGE_KEYS = ["baseline", "training", "evaluation"] as const;
type StageKey = (typeof STAGE_KEYS)[number];

const STAGE_MESSAGE_KEYS: Record<
  StageKey,
  | "auto.features.optimizations.components.lmactivitytab.stage_baseline"
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

// Unified to seconds so the eye doesn't re-parse units row to row. Sub-100ms
// shows ``<0.1s`` rather than ``42ms`` to keep the column dimension uniform —
// the diagnostic question is "where did time go", so consistent scale wins
// over per-cell precision at the millisecond floor.
function formatSeconds(ms: number | null | undefined): string {
  if (ms == null) return "—";
  const seconds = ms / 1000;
  if (seconds < 0.1) return "<0.1s";
  return `${seconds.toFixed(1)}s`;
}

function NumericCell({
  calls,
  ms,
  emphasized = false,
}: {
  calls: number;
  ms: number | null;
  emphasized?: boolean;
}) {
  if (calls === 0) {
    return <span className="text-[var(--text-3)]">—</span>;
  }
  return (
    <div className="flex flex-col items-start gap-0.5">
      <span
        className={`font-mono tabular-nums text-sm text-foreground ${
          emphasized ? "font-semibold" : "font-normal"
        }`}
      >
        {formatCalls(calls)}
      </span>
      <span
        className={`font-mono tabular-nums text-xs ${
          emphasized ? "text-foreground" : "text-muted-foreground"
        }`}
      >
        {formatSeconds(ms)}
      </span>
    </div>
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
  return (
    <tr className="border-t border-border/60">
      <th
        scope="row"
        className="px-3 py-2.5 text-start text-sm font-medium text-foreground whitespace-nowrap"
      >
        <HelpTip text={tip(STAGE_TIP_KEYS[stage])}>{msg(STAGE_MESSAGE_KEYS[stage])}</HelpTip>
      </th>
      <td className="px-3 py-2.5 text-start">
        <NumericCell
          calls={generation?.calls ?? 0}
          ms={generation?.avg_response_time_ms ?? null}
        />
      </td>
      {hasReflection && (
        <td className="px-3 py-2.5 text-start">
          <NumericCell
            calls={reflection?.calls ?? 0}
            ms={reflection?.avg_response_time_ms ?? null}
          />
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
    <tr className="border-t border-border">
      <th
        scope="row"
        className="px-3 py-2.5 text-start text-sm font-bold text-foreground whitespace-nowrap"
      >
        <HelpTip text={tip("lm_activity.total_row")}>
          {msg("auto.features.optimizations.components.lmactivitytab.row_total")}
        </HelpTip>
      </th>
      <td className="px-3 py-2.5 text-start">
        <NumericCell calls={generation.calls} ms={generation.avg_response_time_ms} emphasized />
      </td>
      {hasReflection && (
        <td className="px-3 py-2.5 text-start">
          <NumericCell calls={reflection.calls} ms={reflection.avg_response_time_ms} emphasized />
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

  // Plain ``<section>`` instead of ``<Card>`` to opt out of the global
  // ``[data-slot="card"]`` chrome (gradient bg, backdrop-blur, mouse-spotlight,
  // hover-lift, top hairline). This card is a quiet diagnostic surface; the
  // ornamental defaults fight that intent.
  return (
    <FadeIn>
      <section
        aria-labelledby="lm-activity-title"
        className="rounded-2xl border border-border bg-card text-card-foreground shadow-[var(--shadow-sm)]"
      >
        <header className="flex items-center gap-2 px-6 pt-5 pb-3">
          <Activity
            className="size-4 text-muted-foreground"
            strokeWidth={1.75}
            aria-hidden="true"
          />
          <HelpTip text={tip("lm_activity.section")}>
            <h3
              id="lm-activity-title"
              className="m-0 text-lg font-bold text-foreground"
            >
              {msg("auto.features.optimizations.components.lmactivitytab.title")}
            </h3>
          </HelpTip>
        </header>
        <div className="px-6 pb-5">
          {!hasAnyCalls ? (
            <p className="text-sm text-muted-foreground">
              {msg("auto.features.optimizations.components.lmactivitytab.no_data")}
            </p>
          ) : (
            <table className="guide-table w-full text-sm" dir="rtl">
              <thead>
                <tr>
                  <th scope="col" className="px-3 py-2 text-start">
                    <span className="sr-only">
                      {msg("auto.features.optimizations.components.lmactivitytab.col_stage")}
                    </span>
                  </th>
                  <th
                    scope="col"
                    className="px-3 py-2 text-start text-xs font-medium text-muted-foreground"
                  >
                    <HelpTip text={tip("lm_activity.column.generation")}>
                      {msg("auto.features.optimizations.components.lmactivitytab.col_generation")}
                    </HelpTip>
                  </th>
                  {hasReflection && (
                    <th
                      scope="col"
                      className="px-3 py-2 text-start text-xs font-medium text-muted-foreground"
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
          )}
        </div>
      </section>
    </FadeIn>
  );
}
