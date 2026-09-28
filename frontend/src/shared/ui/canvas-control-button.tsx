"use client";

import * as React from "react";

import { cn } from "@/shared/lib/utils";
import { TooltipButton } from "@/shared/ui/tooltip-button";

const CANVAS_FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#C8A882]/45";

/** The bordered strip that holds a canvas's zoom and view controls. */
export function CanvasControlGroup({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "flex items-center overflow-hidden rounded-lg border border-border/60 bg-background/95 shadow-sm backdrop-blur",
        className,
      )}
      {...props}
    />
  );
}

/** Thin separator between control clusters inside a ``CanvasControlGroup``. */
export function CanvasControlDivider() {
  return <span aria-hidden="true" className="h-4 w-px shrink-0 bg-border/70" />;
}

/** Square icon control for canvas zoom, reset and fullscreen actions. */
export function CanvasControlButton({
  icon: Icon,
  label,
  onClick,
  pressed,
  disabled,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  onClick: () => void;
  pressed?: boolean;
  disabled?: boolean;
}) {
  return (
    <TooltipButton tooltip={label}>
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        aria-label={label}
        aria-pressed={pressed}
        className={cn(
          "inline-flex size-8 cursor-pointer items-center justify-center transition-colors disabled:pointer-events-none disabled:opacity-50",
          CANVAS_FOCUS_RING,
          pressed
            ? "bg-foreground text-background hover:bg-foreground/90"
            : "text-muted-foreground hover:bg-accent hover:text-foreground",
        )}
      >
        <Icon className="size-4" />
      </button>
    </TooltipButton>
  );
}

/** Current zoom percentage; clicking it resets the zoom to 100%. */
export function CanvasZoomReadout({
  zoom,
  label,
  onClick,
}: {
  zoom: number;
  label: string;
  onClick: () => void;
}) {
  return (
    <TooltipButton tooltip={label}>
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "h-8 min-w-12 cursor-pointer px-1 text-center text-[0.6875rem] font-medium tabular-nums text-muted-foreground transition-colors hover:text-foreground",
          CANVAS_FOCUS_RING,
        )}
      >
        {Math.round(zoom * 100)}%
      </button>
    </TooltipButton>
  );
}
