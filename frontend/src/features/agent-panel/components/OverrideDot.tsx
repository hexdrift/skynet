"use client";

import * as React from "react";
import { msg } from "@/shared/lib/messages";

import { cn } from "@/shared/lib/utils";

import { useWizardStateOptional } from "../hooks/use-wizard-state";

interface OverrideDotProps {
  field: string;
  className?: string;
}

/**
 * 6px muted dot rendered next to a field the user modified after the
 * agent last wrote it. Gives a quiet visual cue that the value diverges
 * from what the agent last set without shouting at the user.
 */
export function OverrideDot({ field, className }: OverrideDotProps) {
  const ctx = useWizardStateOptional();
  if (!ctx) return null;
  if (!ctx.overriddenFields.includes(field)) return null;

  return (
    <span
      aria-label={msg("auto.features.agent.panel.components.overridedot.literal.1")}
      title={msg("auto.features.agent.panel.components.overridedot.literal.2")}
      className={cn("inline-block size-1.5 rounded-full bg-[#8C7A6B] shrink-0", className)}
    />
  );
}
