"use client";

/**
 * Metric card component
 * Displays a metric with label, value, icon, and optional trend indicator
 * Preserves exact styling from existing analytics cards
 */

import { type ReactNode } from "react";
import { TrendingUp, TrendingDown } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

interface MetricCardProps {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  trend?: {
    value: number;
    direction: 'up' | 'down';
  };
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'danger';
  className?: string;
}

export function MetricCard({ label, value, icon, trend, variant = 'default', className = "" }: MetricCardProps) {
  const variantClasses = {
    default: "border-border bg-card",
    primary: "border-primary/20 bg-primary/5",
    success: "border-[var(--success)]/20 bg-[var(--success)]/5",
    warning: "border-[var(--warning)]/20 bg-[var(--warning)]/5",
    danger: "border-[var(--danger)]/20 bg-[var(--danger)]/5",
  };

  return (
    <Card className={`${variantClasses[variant]} ${className}`}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-muted-foreground mb-1.5">
              {label}
            </p>
            <p className="text-2xl font-bold tracking-tight">
              {value}
            </p>
            {trend && (
              <div className={`flex items-center gap-1 mt-2 text-sm ${trend.direction === 'up' ? 'text-[var(--success)]' : 'text-[var(--danger)]'}`}>
                {trend.direction === 'up' ? (
                  <TrendingUp className="size-4" />
                ) : (
                  <TrendingDown className="size-4" />
                )}
                <span className="font-medium">
                  {Math.abs(trend.value).toFixed(1)}%
                </span>
              </div>
            )}
          </div>
          {icon && (
            <div className="shrink-0 text-muted-foreground/50">
              {icon}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
