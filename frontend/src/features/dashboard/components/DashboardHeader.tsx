import { AnimatedNumber, FadeIn } from "@/shared/ui/motion";
import { TERMS } from "@/shared/lib/terms";
import type { DashboardStats } from "../lib/get-dashboard-stats";
import { msg } from "@/shared/lib/messages";

type DashboardHeaderProps = {
  stats: DashboardStats;
};

type StatCardProps = {
  label: string;
  value: number;
  accent?: "default" | "warning" | "success" | "danger";
  pulse?: boolean;
};

const ACCENT_TEXT: Record<NonNullable<StatCardProps["accent"]>, string> = {
  default: "text-foreground",
  warning: "text-[var(--warning)]",
  success: "text-emerald-600",
  danger: "text-red-600",
};

const ACCENT_DOT: Record<NonNullable<StatCardProps["accent"]>, string> = {
  default: "bg-foreground/25",
  warning: "bg-[var(--warning)]",
  success: "bg-emerald-500",
  danger: "bg-red-500",
};

function StatCard({ label, value, accent = "default", pulse = false }: StatCardProps) {
  return (
    <div className="group/stat relative flex flex-col gap-5 rounded-2xl border border-border/40 bg-card/60 p-6 transition-colors duration-300 hover:border-border/70 sm:p-7">
      <div className="flex items-center gap-2">
        <span
          className={`size-1.5 rounded-full ${ACCENT_DOT[accent]} ${pulse ? "animate-pulse" : ""}`}
          aria-hidden
        />
        <p className="text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground/70">
          {label}
        </p>
      </div>
      <p
        className={`text-[2.75rem] sm:text-[3.25rem] font-bold leading-[0.9] tracking-tight tabular-nums ${ACCENT_TEXT[accent]}`}
      >
        <AnimatedNumber value={value} />
      </p>
    </div>
  );
}

export function DashboardHeader({ stats }: DashboardHeaderProps) {
  return (
    <>
      <FadeIn>
        <div className="flex flex-col gap-2">
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">
            {msg("auto.features.dashboard.components.dashboardheader.1")}
          </h1>
          {stats && (
            <p className="text-sm text-muted-foreground/80">
              <span className="tabular-nums">{stats.total}</span>{" "}
              {TERMS.optimizationPlural}
              {stats.running > 0 && (
                <>
                  {" · "}
                  <span className="tabular-nums text-[var(--warning)] font-medium">
                    {stats.running}
                  </span>
                  <span className="text-[var(--warning)] font-medium">
                    {msg("auto.features.dashboard.components.dashboardheader.2")}
                  </span>
                </>
              )}
            </p>
          )}
        </div>
      </FadeIn>

      {stats && (
        <div
          className="grid gap-3 sm:gap-4"
          style={{
            gridTemplateColumns: "repeat(auto-fit, minmax(min(200px, 100%), 1fr))",
          }}
          data-tutorial="dashboard-kpis"
        >
          <StatCard
            label={msg("auto.features.dashboard.components.dashboardheader.3")}
            value={stats.total}
          />
          <StatCard
            label={msg("auto.features.dashboard.components.dashboardheader.4")}
            value={stats.running}
            accent={stats.running > 0 ? "warning" : "default"}
            pulse={stats.running > 0}
          />
          <StatCard
            label={msg("auto.features.dashboard.components.dashboardheader.6")}
            value={stats.success}
            accent={stats.success > 0 ? "success" : "default"}
          />
          <StatCard
            label={msg("auto.features.dashboard.components.dashboardheader.7")}
            value={stats.failed}
            accent={stats.failed > 0 ? "danger" : "default"}
          />
        </div>
      )}
    </>
  );
}
