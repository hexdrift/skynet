"use client";

import { CaretDown } from "@/shared/ui/icons";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/shared/ui/primitives/card";
import { Label } from "@/shared/ui/primitives/label";
import { Badge } from "@/shared/ui/primitives/badge";
import { Separator } from "@/shared/ui/primitives/separator";
import { Switch } from "@/shared/ui/primitives/switch";
import { NumberInput } from "@/shared/ui/number-input";
import { HelpTip } from "@/shared/ui/help-tip";
import { Segmented } from "@/shared/ui/segmented";
import { cn } from "@/shared/lib/utils";
import { tip } from "@/shared/lib/tooltips";
import { TERMS } from "@/shared/lib/terms";
import { formatMsg, msg } from "@/shared/lib/messages";

import type { SubmitWizardContext } from "../../hooks/use-submit-wizard";
import { SplitRecommendationCard } from "../SplitRecommendationCard";

// The empty level is the escape hatch: no preset, the user sets the budget.
const DEPTH_LEVELS = ["light", "medium", "heavy", ""] as const;
type DepthLevel = (typeof DEPTH_LEVELS)[number];
// Starting budget when Custom switches from evaluation rounds to metric calls.
const DEFAULT_CUSTOM_METRIC_CALLS = 500;

export function ParamsStep({ w }: { w: SubmitWizardContext }) {
  const {
    split,
    updateSplit,
    splitSum,
    splitMode,
    shuffle,
    setShuffle,
    autoLevel,
    setAutoLevel,
    reflectionMinibatchSize,
    setReflectionMinibatchSize,
    maxFullEvals,
    setMaxFullEvals,
    maxMetricCalls,
    setMaxMetricCalls,
    useMerge,
    setUseMerge,
    optimizerName,
    targetScore,
    setTargetScore,
    pxnParents,
    setPxnParents,
    pxnProposals,
    setPxnProposals,
    optimizerSettingsOpen,
    setOptimizerSettingsOpen,
    optimizerSettingsCustomized,
  } = w;
  const isGepa = optimizerName.toLowerCase() === "gepa";
  const depth: DepthLevel = DEPTH_LEVELS.find((level) => level === autoLevel) ?? "";
  const budgetUnit: "rounds" | "calls" = maxMetricCalls ? "calls" : "rounds";
  const targetScoreValue = Number.parseFloat(targetScore);
  // p*n candidates per reflective round; only worth spelling out once batching
  // is actually on (1x1 is GEPA's classic one-candidate default).
  const pxnBatch = (parseInt(pxnParents, 10) || 1) * (parseInt(pxnProposals, 10) || 1);

  return (
    <Card
      className=" border-border/50 bg-card/80 backdrop-blur-xl shadow-lg"
      data-tutorial="wizard-step-5"
    >
      <CardHeader className="px-4 sm:px-6">
        <CardTitle className="text-lg">
          {msg("auto.features.submit.components.steps.paramsstep.1")}
        </CardTitle>
        <CardDescription>
          {msg("auto.features.submit.components.steps.paramsstep.2")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6 px-4 sm:px-6">
        <div className="space-y-3" data-tutorial="data-splits">
          <div className="flex items-center justify-between">
            <Label className="font-semibold">
              <HelpTip text={tip("data.split_explanation")}>
                {msg("auto.features.submit.components.steps.paramsstep.4")}
                {TERMS.dataset}
              </HelpTip>
            </Label>
            {splitSum !== 1 && (
              <Badge variant="destructive" className="text-xs">
                {msg("auto.features.submit.components.steps.paramsstep.5")}
                {splitSum}
              </Badge>
            )}
          </div>
          <SplitRecommendationCard w={w} />
          {splitMode === "manual" && (
            <div className="space-y-3">
              <div className="flex h-3 rounded-full overflow-hidden">
                <div
                  className="bg-[#3D2E22] transition-all"
                  style={{ width: `${split.train * 100}%` }}
                />
                <div
                  className="bg-[#C8A882] transition-all"
                  style={{ width: `${split.val * 100}%` }}
                />
                <div
                  className="bg-[#8C7A6B] transition-all"
                  style={{ width: `${split.test * 100}%` }}
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="space-y-1">
                  <Label htmlFor="split-train" className="flex items-center gap-1.5 text-xs">
                    <span className="inline-block w-2 h-2 rounded-full bg-[#3D2E22]" />
                    <HelpTip text={tip("data.split.train")}>
                      {msg("auto.features.submit.components.steps.paramsstep.6")}
                    </HelpTip>
                  </Label>
                  <NumberInput
                    id="split-train"
                    step={0.05}
                    min={0}
                    max={1}
                    value={split.train}
                    onChange={(v) => updateSplit("train", String(v))}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="split-val" className="flex items-center gap-1.5 text-xs">
                    <span className="inline-block w-2 h-2 rounded-full bg-[#C8A882]" />
                    <HelpTip text={tip("data.split.val")}>
                      {msg("auto.features.submit.components.steps.paramsstep.7")}
                    </HelpTip>
                  </Label>
                  <NumberInput
                    id="split-val"
                    step={0.05}
                    min={0}
                    max={1}
                    value={split.val}
                    onChange={(v) => updateSplit("val", String(v))}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="split-test" className="flex items-center gap-1.5 text-xs">
                    <span className="inline-block w-2 h-2 rounded-full bg-[#8C7A6B]" />
                    <HelpTip text={tip("data.split.test")}>
                      {msg("auto.features.submit.components.steps.paramsstep.8")}
                    </HelpTip>
                  </Label>
                  <NumberInput
                    id="split-test"
                    step={0.05}
                    min={0}
                    max={1}
                    value={split.test}
                    onChange={(v) => updateSplit("test", String(v))}
                  />
                </div>
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
        </div>

        <Separator />

        <div className="space-y-3" data-tutorial="auto-level">
          <Label className="text-sm font-semibold">
            <HelpTip text={tip("submit.depth")}>
              {msg("auto.features.submit.components.steps.paramsstep.12")}
            </HelpTip>
          </Label>
          <Segmented<DepthLevel>
            label={msg("auto.features.submit.components.steps.paramsstep.12")}
            options={[
              {
                value: "light",
                label: msg("auto.features.submit.components.steps.paramsstep.literal.1"),
              },
              {
                value: "medium",
                label: msg("auto.features.submit.components.steps.paramsstep.literal.2"),
              },
              {
                value: "heavy",
                label: msg("auto.features.submit.components.steps.paramsstep.literal.3"),
              },
              { value: "", label: msg("submit.depth.custom") },
            ]}
            value={depth}
            onChange={setAutoLevel}
          />
          {!depth && (
            <div className="space-y-3 rounded-lg border border-border/50 bg-muted/30 p-3 motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-top-1 motion-safe:duration-200">
              <Segmented<"rounds" | "calls">
                size="sm"
                className="w-full"
                options={[
                  {
                    value: "rounds",
                    label: msg("auto.features.submit.components.steps.paramsstep.14"),
                  },
                  { value: "calls", label: msg("submit.metric_calls") },
                ]}
                value={budgetUnit}
                onChange={(unit) =>
                  setMaxMetricCalls(
                    unit === "calls" ? maxMetricCalls || String(DEFAULT_CUSTOM_METRIC_CALLS) : "",
                  )
                }
              />
              {budgetUnit === "calls" ? (
                <div className="space-y-1.5">
                  <Label htmlFor="max-metric-calls" className="text-xs">
                    <HelpTip text={tip("submit.metric_calls")}>
                      {msg("submit.metric_calls")}
                    </HelpTip>
                  </Label>
                  <NumberInput
                    id="max-metric-calls"
                    min={1}
                    max={100000}
                    step={1}
                    value={parseInt(maxMetricCalls, 10)}
                    onChange={(v) => setMaxMetricCalls(String(v))}
                  />
                </div>
              ) : (
                <div className="space-y-1.5">
                  <Label htmlFor="max-full-evals" className="text-xs">
                    <HelpTip text={tip("submit.eval_rounds")}>
                      {msg("auto.features.submit.components.steps.paramsstep.14")}
                    </HelpTip>
                  </Label>
                  <NumberInput
                    id="max-full-evals"
                    min={1}
                    max={50}
                    step={1}
                    value={maxFullEvals ? parseInt(maxFullEvals, 10) : ""}
                    onChange={(v) => setMaxFullEvals(String(v))}
                  />
                </div>
              )}
            </div>
          )}
        </div>

        <Separator />

        <div className="space-y-3">
          <button
            type="button"
            onClick={() => setOptimizerSettingsOpen(!optimizerSettingsOpen)}
            aria-expanded={optimizerSettingsOpen}
            className="flex w-full cursor-pointer items-center justify-between gap-2"
          >
            <span className="flex items-baseline gap-2">
              <span className="text-sm leading-none font-semibold">
                {msg("auto.features.submit.components.steps.paramsstep.11")}
                {TERMS.optimizer}
              </span>
              {!optimizerSettingsOpen && (
                <span className="text-xs text-muted-foreground">
                  {optimizerSettingsCustomized
                    ? msg("submit.optimizer_settings.customized")
                    : msg("submit.optimizer_settings.defaults")}
                </span>
              )}
            </span>
            <CaretDown
              className={cn(
                "size-4 shrink-0 text-muted-foreground transition-transform duration-150",
                optimizerSettingsOpen && "rotate-180",
              )}
            />
          </button>
          {optimizerSettingsOpen && (
            <div
              className="grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2 motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-top-1 motion-safe:duration-200"
              data-tutorial="gepa-params"
            >
              <div className="space-y-1.5">
                <Label htmlFor="reflection-minibatch" className="text-xs">
                  <HelpTip text={tip("submit.reflection_minibatch")}>
                    {msg("auto.features.submit.components.steps.paramsstep.13")}
                  </HelpTip>
                </Label>
                <NumberInput
                  id="reflection-minibatch"
                  min={1}
                  max={20}
                  step={1}
                  value={reflectionMinibatchSize ? parseInt(reflectionMinibatchSize, 10) : ""}
                  onChange={(v) => setReflectionMinibatchSize(String(v))}
                />
              </div>
              <div className="flex items-center justify-between gap-3 sm:self-end sm:h-9">
                <Label htmlFor="use-merge" className="cursor-pointer text-xs">
                  <HelpTip text={tip("submit.merge")}>
                    {msg("auto.features.submit.components.steps.paramsstep.15")}
                  </HelpTip>
                </Label>
                <Switch id="use-merge" checked={useMerge} onCheckedChange={setUseMerge} />
              </div>
              {isGepa && (
                <>
                  <div className="space-y-1.5">
                    <Label htmlFor="pxn-parents" className="text-xs">
                      <HelpTip text={tip("submit.pxn_parents")}>
                        {msg("submit.pxn.parents")}
                      </HelpTip>
                    </Label>
                    <NumberInput
                      id="pxn-parents"
                      min={1}
                      max={16}
                      step={1}
                      value={pxnParents ? parseInt(pxnParents, 10) : ""}
                      onChange={(v) => setPxnParents(String(v))}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="pxn-proposals" className="text-xs">
                      <HelpTip text={tip("submit.pxn_proposals")}>
                        {msg("submit.pxn.proposals")}
                      </HelpTip>
                    </Label>
                    <NumberInput
                      id="pxn-proposals"
                      min={1}
                      max={16}
                      step={1}
                      value={pxnProposals ? parseInt(pxnProposals, 10) : ""}
                      onChange={(v) => setPxnProposals(String(v))}
                    />
                  </div>
                  {pxnBatch > 1 && (
                    <p className="col-span-1 -mt-2 text-xs text-muted-foreground sm:col-span-2">
                      {formatMsg("submit.pxn.batch_hint", { total: pxnBatch })}
                    </p>
                  )}
                  <div className="col-span-1 space-y-1.5 sm:col-span-2">
                    <Label htmlFor="target-score" className="text-xs">
                      <HelpTip text={tip("submit.target_score")}>
                        {msg("auto.features.submit.components.steps.paramsstep.16")}
                      </HelpTip>
                    </Label>
                    <div className="relative w-full max-w-48">
                      <NumberInput
                        id="target-score"
                        min={1}
                        max={100}
                        step={0.1}
                        value={Number.isFinite(targetScoreValue) ? targetScoreValue : ""}
                        onChange={(value) => setTargetScore(String(value))}
                        className="pe-8"
                      />
                      <span className="pointer-events-none absolute inset-y-0 end-3 flex items-center text-xs text-muted-foreground">
                        %
                      </span>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
