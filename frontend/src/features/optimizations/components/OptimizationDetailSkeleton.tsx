"use client";

import { Skeleton } from "@/shared/ui/skeleton";

export function OptimizationDetailSkeleton() {
  return (
    <div className="space-y-6 pb-12" aria-hidden="true">
      <div className="flex items-center justify-end gap-2">
        <Skeleton width={64} height={12} />
        <Skeleton width={12} height={12} />
        <Skeleton width={120} height={12} />
      </div>

      <div className="rounded-xl border border-border/40 bg-gradient-to-br from-card to-card/80 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-3">
              <Skeleton width={72} height={22} borderRadius={11} />
              <span className="block w-[60%] max-w-[280px]">
                <Skeleton height={22} />
              </span>
            </div>
            <span className="block w-[80%] max-w-[420px]">
              <Skeleton height={12} />
            </span>
            <span className="block w-[55%] max-w-[280px]">
              <Skeleton height={10} />
            </span>
            <div className="flex flex-wrap items-center gap-3 pt-1">
              <Skeleton width={60} height={20} borderRadius={6} />
              <Skeleton width={84} height={16} />
              <Skeleton width={72} height={16} />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Skeleton width={32} height={32} borderRadius={8} />
            <Skeleton width={32} height={32} borderRadius={8} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-border/40 bg-card/60 p-4 space-y-3"
          >
            <Skeleton width={80} height={12} />
            <Skeleton width="60%" height={28} />
            <Skeleton width="80%" height={10} />
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3 border-b border-border/50 pb-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} width={72} height={20} />
        ))}
      </div>

      <div className="rounded-xl border border-border/40 bg-card/60 p-5 space-y-3">
        <Skeleton height={16} />
        <Skeleton height={14} width="85%" />
        <Skeleton height={14} width="70%" />
        <Skeleton height={14} width="92%" />
        <Skeleton height={14} width="60%" />
        <Skeleton height={14} width="78%" />
      </div>
    </div>
  );
}
