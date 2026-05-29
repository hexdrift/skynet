"use client";

import { msg } from "@/shared/lib/messages";

import { cn } from "@/shared/lib/utils";

import {
  ARG_LABELS,
  CODE_KEYS,
  UUID_RE,
  formatValue,
  hasHebrewLabel,
  isPlainObject,
} from "../lib/entry-format";

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
  labelClassName = "text-muted-foreground/70",
}: EntryRowProps) {
  const hebrewLabel = hasHebrewLabel(argKey);
  const label = ARG_LABELS[argKey] ?? argKey;
  const labelDir = hebrewLabel ? undefined : "ltr";
  const labelFont = hebrewLabel ? "" : "font-mono";
  const labelBase = cn("text-[0.6875rem]/[1.55]", labelFont, labelClassName);
  const valueClasses = "text-foreground/90 text-[0.6875rem]/[1.55]";

  if (CODE_KEYS.has(argKey) && typeof value === "string" && value.length > 0) {
    return (
      <div className="min-w-0">
        <dt className={cn("mb-1", labelBase)} dir={labelDir}>
          {label}
        </dt>
        <pre
          className="whitespace-pre-wrap break-words font-mono text-[0.6875rem]/[1.55] max-h-52 overflow-y-auto rounded-md border border-border/40 bg-background/70 p-2 text-foreground/90"
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
          <dt className={cn("shrink-0", labelBase)} dir={labelDir}>
            {label}
          </dt>
          <dd className="min-w-0 flex-1 truncate text-[0.6875rem]/[1.55] text-muted-foreground/60">
            —
          </dd>
        </div>
      );
    }
    return (
      <div className="min-w-0">
        <dt className={cn("mb-1", labelBase)} dir={labelDir}>
          {label}
        </dt>
        <dl className="ms-2 space-y-1 border-s border-border/40 ps-2">
          {objEntries.map(([k, v]) => {
            const innerIsUuid = typeof v === "string" && UUID_RE.test(v);
            const innerHasHebrew = hasHebrewLabel(k);
            const innerLabel = ARG_LABELS[k] ?? k;
            return (
              <div key={k} className="flex items-baseline gap-2 min-w-0">
                <dt
                  className={cn(
                    "shrink-0 text-[0.6875rem]/[1.55]",
                    innerHasHebrew ? "" : "font-mono",
                    labelClassName,
                  )}
                  dir={innerHasHebrew ? undefined : "ltr"}
                >
                  {innerLabel}
                </dt>
                <dd
                  className={cn(valueClasses, "min-w-0 flex-1 break-words font-mono")}
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
        <dt className={cn("shrink-0", labelBase)} dir={labelDir}>
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
  const isNumber = typeof value === "number";
  const hasUuidItems = isArray && value.some((x) => typeof x === "string" && UUID_RE.test(x));
  const isEmpty = value == null || value === "";
  const useMono = isArray || isUuid || isNumber;
  return (
    <div className="flex items-baseline gap-2 min-w-0">
      <dt className={cn("shrink-0", labelBase)} dir={labelDir}>
        {label}
      </dt>
      <dd
        className={cn(
          valueClasses,
          "min-w-0 flex-1",
          isArray ? "break-words" : "truncate",
          useMono && "font-mono",
          isEmpty && "text-muted-foreground/60",
        )}
        dir={isUuid || hasUuidItems ? "ltr" : "auto"}
      >
        {formatValue(value)}
      </dd>
    </div>
  );
}
