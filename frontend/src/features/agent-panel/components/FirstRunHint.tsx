"use client";

import * as React from "react";
import { X } from "lucide-react";
import { msg } from "@/shared/lib/messages";
import { formatShortcut, useUserPrefs } from "@/features/settings";

import { cn } from "@/shared/lib/utils";

interface FirstRunHintProps {
  onDismiss: () => void;
  className?: string;
}

export function FirstRunHint({ onDismiss, className }: FirstRunHintProps) {
  const { prefs } = useUserPrefs();
  const shortcutLabel = formatShortcut(prefs.agentShortcut);
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
          <div className="font-medium">
            {msg("auto.features.agent.panel.components.firstrunhint.1")}
          </div>
          <div className="text-muted-foreground mt-0.5">
            {msg("auto.features.agent.panel.components.firstrunhint.2")}
            <span className="font-mono text-[0.6875rem]">{shortcutLabel}</span>
          </div>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label={msg("auto.features.agent.panel.components.firstrunhint.literal.1")}
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
