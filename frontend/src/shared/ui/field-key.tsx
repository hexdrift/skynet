import type { ComponentProps } from "react";
import { cn } from "@/shared/lib/utils";

/** Monospace column / field-name label chip. */
export function FieldKey({ className, ...props }: ComponentProps<"span">) {
  return (
    <span
      dir="ltr"
      className={cn(
        "inline-flex items-center rounded-md bg-muted/55 px-2 py-0.5 font-mono text-[0.65625rem] uppercase tracking-[0.08em] text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}
