"use client";

import { Tooltip, TooltipTrigger, TooltipContent } from "@/shared/ui/primitives/tooltip";

/**
 * Zero-visual-impact jargon tooltip.
 * Wraps children in a Tooltip that appears on hover.
 * No icons, underlines, or dotted borders — the label looks exactly as before.
 */
export function HelpTip({
  text,
  children,
  side = "top",
}: {
  text: string;
  children: React.ReactNode;
  side?: "top" | "bottom" | "left" | "right";
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="cursor-default">{children}</span>
      </TooltipTrigger>
      <TooltipContent side={side} className="max-w-64 text-center leading-relaxed" dir="rtl">
        {text}
      </TooltipContent>
    </Tooltip>
  );
}
