"use client";

import type { ReactNode } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/ui/primitives/tooltip";
import { cn } from "@/shared/lib/utils";
import { getActiveDir } from "@/shared/lib/runtime-locale";
import { radioNavigationIndex } from "@/shared/lib/radio-navigation";

export interface SegmentedOption<T extends string> {
  value: T;
  /** Visible text; for an icon-only control it becomes the accessible name. */
  label: string;
  /** A ``size-3.5`` icon rendered before the label. */
  icon?: ReactNode;
  /** After the label, e.g. a count pill. */
  trailing?: ReactNode;
  desc?: string;
  // Shown while the option is hovered or focused; explains it without taking
  // a line in the card.
  tip?: string;
  /** Accessible name when it should say more than the visible label. */
  ariaLabel?: string;
  /** Native tooltip, e.g. why a disabled option is unavailable. */
  title?: string;
  disabled?: boolean;
}

/**
 * Single-choice segmented control with a sliding pill: a ``radiogroup`` with
 * roving focus and arrow-key navigation. ``size="sm"`` sits inside toolbars
 * and label rows; the default spans its field.
 */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  size = "default",
  iconOnly = false,
  className,
  segmentClassName,
  controls,
}: {
  /** ``null`` when the current state matches none of the options. */
  value: T | null;
  onChange: (v: T) => void;
  options: ReadonlyArray<SegmentedOption<T>>;
  /** Accessible name of the group; omit when a visible label names it already. */
  label?: string;
  size?: "default" | "sm";
  /** Show only the icons; each option's label names it for screen readers. */
  iconOnly?: boolean;
  /** Layout for the track (width, alignment). */
  className?: string;
  /** Layout for every segment (e.g. a fixed width). */
  segmentClassName?: string;
  /** Id of the region the choice swaps, set as every segment's ``aria-controls``. */
  controls?: string;
}) {
  const sm = size === "sm";
  const selectedIndex = options.findIndex((o) => o.value === value);
  const focusIndex = Math.max(0, selectedIndex);
  // Columns are equal, so the pill's box follows from the index alone. It
  // slides on inset-inline-start in the track's own coordinates: a framer
  // layoutId pill projects in page space and drifts vertically whenever the
  // content around the control reflows on the same click.
  const inset = sm ? 2 : 4;
  const count = options.length;
  const segment = `((100% - ${2 * inset + inset * (count - 1)}px) / ${count})`;

  const moveTo = (from: number, key: string, target: HTMLElement) => {
    const rtl = getActiveDir() === "rtl";
    let next = radioNavigationIndex(key, from, options.length, rtl);
    if (next === null) return false;
    // Disabled options are skipped: Home/End walk inward, arrows keep going.
    const walk = key === "Home" ? "ArrowDown" : key === "End" ? "ArrowUp" : key;
    for (let i = 0; i < options.length && options[next]?.disabled; i++) {
      next = radioNavigationIndex(walk, next, options.length, rtl) ?? next;
    }
    const option = options[next];
    if (!option || option.disabled) return false;
    onChange(option.value);
    target.parentElement?.querySelectorAll<HTMLButtonElement>('[role="radio"]')[next]?.focus();
    return true;
  };

  return (
    <div
      className={cn(
        "relative grid rounded-lg bg-muted",
        sm ? "inline-grid w-auto gap-0.5 p-0.5" : "w-full gap-1 p-1",
        className,
      )}
      style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
      role="radiogroup"
      aria-label={label}
    >
      {selectedIndex >= 0 && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute rounded-md bg-background shadow-[0_1px_2px_oklch(0.25_0.04_45/.12)] transition-[inset-inline-start] duration-[180ms] ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none"
          style={{
            top: inset,
            bottom: inset,
            width: `calc(${segment})`,
            insetInlineStart: `calc(${inset}px + ${selectedIndex} * (${segment} + ${inset}px))`,
          }}
        />
      )}
      {options.map((o, index) => {
        const selected = o.value === value;
        const button = (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={o.ariaLabel ?? (iconOnly ? o.label : undefined)}
            aria-controls={controls}
            title={o.title ?? (iconOnly && !o.tip ? o.label : undefined)}
            disabled={o.disabled}
            tabIndex={index === focusIndex ? 0 : -1}
            onKeyDown={(event) => {
              if (moveTo(index, event.key, event.currentTarget)) event.preventDefault();
            }}
            onClick={() => onChange(o.value)}
            className={cn(
              "relative min-w-0 cursor-pointer rounded-md text-center font-medium transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/45 disabled:cursor-not-allowed disabled:opacity-40",
              sm ? "min-h-[44px] px-2.5 py-1 text-xs" : "min-h-[44px] px-2 py-2 text-sm sm:px-3",
              "lg:min-h-0 [@media(hover:none)_and_(pointer:coarse)]:min-h-[44px]",
              selected
                ? "text-foreground"
                : "text-foreground/60 hover:text-foreground disabled:hover:text-foreground/60",
              segmentClassName,
            )}
          >
            <span className="relative z-10 block">
              <span className="flex items-center justify-center gap-1.5">
                {o.icon}
                {iconOnly ? null : <span className="truncate">{o.label}</span>}
                {o.trailing}
              </span>
              {o.desc ? (
                <span
                  className={cn(
                    "mt-0.5 block text-[0.6875rem] font-normal transition-colors duration-200",
                    selected ? "text-muted-foreground" : "text-foreground/40",
                  )}
                >
                  {o.desc}
                </span>
              ) : null}
            </span>
          </button>
        );
        if (!o.tip) return button;
        return (
          <Tooltip key={o.value}>
            <TooltipTrigger asChild>{button}</TooltipTrigger>
            <TooltipContent className="max-w-64 text-center leading-relaxed" dir={getActiveDir()}>
              {o.tip}
            </TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );
}
