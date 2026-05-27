"use client";

import { Skeleton } from "@/shared/ui/skeleton";

export function ExploreSkeleton() {
  return (
    <div dir="rtl" className="pb-16" aria-hidden="true">
      <div className="space-y-6">
        <section className="space-y-4">
          <div className="relative overflow-hidden rounded-xl border border-border/60 bg-card/70 p-2 shadow-sm">
            <div className="pointer-events-none absolute inset-y-2 end-2 z-20 flex w-14 flex-col gap-1 rounded-lg border-s border-border/60 bg-background/90 p-2 shadow-sm">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} height={40} borderRadius={6} />
              ))}
            </div>

            <div className="relative h-[58vh] min-h-[420px] overflow-hidden rounded-lg bg-background/40">
              <div className="absolute inset-0">
                <ScatterDots />
              </div>

              <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
                <div className="flex items-center gap-3 rounded-full border border-border/60 bg-background/95 px-4 py-2 shadow-sm">
                  <Skeleton width={20} height={10} />
                  <Skeleton width={140} height={6} borderRadius={3} />
                  <Skeleton width={20} height={10} />
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

const DOT_POSITIONS: ReadonlyArray<{
  top: string;
  left: string;
  size: number;
}> = [
  { top: "18%", left: "22%", size: 14 },
  { top: "62%", left: "14%", size: 18 },
  { top: "34%", left: "38%", size: 11 },
  { top: "74%", left: "30%", size: 16 },
  { top: "50%", left: "48%", size: 20 },
  { top: "22%", left: "55%", size: 12 },
  { top: "82%", left: "58%", size: 13 },
  { top: "40%", left: "68%", size: 17 },
  { top: "26%", left: "78%", size: 11 },
  { top: "68%", left: "84%", size: 15 },
  { top: "12%", left: "70%", size: 9 },
  { top: "56%", left: "62%", size: 10 },
];

function ScatterDots() {
  return (
    <>
      {DOT_POSITIONS.map((d, i) => (
        <span
          key={i}
          className="absolute"
          style={{ top: d.top, left: d.left }}
        >
          <Skeleton width={d.size} height={d.size} borderRadius={d.size / 2} />
        </span>
      ))}
    </>
  );
}
