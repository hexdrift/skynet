"use client";

import * as React from "react";
import type { LucideIcon } from "lucide-react";

import { Button } from "@/shared/ui/primitives/button";
import { cn } from "@/shared/lib/utils";

interface EmptyStateProps {
  icon?: LucideIcon;
  /**
   * How the icon is presented.
   * - "none" (default): plain icon at muted color, used for page-level empties.
   * - "tile": rounded-square brand-tinted tile, used inside chat panels.
   * - "circle": small rounded circle tile, used by the dock-pill agent.
   */
  iconWrap?: "none" | "tile" | "circle";
  title: string;
  description?: string;
  /**
   * Density. "page" is the large empty for top-level routes; "compact" is the
   * smaller variant used inside scroll panels (chats, side dialogs).
   */
  variant?: "page" | "compact";
  action?: {
    label: string;
    onClick?: () => void;
    href?: string;
  };
  /** Extra content rendered after the action (e.g. demo cards). */
  children?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  iconWrap = "none",
  title,
  description,
  variant = "page",
  action,
  children,
  className,
}: EmptyStateProps) {
  const isCompact = variant === "compact";

  return (
    <div
      className={cn(
        "flex flex-col items-center text-center",
        isCompact ? "gap-4 py-12 px-6" : "gap-3 py-16",
        className,
      )}
    >
      {Icon && iconWrap === "none" && (
        <Icon className="size-12 text-muted-foreground/30" />
      )}
      {Icon && iconWrap === "tile" && (
        <div className="size-12 rounded-2xl bg-[#3D2E22]/8 flex items-center justify-center">
          <Icon className="size-5 text-[#3D2E22]/40" />
        </div>
      )}
      {Icon && iconWrap === "circle" && (
        <span className="inline-flex size-10 items-center justify-center rounded-full bg-[#3D2E22]/10 text-[#3D2E22]">
          <Icon className="size-5" />
        </span>
      )}

      <div className={cn(isCompact && (description ? "space-y-1.5 max-w-[260px]" : ""))}>
        <p
          className={cn(
            isCompact ? "text-sm font-medium text-foreground/70" : "text-base font-medium",
          )}
        >
          {title}
        </p>
        {description && (
          <p
            className={cn(
              isCompact
                ? "text-xs text-muted-foreground/60 leading-relaxed"
                : "text-sm text-muted-foreground max-w-xs",
            )}
          >
            {description}
          </p>
        )}
      </div>

      {action && (
        <Button
          variant="outline"
          size="sm"
          onClick={action.onClick}
          className="mt-2"
          {...(action.href ? { asChild: true } : {})}
        >
          {action.href ? <a href={action.href}>{action.label}</a> : action.label}
        </Button>
      )}

      {children}
    </div>
  );
}
