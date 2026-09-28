import * as React from "react";

import { cn } from "@/shared/lib/utils";

/** The Input surface stretched to multiple lines; callers add only layout. */
export const TEXTAREA_SURFACE_CLASS =
  "flex min-h-[44px] w-full resize-none rounded-xl border border-input/90 bg-background/75 px-3 py-2 text-base md:text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.72),0_12px_26px_-24px_rgba(15,23,42,0.45)] backdrop-blur-sm transition-[color,box-shadow,border-color] outline-none placeholder:text-muted-foreground/90 focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea data-slot="textarea" className={cn(TEXTAREA_SURFACE_CLASS, className)} {...props} />
  );
}

export { Textarea };
