"use client";

/**
 * Empty state component
 * Displays icon, title, description, and optional action button
 * Preserves exact RTL layout and styling from existing implementations
 */

import { type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import type { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick?: () => void;
    href?: string;
  };
  className?: string;
}

export function EmptyState({ icon: Icon, title, description, action, className = "" }: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center gap-3 py-16 text-center ${className}`}>
      {Icon && <Icon className="size-12 text-muted-foreground/30" />}
      <p className="text-base font-medium">{title}</p>
      {description && (
        <p className="text-sm text-muted-foreground max-w-xs">
          {description}
        </p>
      )}
      {action && (
        <Button
          variant="outline"
          size="sm"
          onClick={action.onClick}
          className="mt-2"
          {...(action.href ? { asChild: true } : {})}
        >
          {action.href ? (
            <a href={action.href}>{action.label}</a>
          ) : (
            action.label
          )}
        </Button>
      )}
    </div>
  );
}
