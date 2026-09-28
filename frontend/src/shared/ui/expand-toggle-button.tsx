"use client";
import * as React from "react";
import { ArrowsIn, ArrowsOut } from "@/shared/ui/icons";
import { Button } from "@/shared/ui/primitives/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/ui/primitives/tooltip";
import { msg } from "@/shared/lib/messages";

/** The grow/shrink toggle for tables and dialogs that can fill the screen. */
export function ExpandToggleButton({
  ref,
  expanded,
  controls,
  onToggle,
  className,
}: {
  ref?: React.Ref<HTMLButtonElement>;
  expanded: boolean;
  /** Id of the element that grows. */
  controls?: string;
  onToggle: () => void;
  className?: string;
}) {
  const label = msg(expanded ? "shared.expand_toggle.collapse" : "shared.expand_toggle.expand");
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          ref={ref}
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={label}
          aria-expanded={expanded}
          aria-controls={controls}
          onClick={onToggle}
          className={className}
        >
          {expanded ? (
            <ArrowsIn className="size-[1.05rem] text-primary" aria-hidden="true" />
          ) : (
            <ArrowsOut className="size-[1.05rem] text-primary" aria-hidden="true" />
          )}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
