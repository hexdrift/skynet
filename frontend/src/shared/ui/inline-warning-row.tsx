"use client";

import * as React from "react";
import { Warning, X } from "@/shared/ui/icons";

import { cn } from "@/shared/lib/utils";
import { msg } from "@/shared/lib/messages";

interface InlineWarningRowProps {
  /** Headline rendered in semibold above the message. Optional. */
  title?: React.ReactNode;
  /** The warning body. Rendered with `dir="auto"` so user-facing strings flip RTL. */
  message: React.ReactNode;
  /** Show a dismiss `×` button when provided. */
  onDismiss?: () => void;
  /** Hide the leading icon (defaults to Warning). */
  hideIcon?: boolean;
  /** ARIA label for the dismiss button. */
  dismissLabel?: string;
  className?: string;
}

/**
 * Warning-tinted counterpart of `InlineErrorRow` for non-blocking notices
 * (truncated data, empty catalogs, guard rails). Uses the `--warning` token so
 * it stays theme-safe without dark-mode overrides.
 */
export function InlineWarningRow({
  title,
  message,
  onDismiss,
  hideIcon = false,
  dismissLabel,
  className,
}: InlineWarningRowProps) {
  return (
    <div
      role="status"
      className={cn(
        "flex items-start gap-2 rounded-lg border border-[var(--warning-border)] bg-[var(--warning-dim)] px-3 py-2 text-xs text-foreground/80",
        className,
      )}
    >
      {!hideIcon && (
        <Warning className="mt-0.5 size-3.5 shrink-0 text-[var(--warning)]" aria-hidden="true" />
      )}
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        <div className={cn("break-words", title && "mt-0.5")} dir="auto">
          {message}
        </div>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label={dismissLabel ?? msg("shared.dismiss")}
          className="close-button shrink-0"
        >
          <X />
        </button>
      )}
    </div>
  );
}
