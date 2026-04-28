"use client";

import * as React from "react";
import { formatMsg, msg } from "@/shared/lib/messages";

import { cn } from "@/shared/lib/utils";
import { TERMS } from "@/shared/lib/terms";

export const ARG_LABELS: Record<string, string> = {
  optimization_id: msg("auto.features.agent.panel.lib.entry.row.literal.1"),
  template_id: msg("auto.features.agent.panel.lib.entry.row.literal.2"),
  job_id: msg("auto.features.agent.panel.lib.entry.row.literal.3"),
  ids: msg("auto.features.agent.panel.lib.entry.row.literal.4"),
  optimization_ids: msg("auto.features.agent.panel.lib.entry.row.literal.5"),
  name: msg("auto.features.agent.panel.lib.entry.row.literal.6"),
  new_name: msg("auto.features.agent.panel.lib.entry.row.literal.7"),
  pinned: msg("auto.features.agent.panel.lib.entry.row.literal.8"),
  archived: msg("auto.features.agent.panel.lib.entry.row.literal.9"),
  model: TERMS.model,
  optimizer: TERMS.optimizer,
  signature: TERMS.signature,
  metric: TERMS.metric,
  code: msg("auto.features.agent.panel.lib.entry.row.literal.10"),
  signature_code: formatMsg("auto.features.agent.panel.lib.entry.row.template.1", {
    p1: TERMS.signature,
  }),
  metric_code: formatMsg("auto.features.agent.panel.lib.entry.row.template.2", {
    p1: TERMS.metric,
  }),
  target: msg("auto.features.agent.panel.lib.entry.row.literal.11"),
  kind: msg("auto.features.agent.panel.lib.entry.row.literal.12"),
  count: msg("auto.features.agent.panel.lib.entry.row.literal.13"),
  name_prefix: msg("auto.features.agent.panel.lib.entry.row.literal.14"),
  value: msg("auto.features.agent.panel.lib.entry.row.literal.15"),
  sample_id: msg("auto.features.agent.panel.lib.entry.row.literal.16"),
  dataset_columns: msg("auto.features.agent.panel.lib.entry.row.literal.17"),
  dataset: TERMS.dataset,
  column_roles: msg("auto.features.agent.panel.lib.entry.row.literal.18"),
  roles: msg("auto.features.agent.panel.lib.entry.row.literal.19"),
  job_name: msg("auto.features.agent.panel.lib.entry.row.literal.20"),
  description: msg("auto.features.agent.panel.lib.entry.row.literal.21"),
  config: msg("auto.features.agent.panel.lib.entry.row.literal.22"),
  model_config: TERMS.modelConfig,
  model_config_override: TERMS.modelConfig,
  optimizer_kwargs: formatMsg("auto.features.agent.panel.lib.entry.row.template.3", {
    p1: TERMS.optimizer,
  }),
  reflection_model_config: TERMS.reflectionModel,
  grid: msg("auto.features.agent.panel.lib.entry.row.literal.23"),
  grid_params: msg("auto.features.agent.panel.lib.entry.row.literal.24"),
  username: msg("auto.features.agent.panel.lib.entry.row.literal.25"),
  status: msg("auto.features.agent.panel.lib.entry.row.literal.26"),
  detail: msg("auto.features.agent.panel.lib.entry.row.literal.27"),
  result: msg("auto.features.agent.panel.lib.entry.row.literal.28"),
  id: msg("auto.features.agent.panel.lib.entry.row.literal.29"),
  message: msg("auto.features.agent.panel.lib.entry.row.literal.30"),
  goal: msg("auto.features.agent.panel.lib.entry.row.literal.31"),
  current_signature: formatMsg("auto.features.agent.panel.lib.entry.row.template.4", {
    p1: TERMS.signature,
  }),
  current_metric: formatMsg("auto.features.agent.panel.lib.entry.row.template.5", {
    p1: TERMS.metric,
  }),
  sample_rows: msg("auto.features.agent.panel.lib.entry.row.literal.32"),
  sample_row: msg("auto.features.agent.panel.lib.entry.row.literal.33"),
  assistant_message: msg("auto.features.agent.panel.lib.entry.row.literal.34"),
  column_mapping: msg("auto.features.agent.panel.lib.entry.row.literal.35"),
  optimizer_name: formatMsg("auto.features.agent.panel.lib.entry.row.template.6", {
    p1: TERMS.optimizer,
  }),
  valid: msg("auto.features.agent.panel.lib.entry.row.literal.36"),
  errors: msg("auto.features.agent.panel.lib.entry.row.literal.37"),
  warnings: msg("auto.features.agent.panel.lib.entry.row.literal.38"),
  error: msg("auto.features.agent.panel.lib.entry.row.literal.39"),
  warning: msg("auto.features.agent.panel.lib.entry.row.literal.40"),
  signature_fields: formatMsg("auto.features.agent.panel.lib.entry.row.template.7", {
    p1: TERMS.signature,
  }),
  inputs: msg("auto.features.agent.panel.lib.entry.row.literal.41"),
  outputs: msg("auto.features.agent.panel.lib.entry.row.literal.42"),
  score: TERMS.score,
  feedback: msg("auto.features.agent.panel.lib.entry.row.literal.43"),
  baseline: msg("auto.features.agent.panel.lib.entry.row.literal.44"),
  optimized: formatMsg("auto.features.agent.panel.lib.entry.row.template.8", {
    p1: TERMS.optimization,
  }),
  task_type: msg("auto.features.agent.panel.lib.entry.row.literal.45"),
  rationale: msg("auto.features.agent.panel.lib.entry.row.literal.46"),
  summary: msg("auto.features.agent.panel.lib.entry.row.literal.47"),
  explanation: msg("auto.features.agent.panel.lib.entry.row.literal.48"),
  reason: msg("auto.features.agent.panel.lib.entry.row.literal.49"),
};

function hasHebrewLabel(key: string): boolean {
  return Object.prototype.hasOwnProperty.call(ARG_LABELS, key);
}

export const CODE_KEYS = new Set([
  "code",
  "signature_code",
  "metric_code",
  "current_signature",
  "current_metric",
]);

export const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function shortenId(s: string): string {
  return UUID_RE.test(s) ? s.slice(0, 8) : s;
}

export function formatValue(v: unknown): string {
  if (typeof v === "string") {
    if (v.length > 240) return `${v.slice(0, 237)}…`;
    return v;
  }
  if (typeof v === "boolean")
    return v
      ? msg("auto.features.agent.panel.lib.entry.row.literal.50")
      : msg("auto.features.agent.panel.lib.entry.row.literal.51");
  if (typeof v === "number") return String(v);
  if (v == null) return "—";
  if (Array.isArray(v)) {
    if (v.length === 0) return "—";
    return v.map((x) => (typeof x === "string" ? shortenId(x) : formatValue(x))).join(", ");
  }
  try {
    const json = JSON.stringify(v);
    return json.length > 240 ? `${json.slice(0, 237)}…` : json;
  } catch {
    return String(v);
  }
}

export function isPlainObject(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === "object" && !Array.isArray(v);
}

function BooleanChip({ value }: { value: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[0.625rem] font-medium",
        value ? "bg-[#3D2E22]/10 text-[#3D2E22]" : "bg-[#9B2C1F]/10 text-[#9B2C1F]",
      )}
    >
      <span
        className={cn(
          "inline-block size-1.5 rounded-full",
          value ? "bg-[#3D2E22]/70" : "bg-[#9B2C1F]/70",
        )}
        aria-hidden="true"
      />
      {value
        ? msg("auto.features.agent.panel.lib.entry.row.literal.52")
        : msg("auto.features.agent.panel.lib.entry.row.literal.53")}
    </span>
  );
}

interface EntryRowProps {
  argKey: string;
  value: unknown;
  /** Tailwind classes applied to the dt label (muted tone). */
  labelClassName?: string;
}

/**
 * One row inside an argument / result list. Handles three shapes:
 * code blocks (fenced <pre> with LTR bypass), nested objects (indented
 * sub-list), and scalar values (inline truncated). Shared by both the
 * pending approval card and the completed tool-call disclosure.
 */
export function EntryRow({
  argKey,
  value,
  labelClassName = "text-muted-foreground",
}: EntryRowProps) {
  const hebrewLabel = hasHebrewLabel(argKey);
  const label = ARG_LABELS[argKey] ?? argKey;
  const labelDir = hebrewLabel ? undefined : "ltr";
  const labelFont = hebrewLabel ? "" : "font-mono";

  if (CODE_KEYS.has(argKey) && typeof value === "string" && value.length > 0) {
    return (
      <div className="min-w-0">
        <dt className={cn("mb-1 text-[0.6875rem]", labelFont, labelClassName)} dir={labelDir}>
          {label}
        </dt>
        <pre
          className="whitespace-pre-wrap break-words font-mono text-[0.6875rem] leading-relaxed max-h-52 overflow-y-auto rounded-md border border-border/40 bg-background/70 p-2 text-foreground"
          dir="ltr"
        >
          {value}
        </pre>
      </div>
    );
  }

  if (isPlainObject(value)) {
    const objEntries = Object.entries(value);
    if (objEntries.length === 0) {
      return (
        <div className="flex items-baseline gap-2 min-w-0">
          <dt className={cn("shrink-0 text-[0.6875rem]", labelFont, labelClassName)} dir={labelDir}>
            {label}
          </dt>
          <dd className="text-foreground min-w-0 flex-1 truncate">—</dd>
        </div>
      );
    }
    return (
      <div className="min-w-0">
        <dt className={cn("mb-1 text-[0.6875rem]", labelFont, labelClassName)} dir={labelDir}>
          {label}
        </dt>
        <dl className="ms-2 space-y-0.5 border-s border-border/40 ps-2">
          {objEntries.map(([k, v]) => {
            const innerIsUuid = typeof v === "string" && UUID_RE.test(v);
            const innerHasHebrew = hasHebrewLabel(k);
            const innerLabel = ARG_LABELS[k] ?? k;
            return (
              <div key={k} className="flex items-baseline gap-2 min-w-0">
                <dt
                  className={cn(
                    "shrink-0 text-[0.6875rem]",
                    innerHasHebrew ? "" : "font-mono",
                    labelClassName,
                  )}
                  dir={innerHasHebrew ? undefined : "ltr"}
                >
                  {innerLabel}
                </dt>
                <dd
                  className="text-foreground min-w-0 flex-1 break-words font-mono text-[0.6875rem]"
                  dir={innerIsUuid ? "ltr" : "auto"}
                >
                  {typeof v === "boolean" ? <BooleanChip value={v} /> : formatValue(v)}
                </dd>
              </div>
            );
          })}
        </dl>
      </div>
    );
  }

  if (typeof value === "boolean") {
    return (
      <div className="flex items-baseline gap-2 min-w-0">
        <dt className={cn("shrink-0 text-[0.6875rem]", labelFont, labelClassName)} dir={labelDir}>
          {label}
        </dt>
        <dd className="min-w-0 flex-1">
          <BooleanChip value={value} />
        </dd>
      </div>
    );
  }

  const isArray = Array.isArray(value);
  const isUuid = typeof value === "string" && UUID_RE.test(value);
  const hasUuidItems = isArray && value.some((x) => typeof x === "string" && UUID_RE.test(x));
  return (
    <div className="flex items-baseline gap-2 min-w-0">
      <dt className={cn("shrink-0 text-[0.6875rem]", labelFont, labelClassName)} dir={labelDir}>
        {label}
      </dt>
      <dd
        className={cn(
          "text-foreground min-w-0 flex-1",
          isArray ? "break-words font-mono text-[0.6875rem]" : "truncate",
        )}
        dir={isUuid || hasUuidItems ? "ltr" : "auto"}
      >
        {formatValue(value)}
      </dd>
    </div>
  );
}
