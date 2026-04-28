"use client";

import { BarChart3, Database, AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/shared/ui/primitives/button";
import { Card, CardContent } from "@/shared/ui/primitives/card";
import { FadeIn } from "@/shared/ui/motion";
import { TERMS } from "@/shared/lib/terms";
import { formatMsg, msg } from "@/shared/lib/messages";

interface AnalyticsEmptyProps {
  variant?: "no-data" | "no-results" | "loading-error";
  onClearFilters?: () => void;
  onRetry?: () => void;
}

export function AnalyticsEmpty({
  variant = "no-data",
  onClearFilters,
  onRetry,
}: AnalyticsEmptyProps) {
  const configs = {
    "no-data": {
      icon: Database,
      title: msg("auto.features.dashboard.components.analyticsempty.literal.1"),
      description: formatMsg("auto.features.dashboard.components.analyticsempty.template.1", {
        p1: TERMS.dataset,
        p2: TERMS.optimization,
      }),
      action: null,
    },
    "no-results": {
      icon: BarChart3,
      title: msg("auto.features.dashboard.components.analyticsempty.literal.2"),
      description: formatMsg("auto.features.dashboard.components.analyticsempty.template.2", {
        p1: TERMS.optimizationPlural,
      }),
      action: onClearFilters ? (
        <Button variant="outline" size="sm" onClick={onClearFilters}>
          {msg("auto.features.dashboard.components.analyticsempty.1")}
        </Button>
      ) : null,
    },
    "loading-error": {
      icon: AlertCircle,
      title: msg("auto.features.dashboard.components.analyticsempty.literal.3"),
      description: msg("auto.features.dashboard.components.analyticsempty.literal.4"),
      action: onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="size-4" />
          {msg("auto.features.dashboard.components.analyticsempty.2")}
        </Button>
      ) : null,
    },
  };

  const config = configs[variant];
  const Icon = config.icon;

  return (
    <FadeIn>
      <Card className="border-border/40">
        <CardContent className="flex flex-col items-center gap-4 py-16 text-center">
          <div className="size-16 rounded-2xl bg-muted/50 flex items-center justify-center">
            <Icon className="size-8 text-muted-foreground/60" />
          </div>
          <div className="space-y-2 max-w-sm">
            <h3 className="text-lg font-semibold">{config.title}</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">{config.description}</p>
          </div>
          {config.action}
        </CardContent>
      </Card>
    </FadeIn>
  );
}
