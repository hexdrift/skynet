"use client";

import { Skeleton } from "@/shared/ui/skeleton";

function StatCard() {
  return (
    <div className="flex min-w-0 flex-[1_1_13rem] flex-col gap-5 rounded-2xl border border-border/40 bg-card/60 p-6 sm:p-7 xl:flex-[1_1_9rem]">
      <div className="flex items-center gap-2">
        <Skeleton width={14} height={14} circle />
        <Skeleton width={80} height={10} />
      </div>
      <Skeleton width={120} height={44} />
    </div>
  );
}

const ROW_GRID =
  "grid grid-cols-[40px_86px_minmax(0,1fr)] items-center gap-1.5 lg:grid-cols-[40px_86px_104px_80px_94px_94px_72px_94px_66px_94px_40px]";

function HeaderRow() {
  return (
    <div className={`${ROW_GRID} border-b border-border/40 bg-muted/20 px-3 py-2.5`}>
      <Skeleton width={16} height={16} borderRadius={4} />
      <Skeleton height={11} width={40} />
      <Skeleton height={11} width={40} />
      <Skeleton height={11} width={40} className="hidden lg:block" />
      <Skeleton height={11} width={40} className="hidden lg:block" />
      <Skeleton height={11} width={40} className="hidden lg:block" />
      <Skeleton height={11} width={40} className="hidden lg:block" />
      <Skeleton height={11} width={40} className="hidden lg:block" />
      <Skeleton height={11} width={40} className="hidden lg:block" />
      <Skeleton height={11} width={40} className="hidden lg:block" />
      <span className="hidden lg:block" />
    </div>
  );
}

function TableRow() {
  return (
    <div className={`${ROW_GRID} border-b border-border/30 px-3 py-2.5`}>
      <Skeleton width={16} height={16} borderRadius={4} />
      <Skeleton height={14} width="80%" />
      <Skeleton height={14} width="70%" />
      <Skeleton height={20} width={56} borderRadius={10} className="hidden lg:block" />
      <Skeleton height={20} width={56} borderRadius={10} className="hidden lg:block" />
      <Skeleton height={14} width={64} className="hidden lg:block" />
      <Skeleton height={14} width={32} className="hidden lg:block" />
      <Skeleton height={14} width={64} className="hidden lg:block" />
      <Skeleton height={14} width={48} className="hidden lg:block" />
      <Skeleton height={14} width={56} className="hidden lg:block" />
      <Skeleton width={14} height={14} borderRadius={4} className="hidden lg:block" />
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-8 -mt-2 md:-mt-4" aria-hidden="true">
      <div className="flex flex-wrap gap-3 sm:gap-4">
        <StatCard />
        <StatCard />
        <StatCard />
        <StatCard />
      </div>

      <div>
        <div className="flex w-full gap-1 rounded-lg border border-border/60 bg-muted/50 p-1">
          <Skeleton height={36} containerClassName="flex-1" borderRadius={6} />
          <Skeleton height={36} containerClassName="flex-1" borderRadius={6} />
        </div>

        <div className="mt-2 rounded-2xl border border-border/60 bg-card/60 px-6 py-5">
          <div className="flex items-center gap-2 mb-3 pt-5">
            <Skeleton width={64} height={11} className="ms-auto" />
          </div>

          <div className="overflow-x-auto rounded-2xl border border-border/40 bg-card/60">
            <HeaderRow />
            {Array.from({ length: 4 }).map((_, i) => (
              <TableRow key={i} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
