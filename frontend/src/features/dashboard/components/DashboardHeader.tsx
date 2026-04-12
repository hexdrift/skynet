import { Activity, CheckCircle2, Layers, XCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { AnimatedNumber, FadeIn, TiltCard } from "@/shared/ui/motion";
import type { DashboardStats } from "../hooks/use-dashboard-stats";

type DashboardHeaderProps = {
  stats: DashboardStats;
};

export function DashboardHeader({ stats }: DashboardHeaderProps) {
  return (
    <>
      <FadeIn>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">לוח בקרה</h1>
            {stats && (
              <p className="text-sm text-muted-foreground mt-1">
                {stats.total} אופטימיזציות
                {stats.running > 0 && (
                  <span className="text-[var(--warning)] font-medium">
                    {" "}
                    &middot; {stats.running} פעילות
                  </span>
                )}
              </p>
            )}
          </div>
        </div>
      </FadeIn>

      {stats && (
        <div
          className="stats-grid grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4"
          style={{
            gridTemplateColumns:
              "repeat(auto-fit, minmax(min(180px, 100%), 1fr))",
          }}
          data-tutorial="dashboard-kpis"
        >
          <TiltCard className="h-full">
            <Card className="h-full border-border/40 hover:border-border/70 transition-colors duration-300">
              <CardContent className="flex h-full flex-col justify-between p-5 sm:p-6">
                <div className="flex items-start justify-between">
                  <div className="space-y-3">
                    <p className="text-[12px] font-medium text-muted-foreground/80 tracking-wide">
                      סה״כ
                    </p>
                    <p className="text-4xl font-bold tracking-tighter tabular-nums">
                      <AnimatedNumber value={stats.total} />
                    </p>
                  </div>
                  <div className="size-9 rounded-lg bg-stone-500/[0.07] flex items-center justify-center">
                    <Layers className="size-4 text-stone-500" />
                  </div>
                </div>
                <p className="mt-3 text-[10px] text-muted-foreground/50">
                  אופטימיזציות
                </p>
              </CardContent>
            </Card>
          </TiltCard>

          <TiltCard className="h-full">
            <Card
              className={`h-full border-border/40 hover:border-border/70 transition-colors duration-300 ${stats.running > 0 ? "border-[var(--warning)]/20" : ""}`}
            >
              <CardContent className="flex h-full flex-col justify-between p-5 sm:p-6">
                <div className="flex items-start justify-between">
                  <div className="space-y-3">
                    <p className="text-[12px] font-medium text-muted-foreground/80 tracking-wide">
                      פעילות
                    </p>
                    <p
                      className={`text-4xl font-bold tracking-tighter tabular-nums ${stats.running > 0 ? "text-[var(--warning)]" : "text-muted-foreground"}`}
                    >
                      <AnimatedNumber value={stats.running} />
                    </p>
                  </div>
                  <div
                    className={`size-9 rounded-lg flex items-center justify-center ${stats.running > 0 ? "bg-[var(--warning)]/[0.08]" : "bg-stone-500/[0.07]"}`}
                  >
                    <Activity
                      className={`size-4 ${stats.running > 0 ? "text-[var(--warning)] animate-pulse" : "text-stone-500"}`}
                    />
                  </div>
                </div>
                <p className="mt-3 text-[10px] text-muted-foreground/50">
                  כרגע רצות
                </p>
              </CardContent>
            </Card>
          </TiltCard>

          <TiltCard className="h-full">
            <Card className="h-full border-border/40 hover:border-border/70 transition-colors duration-300">
              <CardContent className="flex h-full flex-col justify-between p-5 sm:p-6">
                <div className="flex items-start justify-between">
                  <div className="space-y-3">
                    <p className="text-[12px] font-medium text-muted-foreground/80 tracking-wide">
                      הצליחו
                    </p>
                    <p
                      className={`text-4xl font-bold tracking-tighter tabular-nums ${stats.success > 0 ? "text-emerald-700" : "text-muted-foreground"}`}
                    >
                      <AnimatedNumber value={stats.success} />
                    </p>
                  </div>
                  <div
                    className={`size-9 rounded-lg flex items-center justify-center ${stats.success > 0 ? "bg-emerald-500/[0.07]" : "bg-stone-500/[0.07]"}`}
                  >
                    <CheckCircle2
                      className={`size-4 ${stats.success > 0 ? "text-emerald-600" : "text-stone-500"}`}
                    />
                  </div>
                </div>
                {stats.total > 0 && (
                  <div className="mt-3 flex items-center gap-2">
                    <div className="flex-1 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-emerald-500/40 transition-all duration-700"
                        style={{
                          width: `${(stats.success / stats.total) * 100}%`,
                        }}
                      />
                    </div>
                    <span className="text-[10px] tabular-nums text-muted-foreground/50">
                      {Math.round((stats.success / stats.total) * 100)}%
                    </span>
                  </div>
                )}
              </CardContent>
            </Card>
          </TiltCard>

          <TiltCard className="h-full">
            <Card className="h-full border-border/40 hover:border-border/70 transition-colors duration-300">
              <CardContent className="flex h-full flex-col justify-between p-5 sm:p-6">
                <div className="flex items-start justify-between">
                  <div className="space-y-3">
                    <p className="text-[12px] font-medium text-muted-foreground/80 tracking-wide">
                      נכשלו
                    </p>
                    <p
                      className={`text-4xl font-bold tracking-tighter tabular-nums ${stats.failed > 0 ? "text-red-600" : "text-muted-foreground"}`}
                    >
                      <AnimatedNumber value={stats.failed} />
                    </p>
                  </div>
                  <div
                    className={`size-9 rounded-lg flex items-center justify-center ${stats.failed > 0 ? "bg-red-500/[0.07]" : "bg-stone-500/[0.07]"}`}
                  >
                    <XCircle
                      className={`size-4 ${stats.failed > 0 ? "text-red-500" : "text-stone-500"}`}
                    />
                  </div>
                </div>
                {stats.total > 0 && (
                  <div className="mt-3 flex items-center gap-2">
                    <div className="flex-1 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-red-500/40 transition-all duration-700"
                        style={{
                          width: `${(stats.failed / stats.total) * 100}%`,
                        }}
                      />
                    </div>
                    <span className="text-[10px] tabular-nums text-muted-foreground/50">
                      {Math.round((stats.failed / stats.total) * 100)}%
                    </span>
                  </div>
                )}
              </CardContent>
            </Card>
          </TiltCard>
        </div>
      )}
    </>
  );
}
