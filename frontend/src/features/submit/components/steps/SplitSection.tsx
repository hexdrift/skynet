"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/ui/primitives/card";
import { Label } from "@/shared/ui/primitives/label";
import { Badge } from "@/shared/ui/primitives/badge";
import { Switch } from "@/shared/ui/primitives/switch";
import { NumberInput } from "@/shared/ui/number-input";
import { HelpTip } from "@/shared/ui/help-tip";
import { tip, type TooltipKey } from "@/shared/lib/tooltips";
import { TERMS } from "@/shared/lib/terms";
import { msg } from "@/shared/lib/messages";
import { getActiveIntlLocale } from "@/shared/lib/runtime-locale";

import type { SubmitWizardContext } from "../../hooks/use-submit-wizard";
import { SplitRecommendationCard } from "../SplitRecommendationCard";
import { splitExampleCounts } from "../../lib/split-example-counts";

type SplitKey = "train" | "val" | "test";

const FIELDS: ReadonlyArray<{
  key: SplitKey;
  color: string;
  tip: TooltipKey;
  label: () => string;
}> = [
  {
    key: "train",
    color: "#3D2E22",
    tip: "data.split.train",
    label: () => msg("auto.features.submit.components.steps.paramsstep.6"),
  },
  {
    key: "val",
    color: "#C8A882",
    tip: "data.split.val",
    label: () => msg("auto.features.submit.components.steps.paramsstep.7"),
  },
  {
    key: "test",
    color: "#8C7A6B",
    tip: "data.split.test",
    label: () => msg("auto.features.submit.components.steps.paramsstep.8"),
  },
];

// The recommendation card carries the mode switch; the manual fractions only
// appear once the user picks manual selection, each with the number of
// examples it takes from the dataset.
export function SplitSection({ w }: { w: SubmitWizardContext }) {
  const {
    split,
    updateSplit,
    splitSum,
    splitMode,
    splitPlan,
    profileLoading,
    shuffle,
    setShuffle,
    parsedDataset,
  } = w;
  const totalRows = parsedDataset?.rowCount ?? 0;
  const counts = splitExampleCounts(totalRows, split);
  const numberFormat = new Intl.NumberFormat(getActiveIntlLocale());

  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-xl shadow-lg">
      <CardHeader className="px-4 sm:px-6">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">
            <HelpTip text={tip("data.split_explanation")}>
              {msg("auto.features.submit.components.steps.paramsstep.4")}
              {TERMS.dataset}
            </HelpTip>
          </CardTitle>
          {splitSum !== 1 && (
            <Badge variant="destructive" className="text-xs">
              {msg("auto.features.submit.components.steps.paramsstep.5")}
              {splitSum}
            </Badge>
          )}
        </div>
        <CardDescription>{msg("submit.split.step_desc")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 px-4 sm:px-6" data-tutorial="data-splits" id="data-splits">
        {!splitPlan && !profileLoading && (
          <p className="text-sm text-muted-foreground">{msg("submit.split.empty")}</p>
        )}
        <SplitRecommendationCard w={w} />
        {splitMode === "manual" && (
          <div className="space-y-3">
            <div className="flex h-3 rounded-full overflow-hidden">
              {FIELDS.map((field) => (
                <div
                  key={field.key}
                  className="transition-all"
                  style={{ width: `${split[field.key] * 100}%`, backgroundColor: field.color }}
                />
              ))}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {FIELDS.map((field) => (
                <div key={field.key} className="space-y-1">
                  <Label htmlFor={`split-${field.key}`} className="flex items-center gap-1.5 text-xs">
                    <span
                      className="inline-block w-2 h-2 rounded-full"
                      style={{ backgroundColor: field.color }}
                    />
                    <HelpTip text={tip(field.tip)}>{field.label()}</HelpTip>
                  </Label>
                  <NumberInput
                    id={`split-${field.key}`}
                    step={0.05}
                    min={0}
                    max={1}
                    value={split[field.key]}
                    onChange={(v) => updateSplit(field.key, String(v))}
                  />
                  {totalRows > 0 && (
                    <p className="text-xs tabular-nums text-[#8C7A6B]" aria-live="polite" dir="auto">
                      {msg("submit.split.example_count", {
                        count: numberFormat.format(counts[field.key]),
                      })}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="flex items-center justify-between">
          <Label htmlFor="shuffle" className="cursor-pointer text-sm">
            <HelpTip text={tip("data.shuffle_explanation")}>
              {msg("auto.features.submit.components.steps.paramsstep.10")}
            </HelpTip>
          </Label>
          <Switch id="shuffle" checked={shuffle} onCheckedChange={setShuffle} />
        </div>
      </CardContent>
    </Card>
  );
}
