"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import { Sparkles, Check } from "lucide-react";

import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { HelpTip } from "@/shared/ui/help-tip";
import { tip } from "@/shared/lib/tooltips";
import { cn } from "@/shared/lib/utils";
import { TERMS } from "@/shared/lib/terms";

import type { SubmitWizardContext } from "../../hooks/use-submit-wizard";
import type { ArtifactStatus } from "../../hooks/use-code-agent";
import { CodeAgentPanel, VersionStepper } from "./CodeAgentPanel";

const CodeEditor = dynamic(() => import("@/shared/ui/code-editor").then((m) => m.CodeEditor), {
  ssr: false,
  loading: () => (
    <div className="h-[200px] rounded-lg border border-border/40 bg-muted/20 animate-pulse" />
  ),
});

export function CodeStep({ w }: { w: SubmitWizardContext }) {
  const {
    signatureCode,
    setSignatureCode,
    setSignatureManuallyEdited,
    signatureValidation,
    setSignatureValidation,
    metricCode,
    setMetricCode,
    setMetricManuallyEdited,
    metricValidation,
    setMetricValidation,
    runSignatureValidation,
    runMetricValidation,
    codeAssistMode,
    setCodeAssistMode,
    parsedDataset,
    columnRoles,
    agent,
  } = w;

  const hasContext = React.useMemo(() => {
    if (!parsedDataset || parsedDataset.rowCount === 0) return false;
    const hasInput = Object.values(columnRoles).some((r) => r === "input");
    const hasOutput = Object.values(columnRoles).some((r) => r === "output");
    return hasInput && hasOutput;
  }, [parsedDataset, columnRoles]);

  const disabledReason = !hasContext
    ? parsedDataset
      ? "הגדר תפקידי עמודות תחילה (קלט ופלט)"
      : `העלה ${TERMS.dataset} תחילה`
    : undefined;

  return (
    <div data-tutorial="wizard-step-4">
      <div className="overflow-hidden rounded-2xl border border-border/50 bg-card/80 backdrop-blur-xl shadow-lg">
        <ModeToggle
          value={codeAssistMode}
          onChange={setCodeAssistMode}
          disabledReason={disabledReason}
        />
        <div
          className={cn(
            "grid grid-cols-1",
            codeAssistMode === "auto" && "lg:grid-cols-[400px_minmax(0,1fr)]",
          )}
        >
          {codeAssistMode === "auto" && (
            <div className="relative min-h-[560px] self-stretch overflow-hidden border-b border-border/40 lg:border-b-0 lg:border-e">
              <CodeAgentPanel
                agent={agent}
                disabled={!hasContext}
                disabledReason={disabledReason}
                className="absolute inset-0"
              />
            </div>
          )}
          <div className="flex flex-col self-stretch">
            <div className="shrink-0 border-b border-border/30 px-6 py-3">
              <h3 className="inline-flex text-lg font-semibold tracking-tight text-foreground">
                <HelpTip
                  text={
                    codeAssistMode === "auto"
                      ? `הסוכן כתב את הקוד לפי ה${TERMS.dataset} שלך. אפשר לבקש שינוי בצ'אט או לעבור למצב ידני.`
                      : `הגדר את ה${TERMS.signature} של המשימה ו${TERMS.metric} באופן ידני.`
                  }
                >
                  קוד
                </HelpTip>
              </h3>
            </div>
            <div className="space-y-4 px-6 py-4">
              <div
                className={cn(
                  "space-y-2 transition-opacity duration-300",
                  codeAssistMode === "auto" && agent.metricStatus === "writing" && "opacity-50",
                )}
                data-tutorial="signature-editor"
              >
                <div className="flex items-center justify-between gap-2">
                  <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <HelpTip text={tip("code.signature")}>Signature</HelpTip>
                  </Label>
                  <div className="flex items-center gap-2">
                    {codeAssistMode === "auto" && (
                      <VersionStepper agent={agent} artifact="signature" />
                    )}
                    {codeAssistMode === "auto" && (
                      <ArtifactStatusChip status={agent.signatureStatus} />
                    )}
                  </div>
                </div>
                <CodeEditor
                  value={signatureCode}
                  onChange={(v) => {
                    setSignatureCode(v);
                    setSignatureManuallyEdited(true);
                    setSignatureValidation(null);
                  }}
                  height="180px"
                  onRun={runSignatureValidation}
                  validationResult={signatureValidation}
                  streaming={codeAssistMode === "auto" && agent.signatureStatus === "writing"}
                  flashLines={codeAssistMode === "auto" ? agent.signatureFlashLines : undefined}
                />
              </div>
              <Separator />
              <div
                className={cn(
                  "space-y-2 transition-opacity duration-300",
                  codeAssistMode === "auto" && agent.signatureStatus === "writing" && "opacity-50",
                )}
                data-tutorial="metric-editor"
              >
                <div className="flex items-center justify-between gap-2">
                  <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <HelpTip text={tip("code.metric")}>Metric</HelpTip>
                  </Label>
                  <div className="flex items-center gap-2">
                    {codeAssistMode === "auto" && (
                      <VersionStepper agent={agent} artifact="metric" />
                    )}
                    {codeAssistMode === "auto" && (
                      <ArtifactStatusChip status={agent.metricStatus} />
                    )}
                  </div>
                </div>
                <CodeEditor
                  value={metricCode}
                  onChange={(v) => {
                    setMetricCode(v);
                    setMetricManuallyEdited(true);
                    setMetricValidation(null);
                  }}
                  height="180px"
                  onRun={runMetricValidation}
                  validationResult={metricValidation}
                  streaming={codeAssistMode === "auto" && agent.metricStatus === "writing"}
                  flashLines={codeAssistMode === "auto" ? agent.metricFlashLines : undefined}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ArtifactStatusChip({ status }: { status: ArtifactStatus }) {
  if (status === "idle") return null;
  if (status === "waiting") {
    return (
      <span className="inline-flex items-center gap-1 text-[0.6875rem] font-medium text-muted-foreground/70">
        ממתין
        <span className="size-1.5 rounded-full bg-muted-foreground/40" />
      </span>
    );
  }
  if (status === "writing") {
    return (
      <span className="inline-flex items-center gap-1 text-[0.6875rem] font-medium text-[#3D2E22]">
        כותב…
        <span className="size-1.5 rounded-full bg-[#3D2E22] animate-pulse" />
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[0.6875rem] font-medium text-[#5A7247]">
      הושלם
      <Check className="size-3" />
    </span>
  );
}

interface ModeToggleProps {
  value: "auto" | "manual";
  onChange: (mode: "auto" | "manual") => void;
  disabledReason?: string;
}

function ModeToggle({ value, onChange, disabledReason }: ModeToggleProps) {
  const autoDisabled = !!disabledReason && value !== "auto";

  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/40 bg-[#FAF8F5] px-4 py-2.5">
      <div className="flex items-center gap-1.5 text-xs text-[#5C4D40]">
        <Sparkles className="h-3.5 w-3.5 text-[#3D2E22]" />
        <span className="font-medium">
          {value === "auto" ? `הסוכן יכתוב את הקוד לפי ה${TERMS.dataset} שלך` : "כתיבת הקוד ידנית"}
        </span>
      </div>

      <div className="relative inline-grid grid-cols-2 rounded-lg bg-muted p-1 gap-1">
        <div
          aria-hidden
          className="absolute top-1 bottom-1 w-[calc(50%-6px)] rounded-md bg-background shadow-sm transition-[inset-inline-start] duration-150 ease-out pointer-events-none"
          style={{ insetInlineStart: value === "auto" ? 4 : "calc(50% + 2px)" }}
        />
        <button
          type="button"
          onClick={() => onChange("auto")}
          disabled={autoDisabled}
          title={autoDisabled ? disabledReason : undefined}
          aria-pressed={value === "auto"}
          className={cn(
            "relative z-[1] rounded-md px-4 py-1 text-xs font-medium leading-none text-center transition-colors cursor-pointer",
            value === "auto" ? "text-foreground" : "text-muted-foreground hover:text-foreground",
            autoDisabled && "opacity-40 cursor-not-allowed hover:text-muted-foreground",
          )}
        >
          אוטומטי
        </button>
        <button
          type="button"
          onClick={() => onChange("manual")}
          aria-pressed={value === "manual"}
          className={cn(
            "relative z-[1] rounded-md px-4 py-1 text-xs font-medium leading-none text-center transition-colors cursor-pointer",
            value === "manual" ? "text-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          ידני
        </button>
      </div>
    </div>
  );
}
