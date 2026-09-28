"use client";

/**
 * Visual pipeline timeline — renders the run's planned stages (validating →
 * splitting → baseline → optimizing → evaluating, see
 * `planPipelineStages`) as a connected row of nodes. Each finished stage
 * shows how far into the run it was reached (like chapter markers on a
 * video) plus the wall-clock time.
 *
 * Used by OverviewTab for both the job-wide pipeline and (when scoped by
 * pair_index) the per-pair pipeline inside a grid_search. Stage detection
 * + timestamp derivation live in the caller; this component is a pure,
 * non-interactive renderer.
 */

import { useEffect, useRef, useState } from "react";
import { Check, CircleNotch, Minus, X } from "@/shared/ui/icons";
import type { PipelineStage } from "../constants";
import type { PlannedStage } from "../lib/pipeline-plan";
import type { ProgressEvent } from "@/shared/types/api";
import { msg } from "@/shared/lib/messages";
import { formatDuration } from "@/shared/lib/formatters";
import { getActiveIntlLocale } from "@/shared/lib/runtime-locale";
import { cn } from "@/shared/lib/utils";

const VERTICAL_BREAKPOINT_PX = 600;

interface StageTs {
  iso: string;
  date: string;
  time: string;
}

function fmtTs(iso: string): StageTs {
  const d = new Date(iso);
  const tag = getActiveIntlLocale();
  return {
    iso,
    date: d.toLocaleDateString(tag, { month: "short", day: "numeric" }),
    time: d.toLocaleTimeString(tag, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }),
  };
}

// Stage labels come from shared TERMS, some of which are lowercase mid-sentence
// forms ("baseline score"); the tracker reads them as headings.
function sentenceCase(label: string): string {
  return label.charAt(0).toLocaleUpperCase(getActiveIntlLocale()) + label.slice(1);
}

function secondsSince(originIso: string | null, iso: string | undefined): number | null {
  if (!originIso || !iso) return null;
  const ms = new Date(iso).getTime() - new Date(originIso).getTime();
  return Number.isFinite(ms) && ms >= 0 ? ms / 1000 : null;
}

/**
 * Build `{stage → timestamp}` from a progress-event stream. When
 * `pairIndex` is provided, only events tagged with that pair are used
 * for pair-scoped stages (baseline/optimizing/evaluating); pre-pair
 * stages (validating/splitting) still fall back to the global events.
 */
export function computeStageTimestamps(
  events: ProgressEvent[],
  startedAt: string | null | undefined,
  completedAt: string | null | undefined,
  pairIndex?: number,
): Partial<Record<PipelineStage, StageTs>> {
  const globalMap: Record<string, PipelineStage> = {
    validation_passed: "validating",
    dataset_splits_ready: "splitting",
  };
  const pairMap: Record<string, PipelineStage> = {
    grid_pair_started: "baseline",
    baseline_evaluated: "baseline",
    optimizer_progress: "optimizing",
    evaluation_started: "optimizing",
    optimized_evaluated: "evaluating",
    grid_pair_completed: "evaluating",
  };

  const stageTs: Partial<Record<PipelineStage, StageTs>> = {};
  for (const ev of events) {
    if (!ev.event || !ev.timestamp) continue;
    const evPairIndex = ev.metrics?.pair_index;
    const isPairScoped = ev.event in pairMap;

    if (pairIndex != null && isPairScoped) {
      if (typeof evPairIndex !== "number" || evPairIndex !== pairIndex) continue;
    }

    const sk = globalMap[ev.event] ?? pairMap[ev.event];
    if (!sk) continue;
    stageTs[sk] = fmtTs(ev.timestamp);
  }
  if (startedAt && !stageTs.validating) {
    stageTs.validating = fmtTs(startedAt);
  }
  if (completedAt && !stageTs.evaluating && pairIndex == null) {
    stageTs.evaluating = fmtTs(completedAt);
  }
  return stageTs;
}

type StageState = "done" | "skipped" | "current" | "stopped" | "pending";

const NODE_STYLES: Record<StageState, string> = {
  done: "bg-primary text-primary-foreground",
  skipped: "border-2 border-dashed border-border bg-background text-muted-foreground",
  current: "bg-primary text-primary-foreground ring-4 ring-primary/15",
  stopped: "bg-destructive text-white ring-4 ring-destructive/15",
  pending: "border-2 border-border bg-background text-border",
};

const LABEL_STYLES: Record<StageState, string> = {
  done: "text-foreground/85",
  skipped: "text-muted-foreground",
  current: "font-semibold text-primary",
  stopped: "font-semibold text-destructive",
  pending: "text-muted-foreground/70",
};

function StageNode({ state }: { state: StageState }) {
  return (
    <span
      className={cn(
        "grid size-8 shrink-0 place-items-center rounded-full transition-colors duration-300 ease-out",
        NODE_STYLES[state],
      )}
      aria-hidden="true"
    >
      {state === "done" && <Check className="size-3.5" />}
      {state === "skipped" && <Minus className="size-3.5" />}
      {state === "current" && <CircleNotch className="size-3.5 animate-spin" />}
      {state === "stopped" && <X className="size-3.5" />}
      {state === "pending" && <span className="size-1.5 rounded-full bg-current" />}
    </span>
  );
}

function ElapsedChip({ seconds, className }: { seconds: number; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-4 items-center rounded-full border border-border/70 bg-background px-1.5 font-mono text-[0.625rem] leading-none tabular-nums text-foreground/80",
        className,
      )}
      title={msg("pipeline.stage.elapsed")}
      dir="ltr"
    >
      {formatDuration(seconds)}
    </span>
  );
}

function StatusText({ state, text }: { state: StageState; text: string }) {
  return (
    <span
      className={cn(
        "text-[0.625rem] uppercase tracking-[0.08em]",
        state === "stopped" ? "text-destructive" : "text-muted-foreground",
      )}
    >
      {text}
    </span>
  );
}

function StageDetail({ state, text }: { state: StageState; text: string }) {
  return (
    <span
      className={cn(
        "max-w-full truncate text-[0.625rem]",
        state === "pending" ? "text-muted-foreground/60" : "text-muted-foreground",
      )}
    >
      {text}
    </span>
  );
}

export function PipelineStages({
  plan,
  currentStage,
  stageTs,
  startedAt,
  isActive,
  isFailed,
  skippedStages = [],
  dataTutorial,
}: {
  /** The run's stages in order, with the algorithm behind each. */
  plan: readonly PlannedStage[];
  currentStage: PipelineStage | "done";
  stageTs: Partial<Record<PipelineStage, StageTs>>;
  /** Zero point of the elapsed markers; the run's start time. */
  startedAt: string | null | undefined;
  isActive: boolean;
  isFailed: boolean;
  /** Stages the run went past without executing (no test split). */
  skippedStages?: readonly PipelineStage[];
  dataTutorial?: string;
}) {
  const stageCount = plan.length;
  const completedStageIdx =
    currentStage === "done" ? stageCount : plan.findIndex((s) => s.key === currentStage);

  const containerRef = useRef<HTMLDivElement>(null);
  const [isVertical, setIsVertical] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        setIsVertical(e.contentRect.width < VERTICAL_BREAKPOINT_PX);
      }
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // The rail runs between the first and last node centres; each node sits in
  // the middle of an equal column, so the ends are half a column in.
  const railInsetPct = 50 / stageCount;
  const railSpanPct = 100 - railInsetPct * 2;
  const progressFraction = Math.min(completedStageIdx, stageCount - 1) / (stageCount - 1);
  const origin = startedAt ?? stageTs.validating?.iso ?? null;

  const stages = plan.map((s, i) => {
    const isDone = i < completedStageIdx;
    const state: StageState =
      isFailed && i === completedStageIdx
        ? "stopped"
        : isActive && i === completedStageIdx
          ? "current"
          : isDone && skippedStages.includes(s.key)
            ? "skipped"
            : isDone
              ? "done"
              : "pending";
    const ts = state === "done" ? stageTs[s.key] : undefined;
    const prev = i > 0 ? plan[i - 1] : null;
    const prevTs = prev ? stageTs[prev.key] : undefined;
    const elapsed = secondsSince(origin, ts?.iso);
    const dateChanged = ts != null && ts.date !== prevTs?.date;
    const statusText =
      state === "current"
        ? msg("pipeline.stage.running")
        : state === "stopped"
          ? msg("pipeline.stage.failed")
          : state === "skipped"
            ? msg("pipeline.stage.skipped")
            : null;
    return { ...s, i, state, ts, elapsed, dateChanged, statusText, label: sentenceCase(s.label) };
  });

  const railColor = isFailed ? "bg-destructive/70" : "bg-primary";

  if (isVertical) {
    return (
      <div ref={containerRef} className="relative flex flex-col" data-tutorial={dataTutorial}>
        <div
          className="absolute bottom-[22px] top-[22px] w-[2px] rounded-full bg-border/60"
          style={{ insetInlineStart: "calc(1rem + 0.25rem - 1px)" }}
          aria-hidden="true"
        />
        <div
          className={cn(
            "absolute top-[22px] w-[2px] rounded-full transition-[height] duration-700 ease-out",
            railColor,
          )}
          style={{
            insetInlineStart: "calc(1rem + 0.25rem - 1px)",
            height: `calc((100% - 44px) * ${progressFraction})`,
          }}
          aria-hidden="true"
        />
        {stages.map((s) => (
          <div
            key={s.key}
            aria-current={s.state === "current" ? "step" : undefined}
            className="relative z-10 flex w-full min-w-0 items-center gap-3 px-1 py-1.5"
          >
            <StageNode state={s.state} />
            <span className="flex min-w-0 flex-col leading-tight">
              <span className={cn("truncate text-xs", LABEL_STYLES[s.state])}>{s.label}</span>
              {s.detail && <StageDetail state={s.state} text={s.detail} />}
            </span>
            <span className="ms-auto flex shrink-0 items-center gap-2" dir="ltr">
              {s.statusText && <StatusText state={s.state} text={s.statusText} />}
              {s.ts && (
                <span className="font-mono text-[0.6875rem] tabular-nums text-muted-foreground">
                  {s.dateChanged ? `${s.ts.date} · ${s.ts.time}` : s.ts.time}
                </span>
              )}
              {s.elapsed != null && <ElapsedChip seconds={s.elapsed} />}
            </span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="relative grid"
      style={{ gridTemplateColumns: `repeat(${stageCount}, minmax(0, 1fr))` }}
      data-tutorial={dataTutorial}
    >
      <div
        className="absolute top-[15px] h-[2px] rounded-full bg-border/60"
        style={{ insetInlineStart: `${railInsetPct}%`, insetInlineEnd: `${railInsetPct}%` }}
        aria-hidden="true"
      />
      <div
        className={cn(
          "absolute top-[15px] h-[2px] rounded-full transition-[width] duration-700 ease-out",
          railColor,
        )}
        style={{
          insetInlineStart: `${railInsetPct}%`,
          width: `${railSpanPct * progressFraction}%`,
        }}
        aria-hidden="true"
      />
      {stages.map((s) => (
        <div
          key={s.key}
          aria-current={s.state === "current" ? "step" : undefined}
          className="relative z-10 flex min-w-0 flex-col items-center gap-2 px-1 pb-1"
        >
          <StageNode state={s.state} />
          <span className="flex max-w-full flex-col items-center leading-tight">
            <span className={cn("max-w-full truncate text-xs", LABEL_STYLES[s.state])}>
              {s.label}
            </span>
            {s.detail && <StageDetail state={s.state} text={s.detail} />}
          </span>
          <span className="-mt-1 flex flex-col items-center gap-1 leading-tight" dir="ltr">
            {s.statusText ? (
              <StatusText state={s.state} text={s.statusText} />
            ) : s.ts ? (
              <>
                {s.elapsed != null && <ElapsedChip seconds={s.elapsed} />}
                <span className="font-mono text-[0.625rem] tabular-nums text-muted-foreground">
                  {s.dateChanged ? `${s.ts.date} · ${s.ts.time}` : s.ts.time}
                </span>
              </>
            ) : null}
          </span>
        </div>
      ))}
    </div>
  );
}
