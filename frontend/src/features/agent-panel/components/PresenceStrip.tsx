"use client";

import * as React from "react";

import { cn } from "@/shared/lib/utils";

interface PresenceStripProps {
  active: boolean;
  hue?: string;
  className?: string;
}

/**
 * 2px ink strip on the panel's inline-end edge. Pulses while the agent
 * is working so activity is noticeable even at a glance. The hue is
 * driven by the current trust mode so the color carries that signal.
 */
export function PresenceStrip({
  active,
  hue = "#3D2E22",
  className,
}: PresenceStripProps) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "pointer-events-none absolute inset-y-0 end-0 w-[2px] transition-colors duration-200",
        active && "animate-pulse motion-reduce:animate-none",
        className,
      )}
      style={{ backgroundColor: active ? hue : `${hue}26` }}
    />
  );
}
