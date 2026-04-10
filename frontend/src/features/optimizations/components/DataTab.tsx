"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "react-toastify";
import { Loader2, Zap, FlaskConical } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import {
 Table,
 TableBody,
 TableCell,
 TableHeader,
 TableRow,
} from "@/components/ui/table";
import { ColumnHeader, useColumnFilters, useColumnResize, ResetColumnsButton, type SortDir } from "@/components/excel-filter";
import { Skeleton } from "boneyard-js/react";
import { dataTabBones } from "@/components/data-tab-bones";
import { FadeIn } from "@/components/motion";
import { HelpTip } from "@/components/help-tip";
import { msg } from "@/features/shared/messages";
import { getOptimizationDataset, getTestResults, getPairTestResults } from "@/lib/api";
import type { OptimizationDatasetResponse, DatasetRow, OptimizationStatusResponse, EvalExampleResult } from "@/lib/types";
import { DEMO_OPTIMIZATION_ID } from "@/lib/tutorial-demo-data";

type Split = "all" | "train" | "val" | "test";
type ProgramType = "optimized" | "baseline";

/** Map a score (0–1) to a color on an absolute red→green scale via HSL */
function scoreColor(score: number): string {
 const t = Math.max(0, Math.min(1, score));
 const hue = t * 120; // 0 = red, 120 = green
 return `hsl(${hue}, 55%, 42%)`;
}

export function DataTab({ job, pairIndex }: { job: OptimizationStatusResponse; pairIndex?: number | null }) {
 const [dataset, setDataset] = useState<OptimizationDatasetResponse | null>(null);
 const [loading, setLoading] = useState(true);
 const [error, setError] = useState<string | null>(null);
 const [split, setSplit] = useState<Split>("test");
 const [programType, setProgramType] = useState<ProgramType>("optimized");
 const [testResults, setTestResults] = useState<Record<string, Record<number, EvalExampleResult>>>({ optimized: {}, baseline: {} });
 const [testResultsLoading, setTestResultsLoading] = useState(false);

 // Column sorting & filtering
 const colFilters = useColumnFilters();
 const [sortKey, setSortKey] = useState<string>("");
 const [sortDir, setSortDir] = useState<SortDir>("asc");
 const toggleSort = (key: string) => {
  if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
  else { setSortKey(key); setSortDir("asc"); }
 };
 const colResize = useColumnResize();

 const isDemoMode = job.optimization_id === DEMO_OPTIMIZATION_ID;

 // Load dataset
 useEffect(() => {
  if (isDemoMode) {
   // Provide mock dataset for tutorial demo
   setDataset({
    total_rows: 12,
    splits: {
     train: [
      { index: 0, row: { email_text: "Click here to win $1000 now!", category: "spam" } },
      { index: 1, row: { email_text: "Meeting moved to 3pm tomorrow", category: "important" } },
      { index: 2, row: { email_text: "50% off all items this weekend only", category: "promotional" } },
      { index: 3, row: { email_text: "Your account has been compromised! Act now!", category: "spam" } },
      { index: 4, row: { email_text: "Q3 budget review attached for your approval", category: "important" } },
      { index: 5, row: { email_text: "Flash sale: 70% off electronics today", category: "promotional" } },
      { index: 6, row: { email_text: "Reminder: dentist appointment on Thursday", category: "important" } },
     ],
     val: [
      { index: 7, row: { email_text: "You've won a free iPhone! Claim here", category: "spam" } },
      { index: 8, row: { email_text: "New company policy update effective Monday", category: "important" } },
     ],
     test: [
      { index: 9, row: { email_text: "Limited time offer: buy 1 get 1 free", category: "promotional" } },
      { index: 10, row: { email_text: "Team standup notes from Monday", category: "important" } },
      { index: 11, row: { email_text: "Congratulations! You've been selected for a prize", category: "spam" } },
     ],
    },
    column_mapping: { inputs: { email_text: "email_text" }, outputs: { category: "category" } },
    split_counts: { train: 7, val: 2, test: 3 },
   });
   // Mock test results with predictions and scores
   setTestResults({
    optimized: {
     9: { index: 9, outputs: { category: "promotional" }, score: 1.0, pass: true },
     10: { index: 10, outputs: { category: "important" }, score: 1.0, pass: true },
     11: { index: 11, outputs: { category: "spam" }, score: 1.0, pass: true },
    },
    baseline: {
     9: { index: 9, outputs: { category: "spam" }, score: 0.0, pass: false },
     10: { index: 10, outputs: { category: "important" }, score: 1.0, pass: true },
     11: { index: 11, outputs: { category: "promotional" }, score: 0.0, pass: false },
    },
   });
   setLoading(false);
   return;
  }
  getOptimizationDataset(job.optimization_id)
   .then(setDataset)
   .catch(() => setError("שגיאה בטעינת הנתונים"))
   .finally(() => setLoading(false));
 }, [job.optimization_id, isDemoMode]);

 // Load cached test results
 useEffect(() => {
  if (isDemoMode || job.status !== "success") return;
  setTestResultsLoading(true);
  const fetchResults = pairIndex != null
   ? getPairTestResults(job.optimization_id, pairIndex)
   : getTestResults(job.optimization_id);
  fetchResults
   .then((res) => {
    const optimized: Record<number, EvalExampleResult> = {};
    const baseline: Record<number, EvalExampleResult> = {};
    for (const r of res.optimized ?? []) optimized[r.index] = r;
    for (const r of res.baseline ?? []) baseline[r.index] = r;
    setTestResults({ optimized, baseline });
   })
   .catch(() => { /* non-critical */ })
   .finally(() => setTestResultsLoading(false));
 }, [job.optimization_id, job.status, pairIndex, isDemoMode]);

 const inputFields = useMemo(() => dataset ? Object.values(dataset.column_mapping.inputs) : [], [dataset]);
 const outputFields = useMemo(() => dataset ? Object.values(dataset.column_mapping.outputs) : [], [dataset]);
 const allColumns = useMemo(() => [...inputFields, ...outputFields], [inputFields, outputFields]);

 const currentResults = testResults[programType] ?? {};

 const rows = useMemo(() => {
  if (!dataset) return [];
  if (split === "all") return [...dataset.splits.train, ...dataset.splits.val, ...dataset.splits.test];
  return dataset.splits[split];
 }, [dataset, split]);

 // Filter + sort rows
 const filtered = useMemo(() => {
  let result = rows.filter((r) => {
   for (const [col, allowed] of Object.entries(colFilters.filters)) {
    if (allowed.size === 0) continue;
    const val = String(r.row[col] ?? "");
    if (!allowed.has(val)) return false;
   }
   return true;
  });
  if (sortKey) {
   result = [...result].sort((a, b) => {
    const av = String(a.row[sortKey] ?? "");
    const bv = String(b.row[sortKey] ?? "");
    const cmp = av.localeCompare(bv, "he", { numeric: true });
    return sortDir === "asc" ? cmp : -cmp;
   });
  }
  return result;
 }, [rows, colFilters.filters, sortKey, sortDir]);

 // Filter options per column
 const filterOptions = useMemo(() => {
  const opts: Record<string, { value: string; label: string }[]> = {};
  for (const col of allColumns) {
   const vals = [...new Set(rows.map((r) => String(r.row[col] ?? "")))].filter(Boolean).sort();
   opts[col] = vals.map((v) => ({ value: v, label: v.length > 40 ? v.slice(0, 40) + "..." : v }));
  }
  return opts;
 }, [rows, allColumns]);

 const evalCount = Object.keys(currentResults).length;
 const passCount = Object.values(currentResults).filter(r => r.pass).length;
 const failCount = evalCount - passCount;
 const testTotal = dataset?.split_counts.test ?? 0;
 const scores = Object.values(currentResults).map(r => r.score);
 const avgScore = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 0;
 const minScore = scores.length > 0 ? Math.min(...scores) : 0;
 const maxScore = scores.length > 0 ? Math.max(...scores) : 1;

 /** Build a segmented CSS gradient — one block per test example, sorted by score */
 const summaryBarGradient = useMemo(() => {
  const sorted = [...scores].sort((a, b) => a - b);
  if (sorted.length === 0) return "transparent";
  if (sorted.length === 1) return scoreColor(sorted[0]!);
  const n = sorted.length;
  const stops = sorted.map((s, i) => {
   const start = (i / n) * 100;
   const end = ((i + 1) / n) * 100;
   const c = scoreColor(s);
   return `${c} ${start.toFixed(2)}% ${end.toFixed(2)}%`;
  });
  return `linear-gradient(to right, ${stops.join(", ")})`;
 }, [scores]);

 if (loading) return <Skeleton name="data-tab" loading initialBones={dataTabBones} color="var(--muted)" animate="shimmer"><div className="min-h-[400px]" /></Skeleton>;
 if (error || !dataset) return <div className="text-sm text-destructive text-center py-16">{error ?? "אין נתונים"}</div>;

 return (
  <div className="space-y-4 mt-4">

   {/* Test evaluation bar — shows cached results */}
   {split === "test" && (
    <FadeIn delay={0.2}>
     <div className="rounded-2xl border border-[#E5DDD4] bg-gradient-to-l from-[#FAF8F5] to-[#F5F1EC] p-4 space-y-3" dir="rtl" data-tutorial="eval-bar">
      <div className="flex items-center gap-3">
       <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-[#3D2E22]"><HelpTip text="תוצאות הרצת התוכנית על דוגמאות הבדיקה — ציון לכל דוגמה וסיכום כולל">הערכת סט הבדיקה</HelpTip></div>
        <div className="text-[11px] text-[#8C7A6B] mt-0.5">
         {testResultsLoading
          ? "טוען תוצאות..."
          : evalCount > 0
          ? `${evalCount}/${testTotal} דוגמאות · ממוצע ${avgScore.toFixed(2)} · טווח ${minScore.toFixed(2)}–${maxScore.toFixed(2)}`
          : ""}
        </div>
       </div>
       <div className="relative inline-flex rounded-lg bg-[#F0EBE4] p-1 gap-1 text-[11px] shrink-0">
        <div
         className="absolute top-1 bottom-1 rounded-md bg-[#3D2E22] shadow-sm transition-[inset-inline-start] duration-150 ease-out"
         style={{ width: "calc(50% - 6px)", insetInlineStart: programType === "baseline" ? 4 : "calc(50% + 2px)" }}
        />
        <button
         onClick={() => setProgramType("baseline")}
         className={`relative z-10 flex items-center gap-1.5 rounded-md px-3 py-1.5 cursor-pointer transition-colors duration-150 ${programType === "baseline" ? "text-[#FAF8F5] font-semibold" : "text-[#8C7A6B] hover:text-[#3D2E22]"}`}
        >
         <FlaskConical className="size-3" /> בסיס
        </button>
        <button
         onClick={() => setProgramType("optimized")}
         className={`relative z-10 flex items-center gap-1.5 rounded-md px-3 py-1.5 cursor-pointer transition-colors duration-150 ${programType === "optimized" ? "text-[#FAF8F5] font-semibold" : "text-[#8C7A6B] hover:text-[#3D2E22]"}`}
        >
         <Zap className="size-3" /> מאומנת
        </button>
       </div>
       {testResultsLoading && <Loader2 className="size-4 animate-spin text-[#8C7A6B] shrink-0" />}
      </div>
      {evalCount > 0 && (
       <div className="h-2.5 rounded-full overflow-hidden" dir="ltr" style={{ background: summaryBarGradient }} />
      )}
     </div>
    </FadeIn>
   )}

   {/* Toolbar */}
   <FadeIn delay={0.3}>
   <div className="flex items-center gap-3 flex-wrap">
    {(() => {
     const splits: [Split, string][] = [["all", "הכל"], ["train", "אימון"], ["val", "אימות"], ["test", "בדיקה"]];
     const idx = splits.findIndex(([s]) => s === split);
     const count = splits.length;
     return (
      <div className="relative flex w-full rounded-lg bg-muted p-1 gap-1 text-[11px]" data-tutorial="split-selector">
       <div
        className="absolute top-1 bottom-1 rounded-md bg-background shadow-sm transition-[inset-inline-start] duration-150 ease-out"
        style={{ width: `calc(${100 / count}% - 6px)`, insetInlineStart: `calc(${(idx / count) * 100}% + 4px)` }}
       />
       {splits.map(([s, label]) => (
        <button
         key={s}
         onClick={() => setSplit(s)}
         className={`relative z-10 flex-1 rounded-md px-3 py-1.5 cursor-pointer text-center transition-colors duration-150 ${split === s ? "text-foreground font-semibold" : "text-foreground/50 hover:text-foreground"}`}
        >
         {label}
        </button>
       ))}
      </div>
     );
    })()}
    <ResetColumnsButton resize={colResize} />
    <div className="text-[10px] text-muted-foreground tabular-nums ms-auto">{filtered.length} שורות</div>
   </div>
   </FadeIn>

   {/* Data table */}
   <FadeIn delay={0.35}>
   {filtered.length === 0 ? (
    <p className="text-sm text-muted-foreground py-8 text-center">אין תוצאות</p>
   ) : (
    <Card data-tutorial="data-table">
     <CardContent className="p-0">
      <div className="max-h-[520px] overflow-auto">
       <Table className="table-fixed">
        <TableHeader>
         <TableRow>
          {split === "test" && evalCount > 0 && (
           <ColumnHeader label="ציון" sortKey="_score" currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} width={colResize.widths["_score"]} onResize={colResize.setColumnWidth} />
          )}
          {inputFields.map(f => (
           <ColumnHeader key={f} label={f} sortKey={f} currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} filterCol={f} filterOptions={filterOptions[f] ?? []} filters={colFilters.filters} onFilter={colFilters.setColumnFilter} openFilter={colFilters.openFilter} setOpenFilter={colFilters.setOpenFilter} width={colResize.widths[f]} onResize={colResize.setColumnWidth} />
          ))}
          {outputFields.map(f => (
           <ColumnHeader key={f} label={f} sortKey={f} currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} filterCol={f} filterOptions={filterOptions[f] ?? []} filters={colFilters.filters} onFilter={colFilters.setColumnFilter} openFilter={colFilters.openFilter} setOpenFilter={colFilters.setOpenFilter} width={colResize.widths[f]} onResize={colResize.setColumnWidth} />
          ))}
          {split === "test" && evalCount > 0 && outputFields.map(f => (
           <ColumnHeader key={`pred-${f}`} label={`pred_${f}`} sortKey={`_pred_${f}`} currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} width={colResize.widths[`_pred_${f}`]} onResize={colResize.setColumnWidth} />
          ))}
         </TableRow>
        </TableHeader>
        <TableBody>
         {filtered.slice(0, 200).map(row => {
          const ev = currentResults[row.index];
          return (
           <TableRow key={row.index} className="cursor-pointer" onClick={(e) => {
            const td = (e.target as HTMLElement).closest("td");
            if (!td || td === td.parentElement?.lastElementChild) return;
            const text = td.textContent?.trim();
            if (text) { navigator.clipboard.writeText(text); toast.success(msg("clipboard.copied")); }
           }}>
            {split === "test" && evalCount > 0 && (
             <TableCell className="!p-0 !px-1.5 !py-1" style={colResize.widths["_score"] ? { width: colResize.widths["_score"] } : { width: 72 }}>
              {ev ? (
               <div className="flex flex-col items-center gap-0.5">
                <span className="text-[10px] font-mono tabular-nums font-medium" style={{ color: scoreColor(ev.score) }}>
                 {ev.score.toFixed(2)}
                </span>
                <div className="w-full h-1.5 rounded-full overflow-hidden bg-muted">
                 <div
                  className="h-full rounded-full"
                  style={{
                   width: `${Math.max(0, Math.min(1, ev.score)) * 100}%`,
                   background: scoreColor(ev.score),
                  }}
                 />
                </div>
               </div>
              ) : (
               <span className="text-[10px] text-[#E5DDD4] flex justify-center">—</span>
              )}
             </TableCell>
            )}
            {inputFields.map(f => (
             <TableCell key={f} className="text-xs font-mono truncate overflow-hidden" style={colResize.widths[f] ? { width: colResize.widths[f], maxWidth: colResize.widths[f] } : undefined} title={String(row.row[f] ?? "")}>
              {String(row.row[f] ?? "")}
             </TableCell>
            ))}
            {outputFields.map(f => (
             <TableCell key={f} className="text-xs font-mono truncate overflow-hidden" style={colResize.widths[f] ? { width: colResize.widths[f], maxWidth: colResize.widths[f] } : undefined} title={String(row.row[f] ?? "")}>
              {String(row.row[f] ?? "")}
             </TableCell>
            ))}
            {split === "test" && evalCount > 0 && outputFields.map(f => {
             const sigField = Object.entries(dataset.column_mapping.outputs).find(([, col]) => col === f)?.[0];
             const pred = ev?.outputs[sigField ?? ""];
             const key = `_pred_${f}`;
             return (
              <TableCell key={key} className="text-xs font-mono truncate overflow-hidden" style={{ ...(colResize.widths[key] ? { width: colResize.widths[key], maxWidth: colResize.widths[key] } : {}), color: ev ? scoreColor(ev.score) : undefined }} title={pred != null ? String(pred) : ""}>
               {pred != null ? String(pred) : ""}
              </TableCell>
             );
            })}
           </TableRow>
          );
         })}
        </TableBody>
        {filtered.length > 200 && (
         <tfoot><tr><td colSpan={99} className="text-center py-3 text-[10px] text-muted-foreground">מוצגות 200 מתוך {filtered.length} שורות</td></tr></tfoot>
        )}
       </Table>
      </div>
     </CardContent>
    </Card>
   )}
   </FadeIn>
  </div>
 );
}
