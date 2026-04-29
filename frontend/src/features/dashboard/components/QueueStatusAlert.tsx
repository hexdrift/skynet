import type { QueueStatusResponse } from "@/shared/types/api";
import { msg } from "@/shared/lib/messages";

export function QueueStatusAlert({ queueStatus }: { queueStatus: QueueStatusResponse | null }) {
  if (!queueStatus || queueStatus.workers_alive) return null;
  return (
    <div
      role="alert"
      aria-live="polite"
      className="flex items-center gap-4 text-xs text-muted-foreground px-2 py-2 rounded-lg bg-muted/30 border border-border/30"
    >
      <span className="flex items-center gap-1.5">
        <span className="size-2 rounded-full bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.4)]" />
        <span className="font-medium">
          {msg("auto.features.dashboard.components.queuestatusalert.1")}
        </span>
      </span>
    </div>
  );
}
