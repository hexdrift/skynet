"use client";

import { Skeleton } from "@/shared/ui/skeleton";

function KpiCard() {
  return (
    <div className="flex h-full min-w-0 flex-[1_1_13rem] flex-col gap-5 rounded-2xl border border-border/40 bg-card/60 p-6 sm:p-7 xl:flex-[1_1_9rem]">
      <div className="flex items-center gap-2">
        <Skeleton width={6} height={6} circle />
        <Skeleton width={90} height={10} />
      </div>
      <div className="flex flex-1 items-center justify-center">
        <Skeleton width={120} height={48} />
      </div>
    </div>
  );
}

function BarRow() {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Skeleton width={120} height={13} />
        <Skeleton width={28} height={13} />
      </div>
      <Skeleton height={8} borderRadius={9999} />
    </div>
  );
}

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-card/60 px-6 py-5">
      <div className="flex items-center justify-between pb-3">
        <Skeleton width={200} height={18} />
        <Skeleton width={16} height={16} />
      </div>
      {children}
    </div>
  );
}

export function AnalyticsTabSkeleton() {
  return (
    <div className="space-y-6" aria-hidden="true">
      <div className="flex flex-wrap gap-3 sm:gap-4">
        <KpiCard />
        <KpiCard />
        <KpiCard />
        <KpiCard />
      </div>

      <SectionCard>
        <div className="grid gap-5 lg:grid-cols-7">
          <div className="min-w-0 lg:col-span-4 space-y-3">
            <Skeleton width={160} height={14} />
            <Skeleton height={300} borderRadius={10} />
          </div>
          <div className="min-w-0 lg:col-span-3 space-y-3">
            <Skeleton width={120} height={11} />
            <BarRow />
            <BarRow />
            <BarRow />
          </div>
        </div>
      </SectionCard>

      <SectionCard>
        <div className="grid gap-5 md:grid-cols-2">
          <div className="min-w-0 space-y-3">
            <Skeleton width={140} height={14} />
            <Skeleton height={250} borderRadius={10} />
          </div>
          <div className="min-w-0 space-y-3">
            <Skeleton width={140} height={14} />
            <Skeleton height={250} borderRadius={10} />
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
