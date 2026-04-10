"use client";

import { BarChart3, Database, AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FadeIn } from "@/components/motion";

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
      title: "אין עדיין נתונים",
      description: "העלה דאטאסט והגדר אופטימיזציה כדי לראות סטטיסטיקות",
      action: null,
    },
    "no-results": {
      icon: BarChart3,
      title: "לא נמצאו תוצאות",
      description: "הסינון שלך לא מצא אופטימיזציות. נסה להרחיב את הקריטריונים",
      action: onClearFilters ? (
        <Button variant="outline" size="sm" onClick={onClearFilters}>
          נקה סינונים
        </Button>
      ) : null,
    },
    "loading-error": {
      icon: AlertCircle,
      title: "שגיאה בטעינת נתונים",
      description: "לא הצלחנו לטעון את הסטטיסטיקות. נסה שוב",
      action: onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="size-4" />
          נסה שוב
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
