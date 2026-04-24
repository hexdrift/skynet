"use client";

import * as React from "react";
import { AlertTriangle, Boxes, Check, Loader2, Sparkles, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/shared/lib/utils";
import { msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";
import { ModelChip, AddModelButton } from "@/shared/ui/model-chip";
import { ModelConfigModal } from "@/features/submit/components/ModelConfigModal";
import { ModelProbeDialog } from "@/features/submit/components/ModelProbeDialog";

import { emptyModelConfig } from "../../constants";
import type { SubmitWizardContext } from "../../hooks/use-submit-wizard";

interface AllAvailableChipProps {
  availableCount: number;
  onReset: () => void;
}

/**
 * Wide chip shown in place of the manual list once "all available" is on.
 *
 * Uses the same visual language as ModelChip but reads as a single pinned
 * selection that sweeps every catalog model. The reset button flips the
 * sentinel flag back off, returning the side to manual mode.
 */
function AllAvailableChip({ availableCount, onReset }: AllAvailableChipProps) {
  return (
    <div
      className={cn(
        "group relative flex w-full items-center gap-3 rounded-lg border px-3 py-2.5",
        "border-primary/30 bg-primary/5",
      )}
    >
      <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
        <Boxes className="size-4" />
      </span>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="text-sm font-medium text-foreground">כל המודלים הזמינים</span>
        <span className="text-[0.6875rem] text-muted-foreground">
          ירוץ {TERMS.optimization} לכל {TERMS.model} בקטלוג · {availableCount} כרגע
        </span>
      </div>
      <button
        type="button"
        onClick={onReset}
        className="cursor-pointer rounded-md p-1 text-muted-foreground opacity-60 transition-all hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
        title="הסר"
      >
        <Trash2 className="size-3.5" />
      </button>
    </div>
  );
}

export function ModelStep({ w }: { w: SubmitWizardContext }) {
  const {
    globalBaseUrl,
    setGlobalBaseUrl,
    globalApiKey,
    setGlobalApiKey,
    anyProviderHasEnvKey,
    jobType,
    modelConfig,
    setModelConfig,
    secondModelConfig,
    setSecondModelConfig,
    generationModels,
    setGenerationModels,
    reflectionModels,
    setReflectionModels,
    useAllGenerationModels,
    setUseAllGenerationModels,
    useAllReflectionModels,
    setUseAllReflectionModels,
    editingModel,
    setEditingModel,
    saveToRecent,
    recentConfigs,
    clearRecentConfigs,
    catalog,
  } = w;

  const availableCount = catalog?.models.length ?? 0;
  const catalogEmpty = catalog != null && availableCount === 0;
  const [probeOpen, setProbeOpen] = React.useState(false);
  const [probeRunning, setProbeRunning] = React.useState(false);
  const [probeHasResults, setProbeHasResults] = React.useState(false);

  return (
    <Card
      className="border-border/50 bg-card/80 backdrop-blur-xl shadow-lg"
      data-tutorial="wizard-step-3"
    >
      <CardHeader>
        <CardTitle className="text-lg">מודלי שפה</CardTitle>
        <CardDescription>בחר את המודלים שיריצו את ה{TERMS.optimization}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="baseUrl">כתובת שרת (Base URL)</Label>
            <Input
              id="baseUrl"
              dir="ltr"
              value={globalBaseUrl}
              onChange={(e) => setGlobalBaseUrl(e.target.value)}
            />
            <p className="text-[0.625rem] text-muted-foreground">
              ניתן להשאיר ריק — יוגדר אוטומטית לפי הספק
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="apiKey">API key</Label>
            <Input
              id="apiKey"
              dir="ltr"
              type="password"
              placeholder="sk-..."
              value={globalApiKey}
              onChange={(e) => setGlobalApiKey(e.target.value)}
            />
            {anyProviderHasEnvKey && (
              <p className="text-[0.625rem] text-muted-foreground">
                אופציונאלי- API key ילקח ממשתנה סביבה
              </p>
            )}
            {globalApiKey &&
              typeof window !== "undefined" &&
              window.location.protocol !== "https:" &&
              process.env.NODE_ENV === "production" && (
                <p className="text-[0.625rem] text-amber-600 dark:text-amber-400 flex items-center gap-1">
                  <AlertTriangle className="size-3 shrink-0" />
                  חיבור לא מוצפן — API key יישלח ללא הצפנה. השתמשו ב-HTTPS בסביבת ייצור.
                </p>
              )}
          </div>
        </div>

        <Separator />

        {jobType === "run" ? (
          <div className="space-y-3" data-tutorial="model-catalog">
            <Label className="text-sm font-semibold">מודלים</Label>
            <button
              type="button"
              onClick={() => setProbeOpen(true)}
              className={cn(
                "group flex w-full items-start gap-3 rounded-lg border px-3 py-2.5 text-start transition-colors cursor-pointer",
                probeRunning
                  ? "border-primary/60 bg-primary/10 shadow-sm shadow-primary/10"
                  : probeHasResults
                    ? "border-emerald-500/40 bg-emerald-500/5 hover:border-emerald-500/60 hover:bg-emerald-500/10"
                    : "border-dashed border-primary/30 bg-primary/5 hover:border-primary/50 hover:bg-primary/10",
              )}
              data-tutorial="model-probe"
            >
              <span
                className={cn(
                  "flex size-9 shrink-0 items-center justify-center rounded-md",
                  probeRunning
                    ? "bg-primary/20 text-primary"
                    : probeHasResults
                      ? "bg-emerald-500/10 text-emerald-600 group-hover:bg-emerald-500/15"
                      : "bg-primary/10 text-primary group-hover:bg-primary/15",
                )}
              >
                {probeRunning ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : probeHasResults ? (
                  <Check className="size-4" />
                ) : (
                  <Sparkles className="size-4" />
                )}
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="text-sm font-medium text-foreground">
                  {probeRunning
                    ? "בדיקת מודלים רצה…"
                    : probeHasResults
                      ? "צפה בתוצאות הבדיקה"
                      : "לא בטוח איזה מודל לבחור?"}
                </span>
                <span className="text-[0.6875rem] text-muted-foreground">
                  {probeRunning
                    ? "לחץ כדי לראות את ההתקדמות"
                    : probeHasResults
                      ? "לחץ כדי לצפות או לבחור מודל מהתוצאות"
                      : `מצא את ה${TERMS.model} האופטימלי ל${TERMS.dataset} ולהגדרות שלך`}
                </span>
              </span>
            </button>
            <div className="space-y-2">
              <ModelChip
                config={modelConfig}
                roleLabel={msg("model.generation.label")}
                required
                onClick={() =>
                  setEditingModel({
                    config: modelConfig,
                    onSave: setModelConfig,
                    label: msg("model.generation.label"),
                  })
                }
                onRemove={modelConfig.name ? () => setModelConfig(emptyModelConfig()) : undefined}
              />
              <ModelChip
                config={secondModelConfig ?? emptyModelConfig()}
                roleLabel={TERMS.reflectionModel}
                required
                onClick={() =>
                  setEditingModel({
                    config: secondModelConfig ?? emptyModelConfig(),
                    onSave: setSecondModelConfig,
                    label: TERMS.reflectionModel,
                  })
                }
                onRemove={secondModelConfig?.name ? () => setSecondModelConfig(null) : undefined}
              />
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            {catalogEmpty && (
              <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-[0.75rem] text-amber-700 dark:text-amber-400">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                <span>אין מודלים זמינים בקטלוג — הגדר API key של ספק כדי להפעיל סריקה.</span>
              </div>
            )}
            <div className="space-y-2">
              <Label className="text-sm font-semibold">
                {msg("model.generation.label_plural")}
              </Label>
              {useAllGenerationModels ? (
                <AllAvailableChip
                  availableCount={availableCount}
                  onReset={() => setUseAllGenerationModels(false)}
                />
              ) : (
                <div className="flex flex-wrap gap-2">
                  {generationModels.map((m, i) => (
                    <ModelChip
                      key={i}
                      config={m}
                      onClick={() =>
                        setEditingModel({
                          config: m,
                          onSave: (c) => {
                            const u = [...generationModels];
                            u[i] = c;
                            setGenerationModels(u);
                          },
                          label: `${msg("model.generation.label")} ${i + 1}`,
                          onSelectAllAvailable: () => setUseAllGenerationModels(true),
                        })
                      }
                      onRemove={() => {
                        const next = generationModels.filter((_, j) => j !== i);
                        setGenerationModels(next.length ? next : [emptyModelConfig()]);
                      }}
                    />
                  ))}
                  {generationModels.every((m) => m.name.trim()) && (
                    <AddModelButton
                      label="הוסף"
                      onClick={() =>
                        setEditingModel({
                          config: generationModels.length
                            ? { ...generationModels[generationModels.length - 1], name: "" }
                            : emptyModelConfig(),
                          onSave: (c) =>
                            setGenerationModels([
                              ...generationModels.filter((m) => m.name.trim()),
                              c,
                            ]),
                          label: msg("model.generation.new"),
                          onSelectAllAvailable: () => setUseAllGenerationModels(true),
                        })
                      }
                    />
                  )}
                </div>
              )}
            </div>
            <Separator />
            <div className="space-y-2">
              <Label className="text-sm font-semibold">מודלי רפלקציה</Label>
              {useAllReflectionModels ? (
                <AllAvailableChip
                  availableCount={availableCount}
                  onReset={() => setUseAllReflectionModels(false)}
                />
              ) : (
                <div className="flex flex-wrap gap-2">
                  {reflectionModels.map((m, i) => (
                    <ModelChip
                      key={i}
                      config={m}
                      onClick={() =>
                        setEditingModel({
                          config: m,
                          onSave: (c) => {
                            const u = [...reflectionModels];
                            u[i] = c;
                            setReflectionModels(u);
                          },
                          label: `${TERMS.reflectionModel} ${i + 1}`,
                          onSelectAllAvailable: () => setUseAllReflectionModels(true),
                        })
                      }
                      onRemove={() => {
                        const next = reflectionModels.filter((_, j) => j !== i);
                        setReflectionModels(next.length ? next : [emptyModelConfig()]);
                      }}
                    />
                  ))}
                  {reflectionModels.every((m) => m.name.trim()) && (
                    <AddModelButton
                      label="הוסף"
                      onClick={() =>
                        setEditingModel({
                          config: reflectionModels.length
                            ? { ...reflectionModels[reflectionModels.length - 1], name: "" }
                            : emptyModelConfig(),
                          onSave: (c) =>
                            setReflectionModels([
                              ...reflectionModels.filter((m) => m.name.trim()),
                              c,
                            ]),
                          label: `${TERMS.reflectionModel} חדש`,
                          onSelectAllAvailable: () => setUseAllReflectionModels(true),
                        })
                      }
                    />
                  )}
                </div>
              )}
            </div>
          </div>
        )}
        {/* Model config modal — shared across all model chips */}
        <ModelConfigModal
          open={!!editingModel}
          onOpenChange={(open) => {
            if (!open) setEditingModel(null);
          }}
          config={editingModel?.config ?? emptyModelConfig()}
          onSave={(c) => {
            editingModel?.onSave(c);
            saveToRecent(c);
            setEditingModel(null);
          }}
          roleLabel={editingModel?.label ?? "הגדרות מודל"}
          catalogModels={catalog?.models}
          recentConfigs={recentConfigs}
          onClearRecent={clearRecentConfigs}
          onSelectAllAvailable={
            editingModel?.onSelectAllAvailable
              ? () => {
                  editingModel.onSelectAllAvailable?.();
                  setEditingModel(null);
                }
              : undefined
          }
        />
        <ModelProbeDialog
          open={probeOpen}
          onOpenChange={setProbeOpen}
          w={w}
          onSelect={(modelValue) => {
            setModelConfig({ ...modelConfig, name: modelValue });
          }}
          onRunningChange={setProbeRunning}
          onHasResultsChange={setProbeHasResults}
        />
      </CardContent>
    </Card>
  );
}
