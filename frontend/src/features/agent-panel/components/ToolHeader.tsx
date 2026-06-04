"use client";

import * as React from "react";
import { Wrench } from "lucide-react";
import { msg } from "@/shared/lib/messages";

import { cn } from "@/shared/lib/utils";

import { TOOL_META, getToolTitle, type ApprovalSeverity } from "../lib/tool-meta";

const SEVERITY: Record<ApprovalSeverity, { color: string; label: string | null }> = {
  destructive: {
    color: "#9B2C1F",
    label: msg("auto.features.agent.panel.components.toolscarousel.literal.11"),
  },
  warning: {
    color: "#A85A1A",
    label: msg("auto.features.agent.panel.components.toolscarousel.literal.16"),
  },
  info: {
    color: "#3D2E22",
    label: msg("auto.features.agent.panel.components.toolscarousel.literal.12"),
  },
};

interface ToolHeaderProps {
  /** Tool key — resolves the icon, friendly title and severity from metadata. */
  toolKey: string;
  /** Optional end-aligned slot (e.g. a change badge). */
  trailing?: React.ReactNode;
  /** Merged onto the identity row (e.g. ``mb-2.5`` or pinned-header padding). */
  className?: string;
}

/**
 * The shared tool identity row — a severity-tinted circular icon, the friendly
 * title and a severity label — resolved from {@link TOOL_META}. Keys absent
 * from the catalogue fall back to a wrench icon, ``info`` severity and a
 * prettified title, so any tool name renders. Shared by the curated tool tour
 * and the trajectory drawer's tool-description pager so both wear one look.
 */
export function ToolHeader({ toolKey, trailing, className }: ToolHeaderProps) {
  const meta = TOOL_META[toolKey];
  const Icon = meta?.icon ?? Wrench;
  const sev = SEVERITY[meta?.severity ?? "info"];
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <span
        className="inline-flex size-9 items-center justify-center rounded-full shrink-0"
        style={{
          backgroundColor: `${sev.color}14`,
          color: sev.color,
        }}
      >
        <Icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[0.8125rem] font-medium leading-tight truncate">
          {getToolTitle(toolKey)}
        </div>
        {sev.label && (
          <div className="mt-0.5 flex items-center gap-1.5">
            <span
              className="inline-block size-1 rounded-full shrink-0"
              style={{ backgroundColor: sev.color, opacity: 0.55 }}
              aria-hidden="true"
            />
            <span className="text-[0.625rem] text-muted-foreground/75">{sev.label}</span>
          </div>
        )}
      </div>
      {trailing}
    </div>
  );
}
