"use client";

import { Skeleton } from "@/shared/ui/skeleton";

function KpiCard() {
  return (
    <div className="flex h-full min-h-[9.5rem] min-w-0 flex-col gap-4 rounded-2xl border border-border/40 bg-card/60 p-5 sm:p-6">
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
      <Skeleton width={220} height={30} borderRadius={8} />

      <div className="grid auto-rows-fr grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 xl:grid-cols-5">
        <KpiCard />
        <KpiCard />
        <KpiCard />
        <KpiCard />
        <KpiCard />
      </div>

      <SectionCard>
        <div className="grid gap-6 md:grid-cols-2">
          <div className="min-w-0 space-y-3">
            <Skeleton width={140} height={11} />
            <Skeleton height={240} borderRadius={10} />
          </div>
          <div className="min-w-0 space-y-3">
            <Skeleton width={140} height={11} />
            <Skeleton height={240} borderRadius={10} />
          </div>
        </div>
      </SectionCard>

      <SectionCard>
        <Skeleton height={220} borderRadius={10} />
      </SectionCard>

      <SectionCard>
        <div className="grid gap-6 md:grid-cols-3">
          <div className="min-w-0 space-y-3">
            <Skeleton width={100} height={11} />
            <BarRow />
            <BarRow />
            <BarRow />
          </div>
          <div className="min-w-0 space-y-3">
            <Skeleton width={100} height={11} />
            <BarRow />
            <BarRow />
          </div>
          <div className="min-w-0 space-y-3">
            <Skeleton width={100} height={11} />
            <BarRow />
            <BarRow />
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
