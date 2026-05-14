"use client";

import * as React from "react";
import Link from "next/link";
import { X, ChevronLeft, ChevronRight } from "lucide-react";
import { motion } from "framer-motion";
import type { PublicDashboardPoint } from "@/shared/lib/api";
import { Button } from "@/shared/ui/primitives/button";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/shared/ui/primitives/tooltip";
import { msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";
import { formatExploreDate, formatGain, formatMetric } from "../lib/format";

interface ExploreDetailPanelProps {
  point: PublicDashboardPoint;
  onClose: () => void;
  // All variations sharing this point's task_fingerprint (newest first).
  // Defaults to ``[point]`` so existing callers keep their previous
  // single-variation behaviour without changes.
  variations?: PublicDashboardPoint[];
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] items-baseline gap-3">
      <dt className="text-[0.625rem] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </dt>
      <dd className="min-w-0 text-[0.8125rem] text-foreground">{children}</dd>
    </div>
  );
}

const GAIN_TONE: Record<"positive" | "negative" | "neutral", string> = {
  positive: "bg-accent text-foreground",
  negative: "bg-destructive/10 text-destructive",
  neutral: "bg-muted text-muted-foreground",
};

function VariationRow({
  variation,
  onPick,
}: {
  variation: PublicDashboardPoint;
  onPick: () => void;
}) {
  const gain = formatGain(variation.baseline_metric, variation.optimized_metric);
  const dateText = formatExploreDate(variation.created_at);
  return (
    <button
      type="button"
      onClick={onPick}
      className="flex w-full flex-col items-stretch gap-1.5 rounded-md border border-border/60 bg-background px-3 py-2 text-start transition-colors cursor-pointer hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/45"
    >
      <span className="text-[0.6875rem] text-muted-foreground" title={variation.created_at ?? undefined}>
        {dateText}
      </span>
      <span className="inline-flex items-baseline gap-2 font-mono tabular-nums text-[0.8125rem]" dir="ltr">
        <span className="text-foreground">{formatMetric(variation.optimized_metric)}</span>
        {variation.baseline_metric != null && (
          <span className="text-[0.6875rem] text-muted-foreground">
            / {formatMetric(variation.baseline_metric)}
          </span>
        )}
        {gain && (
          <span className={`rounded-sm px-1.5 py-0.5 text-[0.6875rem] ${GAIN_TONE[gain.kind]}`}>
            {gain.text}
          </span>
        )}
      </span>
    </button>
  );
}

export function ExploreDetailPanel({ point, onClose, variations }: ExploreDetailPanelProps) {
  const list = variations && variations.length > 0 ? variations : [point];
  const multi = list.length > 1;
  // ``null`` = picker mode; index ≥ 0 = detail mode for ``list[selectedIndex]``.
  // Single-variation groups skip the picker entirely.
  const [selectedIndex, setSelectedIndex] = React.useState<number | null>(multi ? null : 0);
  // Reset whenever the parent swaps to a different leader so the picker
  // re-shows for the new group (otherwise the old index leaks across).
  React.useEffect(() => {
    setSelectedIndex(multi ? null : 0);
  }, [point.optimization_id, multi]);

  if (multi && selectedIndex === null) {
    return (
      <motion.aside
        key={`${point.optimization_id}-picker`}
        initial={{ x: "100%", opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: "100%", opacity: 0 }}
        transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
        dir="rtl"
        className="flex h-full w-full flex-col overflow-hidden rounded-lg border border-border/50 bg-background"
      >
        <header className="flex items-center justify-between gap-2 border-b border-border/50 px-4 py-3">
          <p className="min-w-0 flex-1 text-xl font-bold leading-tight tracking-tight text-foreground">
            {msg("explore.picker.subtitle")}
          </p>
          <button
            type="button"
            onClick={onClose}
            aria-label={msg("explore.detail.close")}
            className="inline-flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <ul className="flex flex-col gap-2">
            {list.map((variation, idx) => (
              <li key={variation.optimization_id}>
                <VariationRow variation={variation} onPick={() => setSelectedIndex(idx)} />
              </li>
            ))}
          </ul>
        </div>
      </motion.aside>
    );
  }

  const current = list[selectedIndex ?? 0]!;
  const gain = formatGain(current.baseline_metric, current.optimized_metric);
  const dateText = formatExploreDate(current.created_at);

  return (
    <motion.aside
      key={current.optimization_id}
      initial={{ x: "100%", opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: "100%", opacity: 0 }}
      transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
      dir="rtl"
      className="flex h-full w-full flex-col overflow-hidden rounded-lg border border-border/50 bg-background"
    >
      <header className="flex items-center justify-between gap-2 border-b border-border/50 px-4 py-3">
        {multi && (
          <button
            type="button"
            onClick={() => setSelectedIndex(null)}
            aria-label={msg("explore.picker.back")}
            className="inline-flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
          >
            <ChevronRight className="size-4" />
          </button>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold tracking-tight text-foreground">
            {current.task_name ?? current.optimization_type ?? "—"}
          </p>
          <p
            className="mt-0.5 text-[0.6875rem] text-muted-foreground"
            title={current.created_at ?? undefined}
          >
            {dateText}
          </p>
        </div>
        {!multi && (
          <button
            type="button"
            onClick={onClose}
            aria-label={msg("explore.detail.close")}
            className="inline-flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        )}
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <dl className="space-y-3">
          {current.winning_model && (
            <Row label={msg("explore.detail.model")}>
              <span className="break-all font-mono">{current.winning_model}</span>
            </Row>
          )}
          {current.optimizer_name && (
            <Row label={msg("explore.detail.optimizer")}>
              <span className="font-mono">{current.optimizer_name}</span>
            </Row>
          )}
          {current.optimized_metric != null && (
            <Row label={msg("explore.detail.score")}>
              <span className="inline-flex items-baseline gap-2 font-mono tabular-nums" dir="ltr">
                <span className="text-foreground">{formatMetric(current.optimized_metric)}</span>
                {current.baseline_metric != null && (
                  <span className="text-[0.6875rem] text-muted-foreground">
                    / {formatMetric(current.baseline_metric)}
                  </span>
                )}
                {gain && (
                  <span
                    className={`rounded-sm px-1.5 py-0.5 text-[0.6875rem] ${GAIN_TONE[gain.kind]}`}
                  >
                    {gain.text}
                  </span>
                )}
              </span>
            </Row>
          )}
          {current.module_name && (
            <Row label={msg("explore.detail.module")}>
              <span className="font-mono">{current.module_name}</span>
            </Row>
          )}
        </dl>

        {current.summary_text && (
          <div className="mt-5 border-t border-border/50 pt-4">
            <p className="mb-2 text-[0.625rem] font-semibold uppercase tracking-wider text-muted-foreground">
              {msg("explore.detail.task")}
            </p>
            <p dir="auto" className="text-[0.8125rem] leading-relaxed text-foreground/85">
              {current.summary_text}
            </p>
          </div>
        )}

      </div>

      <footer className="flex items-center gap-3 border-t border-border/50 px-4 py-3">
        <span
          dir="ltr"
          title={current.optimization_id}
          className="min-w-0 flex-1 truncate font-mono text-[0.6875rem] text-muted-foreground"
        >
          {current.optimization_id}
        </span>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button asChild size="icon-sm" variant="default" className="shrink-0">
              <Link
                href={`/optimizations/${current.optimization_id}`}
                aria-label={`${msg("explore.detail.open_action")} ${TERMS.optimization}`}
              >
                <ChevronLeft className="size-3.5" />
              </Link>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top" sideOffset={6}>
            {msg("explore.detail.open_action")} {TERMS.optimization}
          </TooltipContent>
        </Tooltip>
      </footer>
    </motion.aside>
  );
}
