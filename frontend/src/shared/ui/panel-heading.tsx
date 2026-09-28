import type { ReactNode } from "react";

import { cn } from "@/shared/lib/utils";

/** Small uppercase heading above a chart, panel or config section. */
export function PanelHeading({
  as: Tag = "p",
  className,
  children,
}: {
  as?: "p" | "h3" | "h4";
  className?: string;
  children: ReactNode;
}) {
  return (
    <Tag
      className={cn(
        "mb-3 text-[0.6875rem] font-semibold uppercase tracking-widest text-muted-foreground",
        className,
      )}
    >
      {children}
    </Tag>
  );
}
