"use client";

import { cn } from "@/shared/lib/utils";

interface PingDotProps {
  /**
   * Tailwind classes for outer wrapper positioning (e.g. "me-1", "ms-1",
   * "shrink-0"). The dot itself is `size-2 bg-[var(--warning)]`.
   */
  className?: string;
}

/**
 * A pulsing warning-colored dot used to flag active/running state on tabs,
 * pills, and table rows. Reduces motion respects `prefers-reduced-motion`.
 */
export function PingDot({ className }: PingDotProps) {
  return (
    <span className={cn("relative flex size-2", className)}>
      <span className="animate-ping motion-reduce:animate-none absolute inline-flex h-full w-full rounded-full bg-[var(--warning)]/60" />
      <span className="relative inline-flex rounded-full size-2 bg-[var(--warning)]" />
    </span>
  );
}
