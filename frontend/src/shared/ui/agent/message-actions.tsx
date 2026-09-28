"use client";

import * as React from "react";
import { Cpu, ArrowsClockwise, Info } from "@/shared/ui/icons";

import { Badge } from "@/shared/ui/primitives/badge";
import { Button } from "@/shared/ui/primitives/button";
import { CopyGlyph, useCopyToClipboard } from "@/shared/ui/copy-button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/ui/primitives/tooltip";
import { formatMsg, msg } from "@/shared/lib/messages";
import { cn } from "@/shared/lib/utils";
import { getActiveDir, getActiveIntlLocale } from "@/shared/lib/runtime-locale";
import type { TurnStats } from "./types";

interface MessageActionsProps {
  text: string;
  model?: string | null;
  /** Concrete model the Auto Router picked for this turn, when known. */
  servedModel?: string | null;
  stats?: TurnStats | null;
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

function formatSeconds(ms: number, locale: string): string {
  const seconds = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(ms / 1000);
  return `${seconds}${msg("shared.agent.seconds_short")}`;
}

/** Tooltip rows for a turn's token usage and timing; empty when nothing was measured. */
function statRows(stats: TurnStats | null | undefined): Array<{ label: string; value: string }> {
  if (!stats) return [];
  const locale = getActiveIntlLocale();
  const count = new Intl.NumberFormat(locale);
  const rows: Array<{ label: string; value: string }> = [];
  if (stats.inputTokens != null) {
    rows.push({
      label: msg("shared.agent.info.input_tokens"),
      value: count.format(stats.inputTokens),
    });
  }
  if (stats.outputTokens != null) {
    rows.push({
      label: msg("shared.agent.info.output_tokens"),
      value: count.format(stats.outputTokens),
    });
  }
  // Generation time excludes the wait for the first token, so the rate
  // reflects how fast the model wrote rather than how long it queued.
  const generationMs = stats.durationMs != null ? stats.durationMs - (stats.ttftMs ?? 0) : null;
  if (stats.outputTokens && generationMs && generationMs > 0) {
    const perSecond = stats.outputTokens / (generationMs / 1000);
    rows.push({
      label: msg("shared.agent.info.speed"),
      value: formatMsg("shared.agent.info.tokens_per_second", {
        value: new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(perSecond),
      }),
    });
  }
  if (stats.ttftMs != null) {
    rows.push({
      label: msg("shared.agent.info.first_token"),
      value: formatSeconds(stats.ttftMs, locale),
    });
  }
  if (stats.durationMs != null) {
    rows.push({
      label: msg("shared.agent.info.total_time"),
      value: formatSeconds(stats.durationMs, locale),
    });
  }
  return rows;
}

export function MessageActions({
  text,
  model,
  servedModel,
  stats,
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
  const rows = statRows(stats);

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
      {rows.length > 0 && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-xs" aria-label={msg("shared.agent.info.label")}>
              <Info className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top" dir={getActiveDir()} className="text-start text-pretty">
            <dl className="grid grid-cols-[auto_auto] gap-x-4 gap-y-1">
              {rows.map((row) => (
                <div key={row.label} className="contents">
                  <dt className="text-background/60">{row.label}</dt>
                  <dd dir="ltr" className="text-end font-mono tabular-nums">
                    {row.value}
                  </dd>
                </div>
              ))}
            </dl>
          </TooltipContent>
        </Tooltip>
      )}
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
