"use client";

import * as React from "react";
import Link from "next/link";
import { X, ChevronLeft } from "lucide-react";
import { motion } from "framer-motion";
import type { PublicDashboardPoint } from "@/shared/lib/api";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";

interface ExploreDetailPanelProps {
  point: PublicDashboardPoint;
  onClose: () => void;
}

function formatAgo(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const diffMs = Date.now() - then;
  if (Number.isNaN(diffMs)) return "—";
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "לפני רגע";
  if (mins < 60) return `לפני ${mins} דק׳`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `לפני ${hrs} שע׳`;
  const days = Math.round(hrs / 24);
  return `לפני ${days} ימים`;
}

function formatMetric(v: number | null | undefined): string {
  if (v == null) return "—";
  // dashboard values already on 0-100 scale (see backend/service_gateway/recommendations._extract_scores)
  return v.toFixed(1);
}

function formatGain(baseline: number | null, optimized: number | null): string | null {
  if (baseline == null || optimized == null) return null;
  const gain = optimized - baseline;
  if (gain <= 0) return null;
  return `+${gain.toFixed(1)}`;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] items-baseline gap-3">
      <dt className="text-[0.625rem] font-semibold uppercase tracking-wider text-[#8C7A6B]">
        {label}
      </dt>
      <dd className="min-w-0 text-[0.8125rem] text-[#3D2E22]">{children}</dd>
    </div>
  );
}

export function ExploreDetailPanel({ point, onClose }: ExploreDetailPanelProps) {
  const gain = formatGain(point.baseline_metric, point.optimized_metric);

  return (
    <motion.aside
      key={point.optimization_id}
      initial={{ x: "100%", opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: "100%", opacity: 0 }}
      transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
      dir="rtl"
      className="flex h-full w-full flex-col overflow-hidden rounded-lg border border-[#DDD6CC]/50 bg-[#FAF8F5]"
    >
      <header className="flex items-center justify-between gap-2 border-b border-[#DDD6CC]/50 px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold tracking-tight text-[#3D2E22]">
            {point.task_name ?? point.optimization_type ?? "—"}
          </p>
          <p className="mt-0.5 text-[0.6875rem] text-[#8C7A6B]">
            {msg("explore.detail.time_ago")} {formatAgo(point.created_at).replace(/^לפני /, "")}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="סגור"
          className="inline-flex size-7 cursor-pointer items-center justify-center rounded-md text-[#8C7A6B] transition-colors hover:bg-[#3D2E22]/5 hover:text-[#3D2E22]"
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
              <span
                className="inline-flex items-baseline gap-2 font-mono tabular-nums"
                dir="ltr"
              >
                <span className="text-[#3D2E22]">{formatMetric(point.optimized_metric)}</span>
                {point.baseline_metric != null && (
                  <span className="text-[0.6875rem] text-[#8C7A6B]">
                    / {formatMetric(point.baseline_metric)}
                  </span>
                )}
                {gain && (
                  <span className="rounded-sm bg-[#EDE7DD] px-1.5 py-0.5 text-[0.6875rem] text-[#3D2E22]">
                    {gain}
                  </span>
                )}
              </span>
            </Row>
          )}
          {point.module_name && (
            <Row label="מודול">
              <span className="font-mono">{point.module_name}</span>
            </Row>
          )}
        </dl>

        {point.summary_text && (
          <div className="mt-5 border-t border-[#DDD6CC]/50 pt-4">
            <p className="mb-2 text-[0.625rem] font-semibold uppercase tracking-wider text-[#8C7A6B]">
              {msg("explore.detail.task")}
            </p>
            <p className="text-[0.8125rem] leading-relaxed text-[#3D2E22]/85">
              {point.summary_text}
            </p>
          </div>
        )}
      </div>

      <footer className="flex items-center gap-3 border-t border-[#DDD6CC]/50 px-4 py-3">
        <span
          dir="ltr"
          title={point.optimization_id}
          className="min-w-0 flex-1 truncate font-mono text-[0.6875rem] text-[#8C7A6B]"
        >
          {point.optimization_id}
        </span>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button asChild size="icon-sm" variant="default" className="shrink-0">
              <Link
                href={`/optimizations/${point.optimization_id}`}
                aria-label={`פתח ${TERMS.optimization}`}
              >
                <ChevronLeft className="size-3.5" />
              </Link>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top" sideOffset={6}>
            פתח {TERMS.optimization}
          </TooltipContent>
        </Tooltip>
      </footer>
    </motion.aside>
  );
}
