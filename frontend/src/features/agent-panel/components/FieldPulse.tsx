"use client";

import * as React from "react";

import { cn } from "@/shared/lib/utils";

import { useWizardStateOptional } from "../hooks/use-wizard-state";

interface FieldPulseProps {
  /** Wizard keys to listen to. If any is pulsed by the agent, this wrapper flashes. */
  fields: readonly string[];
  children: React.ReactNode;
  className?: string;
  /** Optional radius to match the wrapped control. Defaults to 12px. */
  radius?: number;
}

/**
 * Wraps a form field and briefly paints a 1px ink outline when the
 * agent writes a watched field. The effect is 160ms with the ease-snappy
 * curve so it feels like a confirmation, not decoration. Respects
 * `prefers-reduced-motion` — users who reduce motion see a steady tint.
 */
export function FieldPulse({
  fields,
  children,
  className,
  radius = 12,
}: FieldPulseProps) {
  const ctx = useWizardStateOptional();
  const [visible, setVisible] = React.useState(false);
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const watched = React.useMemo(() => new Set(fields), [fields]);
  const lastTickRef = React.useRef<number>(ctx?.agentPulseTick ?? 0);

  React.useEffect(() => {
    if (!ctx) return;
    if (ctx.agentPulseTick === lastTickRef.current) return;
    lastTickRef.current = ctx.agentPulseTick;
    const hit = ctx.agentPulseKeys.some((k) => watched.has(k));
    if (!hit) return;
    setVisible(true);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setVisible(false), 160);
  }, [ctx, ctx?.agentPulseTick, ctx?.agentPulseKeys, watched]);

  React.useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  return (
    <div className={cn("relative", className)}>
      {children}
      <span
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute inset-0 rounded-[inherit]",
          "transition-[opacity,transform] duration-[160ms] ease-[cubic-bezier(0.2,0.8,0.2,1)]",
          visible ? "opacity-100" : "opacity-0",
          "motion-reduce:transition-none",
        )}
        style={{
          boxShadow: "0 0 0 1px #3D2E22",
          borderRadius: radius,
        }}
      />
    </div>
  );
}
