"use client";

import { Skeleton } from "@/shared/ui/skeleton";

function StatCard() {
  return (
    <div className="rounded-xl border border-border/40 bg-card/60 p-4 space-y-3">
      <div className="flex items-start justify-between">
        <Skeleton width={56} height={14} />
        <Skeleton width={36} height={36} borderRadius={10} />
      </div>
      <Skeleton width={68} height={28} />
      <Skeleton width={84} height={10} />
    </div>
  );
}

function TableRow() {
  return (
    <div className="grid grid-cols-[auto_1fr_auto_auto_auto] items-center gap-3 px-4 py-3 sm:grid-cols-[auto_1fr_120px_120px_80px]">
      <Skeleton width={54} height={22} borderRadius={11} />
      <Skeleton height={16} width="70%" />
      <Skeleton height={14} width="80%" className="hidden sm:block" />
      <Skeleton height={14} width="80%" className="hidden sm:block" />
      <Skeleton height={14} width={64} />
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-8" aria-hidden="true">
      <div className="space-y-2">
        <Skeleton width={120} height={28} />
        <Skeleton width={200} height={14} />
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard />
        <StatCard />
        <StatCard />
        <StatCard />
      </div>

      <div>
        <div className="flex gap-1 border-b border-border/60 pb-1">
          <Skeleton width={100} height={32} borderRadius={8} />
          <Skeleton width={100} height={32} borderRadius={8} />
        </div>

        <div className="mt-4 rounded-xl border border-border/40 bg-card/60 overflow-hidden">
          <div className="border-b border-border/40 bg-muted/40 px-4 py-3">
            <Skeleton height={20} />
          </div>
          <div className="divide-y divide-border/30">
            {Array.from({ length: 6 }).map((_, i) => (
              <TableRow key={i} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
