"use client";

import { CaretDown } from "@/shared/ui/icons";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/shared/ui/primitives/card";
import { Input } from "@/shared/ui/primitives/input";
import { Textarea } from "@/shared/ui/primitives/textarea";
import { Label } from "@/shared/ui/primitives/label";
import { Separator } from "@/shared/ui/primitives/separator";
import { Segmented } from "@/shared/ui/segmented";
import { cn } from "@/shared/lib/utils";
import { TERMS } from "@/shared/lib/terms";
import { formatMsg, msg } from "@/shared/lib/messages";

import type { SubmitWizardContext } from "../../hooks/use-submit-wizard";
import { TOUCH_FIELD } from "@/shared/ui/touch";

export function BasicsStep({ w }: { w: SubmitWizardContext }) {
  const {
    jobName,
    setJobName,
    jobDescription,
    setJobDescription,
    jobType,
    setOptimizationType,
    isPrivate,
    setIsPrivate,
    optimizationTypeOpen,
    setOptimizationTypeOpen,
  } = w;

  return (
    <Card
      className="border-border/50 bg-card/80 backdrop-blur-xl shadow-lg"
      data-tutorial="wizard-step-1"
    >
      <CardHeader className="px-4 sm:px-6">
        <CardTitle className="text-lg">
          {msg("auto.features.submit.components.steps.basicsstep.1")}
        </CardTitle>
        <CardDescription>
          {msg("auto.features.submit.components.steps.basicsstep.2")}
          {TERMS.optimization}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 px-4 sm:px-6">
        <div className="space-y-2">
          <Label htmlFor="job-name">
            {msg("auto.features.submit.components.steps.basicsstep.3")}
            {TERMS.optimization}
          </Label>
          <Input
            id="job-name"
            placeholder={msg("auto.features.submit.components.steps.basicsstep.literal.1")}
            value={jobName}
            onChange={(e) => setJobName(e.target.value)}
            className={TOUCH_FIELD}
          />
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>{msg("auto.features.submit.components.steps.basicsstep.4")}</Label>
            <span
              className={cn(
                "text-[0.625rem] tabular-nums transition-colors",
                jobDescription.length > 280
                  ? "text-destructive font-medium"
                  : "text-muted-foreground/50",
              )}
            >
              {jobDescription.length}
              {msg("auto.features.submit.components.steps.basicsstep.5")}
            </span>
          </div>
          <Textarea
            data-tutorial="job-description"
            value={jobDescription}
            onChange={(e) => {
              if (e.target.value.length <= 280) setJobDescription(e.target.value);
            }}
            placeholder={formatMsg("auto.features.submit.components.steps.basicsstep.template.1", {
              p1: TERMS.optimization,
            })}
            rows={4}
          />
        </div>
        <div className="space-y-3">
          <Label>{msg("submit.basics.privacy.label")}</Label>
          <Segmented<"private" | "public">
            label={msg("submit.basics.privacy.label")}
            segmentClassName="sm:px-4"
            value={isPrivate ? "private" : "public"}
            onChange={(v) => setIsPrivate(v === "private")}
            options={[
              {
                value: "private",
                label: msg("submit.basics.privacy.private"),
                desc: msg("submit.basics.privacy.private_desc"),
              },
              {
                value: "public",
                label: msg("submit.basics.privacy.public"),
                desc: msg("submit.basics.privacy.public_desc"),
              },
            ]}
          />
        </div>
        <Separator />
        <div className="space-y-3">
          <button
            type="button"
            onClick={() => setOptimizationTypeOpen(!optimizationTypeOpen)}
            aria-expanded={optimizationTypeOpen}
            className="flex w-full cursor-pointer items-center justify-between gap-2"
          >
            <span className="flex items-baseline gap-2">
              <span className="text-sm leading-none font-medium">
                {msg("auto.features.submit.components.steps.basicsstep.6")}
                {TERMS.optimization}
              </span>
              {!optimizationTypeOpen && (
                <span className="text-xs text-muted-foreground">
                  {jobType === "run" ? TERMS.optimizationTypeRun : TERMS.optimizationTypeGrid}
                </span>
              )}
            </span>
            <CaretDown
              className={cn(
                "size-4 shrink-0 text-muted-foreground transition-transform duration-150",
                optimizationTypeOpen && "rotate-180",
              )}
            />
          </button>
          {optimizationTypeOpen && (
            <div className="motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-top-1 motion-safe:duration-200">
              <Segmented<"run" | "grid_search">
                segmentClassName="sm:px-4"
                value={jobType}
                onChange={setOptimizationType}
                options={[
                  {
                    value: "run",
                    label: TERMS.optimizationTypeRun,
                    desc: formatMsg("auto.features.submit.components.steps.basicsstep.template.2", {
                      p1: TERMS.optimization,
                      p2: TERMS.model,
                    }),
                  },
                  {
                    value: "grid_search",
                    label: TERMS.optimizationTypeGrid,
                    desc: formatMsg("auto.features.submit.components.steps.basicsstep.template.3", {
                      p1: TERMS.optimizationTypeGrid,
                    }),
                  },
                ]}
              />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
