"use client";

import { AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { HelpTip } from "@/components/help-tip";
import { ModelChip, AddModelButton } from "@/components/model-chip";
import { ModelConfigModal } from "@/components/model-config-modal";

import { emptyModelConfig } from "../../constants";
import type { SubmitWizardContext } from "../../hooks/use-submit-wizard";

export function ModelStep({ w }: { w: SubmitWizardContext }) {
  const {
    moduleName,
    setModuleName,
    optimizerName,
    setOptimizerName,
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
    editingModel,
    setEditingModel,
    saveToRecent,
    recentConfigs,
    clearRecentConfigs,
    catalog,
  } = w;

  return (
    <Card
      className="border-border/50 bg-card/80 backdrop-blur-xl shadow-lg"
      data-tutorial="wizard-step-3"
    >
      <CardHeader>
        <CardTitle className="text-lg">הגדרות מודל ואופטימיזציה</CardTitle>
        <CardDescription>בחר מודול, אופטימייזר ומודלי שפה</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-2" data-tutorial="module-selector">
            <Label>
              <HelpTip text="אופן עיבוד הפרומפט — Predict שולח ישירות, CoT מוסיף שלב חשיבה לפני התשובה">
                מודול
              </HelpTip>
            </Label>
            <div className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1">
              <div
                className="absolute top-1 bottom-1 w-[calc(50%-6px)] rounded-md bg-background shadow-sm transition-[inset-inline-start] duration-100 ease-out"
                style={{ insetInlineStart: moduleName === "predict" ? 4 : "calc(50% + 2px)" }}
              />
              {(
                [
                  ["predict", "Predict"],
                  ["cot", "CoT"],
                ] as const
              ).map(([val, label]) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => setModuleName(val)}
                  className={cn(
                    "relative z-10 flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-200 text-center cursor-pointer",
                    moduleName === val
                      ? "text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-2" data-tutorial="optimizer-selector">
            <Label>
              <HelpTip text="אלגוריתם האופטימיזציה — MIPROv2 מנסה שילובי הוראות ודוגמאות, GEPA משפר באמצעות רפלקציה על שגיאות">
                אופטימייזר
              </HelpTip>
            </Label>
            <div className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1">
              <div
                className="absolute top-1 bottom-1 w-[calc(50%-6px)] rounded-md bg-background shadow-sm transition-[inset-inline-start] duration-100 ease-out"
                style={{ insetInlineStart: optimizerName === "miprov2" ? 4 : "calc(50% + 2px)" }}
              />
              {(
                [
                  ["miprov2", "MIPROv2"],
                  ["gepa", "GEPA"],
                ] as const
              ).map(([val, label]) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => setOptimizerName(val)}
                  className={cn(
                    "relative z-10 flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-200 text-center cursor-pointer",
                    optimizerName === val
                      ? "text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <Separator />

        {/* Global provider settings */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="baseUrl">כתובת שרת (Base URL)</Label>
            <Input
              id="baseUrl"
              dir="ltr"
              value={globalBaseUrl}
              onChange={(e) => setGlobalBaseUrl(e.target.value)}
            />
            <p className="text-[10px] text-muted-foreground">
              ניתן להשאיר ריק — יוגדר אוטומטית לפי הספק
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="apiKey">מפתח API</Label>
            <Input
              id="apiKey"
              dir="ltr"
              type="password"
              placeholder="sk-..."
              value={globalApiKey}
              onChange={(e) => setGlobalApiKey(e.target.value)}
            />
            {anyProviderHasEnvKey && (
              <p className="text-[10px] text-muted-foreground">
                אופציונאלי- מפתח API ילקח ממשתנה סביבה
              </p>
            )}
            {globalApiKey &&
              typeof window !== "undefined" &&
              window.location.protocol !== "https:" &&
              process.env.NODE_ENV === "production" && (
                <p className="text-[10px] text-amber-600 dark:text-amber-400 flex items-center gap-1">
                  <AlertTriangle className="size-3 shrink-0" />
                  ⚠️ חיבור לא מוצפן — מפתח ה-API יישלח ללא הצפנה. השתמשו ב-HTTPS בסביבת ייצור.
                </p>
              )}
          </div>
        </div>

        <Separator />

        {/* Model chips */}
        {jobType === "run" ? (
          <div className="space-y-3" data-tutorial="model-catalog">
            <Label className="text-sm font-semibold">מודלים</Label>
            <div className="space-y-2">
              <ModelChip
                config={modelConfig}
                roleLabel="מודל יצירה"
                required
                onClick={() =>
                  setEditingModel({
                    config: modelConfig,
                    onSave: setModelConfig,
                    label: "מודל יצירה",
                  })
                }
                onRemove={modelConfig.name ? () => setModelConfig(emptyModelConfig()) : undefined}
              />
              <ModelChip
                config={secondModelConfig ?? emptyModelConfig()}
                roleLabel="מודל רפלקציה"
                required
                onClick={() =>
                  setEditingModel({
                    config: secondModelConfig ?? emptyModelConfig(),
                    onSave: setSecondModelConfig,
                    label: "מודל רפלקציה",
                  })
                }
                onRemove={secondModelConfig?.name ? () => setSecondModelConfig(null) : undefined}
              />
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            <div className="space-y-2">
              <Label className="text-sm font-semibold">מודלי יצירה</Label>
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
                        label: `מודל יצירה ${i + 1}`,
                      })
                    }
                    onRemove={
                      generationModels.length > 1
                        ? () => setGenerationModels(generationModels.filter((_, j) => j !== i))
                        : undefined
                    }
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
                        label: "מודל יצירה חדש",
                      })
                    }
                  />
                )}
              </div>
            </div>
            <Separator />
            <div className="space-y-2">
              <Label className="text-sm font-semibold">מודלי רפלקציה</Label>
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
                        label: `מודל רפלקציה ${i + 1}`,
                      })
                    }
                    onRemove={
                      reflectionModels.length > 1
                        ? () => setReflectionModels(reflectionModels.filter((_, j) => j !== i))
                        : undefined
                    }
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
                        label: "מודל רפלקציה חדש",
                      })
                    }
                  />
                )}
              </div>
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
        />
      </CardContent>
    </Card>
  );
}
