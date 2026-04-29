"use client";

import * as React from "react";
import Link from "next/link";
import { X, ChevronLeft } from "lucide-react";
import { motion } from "framer-motion";
import type { PublicDashboardPoint } from "@/shared/lib/api";
import { Button } from "@/shared/ui/primitives/button";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/shared/ui/primitives/tooltip";
import { msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";
import { formatAgo, formatGain, formatMetric } from "../lib/format";

interface ExploreDetailPanelProps {
  point: PublicDashboardPoint;
  onClose: () => void;
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

export function ExploreDetailPanel({ point, onClose }: ExploreDetailPanelProps) {
  const gain = formatGain(point.baseline_metric, point.optimized_metric);
  const ago = formatAgo(point.created_at);
  const timeAgoText = ago ? `${msg("explore.detail.time_ago")} ${ago}` : "—";

  return (
    <motion.aside
      key={point.optimization_id}
      initial={{ x: "100%", opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: "100%", opacity: 0 }}
      transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
      dir="rtl"
      className="flex h-full w-full flex-col overflow-hidden rounded-lg border border-border/50 bg-background"
    >
      <header className="flex items-center justify-between gap-2 border-b border-border/50 px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold tracking-tight text-foreground">
            {point.task_name ?? point.optimization_type ?? "—"}
          </p>
          <p
            className="mt-0.5 text-[0.6875rem] text-muted-foreground"
            title={point.created_at ?? undefined}
          >
            {timeAgoText}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label={msg("explore.detail.close")}
          className="inline-flex size-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <dl className="space-y-3">
          {point.winning_model && (
            <Row label={msg("explore.detail.model")}>
              <span className="break-all font-mono">{point.winning_model}</span>
            </Row>
          )}
          {point.optimizer_name && (
            <Row label={msg("explore.detail.optimizer")}>
              <span className="font-mono">{point.optimizer_name}</span>
            </Row>
          )}
          {point.optimized_metric != null && (
            <Row label={msg("explore.detail.score")}>
              <span className="inline-flex items-baseline gap-2 font-mono tabular-nums" dir="ltr">
                <span className="text-foreground">{formatMetric(point.optimized_metric)}</span>
                {point.baseline_metric != null && (
                  <span className="text-[0.6875rem] text-muted-foreground">
                    / {formatMetric(point.baseline_metric)}
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
          {point.module_name && (
            <Row label={msg("explore.detail.module")}>
              <span className="font-mono">{point.module_name}</span>
            </Row>
          )}
        </dl>

        {point.summary_text && (
          <div className="mt-5 border-t border-border/50 pt-4">
            <p className="mb-2 text-[0.625rem] font-semibold uppercase tracking-wider text-muted-foreground">
              {msg("explore.detail.task")}
            </p>
            <p className="text-[0.8125rem] leading-relaxed text-foreground/85">
              {point.summary_text}
            </p>
          </div>
        )}
      </div>

      <footer className="flex items-center gap-3 border-t border-border/50 px-4 py-3">
        <span
          dir="ltr"
          title={point.optimization_id}
          className="min-w-0 flex-1 truncate font-mono text-[0.6875rem] text-muted-foreground"
        >
          {point.optimization_id}
        </span>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button asChild size="icon-sm" variant="default" className="shrink-0">
              <Link
                href={`/optimizations/${point.optimization_id}`}
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
