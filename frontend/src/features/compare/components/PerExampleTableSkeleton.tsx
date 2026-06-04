"use client";

import { Skeleton } from "@/shared/ui/skeleton";
import { Card, CardContent } from "@/shared/ui/primitives/card";

interface PerExampleTableSkeletonProps {
  runCount: number;
  compact: boolean;
}

export function PerExampleTableSkeleton({ runCount, compact }: PerExampleTableSkeletonProps) {
  return (
    <Card className="overflow-hidden" aria-hidden="true">
      <CardContent className="p-0">
        <div className="flex items-center justify-between gap-3 px-4 sm:px-5 py-3 border-b border-border/40">
          <Skeleton width={90} height={11} />
          <Skeleton width={32} height={32} borderRadius={8} />
        </div>

        {compact && (
          <div className="px-4 sm:px-5 py-2.5 border-b border-border/40 bg-muted/15">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
              {Array.from({ length: runCount }).map((_, i) => (
                <span key={i} className="inline-flex items-center gap-1.5">
                  <Skeleton width={16} height={16} borderRadius={4} />
                  <Skeleton width={72} height={11} />
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="table-scroll">
          <table className="w-full text-sm border-separate border-spacing-0">
            <thead>
              <tr>
                <th className="py-2 w-10 border-b border-border/40 sticky start-0 bg-card z-10" />
                <th className="py-2 px-3 text-start w-[min(120px,30%)] border-b border-border/40 sticky start-10 bg-card z-10 border-e border-border/30">
                  <Skeleton width={64} height={10} />
                </th>
                {Array.from({ length: runCount }).map((_, i) => (
                  <th
                    key={i}
                    className={`border-b border-border/40 text-center ${compact ? "py-2 px-1 w-9" : "py-2.5 px-2"}`}
                  >
                    <div className="flex items-center justify-center">
                      <Skeleton width={compact ? 20 : 64} height={compact ? 20 : 22} borderRadius={6} />
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 6 }).map((_, rowIdx) => (
                <tr key={rowIdx} className={rowIdx > 0 ? "border-t border-border/30" : ""}>
                  <td className="py-2.5 w-10 text-center sticky start-0 bg-card z-10">
                    <div className="flex items-center justify-center">
                      <Skeleton width={16} height={16} borderRadius={4} />
                    </div>
                  </td>
                  <td className="py-2.5 px-3 sticky start-10 bg-card z-10 border-e border-border/30">
                    <Skeleton width={40} height={12} />
                  </td>
                  {Array.from({ length: runCount }).map((_, i) => (
                    <td key={i} className={`text-center ${compact ? "py-2 px-1" : "py-2.5 px-2"}`}>
                      <div className="flex items-center justify-center">
                        <Skeleton width={16} height={16} borderRadius={4} />
                      </div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
