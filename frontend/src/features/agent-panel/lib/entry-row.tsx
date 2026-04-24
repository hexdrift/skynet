"use client";

import * as React from "react";

import { cn } from "@/shared/lib/utils";
import { TERMS } from "@/shared/lib/terms";

export const ARG_LABELS: Record<string, string> = {
  optimization_id: "מזהה",
  template_id: "מזהה תבנית",
  job_id: "מזהה",
  ids: "מזהים",
  optimization_ids: "מזהים",
  name: "שם",
  new_name: "שם חדש",
  pinned: "מוצמד",
  archived: "בארכיון",
  model: TERMS.model,
  optimizer: TERMS.optimizer,
  signature: TERMS.signature,
  metric: TERMS.metric,
  code: "קוד",
  signature_code: `קוד ${TERMS.signature}`,
  metric_code: `קוד ${TERMS.metric}`,
  target: "סוג הקוד",
  kind: "סוג",
  count: "מספר עותקים",
  name_prefix: "תחילית שם",
  value: "מצב חדש",
  sample_id: "מזהה דוגמה",
  dataset_columns: "עמודות",
  dataset: TERMS.dataset,
  column_roles: "תפקידים",
  roles: "תפקידים",
  job_name: "שם ריצה",
  description: "תיאור",
  config: "תצורה",
  model_config: TERMS.modelConfig,
  model_config_override: TERMS.modelConfig,
  optimizer_kwargs: `פרמטרים ל${TERMS.optimizer}`,
  reflection_model_config: TERMS.reflectionModel,
  grid: "רשת ערכים",
  grid_params: "רשת ערכים",
  username: "משתמש",
  status: "סטטוס",
  detail: "פרטים",
  result: "תוצאה",
  id: "מזהה",
  message: "הודעה",
  goal: "מטרה",
  current_signature: `${TERMS.signature} נוכחי`,
  current_metric: `${TERMS.metric} נוכחית`,
  sample_rows: "שורות דוגמה",
  sample_row: "שורת דוגמה",
  assistant_message: "תשובת הסוכן",
  column_mapping: "מיפוי עמודות",
  optimizer_name: `שם ${TERMS.optimizer}`,
  valid: "תקין",
  errors: "שגיאות",
  warnings: "אזהרות",
  error: "שגיאה",
  warning: "אזהרה",
  signature_fields: `שדות ב${TERMS.signature}`,
  inputs: "קלטים",
  outputs: "פלטים",
  score: TERMS.score,
  feedback: "משוב",
  baseline: "בסיס",
  optimized: `אחרי ${TERMS.optimization}`,
  task_type: "סוג משימה",
  rationale: "נימוק",
  summary: "סיכום",
  explanation: "הסבר",
  reason: "סיבה",
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
  if (typeof v === "boolean") return v ? "כן" : "לא";
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
      {value ? "כן" : "לא"}
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
