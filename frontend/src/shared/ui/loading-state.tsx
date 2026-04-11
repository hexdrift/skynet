"use client";

/**
 * Loading state component
 * Displays skeleton loaders for different content types
 * Uses boneyard-js Skeleton component under the hood
 */

import { Skeleton } from "boneyard-js/react";

interface LoadingStateProps {
  variant: 'table' | 'card' | 'chart' | 'text';
  rows?: number;
  className?: string;
}

export function LoadingState({ variant, rows = 3, className = "" }: LoadingStateProps) {
  if (variant === 'chart') {
    return (
      <div className={`h-[300px] flex items-center justify-center ${className}`}>
        <span className="text-sm text-muted-foreground">טוען גרפים...</span>
      </div>
    );
  }

  if (variant === 'text') {
    return (
      <div className={`space-y-2 ${className}`}>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="h-4 bg-muted/20 rounded animate-pulse" />
        ))}
      </div>
    );
  }

  if (variant === 'card') {
    return (
      <div className={`space-y-3 ${className}`}>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="p-4 border rounded-lg space-y-3">
            <div className="h-4 bg-muted/20 rounded animate-pulse w-1/3" />
            <div className="h-3 bg-muted/20 rounded animate-pulse w-2/3" />
          </div>
        ))}
      </div>
    );
  }

  // table variant (default)
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-12 bg-muted/20 rounded animate-pulse" />
      ))}
    </div>
  );
}
