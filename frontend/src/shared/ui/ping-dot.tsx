"use client";

import { cn } from "@/shared/lib/utils";

interface PingDotProps {
  /**
   * Tailwind classes for outer wrapper positioning (e.g. "me-1", "ms-1",
   * "shrink-0").
   */
  className?: string;
  /** `sm` = size-1.5, `md` = size-2 (default). */
  size?: "sm" | "md";
  /** `warning` flags running work; `agent` flags a busy agent or a pending approval. */
  tone?: "warning" | "agent";
}

const SIZE_CLASS = { sm: "size-1.5", md: "size-2" } as const;

const TONE_CLASS = {
  warning: { halo: "bg-[var(--warning)]/60", dot: "bg-[var(--warning)]" },
  agent: { halo: "bg-primary/40", dot: "bg-primary" },
} as const;

/**
 * A pulsing dot used to flag active/running state on tabs, pills, and table
 * rows. Respects `prefers-reduced-motion`.
 */
export function PingDot({ className, size = "md", tone = "warning" }: PingDotProps) {
  const sizeClass = SIZE_CLASS[size];
  const { halo, dot } = TONE_CLASS[tone];
  return (
    <span aria-hidden className={cn("relative flex shrink-0", sizeClass, className)}>
      <span
        className={cn(
          "absolute inline-flex h-full w-full animate-ping rounded-full motion-reduce:animate-none",
          halo,
        )}
      />
      <span className={cn("relative inline-flex rounded-full", sizeClass, dot)} />
    </span>
  );
}
