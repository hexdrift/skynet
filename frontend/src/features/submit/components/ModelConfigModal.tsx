"use client";

import * as React from "react";
import { Boxes } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { ModelPicker, modelSupportsThinking } from "@/features/submit/components/ModelPicker";
import { NumberInput } from "@/shared/ui/number-input";
import { cn } from "@/shared/lib/utils";
import type { ModelConfig, CatalogModel } from "@/shared/types/api";
import { HelpTip } from "@/shared/ui/help-tip";
import { tip } from "@/shared/lib/tooltips";
import { TERMS } from "@/shared/lib/terms";

interface ModelConfigModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: ModelConfig;
  onSave: (config: ModelConfig) => void;
  /** Label shown in the dialog header, e.g. "מודל ראשי" or the reflection-model term. */
  roleLabel?: string;
  /** Catalog models for thinking detection */
  catalogModels?: CatalogModel[];
  /** Recently used configs — shown as quick-select at top */
  recentConfigs?: ModelConfig[];
  /** Clear all recent configs */
  onClearRecent?: () => void;
  /**
   * When provided, renders a pinned "all available models" sentinel row at the
   * top of the dialog body. Clicking it closes the modal and invokes the
   * callback — the caller is expected to flip the matching grid-search flag.
   */
  onSelectAllAvailable?: () => void;
}

export function ModelConfigModal({
  open,
  onOpenChange,
  config,
  onSave,
  roleLabel = "הגדרות מודל",
  catalogModels,
  recentConfigs,
  onClearRecent,
  onSelectAllAvailable,
}: ModelConfigModalProps) {
  const [draft, setDraft] = React.useState<ModelConfig>(config);

  // Sync draft when config changes externally (e.g. opening with different model)
  React.useEffect(() => {
    if (open) setDraft(config);
  }, [open, config]);

  const canThink = modelSupportsThinking(draft.name, catalogModels);
  const thinkingEnabled = !!draft.extra?.reasoning_effort;
  const reasoningEffort = (draft.extra?.reasoning_effort as string) ?? "medium";

  const setThinking = (on: boolean) => {
    setDraft((p) => ({
      ...p,
      extra: on
        ? { ...p.extra, reasoning_effort: "medium" }
        : (() => {
            const { reasoning_effort: _, ...rest } = p.extra ?? {};
            return Object.keys(rest).length ? rest : undefined;
          })(),
    }));
  };

  const setEffort = (level: string) => {
    setDraft((p) => ({ ...p, extra: { ...p.extra, reasoning_effort: level } }));
  };

  const handleSave = () => {
    onSave(draft);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{roleLabel}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {onSelectAllAvailable &&
            (() => {
              const availableCount = catalogModels?.length ?? 0;
              const disabled = availableCount === 0;
              return (
                <>
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => {
                      onSelectAllAvailable();
                      onOpenChange(false);
                    }}
                    className={cn(
                      "group flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-start transition-all",
                      disabled
                        ? "cursor-not-allowed border-border/40 bg-muted/20 opacity-60"
                        : "cursor-pointer border-primary/30 bg-primary/5 hover:border-primary/50 hover:bg-primary/10",
                    )}
                  >
                    <span
                      className={cn(
                        "flex size-9 shrink-0 items-center justify-center rounded-md",
                        disabled
                          ? "bg-muted text-muted-foreground"
                          : "bg-primary/10 text-primary group-hover:bg-primary/15",
                      )}
                    >
                      <Boxes className="size-4" />
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="text-sm font-medium text-foreground">
                        כל המודלים הזמינים
                      </span>
                      <span className="text-[0.6875rem] text-muted-foreground">
                        {disabled
                          ? "אין מודלים זמינים — הגדר API key"
                          : `ירוץ ${TERMS.optimization} לכל ${TERMS.model} בקטלוג · ${availableCount} כרגע`}
                      </span>
                    </span>
                  </button>
                  <Separator />
                </>
              );
            })()}

          {/* Recent configs */}
          {recentConfigs && recentConfigs.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label className="text-[0.625rem] uppercase tracking-wide text-muted-foreground">
                  הגדרות אחרונות
                </Label>
                {onClearRecent && (
                  <button
                    type="button"
                    onClick={onClearRecent}
                    className="text-[0.625rem] text-muted-foreground/60 hover:text-destructive transition-colors cursor-pointer"
                  >
                    נקה
                  </button>
                )}
              </div>
              <div className="flex gap-1.5 overflow-x-auto pb-1.5 scrollbar-thin" dir="ltr">
                {recentConfigs.map((rc, i) => (
                  <button
                    key={`${rc.name}-${i}`}
                    type="button"
                    onClick={() => setDraft({ ...rc })}
                    className={cn(
                      "flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 text-[0.6875rem] font-mono transition-all cursor-pointer",
                      draft.name === rc.name
                        ? "border-primary/50 bg-primary/5 text-foreground"
                        : "border-border/40 bg-muted/30 text-muted-foreground hover:border-primary/40 hover:text-foreground hover:bg-muted/50",
                    )}
                  >
                    <span className="truncate max-w-[120px]">{rc.name.split("/").pop()}</span>
                    <span className="text-[9px] opacity-60">{rc.temperature?.toFixed(1)}</span>
                  </button>
                ))}
              </div>
              <Separator />
            </div>
          )}

          {/* Model picker */}
          <div className="space-y-2">
            <Label>מודל</Label>
            <ModelPicker
              value={draft.name}
              onChange={(next) => {
                setDraft((p) => ({ ...p, name: next }));
                // Reset thinking if new model doesn't support it
                if (!modelSupportsThinking(next, catalogModels)) {
                  setDraft((p) => {
                    const { reasoning_effort: _, ...rest } = p.extra ?? {};
                    return { ...p, extra: Object.keys(rest).length ? rest : undefined };
                  });
                }
              }}
              placeholder="בחר מודל..."
            />
          </div>

          <Separator />

          {/* Temperature */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>
                <HelpTip text={tip("model_config.temperature")}>טמפרטורה</HelpTip>
              </Label>
              <span className="text-xs font-mono text-muted-foreground">
                {draft.temperature?.toFixed(1) ?? "0.7"}
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={draft.temperature ?? 0.7}
              onChange={(e) => setDraft((p) => ({ ...p, temperature: parseFloat(e.target.value) }))}
              className="w-full h-2 bg-muted rounded-full appearance-none cursor-pointer accent-primary"
              dir="ltr"
            />
          </div>

          {/* Top P */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>
                <HelpTip text={tip("model_config.top_p")}>Top P</HelpTip>
              </Label>
              <span className="text-xs font-mono text-muted-foreground">
                {draft.top_p?.toFixed(2) ?? "—"}
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={draft.top_p ?? 1}
              onChange={(e) => setDraft((p) => ({ ...p, top_p: parseFloat(e.target.value) }))}
              className="w-full h-2 bg-muted rounded-full appearance-none cursor-pointer accent-primary"
              dir="ltr"
            />
          </div>

          {/* Max tokens */}
          <div className="space-y-2">
            <Label>
              <HelpTip text={tip("model_config.max_tokens")}>מקסימום טוקנים</HelpTip>
            </Label>
            <NumberInput
              min={1}
              step={256}
              value={draft.max_tokens ?? ""}
              onChange={(v) => setDraft((p) => ({ ...p, max_tokens: v }))}
            />
          </div>

          {/* Thinking mode — only if model supports it */}
          {canThink && (
            <>
              <Separator />
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label>מצב חשיבה (Thinking)</Label>
                  <Switch checked={thinkingEnabled} onCheckedChange={setThinking} />
                </div>
                {thinkingEnabled && (
                  <div className="space-y-2 p-3 border rounded-lg bg-muted/30">
                    <Label>רמת חשיבה</Label>
                    <div className="flex rounded-lg bg-muted p-0.5 w-full">
                      {(
                        [
                          ["low", "נמוכה"],
                          ["medium", "בינונית"],
                          ["high", "גבוהה"],
                        ] as const
                      ).map(([val, label]) => (
                        <button
                          key={val}
                          type="button"
                          onClick={() => setEffort(val)}
                          className={cn(
                            "flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors text-center cursor-pointer",
                            reasoningEffort === val
                              ? "bg-background text-foreground shadow-sm"
                              : "text-muted-foreground hover:text-foreground",
                          )}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        <DialogFooter className="grid grid-cols-2 gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} className="w-full">
            ביטול
          </Button>
          <Button onClick={handleSave} disabled={!draft.name.trim()} className="w-full">
            שמור
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
