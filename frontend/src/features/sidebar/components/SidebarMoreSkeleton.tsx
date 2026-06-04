"use client";

import { Skeleton } from "@/shared/ui/skeleton";

const ROW_WIDTHS = ["100%", "80%", "60%"];

export function SidebarMoreSkeleton() {
  return (
    <ul className="flex flex-col gap-1" aria-hidden="true">
      {ROW_WIDTHS.map((width, i) => (
        <li key={i} className="flex items-center gap-1.5 rounded-lg px-2 py-2">
          <span className="flex items-center gap-2 min-w-0 flex-1">
            <Skeleton height={11} width={width} containerClassName="flex-1" />
          </span>
          <Skeleton circle width={8} height={8} />
          <Skeleton circle width={14} height={14} />
        </li>
      ))}
    </ul>
  );
}
