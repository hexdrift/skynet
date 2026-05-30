import * as React from "react";

interface SettingsRowProps {
  label: React.ReactNode;
  description?: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}

/**
 * A label/description-on-the-leading-side, control-on-the-trailing-side row.
 *
 * The shared building block for the Settings modal and any modal that wants the
 * same visual rhythm (e.g. the share dialog) — a bottom border per row, a small
 * leading icon, and a right-aligned control slot.
 */
export function SettingsRow({ label, description, icon: Icon, children }: SettingsRowProps) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-border/40 last:border-b-0">
      <div className="flex items-start gap-3 flex-1 min-w-0">
        {Icon && (
          <Icon className="size-4 mt-0.5 text-muted-foreground shrink-0" aria-hidden="true" />
        )}
        <div className="flex flex-col gap-0.5 min-w-0">
          <span className="text-sm font-medium text-foreground">{label}</span>
          {description && (
            <span className="text-xs text-muted-foreground/80">{description}</span>
          )}
        </div>
      </div>
      <div className="shrink-0 flex items-center gap-2">{children}</div>
    </div>
  );
}
