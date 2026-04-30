"use client";

import * as React from "react";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/ui/primitives/tooltip";

interface TooltipButtonProps {
  /** Tooltip body. Pass `null` to skip the tooltip wrapper entirely. */
  tooltip: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  /** Tooltip text direction; useful for RTL apps that want LTR tooltip strings. */
  dir?: "ltr" | "rtl";
  delayDuration?: number;
  /**
   * The interactive element to wrap. Must accept a ref forwarded by Radix
   * (e.g. `<button>`, `<Button asChild>`, `<PopoverTrigger asChild>`).
   */
  children: React.ReactElement;
  contentClassName?: string;
}

/**
 * Bundles the `<TooltipProvider><Tooltip><TooltipTrigger asChild>...</...><TooltipContent>...`
 * boilerplate so call sites only need to pass the trigger element and tooltip
 * text. The trigger element keeps its own styling — this is purely a wrapping
 * helper, not an opinionated icon button.
 */
export function TooltipButton({
  tooltip,
  side = "bottom",
  dir,
  delayDuration,
  children,
  contentClassName,
}: TooltipButtonProps) {
  if (tooltip == null) return children;
  return (
    <TooltipProvider delayDuration={delayDuration}>
      <Tooltip>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipContent side={side} dir={dir} className={contentClassName}>
          {tooltip}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
