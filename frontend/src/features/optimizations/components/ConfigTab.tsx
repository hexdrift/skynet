"use client";

/**
 * Config tab — displays the optimization settings (module, optimizer,
 * kwargs, models, dataset splits).
 *
 * Extracted from app/optimizations/[id]/page.tsx. Pure display component
 * that takes the job + payload data as props. Owns no state.
 */

import type { ReactNode } from "react";
import {
  Brain,
  Coins,
  Component,
  Cpu,
  Database,
  Dices,
  Layers,
  Lightbulb,
  ListTodo,
  Quote,
  Settings,
  Settings2,
  Shuffle,
  Target,
  Thermometer,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FadeIn } from "@/shared/ui/motion";
import { HelpTip } from "@/shared/ui/help-tip";
import type { OptimizationPayloadResponse, OptimizationStatusResponse } from "@/shared/types/api";
import { InfoCard } from "./ui-primitives";

const OPT_PARAM_LABELS: Record<string, string> = {
  auto: "רמת חיפוש",
  max_bootstrapped_demos: "דוגמאות אוטומטיות",
  max_labeled_demos: "דוגמאות מהנתונים",
  num_trials: "מספר ניסיונות",
  minibatch: "בדיקה חלקית",
  minibatch_size: "גודל מדגם",
  reflection_minibatch_size: "מדגם לרפלקציה",
  max_full_evals: "סבבי הערכה",
  use_merge: "מיזוג מועמדים",
  metric: "מטריקה",
};
const OPT_PARAM_TIPS: Record<string, string> = {
  auto: "עומק החיפוש — קלה מהירה, מעמיקה בודקת יותר שילובים",
  max_bootstrapped_demos: "דוגמאות שהמערכת מייצרת אוטומטית מתוך הנתונים",
  max_labeled_demos: "דוגמאות קלט-פלט מהדאטאסט שמוצגות למודל כהדגמה",
  num_trials: "כמה שילובים שונים של הוראות ודוגמאות האופטימייזר ינסה",
  minibatch: "כשפעיל, הערכה רצה על מדגם קטן במקום הדאטאסט המלא",
  minibatch_size: "מספר הדוגמאות שנבדקות בכל סבב הערכה",
  reflection_minibatch_size: "כמה דוגמאות המודל מנתח בכל סבב רפלקציה",
  max_full_evals: "מספר הפעמים שהמערכת מריצה הערכה מלאה על כל הנתונים",
  use_merge: "כשפעיל, המערכת משלבת הוראות מכמה מועמדים טובים לפרומפט אחד",
};

function labelWithTip(key: string): ReactNode {
  const label = OPT_PARAM_LABELS[key] || key;
  const tip = OPT_PARAM_TIPS[key];
  return tip ? <HelpTip text={tip}>{label}</HelpTip> : label;
}

function formatParamValue(_k: string, v: unknown): string {
  if (typeof v === "boolean") return v ? "כן" : "לא";
  return String(v);
}

/** Inline model-config card — matches the ModelChip style. */
function ModelCard({ label, cfg }: { label: string; cfg: Record<string, unknown> }) {
  const name = String(cfg.name || "—");
  const shortName = name.includes("/") ? name.split("/").pop()! : name;
  const temp = cfg.temperature as number | undefined;
  const maxTok = cfg.max_tokens as number | undefined;
  const extra = (cfg.extra ?? {}) as Record<string, unknown>;
  const reasoning = extra.reasoning_effort as string | undefined;
  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-border/50 bg-card/80 px-3 py-2">
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </span>
        <span className="truncate text-sm text-foreground font-mono font-medium" dir="ltr">
          {shortName}
        </span>
        <div className="flex items-center gap-2.5 text-[10px] text-muted-foreground" dir="ltr">
          {temp != null && (
            <span className="inline-flex items-center gap-0.5">
              <Thermometer className="size-2.5" />
              {temp.toFixed(1)}
            </span>
          )}
          {maxTok != null && (
            <span className="inline-flex items-center gap-0.5">
              <Coins className="size-2.5" />
              {maxTok}
            </span>
          )}
          {reasoning && (
            <span className="inline-flex items-center gap-0.5 text-primary/70">
              <Brain className="size-2.5" />
              {reasoning}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function ConfigTab({
  job,
  payload,
}: {
  job: OptimizationStatusResponse;
  payload: OptimizationPayloadResponse | null;
}) {
  // Merge job-level data with full payload for richer config display
  const p = (payload?.payload ?? {}) as Record<string, unknown>;
  const splitFractions = (p.split_fractions ??
    job.split_fractions ?? { train: 0.7, val: 0.15, test: 0.15 }) as {
    train: number;
    val: number;
    test: number;
  };
  const shuffleVal =
    p.shuffle != null ? Boolean(p.shuffle) : job.shuffle != null ? job.shuffle : true;
  const seedVal = (p.seed ?? job.seed) as number | undefined;
  const optKw = (p.optimizer_kwargs ?? job.optimizer_kwargs ?? {}) as Record<string, unknown>;
  const compKw = (p.compile_kwargs ?? job.compile_kwargs ?? {}) as Record<string, unknown>;
  const modelCfg = (p.model_config ?? job.model_settings ?? null) as Record<string, unknown> | null;
  const reflCfg = (p.reflection_model_config ?? null) as Record<string, unknown> | null;
  const promptCfg = (p.prompt_model_config ?? null) as Record<string, unknown> | null;
  const taskCfg = (p.task_model_config ?? null) as Record<string, unknown> | null;

  const items: { label: ReactNode; value: string; icon: ReactNode }[] = [
    {
      label: (
        <HelpTip text="אופן עיבוד הפרומפט — Predict שולח ישירות, CoT מוסיף שלב חשיבה">
          מודול
        </HelpTip>
      ),
      value: job.module_name ?? "—",
      icon: <Component className="size-3.5" />,
    },
    {
      label: <HelpTip text="אלגוריתם האופטימיזציה שמשפר את הפרומפט">אופטימייזר</HelpTip>,
      value: job.optimizer_name ?? "—",
      icon: <Target className="size-3.5" />,
    },
    ...Object.entries(optKw)
      .filter(([k]) => k !== "metric")
      .map(([k, v]) => ({
        label: labelWithTip(k),
        value: formatParamValue(k, v),
        icon: <Settings2 className="size-3.5" />,
      })),
    ...Object.entries(compKw).map(([k, v]) => ({
      label: labelWithTip(k),
      value: formatParamValue(k, v),
      icon: <Layers className="size-3.5" />,
    })),
  ];

  return (
    <>
      <FadeIn>
        <p className="text-sm text-muted-foreground mb-4">
          פרטי ההגדרות שנבחרו לאופטימיזציה זו — מודל, אופטימייזר, ופרמטרים.
        </p>
        {job.description && (
          <p className="text-sm text-foreground/70 leading-relaxed mb-4 border-s-2 border-[#C8A882]/40 ps-3">
            {job.description}
          </p>
        )}
      </FadeIn>
      <div className="space-y-4">
        {/* Section 1: General + Optimizer Parameters */}
        <Card className="relative overflow-hidden shadow-[0_1px_3px_rgba(28,22,18,0.04),inset_0_1px_0_rgba(255,255,255,0.5)]">
          <div
            className="absolute inset-x-0 top-0 h-px bg-gradient-to-l from-transparent via-[#C8A882]/40 to-transparent"
            aria-hidden="true"
          />
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Settings className="size-4 text-[#7C6350]" aria-hidden="true" />
              <HelpTip text="המודול, האופטימייזר, והפרמטרים שנבחרו להרצה זו">
                <span className="font-bold tracking-tight">הגדרות אופטימיזציה</span>
              </HelpTip>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="divide-y divide-border/40">
              {items.map((item, i) => (
                <div key={i} className="flex items-center justify-between py-2.5 gap-3">
                  <span className="flex items-center gap-2 text-xs text-muted-foreground shrink-0">
                    <span className="text-[#A89680]">{item.icon}</span>
                    {item.label}
                  </span>
                  <span
                    className="text-sm font-semibold text-foreground font-mono truncate"
                    dir="ltr"
                  >
                    {item.value}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Section 2: Models */}
        <Card className="relative overflow-hidden shadow-[0_1px_3px_rgba(28,22,18,0.04),inset_0_1px_0_rgba(255,255,255,0.5)]">
          <div
            className="absolute inset-x-0 top-0 h-px bg-gradient-to-l from-transparent via-[#C8A882]/40 to-transparent"
            aria-hidden="true"
          />
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Cpu className="size-4 text-[#7C6350]" aria-hidden="true" />
              <HelpTip text="מודלי השפה שהוגדרו — יצירה לייצור תשובות, רפלקציה לניתוח שגיאות">
                <span className="font-bold tracking-tight">מודלים</span>
              </HelpTip>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {job.optimization_type !== "grid_search" ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {modelCfg && <ModelCard label="מודל יצירה" cfg={modelCfg} />}
                {reflCfg && <ModelCard label="מודל רפלקציה" cfg={reflCfg} />}
                {promptCfg && <ModelCard label="מודל Prompt" cfg={promptCfg} />}
                {taskCfg && <ModelCard label="מודל Task" cfg={taskCfg} />}
                {!modelCfg && !reflCfg && !promptCfg && !taskCfg && job.model_name && (
                  <>
                    <ModelCard
                      label="מודל יצירה"
                      cfg={{ name: job.model_name, ...(job.model_settings || {}) }}
                    />
                    {job.reflection_model_name && (
                      <ModelCard label="מודל רפלקציה" cfg={{ name: job.reflection_model_name }} />
                    )}
                  </>
                )}
              </div>
            ) : job.generation_models && job.reflection_models ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <p className="text-[10px] font-semibold tracking-[0.08em] uppercase text-[#A89680] mb-1">
                    <HelpTip text="המודלים שמייצרים את התשובות — כל זוג נבדק עם מודל יצירה שונה">
                      מודלי יצירה
                    </HelpTip>
                  </p>
                  {job.generation_models.map((m, i) => (
                    <ModelCard
                      key={i}
                      label={`יצירה ${i + 1}`}
                      cfg={m as unknown as Record<string, unknown>}
                    />
                  ))}
                </div>
                <div className="space-y-2">
                  <p className="text-[10px] font-semibold tracking-[0.08em] uppercase text-[#A89680] mb-1">
                    <HelpTip text="המודלים שמנתחים שגיאות ומציעים שיפורים — כל זוג נבדק עם מודל רפלקציה שונה">
                      מודלי רפלקציה
                    </HelpTip>
                  </p>
                  {job.reflection_models.map((m, i) => (
                    <ModelCard
                      key={i}
                      label={`רפלקציה ${i + 1}`}
                      cfg={m as unknown as Record<string, unknown>}
                    />
                  ))}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* Section 3: Data & Splits */}
        <Card className="relative overflow-hidden shadow-[0_1px_3px_rgba(28,22,18,0.04),inset_0_1px_0_rgba(255,255,255,0.5)]">
          <div
            className="absolute inset-x-0 top-0 h-px bg-gradient-to-l from-transparent via-[#C8A882]/40 to-transparent"
            aria-hidden="true"
          />
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Database className="size-4 text-[#7C6350]" aria-hidden="true" />
              <HelpTip text="חלוקת הדאטאסט לאימון, אימות ובדיקה, והגדרות ערבוב">
                <span className="font-bold tracking-tight">נתונים</span>
              </HelpTip>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Split bar */}
            <div className="space-y-2">
              <p className="text-[10px] font-semibold tracking-[0.08em] uppercase text-[#A89680]">
                <HelpTip text="הנתונים מחולקים לשלוש קבוצות — אימון ללמידה, אימות לכיוונון, ובדיקה למדידת ביצועים סופיים">
                  חלוקת דאטאסט
                </HelpTip>
              </p>
              <div className="flex h-2.5 rounded-full overflow-hidden">
                <div
                  className="bg-[#3D2E22] transition-all"
                  style={{ width: `${splitFractions.train * 100}%` }}
                />
                <div
                  className="bg-[#C8A882] transition-all"
                  style={{ width: `${splitFractions.val * 100}%` }}
                />
                <div
                  className="bg-[#8C7A6B] transition-all"
                  style={{ width: `${splitFractions.test * 100}%` }}
                />
              </div>
              <div className="flex gap-4 text-xs">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-2 h-2 rounded-full bg-[#3D2E22]" />
                  אימון{" "}
                  <span className="font-mono tabular-nums text-muted-foreground" dir="ltr">
                    {splitFractions.train}
                  </span>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-2 h-2 rounded-full bg-[#C8A882]" />
                  אימות{" "}
                  <span className="font-mono tabular-nums text-muted-foreground" dir="ltr">
                    {splitFractions.val}
                  </span>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-2 h-2 rounded-full bg-[#8C7A6B]" />
                  בדיקה{" "}
                  <span className="font-mono tabular-nums text-muted-foreground" dir="ltr">
                    {splitFractions.test}
                  </span>
                </span>
              </div>
            </div>
            {/* Shuffle + Seed */}
            <div className="grid grid-cols-2 gap-2.5">
              <InfoCard
                label={
                  <HelpTip text="ערבוב סדר השורות בדאטאסט לפני החלוקה — מונע הטיה מסדר הנתונים">
                    ערבוב
                  </HelpTip>
                }
                value={shuffleVal ? "כן" : "לא"}
                icon={<Shuffle className="size-3.5" />}
              />
              {seedVal != null && (
                <InfoCard
                  label={
                    <HelpTip text="מספר קבוע שמבטיח שהערבוב והחלוקה יהיו זהים בכל הרצה חוזרת">
                      מספר התחלתי
                    </HelpTip>
                  }
                  value={seedVal}
                  icon={<Dices className="size-3.5" />}
                />
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
