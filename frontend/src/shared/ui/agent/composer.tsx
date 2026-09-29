"use client";

import * as React from "react";
import { Square } from "@/shared/ui/icons";
import { msg } from "@/shared/lib/messages";

import { Button } from "@/shared/ui/primitives/button";
import { TooltipButton } from "@/shared/ui/tooltip-button";
import { cn } from "@/shared/lib/utils";

import { autoResizeTextarea } from "./auto-resize";

interface ComposerProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onStop?: () => void;
  placeholder?: string;
  disabled?: boolean;
  streaming?: boolean;
  sendAriaLabel?: string;
  stopAriaLabel?: string;
  /** Optional model selector chip rendered at the inline end of the control
   *  row, immediately before the send control. */
  modelMenu?: React.ReactNode;
  /** Optional controls docked at the inline start of the control row, such as
   *  attachment and permission controls. */
  leadingControls?: React.ReactNode;
  /** Keep controls below the draft by default; model-free playgrounds can opt
   *  into a single row. */
  layout?: "stacked" | "inline";
  className?: string;
}

/**
 * The shared chat composer, laid out Codex-style: one bordered box holding a
 * borderless textarea with a control row docked under it — attachment and
 * permission controls at the inline start, then the model chip and circular
 * send/stop button at the inline end.
 */
export function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  placeholder,
  disabled,
  streaming,
  sendAriaLabel = msg("auto.shared.ui.agent.composer.literal.1"),
  stopAriaLabel = msg("auto.shared.ui.agent.composer.literal.2"),
  modelMenu,
  leadingControls,
  layout = "stacked",
  className,
}: ComposerProps) {
  const inline = layout === "inline";
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (disabled || streaming || !value.trim()) return;
    onSubmit();
    if (textareaRef.current) textareaRef.current.style.height = inline ? "36px" : "42px";
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className={cn("border-t border-border/40 px-3 py-3 shrink-0", className)}
    >
      <div
        className={cn(
          "rounded-2xl border border-[#DDD4C8] bg-muted/20 transition-colors",
          "focus-within:border-[#C8A882]",
          inline && "flex min-h-[44px] items-end gap-1 p-1",
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            autoResizeTextarea(e.target);
          }}
          onKeyDown={handleKeyDown}
          disabled={disabled || streaming}
          rows={1}
          placeholder={placeholder}
          className={cn(
            "bg-transparent text-sm leading-[20px] resize-none overflow-hidden",
            "max-h-[120px] outline-none ring-0 border-0 shadow-none",
            "focus:outline-none focus-visible:outline-none focus-visible:ring-0",
            "placeholder:text-muted-foreground/40",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            inline
              ? "h-[44px] min-w-0 flex-1 px-3 py-2 sm:h-9 [@media(hover:none)_and_(pointer:coarse)]:h-[44px]"
              : "block h-[44px] w-full px-4 py-[11px] sm:h-[42px] [@media(hover:none)_and_(pointer:coarse)]:h-[44px]",
          )}
        />

        <div
          className={cn(
            "flex min-w-0 items-center gap-1.5",
            inline ? "shrink-0" : "px-2 pb-2 pt-0.5",
          )}
        >
          {leadingControls && (
            <div className="flex min-w-0 items-center gap-1">{leadingControls}</div>
          )}
          <div className="ms-auto flex min-w-0 items-center justify-end gap-1.5">
            {modelMenu}
            {streaming && onStop ? (
              <TooltipButton tooltip={stopAriaLabel} side="top">
                <Button
                  type="button"
                  size="icon"
                  onClick={onStop}
                  className="shrink-0 rounded-full"
                  aria-label={stopAriaLabel}
                >
                  <Square className="size-3 fill-current" />
                </Button>
              </TooltipButton>
            ) : (
              <Button
                type="submit"
                size="icon"
                className="shrink-0 rounded-full"
                disabled={disabled || !value.trim()}
                aria-label={sendAriaLabel}
              >
                <svg viewBox="0 0 24 24" fill="none" className="size-4">
                  <path
                    d="M12 2L12 22M12 2L5 9M12 2L19 9"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </Button>
            )}
          </div>
        </div>
      </div>
    </form>
  );
}
