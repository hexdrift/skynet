import type { ComponentProps } from "react";
import { cn } from "@/shared/lib/utils";

export const KBD_CLASS =
  "inline-flex items-center justify-center rounded-md border border-border/70 bg-muted/55 font-medium text-muted-foreground";

/** A keyboard key or shortcut rendered as a key cap. */
export function Kbd({
  active = false,
  className,
  ...props
}: ComponentProps<"kbd"> & { active?: boolean }) {
  return (
    <kbd
      className={cn(
        KBD_CLASS,
        "h-[18px] min-w-5 px-1 text-[0.6875rem]",
        active && "border-primary/40 bg-primary/10 text-primary",
        className,
      )}
      {...props}
    />
  );
}
