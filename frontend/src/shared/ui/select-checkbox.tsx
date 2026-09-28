"use client";

import * as React from "react";
import { Check, Minus } from "@/shared/ui/icons";

import { cn } from "@/shared/lib/utils";

/** The shared checkbox box look; ``"mixed"`` fills like checked but shows a dash. */
export function checkboxBoxClass(state: boolean | "mixed") {
  return cn(
    "grid size-5 shrink-0 place-items-center rounded-md border transition-colors duration-150",
    state ? "border-transparent bg-foreground text-background" : "border-border/70 bg-background",
  );
}

function CheckboxMark({ state }: { state: boolean | "mixed" }) {
  if (state === "mixed") return <Minus className="size-3.5" aria-hidden="true" />;
  if (state) return <Check className="size-3.5" aria-hidden="true" />;
  return null;
}

interface SelectCheckboxProps {
  checked: boolean;
  /** Partial selection (select-all headers): filled with a dash, ``aria-checked="mixed"``. */
  indeterminate?: boolean;
  /** ``shiftKey`` is true on shift-click, for range selection. */
  onToggle: (shiftKey: boolean) => void;
  ariaLabel: string;
  disabled?: boolean;
}

/**
 * The rounded multi-select checkbox used by the storage cleanup drawer,
 * extracted so card lists (labeling sessions, datasets) select the same way:
 * plain click toggles, shift-click extends a range. Stops its events so a
 * click or Space press never activates the clickable row behind it.
 */
export function SelectCheckbox({
  checked,
  indeterminate,
  onToggle,
  ariaLabel,
  disabled,
}: SelectCheckboxProps) {
  const state = indeterminate ? "mixed" : checked;
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={state}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation();
        onToggle(e.shiftKey);
      }}
      onKeyDown={(e) => e.stopPropagation()}
      className={cn(
        checkboxBoxClass(state),
        // The ::after grows the 20px box to a 44px hit area without changing its look.
        "relative cursor-pointer after:absolute after:-inset-3 after:content-[''] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/45 disabled:cursor-not-allowed disabled:opacity-50",
        !state && "hover:border-foreground/40",
      )}
    >
      <CheckboxMark state={state} />
    </button>
  );
}

/**
 * Visual-only checkbox for rows that are the control themselves: a
 * ``role="checkbox"`` row with the ``group`` class, or a ``group`` label
 * wrapping a ``peer sr-only`` native input placed right before it.
 */
export function CheckboxIndicator({
  checked,
  indeterminate,
}: {
  checked: boolean;
  indeterminate?: boolean;
}) {
  const state = indeterminate ? "mixed" : checked;
  return (
    <span
      aria-hidden="true"
      className={cn(
        checkboxBoxClass(state),
        "peer-focus-visible:ring-2 peer-focus-visible:ring-[#C8A882]/45 peer-disabled:opacity-50",
        !state && "group-hover:border-foreground/40",
      )}
    >
      <CheckboxMark state={state} />
    </span>
  );
}
