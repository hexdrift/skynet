"use client";

import { Skeleton } from "@/shared/ui/skeleton";

const ROW_COUNT = 3;

export function SidebarMoreSkeleton() {
  return (
    <ul className="flex flex-col gap-1" aria-hidden="true">
      {Array.from({ length: ROW_COUNT }).map((_, i) => (
        <li key={i} className="flex items-center gap-2 px-2 py-1.5">
          <Skeleton circle width={6} height={6} />
          <span className="flex-1">
            <Skeleton height={12} />
          </span>
        </li>
      ))}
    </ul>
  );
}
