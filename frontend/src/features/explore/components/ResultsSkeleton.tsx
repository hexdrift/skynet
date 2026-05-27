"use client";

import * as React from "react";

interface ResultsSkeletonProps {
  /** Number of placeholder rows to render. */
  rows?: number;
}

/**
 * Placeholder rows shown while a fresh query is in flight and there are no
 * prior results to keep on screen. Matches the rhythm of ResultsList so the
 * page doesn't jump when real rows replace it.
 */
export function ResultsSkeleton({ rows = 4 }: ResultsSkeletonProps) {
  return (
    <ul
      dir="rtl"
      aria-hidden="true"
      className="divide-y divide-border/55 animate-pulse"
    >
      {Array.from({ length: rows }).map((_, i) => (
        <li key={i} className="flex flex-col gap-2 px-1 py-5">
          <div className="flex items-start justify-between gap-4">
            <div
              className="h-4 rounded bg-foreground/10"
              style={{ width: `${50 + ((i * 13) % 30)}%` }}
            />
            <div className="h-4 w-16 shrink-0 rounded bg-foreground/[0.06]" />
          </div>
          <div className="h-3 max-w-[68%] rounded bg-foreground/[0.07]" />
          <div className="h-3 max-w-[40%] rounded bg-foreground/[0.05]" />
          <div className="mt-1 flex items-center gap-3">
            <div className="h-2.5 w-20 rounded bg-foreground/[0.06]" />
            <div className="h-2.5 w-24 rounded bg-foreground/[0.06]" />
            <div className="h-2.5 w-16 rounded bg-foreground/[0.06]" />
            <div className="ms-auto h-2.5 w-14 rounded bg-foreground/[0.05]" />
          </div>
        </li>
      ))}
    </ul>
  );
}
