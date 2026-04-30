"use client";

import { cn } from "@/shared/lib/utils";
import { msg } from "@/shared/lib/messages";

interface LoadingStateProps {
  variant: "table" | "card" | "chart" | "text" | "block";
  rows?: number;
  className?: string;
}

export function LoadingState({ variant, rows = 3, className = "" }: LoadingStateProps) {
  if (variant === "block") {
    return (
      <div
        className={cn(
          "rounded-lg border border-border/40 bg-muted/20 animate-pulse motion-reduce:animate-none",
          className,
        )}
      />
    );
  }

  if (variant === "chart") {
    return (
      <div className={`h-[300px] flex items-center justify-center ${className}`}>
        <span className="text-sm text-muted-foreground">{msg("shared.loading.charts")}</span>
      </div>
    );
  }

  if (variant === "text") {
    return (
      <div className={`space-y-2 ${className}`}>
        {Array.from({ length: rows }).map((_, i) => (
          <div
            key={i}
            className="h-4 bg-muted/20 rounded animate-pulse motion-reduce:animate-none"
          />
        ))}
      </div>
    );
  }

  if (variant === "card") {
    return (
      <div className={`space-y-3 ${className}`}>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="p-4 border rounded-lg space-y-3">
            <div className="h-4 bg-muted/20 rounded animate-pulse motion-reduce:animate-none w-1/3" />
            <div className="h-3 bg-muted/20 rounded animate-pulse motion-reduce:animate-none w-2/3" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-12 bg-muted/20 rounded animate-pulse motion-reduce:animate-none"
        />
      ))}
    </div>
  );
}
