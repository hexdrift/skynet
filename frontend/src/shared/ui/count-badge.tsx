import type { ComponentProps } from "react";
import { cn } from "@/shared/lib/utils";

/** Numeric badge on an icon/button corner (`overlay`) or inline beside it. */
export function CountBadge({
  overlay = false,
  className,
  ...props
}: ComponentProps<"span"> & { overlay?: boolean }) {
  return (
    <span
      className={cn(
        "grid min-w-4 place-items-center rounded-full bg-primary px-1 text-[0.5625rem] font-bold leading-4 text-primary-foreground tabular-nums",
        overlay && "absolute -end-0.5 -top-0.5",
        className,
      )}
      {...props}
    />
  );
}

/** Quiet count next to a label, tab or section title. `active` tints it with the brand color. */
export function CountPill({
  active = false,
  className,
  ...props
}: ComponentProps<"span"> & { active?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-1.5 py-px text-[0.6875rem] font-medium tabular-nums",
        active ? "bg-primary/10 text-primary" : "bg-foreground/10 text-foreground/75",
        className,
      )}
      {...props}
    />
  );
}
