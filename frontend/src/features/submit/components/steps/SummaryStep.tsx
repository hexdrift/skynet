"use client";

import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import {
  User,
  Code,
  Tag,
  Layers,
  Component,
  Target,
  FileText,
  Columns,
  Shuffle,
  Search,
  Database,
  Cpu,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ModelChip } from "@/components/model-chip";

import type { SubmitWizardContext } from "../../hooks/use-submit-wizard";

const CodeEditor = dynamic(() => import("@/components/code-editor").then((m) => m.CodeEditor), {
  ssr: false,
  loading: () => (
    <div className="h-[200px] rounded-lg border border-border/40 bg-muted/20 animate-pulse" />
  ),
});

const SUMMARY_TABS = [
  { id: "general", label: "כללי", icon: <User className="size-3.5" /> },
  { id: "dataset", label: "דאטאסט", icon: <Database className="size-3.5" /> },
  { id: "models", label: "מודלים", icon: <Cpu className="size-3.5" /> },
  { id: "optimizer", label: "אופטימייזר", icon: <Target className="size-3.5" /> },
  { id: "code", label: "קוד", icon: <Code className="size-3.5" /> },
];

export function SummaryStep({ w }: { w: SubmitWizardContext }) {
  const {
    summaryTab,
    setSummaryTab,
    summaryCodeTab,
    setSummaryCodeTab,
    jobName,
    jobType,
    moduleName,
    optimizerName,
    datasetFileName,
    parsedDataset,
    columnRoles,
    split,
    shuffle,
    modelConfig,
    secondModelConfig,
    generationModels,
    reflectionModels,
    autoLevel,
    maxBootstrappedDemos,
    maxLabeledDemos,
    numTrials,
    minibatch,
    minibatchSize,
    reflectionMinibatchSize,
    maxFullEvals,
    useMerge,
    signatureCode,
    metricCode,
  } = w;

  return (
    <div className="space-y-4" data-tutorial="wizard-step-6">
      {/* Tabbed sections */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.2, 0.8, 0.2, 1] }}
        className="rounded-2xl border border-border bg-card/80 backdrop-blur-xl shadow-lg overflow-hidden"
      >
        {/* Tab bar */}
        <div className="relative flex border-b border-border bg-secondary/50 p-1 gap-0.5">
          <div
            className="absolute top-1 bottom-1 rounded-lg bg-background shadow-sm transition-[inset-inline-start] duration-200 ease-out pointer-events-none"
            style={{
              width: `calc((100% - 12px) / ${SUMMARY_TABS.length})`,
              insetInlineStart: `calc(${summaryTab} * ${100 / SUMMARY_TABS.length}% + 4px)`,
            }}
          />
          {SUMMARY_TABS.map((tab, i) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setSummaryTab(i)}
              className={cn(
                "relative z-10 flex-1 flex items-center justify-center gap-1.5 rounded-lg py-2.5 text-xs font-medium transition-colors duration-150 cursor-pointer",
                summaryTab === i
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground/80",
              )}
            >
              {tab.icon}
              <span className="hidden sm:inline">{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="p-5">
          <AnimatePresence mode="wait">
            <motion.div
              key={summaryTab}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.15 }}
            >
              {/* General */}
              {summaryTab === 0 && (
                <div className="space-y-0">
                  <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Tag className="size-3.5" />
                      שם האופטימיזציה
                    </span>
                    <span className="text-sm font-medium">{jobName || "—"}</span>
                  </div>
                  <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Layers className="size-3.5" />
                      סוג אופטימיזציה
                    </span>
                    <span className="text-sm font-medium">
                      {jobType === "run" ? "ריצה בודדת" : "סריקה"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Component className="size-3.5" />
                      מודול
                    </span>
                    <span className="text-sm font-medium font-mono" dir="ltr">
                      {moduleName === "predict" ? "Predict" : "CoT"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Target className="size-3.5" />
                      אופטימייזר
                    </span>
                    <span className="text-sm font-medium font-mono" dir="ltr">
                      {optimizerName === "miprov2" ? "MIPROv2" : "GEPA"}
                    </span>
                  </div>
                </div>
              )}

              {/* Dataset */}
              {summaryTab === 1 && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      <FileText className="size-3.5" />
                      קובץ
                    </span>
                    <span
                      className="text-sm font-medium truncate max-w-[60%]"
                      title={datasetFileName ?? undefined}
                    >
                      {datasetFileName ?? "—"}
                    </span>
                  </div>
                  {parsedDataset && (
                    <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                      <span className="flex items-center gap-2 text-xs text-muted-foreground">
                        <Database className="size-3.5" />
                        גודל
                      </span>
                      <span className="text-sm font-medium">
                        {parsedDataset.rowCount} שורות · {parsedDataset.columns.length} עמודות
                      </span>
                    </div>
                  )}
                  {parsedDataset && parsedDataset.columns.length > 0 && (
                    <div className="space-y-2 pt-1">
                      <span className="flex items-center gap-2 text-xs text-muted-foreground">
                        <Columns className="size-3.5" />
                        מיפוי עמודות
                      </span>
                      <div className="space-y-1.5">
                        {parsedDataset.columns.map((col) => {
                          const role = columnRoles[col];
                          if (role === "ignore") return null;
                          const roleLabel =
                            role === "input" ? "קלט" : role === "output" ? "פלט" : "התעלם";
                          const roleColor =
                            role === "input"
                              ? "text-[#3D2E22] bg-[#3D2E22]/10"
                              : role === "output"
                                ? "text-primary bg-primary/10"
                                : "text-muted-foreground bg-muted";
                          return (
                            <div key={col} className="flex items-center justify-between gap-2 py-1">
                              <span className="text-xs font-mono truncate" dir="ltr">
                                {col}
                              </span>
                              <span
                                className={cn(
                                  "text-[10px] font-semibold px-2 py-0.5 rounded-full",
                                  roleColor,
                                )}
                              >
                                {roleLabel}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                  <Separator />
                  <div className="space-y-3">
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Layers className="size-3.5" />
                      חלוקת דאטאסט
                    </span>
                    <div className="flex h-3 rounded-full overflow-hidden">
                      <div className="bg-[#3D2E22]" style={{ width: `${split.train * 100}%` }} />
                      <div className="bg-[#C8A882]" style={{ width: `${split.val * 100}%` }} />
                      <div className="bg-[#8C7A6B]" style={{ width: `${split.test * 100}%` }} />
                    </div>
                    <div className="grid grid-cols-3 gap-4">
                      <div className="flex items-center gap-1.5 text-xs">
                        <span className="inline-block w-2 h-2 rounded-full bg-[#3D2E22]" />
                        אימון {split.train}
                      </div>
                      <div className="flex items-center gap-1.5 text-xs">
                        <span className="inline-block w-2 h-2 rounded-full bg-[#C8A882]" />
                        אימות {split.val}
                      </div>
                      <div className="flex items-center gap-1.5 text-xs">
                        <span className="inline-block w-2 h-2 rounded-full bg-[#8C7A6B]" />
                        בדיקה {split.test}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Shuffle className="size-3.5" />
                      ערבוב
                    </span>
                    <span className="text-sm font-medium">{shuffle ? "כן" : "לא"}</span>
                  </div>
                </div>
              )}

              {/* Models */}
              {summaryTab === 2 && (
                <div className="space-y-2 pointer-events-none">
                  {jobType === "run" ? (
                    <div className="space-y-2">
                      <ModelChip config={modelConfig} roleLabel="מודל יצירה" onClick={() => {}} />
                      {secondModelConfig?.name && (
                        <ModelChip
                          config={secondModelConfig}
                          roleLabel="מודל רפלקציה"
                          onClick={() => {}}
                        />
                      )}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                        מודלי יצירה
                      </span>
                      <div className="space-y-1.5">
                        {generationModels
                          .filter((m) => m.name)
                          .map((m, i) => (
                            <ModelChip key={i} config={m} onClick={() => {}} />
                          ))}
                      </div>
                      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                        מודלי רפלקציה
                      </span>
                      <div className="space-y-1.5">
                        {reflectionModels
                          .filter((m) => m.name)
                          .map((m, i) => (
                            <ModelChip key={i} config={m} onClick={() => {}} />
                          ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Optimizer */}
              {summaryTab === 3 && (
                <div className="space-y-0">
                  <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Search className="size-3.5" />
                      רמת חיפוש
                    </span>
                    <span className="text-sm font-medium">
                      {autoLevel === "light"
                        ? "קלה"
                        : autoLevel === "medium"
                          ? "בינונית"
                          : "מעמיקה"}
                    </span>
                  </div>
                  {optimizerName === "miprov2" ? (
                    <>
                      <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                        <span className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Cpu className="size-3.5" />
                          דוגמאות אוטומטיות
                        </span>
                        <span className="text-sm font-medium font-mono">
                          {maxBootstrappedDemos || "—"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                        <span className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Database className="size-3.5" />
                          דוגמאות מהנתונים
                        </span>
                        <span className="text-sm font-medium font-mono">
                          {maxLabeledDemos || "—"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                        <span className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Layers className="size-3.5" />
                          מספר ניסיונות
                        </span>
                        <span className="text-sm font-medium font-mono">{numTrials || "—"}</span>
                      </div>
                      <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                        <span className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Layers className="size-3.5" />
                          בדיקה חלקית
                        </span>
                        <span className="text-sm font-medium">
                          {minibatch ? `כן (${minibatchSize})` : "לא"}
                        </span>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                        <span className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Database className="size-3.5" />
                          גודל מדגם לרפלקציה
                        </span>
                        <span className="text-sm font-medium font-mono">
                          {reflectionMinibatchSize || "—"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                        <span className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Layers className="size-3.5" />
                          מקסימום סבבי הערכה
                        </span>
                        <span className="text-sm font-medium font-mono">{maxFullEvals || "—"}</span>
                      </div>
                      <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                        <span className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Shuffle className="size-3.5" />
                          מיזוג מועמדים
                        </span>
                        <span className="text-sm font-medium">{useMerge ? "כן" : "לא"}</span>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* Code */}
              {summaryTab === 4 && (
                <Tabs
                  defaultValue={signatureCode ? "signature" : "metric"}
                  dir="ltr"
                  onValueChange={setSummaryCodeTab}
                >
                  <TabsList className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1 border-none shadow-none h-auto">
                    {signatureCode && metricCode && (
                      <div
                        className="absolute top-1 bottom-1 w-[calc(50%-6px)] rounded-md bg-[#3D2E22] shadow-sm transition-[inset-inline-start] duration-200 ease-out"
                        style={{
                          insetInlineStart: summaryCodeTab === "signature" ? 4 : "calc(50% + 2px)",
                        }}
                      />
                    )}
                    {signatureCode && (
                      <TabsTrigger
                        value="signature"
                        className="relative z-10 rounded-md px-4 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5"
                      >
                        חתימה (Signature)
                      </TabsTrigger>
                    )}
                    {metricCode && (
                      <TabsTrigger
                        value="metric"
                        className="relative z-10 rounded-md px-4 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5"
                      >
                        מטריקה (Metric)
                      </TabsTrigger>
                    )}
                  </TabsList>
                  {signatureCode && (
                    <TabsContent value="signature">
                      <CodeEditor
                        value={signatureCode}
                        onChange={() => {}}
                        height={`${Math.min(signatureCode.split("\n").length + 1, 10) * 19.6 + 8}px`}
                        readOnly
                      />
                    </TabsContent>
                  )}
                  {metricCode && (
                    <TabsContent value="metric">
                      <CodeEditor
                        value={metricCode}
                        onChange={() => {}}
                        height={`${Math.min(metricCode.split("\n").length + 1, 10) * 19.6 + 8}px`}
                        readOnly
                      />
                    </TabsContent>
                  )}
                </Tabs>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
}
