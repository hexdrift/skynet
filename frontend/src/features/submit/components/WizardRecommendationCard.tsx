"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, Info, Sparkles, X } from "lucide-react";

import { Button } from "@/shared/ui/primitives/button";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/shared/ui/primitives/tooltip";
import { msg } from "@/shared/lib/messages";
import { fetchSimilarJobs, type SimilarJob } from "@/shared/lib/api";
import { cn } from "@/shared/lib/utils";
import { useUserPrefs } from "@/features/settings";

import type { SubmitWizardContext } from "../hooks/use-submit-wizard";

const SIGNATURE_MIN_CHARS = 30;
const DEBOUNCE_MS = 800;
const DISMISS_KEY = "skynet:rec-dismissed";
const HIT_SCORE_THRESHOLD = 0.45;

type CardView =
  | { kind: "hidden" }
  | { kind: "loading" }
  | { kind: "hit"; job: SimilarJob }
  | { kind: "cold"; coldDefault: ColdDefault };

interface ColdDefault {
  optimizer_name: string;
  optimizer_kwargs: Record<string, unknown>;
  module_name: string;
  summary: string;
}

const COLD_DEFAULTS = {
  run: {
    optimizer_name: "gepa",
    optimizer_kwargs: { auto: "light", reflection_minibatch_size: 3, use_merge: true },
    module_name: "dspy.ChainOfThought",
    summary: msg("submit.rec.cold_run_summary"),
  },
  grid_search: {
    optimizer_name: "gepa",
    optimizer_kwargs: { auto: "light", reflection_minibatch_size: 3, use_merge: true },
    module_name: "dspy.ChainOfThought",
    summary: msg("submit.rec.cold_grid_summary"),
  },
} satisfies Record<string, ColdDefault>;

function coldDefaultFor(kind: string): ColdDefault {
  return kind === "grid_search" ? COLD_DEFAULTS.grid_search : COLD_DEFAULTS.run;
}

function buildDatasetSchema(
  columnRoles: Record<string, "input" | "output" | "ignore">,
  sampleRow: Record<string, unknown> | null,
): { columns: Array<{ name: string; role: "input" | "output" | "ignore"; dtype: string }> } | null {
  if (!Object.keys(columnRoles).length) return null;
  return {
    columns: Object.entries(columnRoles).map(([name, role]) => ({
      name,
      role,
      dtype: inferDtype(sampleRow?.[name]),
    })),
  };
}

function inferDtype(value: unknown): string {
  if (value === null || value === undefined) return "unknown";
  if (typeof value === "number") return Number.isInteger(value) ? "int" : "float";
  if (typeof value === "boolean") return "bool";
  return "str";
}

function trimmedLength(s: string | null | undefined): number {
  return (s ?? "").trim().length;
}

function useDismissed(): [boolean, () => void, () => void] {
  const [dismissed, setDismissed] = React.useState(false);
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    setDismissed(sessionStorage.getItem(DISMISS_KEY) === "1");
  }, []);
  const dismiss = React.useCallback(() => {
    if (typeof window !== "undefined") sessionStorage.setItem(DISMISS_KEY, "1");
    setDismissed(true);
  }, []);
  const reset = React.useCallback(() => {
    if (typeof window !== "undefined") sessionStorage.removeItem(DISMISS_KEY);
    setDismissed(false);
  }, []);
  return [dismissed, dismiss, reset];
}

export function WizardRecommendationCard({ w }: { w: SubmitWizardContext }) {
  const { prefs } = useUserPrefs();
  if (!prefs.advancedMode) return null;
  return <WizardRecommendationCardInner w={w} />;
}

function WizardRecommendationCardInner({ w }: { w: SubmitWizardContext }) {
  const {
    signatureCode,
    metricCode,
    columnRoles,
    parsedDataset,
    jobType,
    setOptimizerName,
    setModuleName,
    setAutoLevel,
    setReflectionMinibatchSize,
    setUseMerge,
    step,
  } = w;

  const [view, setView] = React.useState<CardView>({ kind: "hidden" });
  const [expanded, setExpanded] = React.useState(false);
  const [appliedPulse, setAppliedPulse] = React.useState(false);
  const [dismissed, dismiss] = useDismissed();

  const isCodeOrLaterStep = step >= 3;
  const hasDrafted = trimmedLength(signatureCode) >= SIGNATURE_MIN_CHARS;

  const schema = React.useMemo(
    () => buildDatasetSchema(columnRoles, parsedDataset?.rows?.[0] ?? null),
    [columnRoles, parsedDataset],
  );

  React.useEffect(() => {
    if (!isCodeOrLaterStep || !hasDrafted || dismissed) {
      setView({ kind: "hidden" });
      return;
    }

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setView({ kind: "loading" });
      try {
        const hits = await fetchSimilarJobs(
          {
            signature_code: signatureCode,
            metric_code: metricCode,
            dataset_schema: schema,
            optimization_type: jobType,
            top_k: 1,
          },
          controller.signal,
        );
        if (controller.signal.aborted) return;
        const top = hits[0];
        if (top && top.score >= HIT_SCORE_THRESHOLD) {
          setView({ kind: "hit", job: top });
        } else {
          setView({ kind: "cold", coldDefault: coldDefaultFor(jobType) });
        }
      } catch {
        if (!controller.signal.aborted) {
          setView({ kind: "hidden" });
        }
      }
    }, DEBOUNCE_MS);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [signatureCode, metricCode, schema, jobType, hasDrafted, isCodeOrLaterStep, dismissed]);

  const applyRun = React.useCallback(
    (opts: {
      optimizer_name?: string | null;
      module_name?: string | null;
      optimizer_kwargs?: Record<string, unknown>;
    }) => {
      if (opts.optimizer_name) setOptimizerName(opts.optimizer_name);
      if (opts.module_name) setModuleName(opts.module_name);
      const kw = opts.optimizer_kwargs ?? {};
      if (typeof kw.auto === "string") setAutoLevel(kw.auto);
      if (typeof kw.reflection_minibatch_size === "number") {
        setReflectionMinibatchSize(String(kw.reflection_minibatch_size));
      }
      if (typeof kw.use_merge === "boolean") setUseMerge(kw.use_merge);
      setAppliedPulse(true);
      window.setTimeout(() => {
        setAppliedPulse(false);
        setView({ kind: "hidden" });
        dismiss();
      }, 1500);
    },
    [
      setOptimizerName,
      setModuleName,
      setAutoLevel,
      setReflectionMinibatchSize,
      setUseMerge,
      dismiss,
    ],
  );

  const onApply = React.useCallback(() => {
    if (view.kind === "hit") {
      applyRun({
        optimizer_name: view.job.optimizer_name,
        module_name: view.job.module_name,
        optimizer_kwargs: view.job.optimizer_kwargs,
      });
    } else if (view.kind === "cold") {
      applyRun({
        optimizer_name: view.coldDefault.optimizer_name,
        module_name: view.coldDefault.module_name,
        optimizer_kwargs: view.coldDefault.optimizer_kwargs,
      });
    }
  }, [view, applyRun]);

  const onKeyDown = React.useCallback(
    (e: React.KeyboardEvent<HTMLElement>) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        dismiss();
        setView({ kind: "hidden" });
      } else if (e.key === "Enter" && (view.kind === "hit" || view.kind === "cold")) {
        e.preventDefault();
        onApply();
      }
    },
    [dismiss, onApply, view.kind],
  );

  if (view.kind === "hidden") return null;

  return (
    <AnimatePresence>
      <motion.aside
        key="rec-card"
        dir="rtl"
        role="complementary"
        aria-label={msg("submit.rec.label")}
        tabIndex={0}
        onKeyDown={onKeyDown}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 8 }}
        transition={{ duration: 0.18, ease: [0.2, 0.8, 0.2, 1] }}
        className={cn(
          "fixed z-40 w-[min(360px,calc(100vw-2rem))] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/60 focus-visible:rounded-lg",
          "bottom-4 start-4 md:start-[calc(clamp(200px,16vw,240px)+1rem)]",
        )}
      >
        {appliedPulse ? (
          <div className="flex items-center gap-2 rounded-lg border border-[#DDD6CC]/80 bg-[#FAF8F5] px-4 py-3 shadow-sm">
            <Check className="h-4 w-4 text-[#3D2E22]" />
            <span className="text-sm text-[#3D2E22]">{msg("submit.rec.applied")}</span>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-[#DDD6CC]/70 bg-[#FAF8F5] shadow-sm">
            <CardHeader
              view={view}
              onDismiss={() => {
                dismiss();
                setView({ kind: "hidden" });
              }}
            />
            <CardBody view={view} expanded={expanded} />
            <CardFooter
              view={view}
              expanded={expanded}
              onToggle={() => setExpanded((v) => !v)}
              onApply={onApply}
            />
          </div>
        )}
      </motion.aside>
    </AnimatePresence>
  );
}

function CardHeader({ view, onDismiss }: { view: CardView; onDismiss: () => void }) {
  const showQualityInfo = view.kind === "hit";
  return (
    <div className="flex items-center justify-between gap-2 border-b border-[#DDD6CC]/60 px-4 py-2.5">
      <div className="flex items-center gap-2 min-w-0">
        <Sparkles className="h-3.5 w-3.5 text-[#C8A882] shrink-0" aria-hidden />
        <span className="text-[11px] font-semibold uppercase tracking-wide text-[#8C7A6B] truncate">
          {view.kind === "cold" ? msg("submit.rec.cold_title") : msg("submit.rec.label")}
        </span>
        {view.kind === "hit" && typeof view.job.score === "number" && (
          <span className="text-[11px] text-[#8C7A6B] whitespace-nowrap">
            · {Math.round(view.job.score * 100)}% {msg("submit.rec.match_suffix")}
          </span>
        )}
        {showQualityInfo && (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label={msg("submit.rec.recommendability_tooltip")}
                className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[#8C7A6B] hover:text-[#3D2E22] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/60 transition-colors cursor-default"
              >
                <Info className="h-3 w-3" />
              </button>
            </TooltipTrigger>
            <TooltipContent
              side="top"
              sideOffset={6}
              dir="rtl"
              className="max-w-[260px] rounded-xl border border-[#C8B9A8]/60 bg-[#FAF8F5] px-3 py-2 text-right text-[11px] leading-relaxed text-[#3D2E22] shadow-[0_8px_24px_-8px_rgba(61,46,34,0.2)] [&>svg]:fill-[#FAF8F5] [&>svg]:bg-[#FAF8F5]"
            >
              {msg("submit.rec.recommendability_tooltip")}
            </TooltipContent>
          </Tooltip>
        )}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label={msg("submit.rec.dismiss")}
        className="text-[#8C7A6B] hover:text-[#3D2E22] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/60 rounded-sm cursor-pointer shrink-0"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

function CardBody({ view, expanded }: { view: CardView; expanded: boolean }) {
  if (view.kind === "loading") {
    return (
      <div className="space-y-2 px-4 py-3">
        <div className="h-3 w-3/4 animate-pulse rounded bg-[#EDE7DD]" />
        <div className="h-3 w-1/2 animate-pulse rounded bg-[#EDE7DD]" />
      </div>
    );
  }

  if (view.kind === "cold") {
    const c = view.coldDefault;
    return (
      <div className="space-y-2 px-4 py-3">
        <p className="text-xs leading-relaxed text-[#5C4A3A]">{msg("submit.rec.cold_body")}</p>
        <div className="flex flex-wrap gap-1.5">
          <Pill>{c.optimizer_name}</Pill>
          <Pill>{c.module_name.replace("dspy.", "")}</Pill>
        </div>
      </div>
    );
  }

  if (view.kind === "hit") {
    const j = view.job;
    const description = j.summary_text ?? j.task_name ?? "";
    const gain =
      j.baseline_metric !== null && j.optimized_metric !== null
        ? msg("submit.rec.from_to")
            .replace("{baseline}", j.baseline_metric.toFixed(1))
            .replace("{optimized}", j.optimized_metric.toFixed(1))
        : null;
    return (
      <div className="space-y-2.5 px-4 py-3">
        {description && (
          <p dir="auto" className="text-xs leading-relaxed text-[#3D2E22] line-clamp-3">
            {description}
          </p>
        )}
        <div className="flex flex-wrap gap-1.5">
          {j.winning_model && <Pill>{j.winning_model}</Pill>}
          {j.optimizer_name && <Pill>{j.optimizer_name}</Pill>}
          {j.module_name && <Pill>{j.module_name.replace("dspy.", "")}</Pill>}
        </div>
        {gain && (
          <div className="flex items-baseline gap-1.5 text-[11px] text-[#8C7A6B]">
            <span>{msg("submit.rec.gain_label")}:</span>
            <span className="font-mono text-[#3D2E22]">{gain}</span>
          </div>
        )}
        {expanded && j.signature_code && (
          <pre
            dir="ltr"
            className="mt-2 max-h-48 overflow-auto rounded-md border border-[#DDD6CC]/60 bg-white/60 p-2 text-[10px] leading-relaxed text-[#3D2E22] font-mono"
          >
            {j.signature_code}
          </pre>
        )}
      </div>
    );
  }

  return null;
}

function CardFooter({
  view,
  expanded,
  onToggle,
  onApply,
}: {
  view: CardView;
  expanded: boolean;
  onToggle: () => void;
  onApply: () => void;
}) {
  if (view.kind === "loading") return <div className="h-9" />;
  const canExpand = view.kind === "hit";
  return (
    <div className="flex items-center gap-2 border-t border-[#DDD6CC]/60 px-3 py-2">
      <Button size="xs" variant="default" onClick={onApply}>
        {msg("submit.rec.apply")}
      </Button>
      {canExpand && (
        <Button size="xs" variant="ghost" onClick={onToggle}>
          {expanded ? msg("submit.rec.hide_details") : msg("submit.rec.details")}
        </Button>
      )}
    </div>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full border border-[#DDD6CC]/70 bg-white/70 px-2 py-0.5 font-mono text-[10px] text-[#3D2E22]">
      {children}
    </span>
  );
}
