"use client";

import * as React from "react";
import { X } from "lucide-react";

import { cn } from "@/shared/lib/utils";

interface FirstRunHintProps {
  onDismiss: () => void;
  className?: string;
}

/**
 * One-time tooltip anchored above the minimized pill that teaches
 * users about the Ctrl+J shortcut. Dismisses permanently on first
 * interaction anywhere on the hint or the pill itself.
 */
export function FirstRunHint({ onDismiss, className }: FirstRunHintProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      dir="rtl"
      className={cn(
        "fixed bottom-[68px] left-4 z-40",
        "max-w-[240px] rounded-2xl border border-[#C8A882]/40 bg-background/95 backdrop-blur-md",
        "px-3.5 py-2.5 shadow-[0_10px_30px_rgba(61,46,34,0.14)]",
        "text-[0.75rem] text-foreground",
        "motion-safe:animate-[fade-in_200ms_ease-out]",
        className,
      )}
    >
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0 leading-snug">
          <div className="font-medium">עוזר חדש</div>
          <div className="text-muted-foreground mt-0.5">
            נסה — <span className="font-mono text-[0.6875rem]">Ctrl+J</span>
          </div>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="סגור"
          className="rounded-md p-0.5 text-muted-foreground hover:bg-accent/60 hover:text-foreground transition-colors cursor-pointer -me-1 -mt-0.5"
        >
          <X className="size-3" />
        </button>
      </div>
      <span
        aria-hidden="true"
        className="absolute -bottom-1.5 left-8 size-3 rotate-45 border-b border-r border-[#C8A882]/40 bg-background/95"
      />
    </div>
  );
}
