"use client";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { NumberInput } from "@/components/number-input";
import { HelpTip } from "@/components/help-tip";
import { cn } from "@/lib/utils";

import type { SubmitWizardContext } from "../../hooks/use-submit-wizard";

export function ParamsStep({ w }: { w: SubmitWizardContext }) {
  const {
    split,
    updateSplit,
    splitSum,
    shuffle,
    setShuffle,
    optimizerName,
    autoLevel,
    setAutoLevel,
    maxBootstrappedDemos,
    setMaxBootstrappedDemos,
    maxLabeledDemos,
    setMaxLabeledDemos,
    numTrials,
    setNumTrials,
    minibatch,
    setMinibatch,
    minibatchSize,
    setMinibatchSize,
    reflectionMinibatchSize,
    setReflectionMinibatchSize,
    maxFullEvals,
    setMaxFullEvals,
    useMerge,
    setUseMerge,
  } = w;

  return (
    <Card
      className=" border-border/50 bg-card/80 backdrop-blur-xl shadow-lg"
      data-tutorial="wizard-step-5"
    >
      <CardHeader>
        <CardTitle className="text-lg">פרמטרים</CardTitle>
        <CardDescription>חלוקת הנתונים והגדרות האופטימייזר</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Split fractions */}
        <div className="space-y-3" data-tutorial="data-splits">
          <div className="flex items-center justify-between">
            <Label className="font-semibold">
              <HelpTip text="הנתונים מחולקים לשלוש קבוצות — אימון ללמידה, אימות לכיוונון, ובדיקה למדידת הביצועים הסופיים">
                חלוקת דאטאסט
              </HelpTip>
            </Label>
            {splitSum !== 1 && (
              <Badge variant="destructive" className="text-xs">
                סכום: {splitSum}
              </Badge>
            )}
          </div>
          <div className="flex h-3 rounded-full overflow-hidden">
            <div
              className="bg-[#3D2E22] transition-all"
              style={{ width: `${split.train * 100}%` }}
            />
            <div className="bg-[#C8A882] transition-all" style={{ width: `${split.val * 100}%` }} />
            <div
              className="bg-[#8C7A6B] transition-all"
              style={{ width: `${split.test * 100}%` }}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="space-y-1">
              <Label htmlFor="split-train" className="flex items-center gap-1.5 text-xs">
                <span className="inline-block w-2 h-2 rounded-full bg-[#3D2E22]" />
                <HelpTip text="דוגמאות שהאופטימייזר לומד מהן">אימון</HelpTip>
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
                <HelpTip text="דוגמאות לכיוונון פנימי במהלך האופטימיזציה">אימות</HelpTip>
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
                <HelpTip text="דוגמאות שמורות למדידה סופית — לא נחשפות באימון">בדיקה</HelpTip>
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

        <Separator />

        {/* Advanced settings inline */}
        <div className="space-y-4">
          <Label className="font-semibold">הגדרות נוספות</Label>
          <div className="flex items-center justify-between">
            <Label htmlFor="shuffle" className="cursor-pointer text-sm">
              <HelpTip text="ערבוב סדר השורות בדאטאסט לפני החלוקה — מונע הטיה מסדר הנתונים">
                ערבוב
              </HelpTip>
            </Label>
            <Switch id="shuffle" checked={shuffle} onCheckedChange={setShuffle} />
          </div>
          {/* Optimizer-specific parameters */}
          <Separator />
          <Label className="font-semibold text-xs text-muted-foreground">פרמטרי אופטימייזר</Label>

          {/* Common: auto level */}
          <div className="space-y-2" data-tutorial="auto-level">
            <Label className="text-sm">
              <HelpTip text="עומק החיפוש — קלה מהירה עם פחות ניסיונות, מעמיקה בודקת יותר שילובים אך לוקחת זמן רב יותר">
                רמת חיפוש (auto)
              </HelpTip>
            </Label>
            <div className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1">
              {autoLevel && (
                <div
                  className="absolute top-1 bottom-1 rounded-md bg-background shadow-sm transition-[inset-inline-start] duration-100 ease-out pointer-events-none"
                  style={{
                    width: "calc((100% - 8px) / 3)",
                    insetInlineStart: `calc(${(["light", "medium", "heavy"] as string[]).indexOf(autoLevel)} * (100% / 3) + 4px)`,
                  }}
                />
              )}
              {(
                [
                  ["light", "קלה"],
                  ["medium", "בינונית"],
                  ["heavy", "מעמיקה"],
                ] as const
              ).map(([val, label]) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => setAutoLevel(autoLevel === val ? "" : val)}
                  className={cn(
                    "relative z-[1] flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors text-center cursor-pointer",
                    autoLevel === val
                      ? "text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {optimizerName === "miprov2" ? (
            <div className="grid grid-cols-2 gap-3" data-tutorial="mipro-params">
              <div className="space-y-1.5">
                <Label className="text-xs">
                  <HelpTip text="דוגמאות שהמערכת מייצרת אוטומטית מתוך הנתונים כדי ללמד את המודל">
                    דוגמאות אוטומטיות
                  </HelpTip>
                </Label>
                <NumberInput
                  min={0}
                  max={20}
                  step={1}
                  value={maxBootstrappedDemos ? parseInt(maxBootstrappedDemos, 10) : ""}
                  onChange={(v) => setMaxBootstrappedDemos(String(v))}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">
                  <HelpTip text="דוגמאות קלט-פלט מתוך הדאטאסט שמוצגות למודל כהדגמה">
                    דוגמאות מהנתונים
                  </HelpTip>
                </Label>
                <NumberInput
                  min={0}
                  max={20}
                  step={1}
                  value={maxLabeledDemos ? parseInt(maxLabeledDemos, 10) : ""}
                  onChange={(v) => setMaxLabeledDemos(String(v))}
                />
              </div>
              <div className="space-y-1.5">
                <Label className={cn("text-xs", autoLevel && "text-muted-foreground/50")}>
                  <HelpTip text="כמה שילובים שונים של הוראות ודוגמאות האופטימייזר ינסה">
                    מספר ניסיונות
                  </HelpTip>
                </Label>
                <NumberInput
                  min={1}
                  max={100}
                  step={1}
                  value={numTrials ? parseInt(numTrials, 10) : ""}
                  onChange={(v) => setNumTrials(String(v))}
                  disabled={!!autoLevel}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">
                  <HelpTip text="מספר הדוגמאות שנבדקות בכל סבב הערכה — מדגם קטן מזרז, גדול מדויק יותר">
                    גודל מדגם
                  </HelpTip>
                </Label>
                <NumberInput
                  min={1}
                  max={200}
                  step={1}
                  value={minibatchSize ? parseInt(minibatchSize, 10) : ""}
                  onChange={(v) => setMinibatchSize(String(v))}
                />
              </div>
              <div className="col-span-2 flex items-center justify-between">
                <Label className="text-sm cursor-pointer">
                  <HelpTip text="כשפעיל, הערכה רצה על מדגם קטן במקום הדאטאסט המלא — מאיץ את התהליך">
                    בדיקה חלקית
                  </HelpTip>
                </Label>
                <Switch checked={minibatch} onCheckedChange={setMinibatch} />
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3" data-tutorial="gepa-params">
              <div className="space-y-1.5">
                <Label className="text-xs">
                  <HelpTip text="כמה דוגמאות המודל מנתח בכל סבב רפלקציה כדי לזהות דפוסי שגיאה">
                    גודל מדגם לרפלקציה
                  </HelpTip>
                </Label>
                <NumberInput
                  min={1}
                  max={20}
                  step={1}
                  value={reflectionMinibatchSize ? parseInt(reflectionMinibatchSize, 10) : ""}
                  onChange={(v) => setReflectionMinibatchSize(String(v))}
                />
              </div>
              <div className="space-y-1.5">
                <Label className={cn("text-xs", autoLevel && "text-muted-foreground/50")}>
                  <HelpTip text="מספר הפעמים שהמערכת מריצה הערכה מלאה על כל הנתונים">
                    מקסימום סבבי הערכה
                  </HelpTip>
                </Label>
                <NumberInput
                  min={1}
                  max={50}
                  step={1}
                  value={maxFullEvals ? parseInt(maxFullEvals, 10) : ""}
                  onChange={(v) => setMaxFullEvals(String(v))}
                  disabled={!!autoLevel}
                />
              </div>
              <div className="col-span-2 flex items-center justify-between">
                <Label className="text-sm cursor-pointer">
                  <HelpTip text="כשפעיל, המערכת משלבת הוראות מכמה מועמדים טובים לפרומפט אחד משופר">
                    מיזוג מועמדים
                  </HelpTip>
                </Label>
                <Switch checked={useMerge} onCheckedChange={setUseMerge} />
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
