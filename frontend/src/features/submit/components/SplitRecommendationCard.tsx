"use client";

import { Sparkles, AlertTriangle, Info } from "lucide-react";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/shared/ui/primitives/tooltip";
import { cn } from "@/shared/lib/utils";
import { msg } from "@/shared/lib/messages";

import type { SubmitWizardContext } from "../hooks/use-submit-wizard";

const percent = (value: number): string => `${Math.round(value * 100)}%`;

export function SplitRecommendationCard({ w }: { w: SubmitWizardContext }) {
  const { splitPlan, datasetProfile, splitMode, setSplitMode, profileLoading } = w;

  if (!splitPlan) {
    if (profileLoading) {
      return (
        <div className="rounded-lg border border-[#DDD6CC]/60 bg-[#FAF8F5] px-3 py-2 text-xs text-[#8C7A6B]">
          {msg("submit.split.recommended_title")}…
        </div>
      );
    }
    return null;
  }

  const { fractions, counts, rationale } = splitPlan;
  const warnings = datasetProfile?.warnings ?? [];
  const hasRationale = rationale.length > 0;

  return (
    <div dir="rtl" className="rounded-lg border border-[#C8B9A8]/50 bg-[#FAF8F5] p-3 space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-[#3D2E22]">
          <Sparkles className="h-3.5 w-3.5" />
          <span className="text-xs font-semibold">{msg("submit.split.recommended_title")}</span>
          {hasRationale && (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label={msg("submit.split.rationale_aria")}
                  className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[#8C7A6B] hover:text-[#3D2E22] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/60 transition-colors cursor-default"
                >
                  <Info className="h-3 w-3" />
                </button>
              </TooltipTrigger>
              <TooltipContent
                side="bottom"
                sideOffset={8}
                dir="rtl"
                className="max-w-[280px] rounded-xl border border-[#C8B9A8]/60 bg-[#FAF8F5] px-4 py-3 text-right text-[#3D2E22] shadow-[0_8px_24px_-8px_rgba(61,46,34,0.2)] [&>svg]:fill-[#FAF8F5] [&>svg]:bg-[#FAF8F5]"
              >
                <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold text-[#3D2E22]">
                  <Sparkles className="h-3 w-3 text-[#C8A882]" />
                  {msg("submit.split.rationale_title")}
                </div>
                <ul className="space-y-1.5 text-[11px] leading-relaxed text-[#5C4A3A]">
                  {rationale.map((line, idx) => (
                    <li key={idx} className="flex gap-1.5">
                      <span className="mt-[5px] inline-block h-1 w-1 shrink-0 rounded-full bg-[#C8A882]" />
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
              </TooltipContent>
            </Tooltip>
          )}
        </div>
        <ModeToggle value={splitMode} onChange={setSplitMode} />
      </div>

      {splitMode === "auto" && (
        <div className="space-y-2">
          <div
            dir="ltr"
            className="flex h-2 overflow-hidden rounded-full bg-white/70 ring-1 ring-[#DDD6CC]/80"
          >
            <div
              className="bg-[#3D2E22] transition-[width] duration-300 ease-out"
              style={{ width: `${fractions.train * 100}%` }}
            />
            <div
              className="bg-[#C8A882] transition-[width] duration-300 ease-out"
              style={{ width: `${fractions.val * 100}%` }}
            />
            <div
              className="bg-[#8C7A6B] transition-[width] duration-300 ease-out"
              style={{ width: `${fractions.test * 100}%` }}
            />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <PlanChip
              color="#3D2E22"
              label={msg("submit.split.label_train")}
              percent={percent(fractions.train)}
              count={counts.train}
            />
            <PlanChip
              color="#C8A882"
              label={msg("submit.split.label_val")}
              percent={percent(fractions.val)}
              count={counts.val}
            />
            <PlanChip
              color="#8C7A6B"
              label={msg("submit.split.label_test")}
              percent={percent(fractions.test)}
              count={counts.test}
            />
          </div>
        </div>
      )}

      {warnings.length > 0 && (
        <ul className="space-y-1">
          {warnings.map((warning) => (
            <li
              key={warning.code}
              className="flex items-start gap-1.5 text-[11px] text-[#8C6D4A] leading-snug"
            >
              <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
              <span>{warning.message}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ModeToggle({
  value,
  onChange,
}: {
  value: "auto" | "manual";
  onChange: (mode: "auto" | "manual") => void;
}) {
  return (
    <div className="relative inline-grid grid-cols-2 rounded-lg bg-muted p-1 gap-1">
      <div
        aria-hidden
        className="absolute top-1 bottom-1 w-[calc(50%-6px)] rounded-md bg-background shadow-sm transition-[inset-inline-start] duration-150 ease-out pointer-events-none"
        style={{ insetInlineStart: value === "auto" ? 4 : "calc(50% + 2px)" }}
      />
      {(
        [
          ["auto", msg("submit.split.mode_auto")],
          ["manual", msg("submit.split.mode_manual")],
        ] as const
      ).map(([mode, label]) => (
        <button
          key={mode}
          type="button"
          onClick={() => onChange(mode)}
          aria-pressed={value === mode}
          className={cn(
            "relative z-[1] rounded-md px-4 py-1 text-xs font-medium leading-none text-center transition-colors cursor-pointer",
            value === mode ? "text-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function PlanChip({
  color,
  label,
  percent,
  count,
}: {
  color: string;
  label: string;
  percent: string;
  count: number;
}) {
  return (
    <div className="rounded-md border border-[#DDD6CC]/60 bg-white/60 px-2 py-1.5">
      <div className="flex items-center gap-1.5">
        <span
          className="inline-block w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: color }}
        />
        <span className="text-[11px] text-[#8C7A6B]">{label}</span>
      </div>
      <div className="mt-0.5 flex items-baseline gap-1 text-[#3D2E22]">
        <span className="text-sm font-semibold">{percent}</span>
        <span className="text-[10px] text-[#8C7A6B]">· {count}</span>
      </div>
    </div>
  );
}
