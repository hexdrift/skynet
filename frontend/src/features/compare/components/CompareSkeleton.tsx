"use client";

import { Skeleton } from "@/shared/ui/skeleton";

function RunCard() {
  return (
    <div className="rounded-xl border border-border/40 bg-card/60 p-4 space-y-3">
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <Skeleton width={140} height={14} />
          <Skeleton width={96} height={10} />
        </div>
        <Skeleton width={60} height={40} />
      </div>
      <Skeleton width="80%" height={10} />
      <Skeleton width="60%" height={10} />
      <Skeleton width="45%" height={10} />
    </div>
  );
}

export function CompareSkeleton() {
  return (
    <div className="space-y-6 pb-12" aria-hidden="true">
      <div className="flex items-center justify-end gap-2">
        <Skeleton width={48} height={12} />
        <Skeleton width={12} height={12} />
        <Skeleton width={180} height={20} />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <RunCard />
        <RunCard />
      </div>

      <div className="rounded-xl border border-border/40 bg-card/60 overflow-hidden">
        <div className="border-b border-border/40 bg-muted/40 px-4 py-3">
          <Skeleton height={20} />
        </div>
        <div className="divide-y divide-border/30">
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="grid grid-cols-[1fr_auto_auto] items-center gap-3 px-4 py-3"
            >
              <Skeleton height={14} width="70%" />
              <Skeleton height={14} width={64} />
              <Skeleton height={14} width={64} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
