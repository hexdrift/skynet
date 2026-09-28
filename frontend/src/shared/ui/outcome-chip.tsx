import type * as React from "react";
import { cn } from "@/shared/lib/utils";

const SCORE_TONE = {
  gain: "bg-[var(--success-dim)] text-[var(--success)]",
  loss: "bg-[var(--danger-dim)] text-[var(--danger)]",
  neutral: "bg-primary/10 text-primary",
} as const;

/** Numeric score / relevance / gain pill. Icons inside should be `size-2.5`. */
export function ScorePill({
  tone,
  className,
  children,
  ...props
}: React.ComponentProps<"span"> & { tone: keyof typeof SCORE_TONE }) {
  return (
    <span
      dir="ltr"
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 font-mono text-[0.6875rem] leading-none tabular-nums",
        SCORE_TONE[tone],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}

const OUTCOME_TONE = {
  pass: "bg-[var(--success-dim)] text-[var(--success)]",
  fail: "bg-[var(--danger-dim)] text-[var(--danger)]",
  neutral: "bg-muted text-muted-foreground",
} as const;

/**
 * Pass/fail outcome or boolean-value chip. A `false` data value is `neutral`,
 * not `fail` — it is not an error.
 */
export function OutcomeChip({
  tone,
  className,
  children,
  ...props
}: React.ComponentProps<"span"> & { tone: keyof typeof OUTCOME_TONE }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-[0.625rem] font-medium leading-none",
        OUTCOME_TONE[tone],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}
