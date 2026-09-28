"use client";

import type * as React from "react";
import { CircleNotch, X } from "@/shared/ui/icons";
import { Button } from "@/shared/ui/primitives/button";
import { TOUCH_FIELD_SM } from "@/shared/ui/touch";
import { msg } from "@/shared/lib/messages";
import { cn } from "@/shared/lib/utils";

/**
 * The full-width Cancel / submit pair under a credential form's fields,
 * split into two equal halves in the same order as dialog footers.
 */
export function KeyFormActions({
  submitLabel,
  submitIcon,
  busy,
  disabled,
  onSubmit,
  onCancel,
}: {
  submitLabel: string;
  submitIcon: React.ReactNode;
  busy: boolean;
  disabled: boolean;
  onSubmit: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <Button
        variant="outline"
        size="sm"
        onClick={onCancel}
        className={cn(TOUCH_FIELD_SM, "w-full")}
      >
        <X className="size-4" aria-hidden="true" />
        {msg("settings.keys.cancel")}
      </Button>
      <Button
        size="sm"
        onClick={onSubmit}
        disabled={disabled}
        aria-busy={busy || undefined}
        className={cn(TOUCH_FIELD_SM, "w-full")}
      >
        {busy ? (
          <CircleNotch
            className="size-4 animate-spin motion-reduce:animate-none"
            aria-hidden="true"
          />
        ) : (
          submitIcon
        )}
        {submitLabel}
      </Button>
    </div>
  );
}
