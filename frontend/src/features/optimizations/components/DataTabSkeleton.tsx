"use client";

import { Skeleton } from "@/shared/ui/skeleton";

export function DataTabSkeleton() {
  return (
    <div className="space-y-4 mt-4" aria-hidden="true">
      <div className="rounded-2xl border border-border/40 bg-gradient-to-br from-card/80 to-card p-4 space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <Skeleton width={140} height={14} />
            <Skeleton width={200} height={10} />
          </div>
          <Skeleton width={84} height={32} borderRadius={8} />
        </div>
        <Skeleton height={8} borderRadius={4} />
      </div>

      <div className="flex items-center gap-2 border-b border-border/50 pb-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} width={60} height={18} />
        ))}
      </div>

      <div className="flex justify-end">
        <Skeleton width={64} height={10} />
      </div>

      <div className="rounded-xl border border-border/40 bg-card/60 overflow-hidden">
        <div className="border-b border-border/40 bg-muted/40 px-4 py-2">
          <Skeleton height={20} />
        </div>
        <div className="divide-y divide-border/30">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="grid grid-cols-2 gap-4 px-4 py-3 sm:grid-cols-4 lg:grid-cols-5"
            >
              <Skeleton height={14} width="60%" />
              <Skeleton height={14} width="80%" />
              <Skeleton height={14} width="70%" className="hidden sm:block" />
              <Skeleton height={14} width="65%" className="hidden sm:block" />
              <Skeleton height={14} width="55%" className="hidden lg:block" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
