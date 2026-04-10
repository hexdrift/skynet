"use client";

import * as React from "react";
import { Settings, Copy, RotateCcw, Sparkles, Plus, Thermometer, Coins, Brain } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ModelConfig } from "@/lib/types";

interface ModelChipProps {
  config: ModelConfig;
  roleLabel?: string;
  onClick: () => void;
  onClone?: () => void;
  onRemove?: () => void;
  /** If true, shows a subtle "required" style */
  required?: boolean;
  /** Shows a visible "copy from X" button when the chip is empty */
  copyFromLabel?: string;
  onCopyFrom?: () => void;
  className?: string;
}

/** Compact card showing a configured model. Click to open config modal. */
export function ModelChip({
  config,
  roleLabel,
  onClick,
  onClone,
  onRemove,
  required,
  copyFromLabel,
  onCopyFrom,
  className,
}: ModelChipProps) {
  const hasThinking = !!config.extra?.reasoning_effort;
  const effort = config.extra?.reasoning_effort as string | undefined;
  const name = config.name || (required ? "בחר מודל..." : "לא הוגדר");
  const isEmpty = !config.name;

  return (
    <div
      className={cn(
        "group relative flex items-center gap-2.5 rounded-lg border px-3 py-2 cursor-pointer",
        "transition-[border-color,box-shadow,background-color] duration-150",
        isEmpty
          ? "border-dashed border-border/60 bg-muted/20 hover:border-primary/40 hover:bg-muted/40"
          : "border-border/50 bg-card/80 hover:border-primary/40 hover:shadow-sm",
        className,
      )}
      onClick={onClick}
    >
      {/* Model info */}
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        {roleLabel && (
          <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{roleLabel}</span>
        )}
        <span className={cn("truncate text-sm", isEmpty ? "text-muted-foreground" : "text-foreground font-mono font-medium")} dir={isEmpty ? "rtl" : "ltr"}>
          {isEmpty ? name : (name.split("/").pop() ?? name)}
        </span>
        {/* Settings summary */}
        {!isEmpty && (
          <div className="flex items-center gap-2.5 text-[10px] text-muted-foreground" dir="ltr">
            <span className="inline-flex items-center gap-0.5"><Thermometer className="size-2.5" />{config.temperature?.toFixed(1) ?? "0.7"}</span>
            {config.max_tokens && <span className="inline-flex items-center gap-0.5"><Coins className="size-2.5" />{config.max_tokens}</span>}
            {hasThinking && (
              <span className="inline-flex items-center gap-0.5 text-primary/70">
                <Brain className="size-2.5" />
                {effort}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Copy-from shortcut — visible when chip is empty and a source exists */}
      {isEmpty && copyFromLabel && onCopyFrom && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onCopyFrom(); }}
          className="flex shrink-0 items-center gap-1 rounded-md border border-dashed border-primary/30 px-2 py-1 text-[10px] font-medium text-primary/80 hover:bg-primary/5 hover:border-primary/50 transition-all cursor-pointer"
        >
          <Copy className="size-2.5" />
          {copyFromLabel}
        </button>
      )}

      {/* Right: action buttons */}
      <div className="flex shrink-0 items-center gap-1">
        {onClone && !isEmpty && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onClone(); }}
            className="rounded-md p-1 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-accent hover:text-foreground transition-all cursor-pointer"
            title="שכפל"
          >
            <Copy className="size-3" />
          </button>
        )}
        {onRemove && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onRemove(); }}
            className="rounded-md p-1 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive transition-all cursor-pointer"
            title="אפס"
          >
            <RotateCcw className="size-3" />
          </button>
        )}
        <Settings className="size-3.5 text-muted-foreground/60 group-hover:text-foreground/70 transition-colors" />
      </div>
    </div>
  );
}

interface AddModelButtonProps {
  label?: string;
  onClick: () => void;
  className?: string;
}

/** "Add model" button that looks like an empty chip. */
export function AddModelButton({ label = "הוסף מודל", onClick, className }: AddModelButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-2 rounded-lg border border-dashed border-border/50 px-3 py-2",
        "text-sm text-muted-foreground hover:border-primary/40 hover:text-foreground hover:bg-muted/30",
        "transition-all duration-150 cursor-pointer",
        className,
      )}
    >
      <Plus className="size-3.5" />
      {label}
    </button>
  );
}
