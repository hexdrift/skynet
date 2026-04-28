"use client";

import * as React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronLeft, ChevronRight, type LucideIcon } from "lucide-react";
import { formatMsg, msg } from "@/shared/lib/messages";

import { cn } from "@/shared/lib/utils";
import { TERMS } from "@/shared/lib/terms";

import { TOOL_META, type ApprovalSeverity } from "../lib/tool-meta";

interface ToolEntry {
  key: string;
  title: string;
  description: string;
  icon: LucideIcon;
  severity: ApprovalSeverity;
}

// Curated subset of TOOL_META. Bulk variants are folded into their singular
// counterparts so the user sees distinct capabilities, not API permutations.
const FEATURED_TOOLS: readonly string[] = [
  "submit_job_run_post",
  "submit_grid_search_grid_search_post",
  "rename_job_optimizations",
  "clone_job_optimizations",
  "retry_job_optimizations",
  "cancel_job_optimizations",
  "delete_job_optimizations",
  "toggle_pin_job_optimizations",
  "toggle_archive_job_optimizations",
  "compare_jobs_optimizations_compare_post",
  "list_jobs_optimizations_get",
  "create_template_templates_post",
  "apply_template_templates",
  "edit_code_optimizations_edit_code_post",
  "validate_code_validate_code_post",
  "profile_datasets_profile_post",
  "stage_sample_dataset_datasets_samples",
  "set_column_roles_datasets_column_roles_post",
  "discover_models_models_discover_post",
  "serve_program_serve",
];

// Tour-oriented descriptions (capabilities, not approval warnings). Fallback
// to TOOL_META.description when a key is missing.
const TOUR_DESCRIPTIONS: Record<string, string> = {
  submit_job_run_post: formatMsg("auto.features.agent.panel.components.toolscarousel.template.1", {
    p1: TERMS.optimization,
  }),
  submit_grid_search_grid_search_post: msg(
    "auto.features.agent.panel.components.toolscarousel.literal.1",
  ),
  rename_job_optimizations: formatMsg(
    "auto.features.agent.panel.components.toolscarousel.template.2",
    { p1: TERMS.optimization },
  ),
  clone_job_optimizations: msg("auto.features.agent.panel.components.toolscarousel.literal.2"),
  retry_job_optimizations: msg("auto.features.agent.panel.components.toolscarousel.literal.3"),
  cancel_job_optimizations: msg("auto.features.agent.panel.components.toolscarousel.literal.4"),
  delete_job_optimizations: formatMsg(
    "auto.features.agent.panel.components.toolscarousel.template.3",
    { p1: TERMS.optimization },
  ),
  toggle_pin_job_optimizations: formatMsg(
    "auto.features.agent.panel.components.toolscarousel.template.4",
    { p1: TERMS.optimization },
  ),
  toggle_archive_job_optimizations: formatMsg(
    "auto.features.agent.panel.components.toolscarousel.template.5",
    { p1: TERMS.optimization },
  ),
  compare_jobs_optimizations_compare_post: msg(
    "auto.features.agent.panel.components.toolscarousel.literal.5",
  ),
  list_jobs_optimizations_get: formatMsg(
    "auto.features.agent.panel.components.toolscarousel.template.6",
    { p1: TERMS.optimizationPlural },
  ),
  create_template_templates_post: msg(
    "auto.features.agent.panel.components.toolscarousel.literal.6",
  ),
  apply_template_templates: msg("auto.features.agent.panel.components.toolscarousel.literal.7"),
  edit_code_optimizations_edit_code_post: formatMsg(
    "auto.features.agent.panel.components.toolscarousel.template.7",
    { p1: TERMS.signature, p2: TERMS.metric },
  ),
  validate_code_validate_code_post: msg(
    "auto.features.agent.panel.components.toolscarousel.literal.8",
  ),
  profile_datasets_profile_post: formatMsg(
    "auto.features.agent.panel.components.toolscarousel.template.8",
    { p1: TERMS.dataset },
  ),
  stage_sample_dataset_datasets_samples: formatMsg(
    "auto.features.agent.panel.components.toolscarousel.template.9",
    { p1: TERMS.dataset },
  ),
  set_column_roles_datasets_column_roles_post: msg(
    "auto.features.agent.panel.components.toolscarousel.literal.9",
  ),
  discover_models_models_discover_post: msg(
    "auto.features.agent.panel.components.toolscarousel.literal.10",
  ),
  serve_program_serve: formatMsg("auto.features.agent.panel.components.toolscarousel.template.10", {
    p1: TERMS.optimization,
  }),
};

const SEVERITY: Record<ApprovalSeverity, { color: string; label: string | null }> = {
  destructive: {
    color: "#9B2C1F",
    label: msg("auto.features.agent.panel.components.toolscarousel.literal.11"),
  },
  warning: { color: "#A85A1A", label: null },
  info: {
    color: "#3D2E22",
    label: msg("auto.features.agent.panel.components.toolscarousel.literal.12"),
  },
};

export function ToolsCarousel() {
  const tools = React.useMemo<ToolEntry[]>(() => {
    const out: ToolEntry[] = [];
    for (const key of FEATURED_TOOLS) {
      const m = TOOL_META[key];
      if (!m) continue;
      out.push({
        key,
        ...m,
        description: TOUR_DESCRIPTIONS[key] ?? m.description,
      });
    }
    return out;
  }, []);

  const [idx, setIdx] = React.useState(0);
  const [dir, setDir] = React.useState<1 | -1>(-1);
  const reduceMotion = useReducedMotion();

  const go = React.useCallback(
    (next: number) => {
      const clamped = Math.max(0, Math.min(tools.length - 1, next));
      setDir(clamped > idx ? -1 : 1);
      setIdx(clamped);
    },
    [idx, tools.length],
  );

  const onKey = React.useCallback(
    (e: React.KeyboardEvent) => {
      // In RTL context, ArrowLeft = forward (next), ArrowRight = backward (prev).
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        go(idx + 1);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        go(idx - 1);
      }
    },
    [go, idx],
  );

  const active = tools[idx];
  if (!active) return null;

  return (
    <div
      className="w-[min(300px,calc(100vw-2rem))] p-3 select-none outline-none focus:outline-none focus-visible:outline-none"
      dir="rtl"
      role="region"
      aria-label={msg("auto.features.agent.panel.components.toolscarousel.literal.13")}
      tabIndex={0}
      onKeyDown={onKey}
    >
      <div className="mb-2.5 flex items-baseline justify-between gap-2">
        <span className="text-[0.8125rem] font-medium text-foreground">
          {msg("auto.features.agent.panel.components.toolscarousel.1")}
        </span>
        <span className="font-mono tabular-nums text-[0.625rem] text-muted-foreground/70">
          {idx + 1} / {tools.length}
        </span>
      </div>

      <div className="relative h-[132px] overflow-hidden rounded-xl">
        <AnimatePresence custom={dir} mode="popLayout" initial={false}>
          <motion.div
            key={active.key}
            custom={dir}
            variants={{
              enter: (d: 1 | -1) => ({
                x: reduceMotion ? 0 : d * 28,
                opacity: 0,
              }),
              center: { x: 0, opacity: 1 },
              exit: (d: 1 | -1) => ({
                x: reduceMotion ? 0 : d * -28,
                opacity: 0,
              }),
            }}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.18, ease: [0.2, 0.8, 0.2, 1] }}
            className="absolute inset-0"
          >
            <ToolCard tool={active} />
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="mt-2.5 flex items-center justify-center gap-1">
        {tools.map((t, i) => (
          <button
            key={t.key}
            type="button"
            onClick={() => go(i)}
            aria-label={formatMsg(
              "auto.features.agent.panel.components.toolscarousel.template.11",
              { p1: i + 1, p2: tools.length },
            )}
            aria-current={i === idx ? "true" : undefined}
            className={cn(
              "h-1.5 rounded-full transition-all duration-200 cursor-pointer",
              "outline-none focus:outline-none focus-visible:outline-none",
              i === idx ? "w-4 bg-[#3D2E22]/70" : "w-1.5 bg-[#3D2E22]/20 hover:bg-[#3D2E22]/40",
            )}
          />
        ))}
      </div>

      <div className="mt-2.5 flex items-center justify-between gap-2">
        {/* Prev: visually on the RIGHT in RTL (rightmost = flex start). */}
        <NavButton direction="prev" disabled={idx === 0} onClick={() => go(idx - 1)} />
        <NavButton
          direction="next"
          disabled={idx >= tools.length - 1}
          onClick={() => go(idx + 1)}
        />
      </div>
    </div>
  );
}

function ToolCard({ tool }: { tool: ToolEntry }) {
  const Icon = tool.icon;
  const sev = SEVERITY[tool.severity];
  return (
    <div className="h-full w-full p-3.5">
      <div className="flex items-center gap-2.5 mb-2.5">
        <span
          className="inline-flex size-9 items-center justify-center rounded-full shrink-0"
          style={{
            backgroundColor: `${sev.color}14`,
            color: sev.color,
          }}
        >
          <Icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[0.8125rem] font-medium leading-tight truncate">{tool.title}</div>
          {sev.label && (
            <div className="mt-0.5 flex items-center gap-1.5">
              <span
                className="inline-block size-1 rounded-full shrink-0"
                style={{ backgroundColor: sev.color, opacity: 0.55 }}
                aria-hidden="true"
              />
              <span className="text-[0.625rem] text-muted-foreground/75">{sev.label}</span>
            </div>
          )}
        </div>
      </div>
      <p className="text-[0.75rem] leading-relaxed text-foreground/75 line-clamp-3">
        {tool.description}
      </p>
    </div>
  );
}

function NavButton({
  direction,
  disabled,
  onClick,
}: {
  direction: "prev" | "next";
  disabled: boolean;
  onClick: () => void;
}) {
  // In RTL reading flow: "prev" = step backwards = rightward chevron;
  // "next" = step forwards = leftward chevron.
  const Icon = direction === "prev" ? ChevronRight : ChevronLeft;
  const label =
    direction === "prev"
      ? msg("auto.features.agent.panel.components.toolscarousel.literal.14")
      : msg("auto.features.agent.panel.components.toolscarousel.literal.15");
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className={cn(
        "inline-flex size-7 items-center justify-center rounded-full",
        "border border-border/50 bg-background/85",
        "transition-all duration-150 cursor-pointer",
        "outline-none focus:outline-none focus-visible:outline-none",
        "hover:bg-accent/60 hover:border-border active:scale-[0.96]",
        "disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-background/85",
      )}
    >
      <Icon className="size-3.5 text-foreground/70" aria-hidden="true" />
    </button>
  );
}
