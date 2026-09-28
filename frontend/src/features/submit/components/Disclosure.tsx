"use client";

import type { ReactNode } from "react";

import { HelpTip } from "@/shared/ui/help-tip";
import { CaretDown } from "@/shared/ui/icons";
import { cn } from "@/shared/lib/utils";

// Optional controls fold behind a caret: closed, the panel is out of the tab
// order as well as out of sight; open, `trailing` sits at the row's end.
export function Disclosure({
  id,
  label,
  tip,
  open,
  onOpenChange,
  trailing,
  children,
}: {
  id: string;
  label: ReactNode;
  tip?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trailing?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => onOpenChange(!open)}
          aria-expanded={open}
          aria-controls={id}
          className="flex min-h-[44px] items-center gap-2 text-start text-sm font-medium lg:min-h-0"
        >
          <CaretDown
            className={cn("size-4 transition-transform", open && "rotate-180")}
            aria-hidden="true"
          />
          {tip ? (
            <HelpTip text={tip}>
              <span>{label}</span>
            </HelpTip>
          ) : (
            <span>{label}</span>
          )}
        </button>
        {open && trailing}
      </div>
      <div
        id={id}
        className={cn(
          "grid transition-[grid-template-rows,opacity] duration-200 ease-out",
          open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
        )}
        inert={open ? undefined : true}
      >
        <div className="overflow-hidden">{children}</div>
      </div>
    </div>
  );
}
