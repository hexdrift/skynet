"use client";

import * as React from "react";
import { Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

interface NumberInputProps {
  id?: string;
  value: number | "";
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  className?: string;
  disabled?: boolean;
}

export function NumberInput({
  id,
  value,
  onChange,
  min,
  max,
  step = 1,
  className,
  disabled,
}: NumberInputProps) {
  const numValue = typeof value === "number" ? value : 0;
  const decimals = step < 1 ? Math.max(String(step).split(".")[1]?.length ?? 0, 2) : 0;
  const round = (n: number) => decimals ? parseFloat(n.toFixed(decimals)) : n;

  const decrement = () => {
    const next = round(numValue - step);
    if (min != null && next < min) return;
    onChange(next);
  };

  const increment = () => {
    const next = round(numValue + step);
    if (max != null && next > max) return;
    onChange(next);
  };

  return (
    <div className={cn("flex items-center h-9 rounded-xl border border-input/90 bg-background/75 shadow-[inset_0_1px_0_rgba(255,255,255,0.72),0_12px_26px_-24px_rgba(15,23,42,0.45)] backdrop-blur-sm overflow-hidden", disabled && "opacity-50 pointer-events-none", className)}>
      <button
        type="button"
        onClick={decrement}
        disabled={disabled || (min != null && numValue <= min)}
        className="flex items-center justify-center size-9 shrink-0 text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
        tabIndex={-1}
        aria-label="Decrease"
      >
        <Minus className="size-3" />
      </button>
      <input
        id={id}
        type="text"
        inputMode="numeric"
        value={typeof value === "number" && decimals ? value.toFixed(decimals) : value}
        onChange={(e) => {
          const raw = e.target.value.replace(/[^0-9.]/g, "");
          if (raw === "" || raw === ".") { onChange(min ?? 0); return; }
          const n = parseFloat(raw);
          if (isNaN(n)) return;
          if (min != null && n < min) return;
          if (max != null && n > max) return;
          onChange(round(n));
        }}
        disabled={disabled}
        className="flex-1 min-w-0 h-full bg-transparent text-center text-sm tabular-nums outline-none"
        dir="ltr"
      />
      <button
        type="button"
        onClick={increment}
        disabled={disabled || (max != null && numValue >= max)}
        className="flex items-center justify-center size-9 shrink-0 text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
        tabIndex={-1}
        aria-label="Increase"
      >
        <Plus className="size-3" />
      </button>
    </div>
  );
}
