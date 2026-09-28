"use client";

import * as React from "react";
import { Cpu, ArrowsClockwise } from "@/shared/ui/icons";

import { Badge } from "@/shared/ui/primitives/badge";
import { Button } from "@/shared/ui/primitives/button";
import { CopyGlyph, useCopyToClipboard } from "@/shared/ui/copy-button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/ui/primitives/tooltip";
import { msg } from "@/shared/lib/messages";
import { cn } from "@/shared/lib/utils";
import { getActiveDir } from "@/shared/lib/runtime-locale";

interface MessageActionsProps {
  text: string;
  model?: string | null;
  /** Concrete model the Auto Router picked for this turn, when known. */
  servedModel?: string | null;
  onRegenerate?: () => void;
  className?: string;
}

interface ActionButtonProps {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}

function ActionButton({ label, onClick, children }: ActionButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon-xs" onClick={onClick} aria-label={label}>
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom" dir={getActiveDir()}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}

export function MessageActions({
  text,
  model,
  servedModel,
  onRegenerate,
  className,
}: MessageActionsProps) {
  const { copied, copy } = useCopyToClipboard();

  // Turns routed by OpenRouter's Auto Router (the composer's Auto tiers)
  // report the router's own id — read it back as "Auto", and when the
  // backend resolved the concrete pick, reveal it: "Auto · gemini-3.6-flash".
  const isAutoRouted = !!model && model.startsWith("openrouter/openrouter/auto");
  const served = servedModel ? (servedModel.split("/").pop() ?? servedModel) : null;
  const shortModel = isAutoRouted
    ? served
      ? `${msg("agent.model_menu.auto")} · ${served}`
      : msg("agent.model_menu.auto")
    : model
      ? (model.split("/").pop() ?? model)
      : null;
  const fullModel = isAutoRouted && servedModel ? servedModel : model;

  return (
    <div className={cn("flex items-center gap-1 -ms-1.5", className)}>
      {text.length > 0 && (
        <ActionButton
          label={msg(copied ? "shared.agent.copied" : "shared.agent.copy")}
          onClick={() => void copy(text)}
        >
          <CopyGlyph copied={copied} className="size-3.5" />
        </ActionButton>
      )}
      {onRegenerate && (
        <ActionButton label={msg("shared.agent.regenerate")} onClick={onRegenerate}>
          <ArrowsClockwise className="size-3.5" />
        </ActionButton>
      )}
      <span className="sr-only" role="status" aria-live="polite">
        {copied ? msg("shared.agent.copied") : ""}
      </span>
      {model && shortModel && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge
              variant="ghost"
              size="sm"
              dir="ltr"
              className={cn(
                "ms-1.5 h-[26px] rounded-md px-2 font-mono cursor-default",
                "shadow-none text-muted-foreground/80",
              )}
            >
              <Cpu aria-hidden="true" />
              <span className="truncate max-w-[180px]">{shortModel}</span>
            </Badge>
          </TooltipTrigger>
          <TooltipContent side="top" dir="ltr" className="font-mono">
            {fullModel}
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}
