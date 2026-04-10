"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
 Loader2,
 XCircle,
 Trash2,
 Clock,
 Code,
 Code2,
 Terminal,
 TrendingUp,
 ChevronRight,
 ChevronLeft,
 Activity,
 CheckCircle2,
 Circle,
 Timer,
 Clipboard,
 Check,
 Send,
 Zap,
 Sparkles,
 CopyPlus,
 Download,
 ChevronDown,
 FileText,
 FileJson,
 FileSpreadsheet,
 Package,
 Pencil,
 MessageSquare,
 Component,
 Target,
 Cpu,
 Lightbulb,
 Quote,
 ListTodo,
 User,
 Database,
 PieChart,
 Shuffle,
 Dices,
 Crown,
 ArrowRight,
 ArrowLeft,
 Grid2x2,
 Layers,
 BarChart3,
 Settings2,
 Settings,
 Thermometer,
 Coins,
 Brain,
} from "lucide-react";
import { toast } from "react-toastify";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
 Table,
 TableBody,
 TableCell,
 TableHead,
 TableHeader,
 TableRow,
} from "@/components/ui/table";
import { ColumnHeader, useColumnFilters, useColumnResize, ResetColumnsButton, type SortDir } from "@/components/excel-filter";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { motion, AnimatePresence } from "framer-motion";
import { FadeIn, TiltCard, StaggerContainer, StaggerItem } from "@/components/motion";
import dynamic from "next/dynamic";

const CodeEditor = dynamic(
 () => import("@/components/code-editor").then((m) => m.CodeEditor),
 { ssr: false, loading: () => <div className="h-[180px] rounded-lg border border-border/40 bg-muted/20 animate-pulse" /> },
);
const ScoreChart = dynamic(() => import("@/components/score-chart").then(m => m.ScoreChart), { ssr: false, loading: () => <div className="h-full" /> });
import { Tooltip as UiTooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { getJob, cancelJob, deleteJob, getOptimizationPayload, getServeInfo, getPairServeInfo, serveProgramStream, servePairProgramStream } from "@/lib/api";
import type { ServeInfoResponse } from "@/lib/types";
import { DEMO_OPTIMIZATION_ID, startDemoSimulation } from "@/lib/tutorial-demo-data";
import { Skeleton } from "boneyard-js/react";
import { optimizationDetailBones } from "@/components/optimization-detail-bones";
import { DataTab } from "@/features/optimizations/components/DataTab";
import { ACTIVE_STATUSES, TERMINAL_STATUSES, STATUS_LABELS } from "@/lib/constants";
import { registerTutorialHook } from "@/lib/tutorial-bridge";
import { HelpTip } from "@/components/help-tip";
import type {
 OptimizationStatusResponse,
 OptimizationLogEntry,
 OptimizationPayloadResponse,
} from "@/lib/types";

/* ── Helpers ── */
// Pure helpers, constants, and the pipeline-stage detector have moved
// to @/features/optimizations — see index.ts for the public surface.

import {
 STATUS_COLORS,
 PIPELINE_STAGES,
 STAGE_INFO,
 type PipelineStage,
 formatPercent,
 formatImprovement,
 jsonPreview,
 formatDuration,
 detectStage,
 extractScoresFromLogs,
 type ScorePoint,
} from "@/features/optimizations";


function StatusBadge({ status }: { status: string }) {
 return (
 <Badge variant="outline" className={`text-[13px] px-3 py-1 font-bold tracking-wide ${STATUS_COLORS[status] ??""}`}>
 {status === "running" && <span className="relative flex size-2 me-1"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--warning)]/60"/><span className="relative inline-flex rounded-full size-2 bg-[var(--warning)]"/></span>}
 {STATUS_LABELS[status] ?? status}
 </Badge>
 );
}

function InfoCard({ label, value, icon }: { label: React.ReactNode; value: React.ReactNode; icon?: React.ReactNode }) {
 return (
 <motion.div
 whileHover={{ y: -1 }}
 transition={{ duration: 0.2, ease: [0.2, 0.8, 0.2, 1] }}
 className="group relative rounded-lg border border-[#E3DCD0] bg-[#FBF9F4] px-3.5 py-3 transition-[border-color,box-shadow] duration-200 hover:border-[#C8A882]/55 hover:shadow-[0_2px_8px_-2px_rgba(124,99,80,0.1)]"
 >
 <div className="flex items-center gap-1.5 mb-1.5">
 {icon && (
 <span className="shrink-0 inline-flex items-center justify-center size-3.5 text-[#A89680] transition-colors duration-200 group-hover:text-[#7C6350]" aria-hidden="true">
 {icon}
 </span>
 )}
 <p className="text-[10px] font-semibold tracking-[0.08em] uppercase text-[#A89680] truncate">
 {label}
 </p>
 </div>
 <p className="text-sm font-semibold text-[#1C1612] truncate">
 {value ?? <span className="text-[#BFB3A3] font-normal">—</span>}
 </p>
 </motion.div>
 );
}



function LangPicker<T extends string>({ value, onChange, labels }: {
 value: T;
 onChange: (v: T) => void;
 labels: Record<T, string>;
}) {
 const [open, setOpen] = useState(false);
 const ref = useRef<HTMLDivElement>(null);
 useEffect(() => {
 if (!open) return;
 const onClick = (e: MouseEvent) => {
  if (!ref.current?.contains(e.target as Node)) setOpen(false);
 };
 const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
 window.addEventListener("mousedown", onClick);
 window.addEventListener("keydown", onKey);
 return () => {
  window.removeEventListener("mousedown", onClick);
  window.removeEventListener("keydown", onKey);
 };
 }, [open]);
 const keys = Object.keys(labels) as T[];
 return (
 <div ref={ref} className="relative">
 <button
  type="button"
  onClick={() => setOpen(o => !o)}
  className="flex items-center gap-1 px-1.5 py-0.5 -mx-1.5 -my-0.5 rounded-md font-semibold text-[#7C6350] tracking-wide hover:bg-black/5 transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/50"
  aria-haspopup="listbox"
  aria-expanded={open}
 >
  <span>{labels[value]}</span>
  <ChevronDown className={`size-3 text-[#8C7A6B] transition-transform duration-150 ${open ? "rotate-180" : ""}`} />
 </button>
 <AnimatePresence>
 {open && (
 <motion.ul
  role="listbox"
  initial={{ opacity: 0, y: 4, scale: 0.96 }}
  animate={{ opacity: 1, y: 0, scale: 1 }}
  exit={{ opacity: 0, y: 4, scale: 0.96 }}
  transition={{ duration: 0.12, ease: [0.16, 1, 0.3, 1] }}
  className="absolute bottom-full mb-1.5 start-0 z-20 min-w-[120px] rounded-lg border border-[#E5DDD4] bg-[#FAF6F0] shadow-lg overflow-hidden py-1"
 >
  {keys.map((k) => (
  <li key={k}>
   <button
   type="button"
   onClick={() => { onChange(k); setOpen(false); }}
   className={`w-full text-start px-3 py-1.5 text-[11px] font-semibold tracking-wide transition-colors cursor-pointer flex items-center justify-between ${k === value ? "bg-[#3D2E22]/8 text-[#3D2E22]" : "text-[#7C6350] hover:bg-black/5"}`}
   role="option"
   aria-selected={k === value}
   >
   <span>{labels[k]}</span>
   {k === value && <Check className="size-3" />}
   </button>
  </li>
  ))}
 </motion.ul>
 )}
 </AnimatePresence>
 </div>
 );
}

function CopyButton({ text, className =""}: { text: string; className?: string }) {
 const [copied, setCopied] = useState(false);
 return (
 <button
 type="button" onClick={() => {
 navigator.clipboard.writeText(text);
 setCopied(true);
 setTimeout(() => setCopied(false), 1500);
 }}
 className={`p-1.5 cursor-pointer transition-opacity duration-200 outline-none border-none shadow-none ring-0 bg-transparent hover:opacity-100 ${className}`}
 title="העתק"
 aria-label="העתק">
 {copied
 ? <Check className="size-3.5 text-foreground/70"/>
 : <Clipboard className="size-3.5 text-foreground/40 hover:text-foreground/70"/>}
 </button>
 );
}

/* ── Download helpers ── */

function formatLogTimestamp(ts: string): string {
  // Accept ISO "2026-03-30T23:32:45.971393" — return "30/03 23:32:45"
  const m = ts.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/);
  if (!m) return ts;
  const [, , mm, dd, hh, mi, ss] = m;
  return `${dd}/${mm} ${hh}:${mi}:${ss}`;
}

function logTimeBucket(ts: string): string {
  // Group timestamps by minute for filter options: "30/03 23:32"
  const m = ts.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (!m) return ts;
  const [, , mm, dd, hh, mi] = m;
  return `${dd}/${mm} ${hh}:${mi}`;
}

function formatOutput(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try { return JSON.stringify(v, null, 2); } catch { return String(v); }
}

/* ── Extracted chat component — isolates edit/cancel state from the heavy parent ── */
interface ServeChatProps {
 serveInfo: ServeInfoResponse;
 runHistory: Array<{ inputs: Record<string, string>; outputs: Record<string, unknown>; model: string; ts: number }>;
 setRunHistory: React.Dispatch<React.SetStateAction<ServeChatProps["runHistory"]>>;
 streamingRun: { inputs: Record<string, string>; partial: Record<string, string> } | null;
 serveLoading: boolean;
 serveError: string | null;
 setServeError: React.Dispatch<React.SetStateAction<string | null>>;
 textareaRefs: React.MutableRefObject<Record<string, HTMLTextAreaElement | null>>;
 chatScrollRef: React.RefObject<HTMLDivElement | null>;
 handleServe: (overrideInputs?: Record<string, string>) => void;
 demos: Array<{ inputs: Record<string, unknown> }>;
}

function ServeChat({ serveInfo, runHistory, setRunHistory, streamingRun, serveLoading, serveError, setServeError, textareaRefs, chatScrollRef, handleServe, demos }: ServeChatProps) {
 const [editingRunTs, setEditingRunTs] = useState<number | null>(null);
 const editTextareaRefs = useRef<Record<string, HTMLTextAreaElement | null>>({});

 const handleEditAndResend = (runTs: number) => {
 setRunHistory((prev) => {
  const idx = prev.findIndex((r) => r.ts === runTs);
  if (idx === -1) return prev;
  return prev.slice(idx + 1);
 });
 const edited: Record<string, string> = {};
 for (const f of serveInfo.input_fields) edited[f] = editTextareaRefs.current[f]?.value ?? "";
 handleServe(edited);
 setEditingRunTs(null);
 };

 return (
 <div className="flex flex-col max-h-[560px] pt-2">
  <div ref={chatScrollRef} className="flex-1 overflow-y-auto pb-4 space-y-6">
  {runHistory.length === 0 && !streamingRun && (
   <div className="flex flex-col items-center justify-center py-16 gap-5 text-center">
   <div className="size-12 rounded-2xl bg-[#3D2E22]/8 flex items-center justify-center">
    <MessageSquare className="size-5 text-[#3D2E22]/35" />
   </div>
   <div className="space-y-2">
    <p className="text-sm font-medium text-foreground/60">הרצת התוכנית המאומנת</p>
    <p className="text-xs text-muted-foreground/50 max-w-xs leading-relaxed">
    הזן ערכים בשדות הקלט למטה ולחץ על כפתור השליחה.
    </p>
   </div>
   {demos.length > 0 && (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-md w-full mt-2">
    {demos.slice(0, 4).map((demo, i) => (
     <button
     key={i}
     onClick={() => {
      for (const f of serveInfo.input_fields) {
      const el = textareaRefs.current[f];
      if (el) {
       el.value = String(demo.inputs[f] ?? "");
       el.style.height = "auto";
       el.style.height = Math.min(el.scrollHeight, 120) + "px";
      }
      }
     }}
     className="text-right p-3 rounded-xl border border-[#DDD4C8]/60 hover:border-[#C8A882]/60 bg-muted/10 hover:bg-muted/20 transition-all group"
     dir="auto"
     >
     <div className="text-[10px] font-medium text-[#3D2E22]/50 mb-1">דוגמה {i + 1}</div>
     <div className="text-xs text-foreground/70 line-clamp-2 font-mono" dir="ltr">
      {Object.entries(demo.inputs).map(([k, v]) => `${k}: ${String(v)}`).join(", ").slice(0, 80)}
      {Object.entries(demo.inputs).map(([k, v]) => `${k}: ${String(v)}`).join(", ").length > 80 ? "..." : ""}
     </div>
     </button>
    ))}
    </div>
   )}
   </div>
  )}
  {[...runHistory].reverse().map((run) => {
   const isEditing = editingRunTs === run.ts;
   return (
   <div key={run.ts} className="space-y-3">
    {isEditing ? (
    <div className="flex justify-start">
     <div className="max-w-[85%] w-full space-y-2">
     {serveInfo.input_fields.map((field) => (
      <div key={field}>
      {serveInfo.input_fields.length > 1 && (
       <label className="text-[10px] text-muted-foreground/50 font-mono px-1 mb-0.5 block" dir="ltr">{field}</label>
      )}
      <textarea
       ref={(el) => {
       editTextareaRefs.current[field] = el;
       if (el) {
        el.style.height = "auto";
        el.style.height = Math.min(el.scrollHeight, 120) + "px";
       }
       }}
       dir="auto"
       defaultValue={run.inputs[field] ?? ""}
       onChange={(e) => {
       e.target.style.height = "auto";
       e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
       }}
       className="w-full bg-white border border-[#DDD4C8] rounded-xl px-3 py-2 text-sm font-mono resize-none outline-none focus:border-[#C8A882] transition-colors min-h-[40px] max-h-[120px]"
       rows={1}
       autoFocus={serveInfo.input_fields[0] === field}
      />
      </div>
     ))}
     <div className="flex justify-start gap-1.5">
      <button onClick={() => setEditingRunTs(null)} className="text-[11px] text-muted-foreground hover:text-foreground px-3 py-1 rounded-lg hover:bg-muted transition-colors">
      ביטול
      </button>
      <button
      onClick={() => handleEditAndResend(run.ts)}
      className="text-[11px] text-white bg-[#3D2E22] hover:bg-[#3D2E22]/90 disabled:opacity-40 px-3 py-1 rounded-lg transition-colors"
      >
      שלח
      </button>
     </div>
     </div>
    </div>
    ) : (
    <div className="flex justify-start group/user">
     <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-[#3D2E22] text-[#FAF8F5] px-4 py-3 text-sm shadow-sm" dir="ltr">
     {serveInfo.input_fields.map((k, i, arr) => (
      <div key={k} className="font-mono leading-relaxed">
      <span className="text-[#C8A882] text-xs">{k}: </span>
      <span className="whitespace-pre-wrap break-words">{run.inputs[k] ?? ""}</span>
      {i < arr.length - 1 && arr.length > 1 && <div className="h-px bg-white/10 my-1.5" />}
      </div>
     ))}
     </div>
     {!serveLoading && (
     <button
      onClick={() => setEditingRunTs(run.ts)}
      className="self-center ms-1.5 opacity-0 group-hover/user:opacity-100 transition-opacity p-1.5 rounded-lg hover:bg-muted/60"
      title="ערוך ושלח שוב"
     >
      <Pencil className="size-3 text-muted-foreground" />
     </button>
     )}
    </div>
    )}
    {!isEditing && (
    <div className="px-1" dir="ltr">
     {serveInfo.output_fields.map((k, i, arr) => (
     <div key={k} className={`font-mono text-sm leading-relaxed ${arr.length > 1 ? "mb-1" : ""}`}>
      <span className="text-muted-foreground text-xs">{k}: </span>
      <span className="whitespace-pre-wrap break-words">{formatOutput(run.outputs[k])}</span>
     </div>
     ))}
     <div className="flex items-center gap-0.5 mt-1 -ms-1">
     <CopyButton text={serveInfo.output_fields.map((k) => `${k}: ${formatOutput(run.outputs[k])}`).join("\n")} />
     <span className="text-[9px] text-muted-foreground/30 ms-1 font-mono" dir="ltr">{run.model}</span>
     </div>
    </div>
    )}
   </div>
   );
  })}
  {streamingRun && (
   <div className="space-y-3">
   <div className="flex justify-start">
    <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-[#3D2E22] text-[#FAF8F5] px-4 py-3 text-sm shadow-sm" dir="ltr">
    {serveInfo.input_fields.map((k, i, arr) => (
     <div key={k} className="font-mono leading-relaxed">
     <span className="text-[#C8A882] text-xs">{k}: </span>
     <span className="whitespace-pre-wrap break-words">{streamingRun.inputs[k] ?? ""}</span>
     {i < arr.length - 1 && arr.length > 1 && <div className="h-px bg-white/10 my-1.5" />}
     </div>
    ))}
    </div>
   </div>
   <div className="px-1" dir="ltr">
    {Object.keys(streamingRun.partial).length === 0 ? (
    <div className="flex items-center gap-1.5 py-2">
     <span className="w-1.5 h-1.5 rounded-full bg-[#3D2E22]/30 animate-bounce" />
     <span className="w-1.5 h-1.5 rounded-full bg-[#3D2E22]/30 animate-bounce" style={{ animationDelay: "150ms" }} />
     <span className="w-1.5 h-1.5 rounded-full bg-[#3D2E22]/30 animate-bounce" style={{ animationDelay: "300ms" }} />
     <span className="text-xs text-muted-foreground/40">חושב</span>
    </div>
    ) : (
    serveInfo.output_fields.map((k, i, arr) => (
     <div key={k} className={`font-mono text-sm leading-relaxed ${arr.length > 1 ? "mb-1" : ""}`}>
     <span className="text-muted-foreground text-xs">{k}: </span>
     <span className="whitespace-pre-wrap break-words">{streamingRun.partial[k] ?? ""}</span>
     {streamingRun.partial[k] && <span className="inline-block w-1 h-3 bg-foreground/40 ms-0.5 animate-pulse" />}
     </div>
    ))
    )}
   </div>
   </div>
  )}
  </div>

  <div className="border-t border-border/40 pt-3">
  {serveError && (
   <div className="flex items-center gap-1.5 text-xs text-red-600 bg-red-50 rounded-lg px-2.5 py-1.5 mb-2 max-w-2xl mx-auto">
   <XCircle className="size-3 shrink-0" />
    <span className="flex-1 break-words min-w-0">{serveError}</span>
   <button onClick={() => setServeError(null)} className="ms-auto p-0.5 hover:bg-red-100 rounded">
    <span className="sr-only">סגור</span>×
   </button>
   </div>
  )}
  <form
   onSubmit={(e) => { e.preventDefault(); handleServe(); }}
   className="max-w-2xl mx-auto"
  >
   <div className={`flex gap-2 ${serveInfo.input_fields.length > 1 ? "items-center" : "items-start"}`}>
   <Button
    type="submit"
    size="icon"
    className="shrink-0 rounded-full !size-[42px]"
    disabled={serveLoading}
    aria-label="שלח"
   >
    {serveLoading
    ? <Loader2 className="size-4 animate-spin" />
    : <svg viewBox="0 0 24 24" fill="currentColor" className="size-4"><path d="M12 2L12 22M12 2L5 9M12 2L19 9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none" /></svg>
    }
   </Button>
   <div className={`flex-1 ${serveInfo.input_fields.length > 1 ? "space-y-2" : "flex gap-2 items-start"}`}>
    {serveInfo.input_fields.map((field) => (
    <div key={field} className="flex-1 min-w-0">
     {serveInfo.input_fields.length > 1 && (
     <label htmlFor={`serve-${field}`} className="text-[10px] text-muted-foreground/50 font-mono px-3 mb-0.5 block" dir="ltr">{field}</label>
     )}
     <textarea
     id={`serve-${field}`}
     ref={(el) => { textareaRefs.current[field] = el; }}
     dir="auto"
     placeholder={field}
     defaultValue=""
     onChange={(e) => {
      e.target.style.height = "auto";
      e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
      if (serveError) setServeError(null);
     }}
     onKeyDown={(e) => {
      if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const allFilled = serveInfo.input_fields.every((f) => textareaRefs.current[f]?.value?.trim());
      if (!serveLoading && allFilled) handleServe();
      }
     }}
     rows={1}
     className="block w-full bg-muted/20 rounded-2xl border border-[#DDD4C8] px-4 py-[11px] text-sm font-mono leading-[20px] outline-none ring-0 shadow-none resize-none overflow-hidden h-[42px] max-h-[120px] focus:outline-none focus-visible:outline-none focus-visible:ring-0 focus:border-[#C8A882] transition-colors placeholder:text-muted-foreground/40"
     />
    </div>
    ))}
   </div>
   </div>
  </form>
  </div>
 </div>
 );
}

/* ── Code snippets component — isolates language tab state from heavy parent ── */
function ServeCodeSnippets({ serveInfo, optimizationId }: { serveInfo: ServeInfoResponse; optimizationId: string }) {
 const [codeTab, setCodeTab] = useState<"curl" | "python" | "javascript" | "go" | "dspy">("curl");
 const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
 const url = `${apiBase}/serve/${optimizationId}`;
 const inputsObj = serveInfo.input_fields.map(f => `"${f}": "<${f}>"`).join(", ");
 const inputsJson = JSON.stringify({ inputs: Object.fromEntries(serveInfo.input_fields.map(f => [f, `<${f}>`])) });
 const snippets = {
  curl: [
   `# Send a POST request to the optimized program endpoint`,
   `# Replace <field> placeholders with your actual input values`,
   `curl -X POST ${url} \\`,
   `  -H "Content-Type: application/json" \\`,
   `  -d '${inputsJson}'`,
  ].join("\n"),
  python: [
   `import requests`,
   ``,
   `# Call the optimized program via the REST API`,
   `response = requests.post(`,
   `    "${url}",`,
   `    json={"inputs": {${inputsObj}}},`,
   `)`,
   ``,
   `# Parse and print the results`,
   `result = response.json()`,
   ...serveInfo.output_fields.map(f => `print(result["outputs"]["${f}"])`),
  ].join("\n"),
  javascript: [
   `// Call the optimized program via fetch`,
   `const response = await fetch("${url}", {`,
   `  method: "POST",`,
   `  headers: { "Content-Type": "application/json" },`,
   `  body: JSON.stringify({ inputs: { ${serveInfo.input_fields.map(f => `${f}: "<${f}>"`).join(", ")} } }),`,
   `});`,
   ``,
   `// Parse and use the results`,
   `const result = await response.json();`,
   ...serveInfo.output_fields.map(f => `console.log(result.outputs.${f});`),
  ].join("\n"),
  go: [
   `package main`,
   ``,
   `import (`,
   `\t"bytes"`,
   `\t"encoding/json"`,
   `\t"fmt"`,
   `\t"net/http"`,
   `)`,
   ``,
   `func main() {`,
   `\t// Build the request payload`,
   `\tpayload, _ := json.Marshal(map[string]any{`,
   `\t\t"inputs": map[string]string{`,
   ...serveInfo.input_fields.map(f => `\t\t\t"${f}": "<${f}>",`),
   `\t\t},`,
   `\t})`,
   ``,
   `\t// Send POST request to the optimized program`,
   `\tresp, _ := http.Post("${url}", "application/json", bytes.NewReader(payload))`,
   `\tdefer resp.Body.Close()`,
   ``,
   `\t// Decode the response`,
   `\tvar result map[string]any`,
   `\tjson.NewDecoder(resp.Body).Decode(&result)`,
   `\toutputs := result["outputs"].(map[string]any)`,
   ...serveInfo.output_fields.map(f => `\tfmt.Println(outputs["${f}"])`),
   `}`,
  ].join("\n"),
  dspy: [
   `import dspy`,
   `import base64, pickle, requests`,
   ``,
   `# Download the optimized program artifact`,
   `artifact = requests.get(`,
   `    "${apiBase}/optimizations/${optimizationId}/artifact"`,
   `).json()`,
   ``,
   `# Deserialize the compiled program from the artifact`,
   `program = pickle.loads(`,
   `    base64.b64decode(artifact["program_artifact"]["program_pickle_base64"])`,
   `)`,
   ``,
   `# Configure your language model and run the program`,
   `lm = dspy.LM("gpt-4o-mini")`,
   `with dspy.context(lm=lm):`,
   `    result = program(${serveInfo.input_fields.map(f => `${f}="<${f}>"`).join(", ")})`,
   ...serveInfo.output_fields.map(f => `    print(result.${f})`),
  ].join("\n"),
 };
 const labels = { curl: "cURL", python: "Python", javascript: "JavaScript", go: "Go", dspy: "DSPy" } as const;
 const snippet = snippets[codeTab];
 return (
  <CodeEditor
   value={snippet}
   onChange={() => {}}
   height={`${(snippet.split("\n").length + 1) * 19.6 + 8}px`}
   readOnly
   label={<LangPicker value={codeTab} onChange={setCodeTab} labels={labels} />}
  />
 );
}

/* ── Logs tab — isolates filter/sort state from heavy parent ── */
function LogsTab({ logs, pairNames, live }: { logs: import("@/lib/types").OptimizationLogEntry[]; pairNames?: Record<number, string>; live?: boolean }) {
 const showPairCol = !!pairNames && Object.keys(pairNames).length > 0;
 const logFilters = useColumnFilters();
 const logResize = useColumnResize();
 const [messageSearch, setMessageSearch] = useState("");
 const [sortKey, setSortKey] = useState<string>("timestamp");
 const [sortDir, setSortDir] = useState<SortDir>("desc");
 const toggleSort = (key: string) => {
 if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
 else { setSortKey(key); setSortDir("asc"); }
 };

 const filtered = useMemo(() => {
 const q = messageSearch.trim().toLowerCase();
 let result = logs.filter((l) => {
  if (q && !l.message.toLowerCase().includes(q)) return false;
  for (const [col, allowed] of Object.entries(logFilters.filters)) {
  if (allowed.size === 0) continue;
  const val = col === "timestamp"
   ? logTimeBucket(l.timestamp)
   : col === "pair_index"
   ? (l.pair_index != null ? String(l.pair_index) : "—")
   : String((l as unknown as Record<string, unknown>)[col] ?? "");
  if (!allowed.has(val)) return false;
  }
  return true;
 });
 result = [...result].sort((a, b) => {
  const av = String((a as unknown as Record<string, unknown>)[sortKey] ?? "");
  const bv = String((b as unknown as Record<string, unknown>)[sortKey] ?? "");
  const cmp = av.localeCompare(bv, "he", { numeric: true });
  return sortDir === "asc" ? cmp : -cmp;
 });
 return result;
 }, [logs, logFilters.filters, sortKey, sortDir, messageSearch]);

 const filterOptions = useMemo(() => {
 const unique = (key: string) => {
  const vals = [...new Set(logs.map((l) => String((l as unknown as Record<string, unknown>)[key] ?? "")))].filter(Boolean).sort();
  return vals.map((v) => ({ value: v, label: v }));
 };
 const timestampBuckets = [...new Set(logs.map((l) => logTimeBucket(l.timestamp)))]
  .filter(Boolean).sort().map((v) => ({ value: v, label: v }));
 const pairOpts = showPairCol
  ? [...new Set(logs.map((l) => l.pair_index != null ? String(l.pair_index) : "—"))].sort().map(v => ({ value: v, label: v === "—" ? "כללי" : (pairNames?.[parseInt(v)] ?? `ריצה ${parseInt(v) + 1}`) }))
  : [];
 return { level: unique("level"), logger: unique("logger"), timestamp: timestampBuckets, pair_index: pairOpts };
 }, [logs, showPairCol, pairNames]);

 return (
 <div className="mt-4">
  <FadeIn>
  <div className="flex items-center justify-between gap-3 mb-4">
  <p className="text-sm text-muted-foreground">{live ? "" : "לוגים מפורטים מתהליך האופטימיזציה — סננו לפי עמודה או חפשו בתוכן."}</p>
  <span className="text-xs text-muted-foreground shrink-0">{filtered.length} רשומות</span>
  </div>
  </FadeIn>
  <div className="flex items-center gap-3 mb-5">
  <Input
  type="text"
  value={messageSearch}
  onChange={(e) => setMessageSearch(e.target.value)}
  placeholder="Search log messages..."
  aria-label="Search log messages"
  dir="ltr"
  className="text-left w-full"
  />
  <ResetColumnsButton resize={logResize} />
  </div>
  {filtered.length === 0 ? (
  <p className="text-sm text-muted-foreground py-8 text-center">אין לוגים</p>
  ) : (
  <Card>
  <CardContent className="p-0">
  <div className="max-h-[600px] overflow-auto">
  <Table className={"table-fixed w-full"}>
   <colgroup>
   {showPairCol && <col style={{ width: logResize.widths["pair_index"] ?? "12%" }} />}
   <col style={{ width: logResize.widths["timestamp"] ?? (showPairCol ? "13%" : "15%") }} />
   <col style={{ width: logResize.widths["level"] ?? (showPairCol ? "10%" : "12%") }} />
   <col style={{ width: logResize.widths["logger"] ?? (showPairCol ? "14%" : "17%") }} />
   <col />
   </colgroup>
   <TableHeader>
   <TableRow>
   {showPairCol && <ColumnHeader label="ריצה" sortKey="pair_index" currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} filterCol="pair_index" filterOptions={filterOptions.pair_index} filters={logFilters.filters} onFilter={logFilters.setColumnFilter} openFilter={logFilters.openFilter} setOpenFilter={logFilters.setOpenFilter} width={logResize.widths["pair_index"]} onResize={logResize.setColumnWidth} />}
   <ColumnHeader label="זמן" sortKey="timestamp" currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} filterCol="timestamp" filterOptions={filterOptions.timestamp} filters={logFilters.filters} onFilter={logFilters.setColumnFilter} openFilter={logFilters.openFilter} setOpenFilter={logFilters.setOpenFilter} width={logResize.widths["timestamp"]} onResize={logResize.setColumnWidth} />
   <ColumnHeader label="רמה" sortKey="level" currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} filterCol="level" filterOptions={filterOptions.level} filters={logFilters.filters} onFilter={logFilters.setColumnFilter} openFilter={logFilters.openFilter} setOpenFilter={logFilters.setOpenFilter} width={logResize.widths["level"]} onResize={logResize.setColumnWidth} />
   <ColumnHeader label="לוגר" sortKey="logger" currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} filterCol="logger" filterOptions={filterOptions.logger} filters={logFilters.filters} onFilter={logFilters.setColumnFilter} openFilter={logFilters.openFilter} setOpenFilter={logFilters.setOpenFilter} width={logResize.widths["logger"]} onResize={logResize.setColumnWidth} />
   <ColumnHeader label="הודעה" sortKey="message" currentSort={sortKey} sortDir={sortDir} onSort={toggleSort} width={logResize.widths["message"]} onResize={logResize.setColumnWidth} />
   </TableRow>
   </TableHeader>
   <TableBody>
   {filtered.slice(0, 300).map((log, i) => (
   <TableRow
    key={i}
    className="cursor-pointer"
    onClick={(e) => {
     const td = (e.target as HTMLElement).closest("td");
     if (!td) return;
     const text = td.textContent?.trim();
     if (text) { navigator.clipboard.writeText(text); toast.success("הועתק בהצלחה"); }
    }}
   >
    {showPairCol && (
     <TableCell className="text-xs font-mono truncate overflow-hidden" style={logResize.widths["pair_index"] ? { width: logResize.widths["pair_index"], maxWidth: logResize.widths["pair_index"] } : undefined}>
      {log.pair_index != null ? (
       <Badge variant="secondary" className="text-[9px] font-mono">{pairNames?.[log.pair_index] ?? `ריצה ${log.pair_index + 1}`}</Badge>
      ) : (
       <span className="text-muted-foreground/40">—</span>
      )}
     </TableCell>
    )}
    <TableCell className="text-xs font-mono text-muted-foreground truncate overflow-hidden" style={logResize.widths["timestamp"] ? { width: logResize.widths["timestamp"], maxWidth: logResize.widths["timestamp"] } : undefined} dir="ltr">{formatLogTimestamp(log.timestamp)}</TableCell>
    <TableCell className="truncate overflow-hidden" style={logResize.widths["level"] ? { width: logResize.widths["level"], maxWidth: logResize.widths["level"] } : undefined}>
    <Badge variant={log.level === "ERROR" ? "destructive" : log.level === "WARNING" ? "outline" : "secondary"} className="text-[10px] font-mono">
     {log.level}
    </Badge>
    </TableCell>
    <TableCell className="text-xs font-mono text-muted-foreground truncate overflow-hidden" style={logResize.widths["logger"] ? { width: logResize.widths["logger"], maxWidth: logResize.widths["logger"] } : undefined} title={log.logger}>{log.logger}</TableCell>
    <TableCell className="text-xs font-mono whitespace-pre-wrap break-all overflow-hidden hover:underline" style={logResize.widths["message"] ? { width: logResize.widths["message"], maxWidth: logResize.widths["message"] } : undefined} title={log.message}>{log.message}</TableCell>
   </TableRow>
   ))}
   </TableBody>
   {filtered.length > 300 && (
   <tfoot><tr><td colSpan={showPairCol ? 5 : 4} className="text-center py-3 text-[10px] text-muted-foreground">מוצגות 300 מתוך {filtered.length} רשומות</td></tr></tfoot>
   )}
  </Table>
  </div>
  </CardContent>
  </Card>
  )}
 </div>
 );
}

function downloadFile(content: string, filename: string, mimeType: string) {
 const blob = new Blob([content], { type: mimeType });
 const url = URL.createObjectURL(blob);
 const a = document.createElement("a");
 a.href = url;
 a.download = filename;
 a.click();
 URL.revokeObjectURL(url);
}

function exportPromptAsText(prompt: import("@/lib/types").OptimizedPredictor, optimizationId: string) {
 let text = `# Optimized Prompt — ${prompt.predictor_name}\n\n`;
 text += `## Instructions\n${prompt.instructions}\n\n`;
 if (prompt.demos.length > 0) {
 text += `## Demos (${prompt.demos.length})\n\n`;
 prompt.demos.forEach((demo, i) => {
 text += `--- Demo ${i + 1} ---\n`;
 for (const [k, v] of Object.entries(demo.inputs)) text += `[Input] ${k}: ${v}\n`;
 for (const [k, v] of Object.entries(demo.outputs)) text += `[Output] ${k}: ${v}\n`;
 text += "\n";
 });
 }
 if (prompt.formatted_prompt) {
 text += `## Full Formatted Prompt\n${prompt.formatted_prompt}\n`;
 }
 downloadFile(text, `prompt_${optimizationId.slice(0, 8)}.txt`, "text/plain");
}

function exportPromptAsJson(prompt: import("@/lib/types").OptimizedPredictor, optimizationId: string) {
 downloadFile(JSON.stringify(prompt, null, 2), `prompt_${optimizationId.slice(0, 8)}.json`, "application/json");
}

function exportLogsAsCsv(logs: import("@/lib/types").OptimizationLogEntry[], optimizationId: string) {
 const header = "timestamp,level,logger,message\n";
 const rows = logs.map((l) => {
 const escapedMsg = `"${l.message.replace(/"/g, '""')}"`;
 return `${l.timestamp},${l.level},${l.logger},${escapedMsg}`;
 }).join("\n");
 downloadFile(header + rows, `logs_${optimizationId.slice(0, 8)}.csv`, "text/csv");
}

/* ── Export menu — isolates open state from heavy parent ── */
function ExportMenu({ job, optimizedPrompt }: { job: import("@/lib/types").OptimizationStatusResponse; optimizedPrompt: import("@/lib/types").OptimizedPredictor | null }) {
 const [open, setOpen] = useState(false);
 const ref = useRef<HTMLDivElement>(null);
 useEffect(() => {
 if (!open) return;
 const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
 document.addEventListener("mousedown", handler);
 return () => document.removeEventListener("mousedown", handler);
 }, [open]);

 const hasPkl = !!(job.result?.program_artifact?.program_pickle_base64 || job.grid_result?.best_pair?.program_artifact?.program_pickle_base64);
 const itemCls = "w-full flex items-center gap-2.5 px-3.5 py-2 text-[12px] text-foreground hover:bg-muted/40 cursor-pointer transition-colors";
 const iconCls = "size-4 shrink-0 text-muted-foreground/60";
 const extCls = "text-muted-foreground/60 font-mono text-[10px] ms-auto";
 const divider = <div className="h-px bg-border/40 mx-2 my-1" />;

 return (
 <div className="relative" ref={ref}>
  <Button size="sm" onClick={() => setOpen(o => !o)} className="gap-1.5">
  <Download className="size-4" />
  הורדה
  <ChevronDown className={`size-3.5 transition-transform duration-150 ${open ? "rotate-180" : ""}`} />
  </Button>
  <AnimatePresence>
  {open && (
  <motion.div
   role="menu"
   initial={{ opacity: 0, scale: 0.95, y: -4 }}
   animate={{ opacity: 1, scale: 1, y: 0 }}
   exit={{ opacity: 0, scale: 0.95, y: -4 }}
   transition={{ duration: 0.12 }}
   className="absolute end-0 top-full mt-1.5 z-50 min-w-[180px] max-w-[min(240px,90vw)] rounded-2xl border border-border/40 bg-card shadow-[0_4px_24px_rgba(28,22,18,0.1)] py-1.5"
  >
   {hasPkl && (
   <button type="button" role="menuitem" onClick={() => {
    setOpen(false);
    const b64 = job.result?.program_artifact?.program_pickle_base64 ?? job.grid_result?.best_pair?.program_artifact?.program_pickle_base64;
    if (!b64) return;
    try {
    const blob = new Blob([Uint8Array.from(atob(b64), c => c.charCodeAt(0))], { type: "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `program_${job.optimization_id.slice(0, 8)}.pkl`; a.click();
    URL.revokeObjectURL(url);
    } catch { toast.error("שגיאה בפענוח הקובץ"); }
   }} className={itemCls}>
    <Package className={iconCls} />
    <span className="flex-1">תוכנית מאומנת</span>
    <span className={extCls}>.pkl</span>
   </button>
   )}
   {optimizedPrompt && (
   <>
    {hasPkl && divider}
    <button type="button" role="menuitem" onClick={() => { setOpen(false); exportPromptAsJson(optimizedPrompt, job.optimization_id); }} className={itemCls}>
    <FileJson className={iconCls} />
    <span className="flex-1">פרומפט</span>
    <span className={extCls}>.json</span>
    </button>
   </>
   )}
   {job.logs && job.logs.length > 0 && (
   <>
    {divider}
    <button type="button" role="menuitem" onClick={() => { setOpen(false); exportLogsAsCsv(job.logs, job.optimization_id); }} className={itemCls}>
    <FileSpreadsheet className={iconCls} />
    <span className="flex-1">לוגים</span>
    <span className={extCls}>.csv</span>
    </button>
   </>
   )}
  </motion.div>
  )}
  </AnimatePresence>
 </div>
 );
}

/* ── Delete dialog — isolates open/loading state from heavy parent ── */
function DeleteJobDialog({ optimizationId, onDeleted }: { optimizationId: string; onDeleted: () => void }) {
 const [open, setOpen] = useState(false);
 const [loading, setLoading] = useState(false);
 const handleDelete = async () => {
 setLoading(true);
 try {
  await deleteJob(optimizationId);
  setOpen(false);
  window.dispatchEvent(new Event("optimizations-changed"));
  onDeleted();
 } catch (err) {
  toast.error(err instanceof Error ? err.message : "מחיקה נכשלה");
 } finally {
  setLoading(false);
 }
 };
 return (
 <>
  <TooltipProvider>
  <UiTooltip>
  <TooltipTrigger asChild>
  <Button variant="ghost" size="icon" className="size-8 text-muted-foreground hover:text-red-600" onClick={() => setOpen(true)} aria-label="מחיקה">
  <Trash2 className="size-4" />
  </Button>
  </TooltipTrigger>
  <TooltipContent side="bottom">מחיקה</TooltipContent>
  </UiTooltip>
  </TooltipProvider>
  <Dialog open={open} onOpenChange={setOpen}>
  <DialogContent className="max-w-sm">
   <DialogHeader>
   <DialogTitle>מחיקת אופטימיזציה</DialogTitle>
   <DialogDescription>
    האם למחוק את האופטימיזציה{" "}
    <span className="font-mono font-medium text-foreground break-all">{optimizationId}</span>
    ?
   </DialogDescription>
   </DialogHeader>
   <DialogFooter className="grid grid-cols-2 gap-2">
   <Button variant="outline" onClick={() => setOpen(false)} disabled={loading} className="w-full justify-center">
    ביטול
   </Button>
   <Button variant="destructive" onClick={handleDelete} disabled={loading} className="w-full justify-center">
    {loading ? <Loader2 className="size-4 animate-spin"/> : "מחיקה"}
   </Button>
   </DialogFooter>
  </DialogContent>
  </Dialog>
 </>
 );
}

/* ── Page Component ── */

export default function JobDetailPage() {
 const { id } = useParams<{ id: string }>();
 const router = useRouter();
 const searchParams = useSearchParams();
 const initialTab = searchParams.get("tab") ?? "overview";
 const [detailTab, setDetailTab] = useState(initialTab);
 // Expose for tutorial via the typed bridge (see lib/tutorial-bridge.ts).
 useEffect(() => registerTutorialHook("setDetailTab", setDetailTab), []);

 const isDemoMode = id === DEMO_OPTIMIZATION_ID;

 const [job, setJob] = useState<OptimizationStatusResponse | null>(null);
 const [payload, setPayload] = useState<OptimizationPayloadResponse | null>(null);
 const [loading, setLoading] = useState(true);
 const [error, setError] = useState<string | null>(null);

 /* Demo simulation — runs instead of real API calls when id is tutorial-demo */
 useEffect(() => {
  if (!isDemoMode) return;
  return startDemoSimulation({ setJob: (fn) => setJob(fn), setLoading });
 }, [isDemoMode]);

 /* Serving playground */
 const [serveInfo, setServeInfo] = useState<ServeInfoResponse | null>(null);
 const [serveLoading, setServeLoading] = useState(false);
 const [runHistory, setRunHistory] = useState<Array<{ inputs: Record<string, string>; outputs: Record<string, unknown>; model: string; ts: number }>>([]);
 const [streamingRun, setStreamingRun] = useState<{ inputs: Record<string, string>; partial: Record<string, string> } | null>(null);
 const streamReqIdRef = useRef(0);
 const streamAbortRef = useRef<AbortController | null>(null);
 const chatScrollRef = useRef<HTMLDivElement>(null);
 const textareaRefs = useRef<Record<string, HTMLTextAreaElement | null>>({});
 const [serveError, setServeError] = useState<string | null>(null);
 const [stageModal, setStageModal] = useState<PipelineStage | null>(null);
 const [activeCodeTab, setActiveCodeTab] = useState<string>("signature");
 const recentLogsResize = useColumnResize();
 const recentLogsFilters = useColumnFilters();
 const gridResize = useColumnResize();
 const gridFilters = useColumnFilters();

 /* URL-based pair selection for grid search */
 const activePairIndex = searchParams.get("pair") != null ? parseInt(searchParams.get("pair")!, 10) : null;

 const activePair = useMemo(() => {
  if (activePairIndex === null || !job?.grid_result) return null;
  return job.grid_result.pair_results.find(p => p.pair_index === activePairIndex) ?? null;
 }, [activePairIndex, job?.grid_result]);

 const pairScorePoints = useMemo(() => {
  if (activePairIndex === null || !job?.logs) return [];
  // For single-pair grid search, all logs belong to that pair
  // For multi-pair, we heuristically filter
  const totalPairs = job.grid_result?.pair_results.length ?? 1;
  if (totalPairs === 1) return extractScoresFromLogs(job.logs);
  // Multi-pair: filter logs by pair mention
  const pairNum = activePairIndex + 1;
  const pairLogs = job.logs.filter(l =>
   l.message.includes(`Grid pair ${pairNum}/`) || l.message.includes(`Grid pair ${pairNum}:`)
  );
  return extractScoresFromLogs(pairLogs.length > 0 ? pairLogs : job.logs);
 }, [activePairIndex, job?.logs, job?.grid_result]);

 const pairFilteredLogs = useMemo(() => {
  if (activePairIndex === null || !job?.logs) return job?.logs ?? [];
  const pairNum = activePairIndex + 1;
  const filtered = job.logs.filter(l =>
   l.message.includes(`Grid pair ${pairNum}/`) || l.message.includes(`Grid pair ${pairNum}:`)
  );
  return filtered.length > 0 ? filtered : job.logs;
 }, [activePairIndex, job?.logs]);

 /* Fetch job data */
 const fetchJob = useCallback(async () => {
 try {
 const data = await getJob(id);
 setJob(data);
 setError(null);
 } catch (err) {
 setError("האופטימיזציה לא נמצאה");
 } finally {
 setLoading(false);
 }
 }, [id]);

 /* Fetch payload (once) */
 useEffect(() => {
 if (isDemoMode) return;
 getOptimizationPayload(id)
 .then(setPayload)
 .catch(() => {});
 }, [id, isDemoMode]);

 /* Initial fetch + SSE streaming for real-time updates */
 const jobRef = useRef(job);
 jobRef.current = job;

 useEffect(() => {
 if (isDemoMode) return;
 fetchJob();

 const API = process.env.NEXT_PUBLIC_API_URL ??"http://localhost:8000";
 let eventSource: EventSource | null = null;
 let fallbackInterval: ReturnType<typeof setInterval> | null = null;

 try {
 eventSource = new EventSource(`${API}/optimizations/${id}/stream`);

 const lastCountsRef = useRef({ logs: 0, progress: 0 });
 eventSource.onmessage = (event) => {
 try {
   const sseData = JSON.parse(event.data);
   const logCount = sseData.log_count ?? 0;
   const progressCount = sseData.progress_count ?? 0;
   const prev = lastCountsRef.current;
   // Full re-fetch when new logs/events arrive or status changes
   if (logCount > prev.logs || progressCount > prev.progress || sseData.status !== jobRef.current?.status) {
     lastCountsRef.current = { logs: logCount, progress: progressCount };
     fetchJob();
   } else {
     // Lightweight merge for metrics-only updates
     setJob((p) => p ? {
       ...p,
       status: sseData.status ?? p.status,
       message: sseData.message ?? p.message,
       latest_metrics: sseData.latest_metrics ?? p.latest_metrics,
     } : p);
   }
 } catch {
   fetchJob();
 }
 };

 eventSource.addEventListener("done", () => {
 eventSource?.close();
 fetchJob();
 });

 eventSource.onerror = () => {
 eventSource?.close();
 eventSource = null;
 // Fall back to polling
 fallbackInterval = setInterval(() => {
 if (jobRef.current && TERMINAL_STATUSES.has(jobRef.current.status)) {
 if (fallbackInterval) clearInterval(fallbackInterval);
 return;
 }
 fetchJob();
 }, 5000);
 };
 } catch {
 // SSE not supported — use polling
 fallbackInterval = setInterval(() => {
 if (jobRef.current && TERMINAL_STATUSES.has(jobRef.current.status)) {
 if (fallbackInterval) clearInterval(fallbackInterval);
 return;
 }
 fetchJob();
 }, 5000);
 }

 return () => {
 eventSource?.close();
 if (fallbackInterval) clearInterval(fallbackInterval);
 };
 }, [id, isDemoMode, fetchJob]);

 /* Listen for rename/update events from sidebar */
 useEffect(() => {
 if (isDemoMode) return;
 const onRenamed = (e: Event) => {
 const { optimizationId, name } = (e as CustomEvent).detail;
 if (optimizationId === id) setJob(prev => prev ? { ...prev, name } : prev);
 };
 const onUpdated = (e: Event) => {
 const { optimizationId } = (e as CustomEvent).detail;
 if (optimizationId === id) fetchJob();
 };
 window.addEventListener("optimization-renamed", onRenamed);
 window.addEventListener("optimization-updated", onUpdated);
 return () => {
 window.removeEventListener("optimization-renamed", onRenamed);
 window.removeEventListener("optimization-updated", onUpdated);
 };
 }, [id, fetchJob]);

 /* Actions */
 const handleCancel = async () => {
 if (isDemoMode) return;
 try {
 await cancelJob(id);
 toast.success("בקשת ביטול נשלחה");
 fetchJob();
 } catch (err) {
 toast.error(err instanceof Error ? err.message :"ביטול נכשל");
 }
 };


 /* Provide mock serve info for demo mode */
 useEffect(() => {
 if (isDemoMode && job?.status === "success") {
  setServeInfo({
   optimization_id: id,
   module_name: "Predict",
   optimizer_name: "MIPROv2",
   model_name: "gpt-4o-mini",
   input_fields: ["email_text"],
   output_fields: ["category"],
   instructions: "Classify an email into a category: spam, important, or promotional.",
   demo_count: 3,
  });
 }
 }, [isDemoMode, id, job?.status]);

 /* Fetch serve info once job succeeds */
 useEffect(() => {
 if (isDemoMode) return;
 if (job?.status !=="success") return;
 if (job.optimization_type === "grid_search") {
  if (activePairIndex != null) {
   getPairServeInfo(id, activePairIndex).then(setServeInfo).catch(() => setServeInfo(null));
  } else {
   // Grid overview — fetch serve info for best pair (used for playground on overview)
   getServeInfo(id).then(setServeInfo).catch(() => setServeInfo(null));
  }
 } else {
  getServeInfo(id).then(setServeInfo).catch(() => setServeInfo(null));
 }
 }, [id, job?.status, job?.optimization_type, activePairIndex]);

 /* Auto-scroll chat — keep up with new messages unless user scrolled up */
 useEffect(() => {
 if (chatScrollRef.current) {
 const el = chatScrollRef.current;
 if (el.scrollHeight - el.scrollTop - el.clientHeight < 300) {
 el.scrollTop = el.scrollHeight;
 }
 }
 }, [runHistory, streamingRun]);

 /* Abort any active stream when the page unmounts */
 useEffect(() => {
 return () => { streamAbortRef.current?.abort(); };
 }, []);

 /* Reset serve state when switching between pairs */
 useEffect(() => {
 streamAbortRef.current?.abort();
 setRunHistory([]);
 setStreamingRun(null);
 setServeLoading(false);
 setServeError(null);
 setServeInfo(null);
 }, [activePairIndex]);

 const readServeInputs = () => {
 const vals: Record<string, string> = {};
 for (const f of (serveInfo?.input_fields ?? [])) vals[f] = textareaRefs.current[f]?.value ?? "";
 return vals;
 };

 const handleServe = async (overrideInputs?: Record<string, string>) => {
 if (!serveInfo) return;
 const inputs = overrideInputs ?? readServeInputs();
 const missing = serveInfo.input_fields.filter((f) => !inputs[f]?.trim());
 if (missing.length > 0) {
 toast.error(<div>נא למלא את כל השדות:<br />{missing.join(", ")}</div>);
 return;
 }
 // Abort any in-flight stream, then start a new one tagged with a fresh id
 streamAbortRef.current?.abort();
 const reqId = ++streamReqIdRef.current;
 const controller = new AbortController();
 streamAbortRef.current = controller;
 setServeLoading(true);
 setServeError(null);
 setStreamingRun({ inputs: { ...inputs }, partial: {} });
 if (!overrideInputs) {
 Object.values(textareaRefs.current).forEach((el) => {
  if (el) { el.value = ""; el.style.height = "auto"; }
 });
 }
 const isStale = () => reqId !== streamReqIdRef.current;
 const streamFn = (job?.optimization_type === "grid_search" && activePairIndex != null)
  ? (i: Record<string, string>, h: Parameters<typeof serveProgramStream>[2]) => servePairProgramStream(id, activePairIndex, i, h)
  : (i: Record<string, string>, h: Parameters<typeof serveProgramStream>[2]) => serveProgramStream(id, i, h);
 await streamFn(inputs, {
 signal: controller.signal,
 onToken: (field, chunk) => {
  if (isStale()) return;
  setStreamingRun((prev) => prev
  ? { ...prev, partial: { ...prev.partial, [field]: (prev.partial[field] ?? "") + chunk } }
  : prev);
 },
 onFinal: (res) => {
  if (isStale()) return;
  setRunHistory((prev) => [{ inputs: { ...inputs }, outputs: res.outputs, model: res.model_used, ts: Date.now() }, ...prev]);
  setStreamingRun(null);
 },
 onError: (msg) => {
  if (isStale()) return;
  setServeError(msg);
  setStreamingRun(null);
 },
 });
 if (!isStale()) setServeLoading(false);
 };

 const handleClearHistory = () => {
 setRunHistory([]);
 setServeError(null);
 };

 /* Progress metrics */
 const metrics = job?.latest_metrics ?? {};

 /* Signature & metric code from payload */
 const signatureCode =
 (payload?.payload?.signature_code as string) ?? null;
 const metricCode =
 (payload?.payload?.metric_code as string) ?? null;

 /* Optimized prompt */
 /* Score progression from logs */
 const scorePoints = useMemo(() => {
 if (!job?.logs?.length) return [];
 return extractScoresFromLogs(job.logs);
 }, [job?.logs]);

 const optimizedPrompt =
 job?.result?.program_artifact?.optimized_prompt ??
 job?.grid_result?.best_pair?.program_artifact?.optimized_prompt ??
 null;

 // Live elapsed timer — ticks every second for active jobs (must be before early returns)
 const isActive = job ? ACTIVE_STATUSES.has(job.status) : false;
 const [liveElapsed, setLiveElapsed] = useState("00:00:00");
 useEffect(() => {
 const startStr = job?.started_at ?? job?.created_at;
 if (!startStr) return;
 const start = new Date(startStr).getTime();

 // For completed/cancelled/failed jobs: use server-provided elapsed or completed_at
 if (!isActive) {
 if (job?.elapsed_seconds != null && job.elapsed_seconds > 0) {
 const diff = Math.floor(job.elapsed_seconds);
 const h = String(Math.floor(diff / 3600)).padStart(2, "0");
 const m = String(Math.floor((diff % 3600) / 60)).padStart(2, "0");
 const s = String(diff % 60).padStart(2, "0");
 setLiveElapsed(`${h}:${m}:${s}`);
 } else if (job?.completed_at) {
 const end = new Date(job.completed_at).getTime();
 const diff = Math.max(0, Math.floor((end - start) / 1000));
 const h = String(Math.floor(diff / 3600)).padStart(2, "0");
 const m = String(Math.floor((diff % 3600) / 60)).padStart(2, "0");
 const s = String(diff % 60).padStart(2, "0");
 setLiveElapsed(`${h}:${m}:${s}`);
 }
 return;
 }

 // For active jobs: live tick from now
 const fmt = () => {
 const diff = Math.max(0, Math.floor((Date.now() - start) / 1000));
 const h = String(Math.floor(diff / 3600)).padStart(2, "0");
 const m = String(Math.floor((diff % 3600) / 60)).padStart(2, "0");
 const s = String(diff % 60).padStart(2, "0");
 setLiveElapsed(`${h}:${m}:${s}`);
 };
 fmt();
 const id = setInterval(fmt, 1000);
 return () => clearInterval(id);
 }, [job?.started_at ?? null, job?.created_at ?? null, job?.completed_at ?? null, job?.elapsed_seconds ?? null, isActive]);

 /* ── Render ── */

 if (loading) {
 return (
 <Skeleton name="optimization-detail" loading initialBones={optimizationDetailBones} color="var(--muted)" animate="shimmer">
 <div className="min-h-[60vh]" />
 </Skeleton>
 );
 }

 if (error || !job) {
 return (
 <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
 <XCircle className="size-12 text-destructive"/>
 <p className="text-lg text-muted-foreground">{error ??"האופטימיזציה לא נמצאה"}</p>
 </div>
 );
 }

 const isTerminal = TERMINAL_STATUSES.has(job.status);

 return (
 <div className="space-y-6 pb-12">
 {/* Breadcrumb */}
 <FadeIn>
 <div className="flex items-center gap-2 text-sm text-muted-foreground">
 <Link href="/" className="hover:text-foreground transition-colors">לוח בקרה</Link>
 <ChevronLeft className="h-3 w-3"/>
 <span className="text-foreground font-medium text-xs sm:text-sm break-all" dir="auto">{job.name || job.optimization_id.slice(0, 8)}</span>
 </div>
 </FadeIn>

 {/* ── 1. Header (hidden when viewing a grid pair) ── */}
 {!(job.optimization_type === "grid_search" && activePairIndex !== null) && (
 <FadeIn delay={0.1}>
 <div className=" rounded-xl border border-border/40 bg-gradient-to-br from-card to-card/80 p-5" data-tutorial="detail-header">
 <div className="flex flex-wrap items-start justify-between gap-4">
 <div className="space-y-2 min-w-0">
 <div className="flex items-center gap-3 flex-wrap">
 {job.name && (
 <h2 className="text-lg sm:text-xl font-bold tracking-tight" dir="auto">{job.name}</h2>
 )}
 <StatusBadge status={job.status} />
 </div>
 {job.description && (
 <p className="text-sm text-muted-foreground/70 leading-relaxed">{job.description}</p>
 )}
 <code
 className="text-xs font-mono text-muted-foreground/60 cursor-pointer hover:text-primary transition-colors break-all"
 title="לחץ להעתקה"
 aria-label="העתק מזהה אופטימיזציה"
 role="button"
 tabIndex={0}
 onClick={() => { navigator.clipboard.writeText(job.optimization_id); toast.success("הועתק", { autoClose: 1000 }); }}
 onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); navigator.clipboard.writeText(job.optimization_id); toast.success("הועתק", { autoClose: 1000 }); } }}
 >
 {job.optimization_id}
 </code>
 <div className="flex items-center gap-3 flex-wrap text-sm text-muted-foreground">
 <Badge variant="secondary" className="text-[11px]">{job.optimization_type === "grid_search"?"סריקה":"ריצה בודדת"}</Badge>
 <span className="flex items-center gap-1.5 tabular-nums" dir="ltr">
 <Clock className="size-3.5"/>
 {liveElapsed}
 </span>
 {isActive && job.estimated_remaining && (
 <span className="flex items-center gap-1.5">
 <Timer className="size-3.5"/>
 נותר: {job.estimated_remaining}
 </span>
 )}
 </div>
 </div>
 <div className="flex items-center gap-2">
 <TooltipProvider>
 <UiTooltip>
 <TooltipTrigger asChild>
 <Button variant="ghost" size="icon" className="size-8" onClick={() => router.push(`/submit?clone=${job.optimization_id}`)} aria-label="שכפול">
 <CopyPlus className="size-4"/>
 </Button>
 </TooltipTrigger>
 <TooltipContent side="bottom">שכפול</TooltipContent>
 </UiTooltip>
 </TooltipProvider>
 {isActive && (
 <TooltipProvider>
 <UiTooltip>
 <TooltipTrigger asChild>
 <Button variant="ghost" size="icon" className="size-8 text-destructive hover:bg-destructive/10 hover:text-destructive focus-visible:ring-0 focus-visible:border-0" onClick={handleCancel} aria-label="ביטול">
 <XCircle className="size-4"/>
 </Button>
 </TooltipTrigger>
 <TooltipContent side="bottom">ביטול</TooltipContent>
 </UiTooltip>
 </TooltipProvider>
 )}
 {isTerminal && <DeleteJobDialog optimizationId={job.optimization_id} onDeleted={() => router.push("/")} />}
 </div>
 </div>
 </div>
 </FadeIn>
 )}

 {/* ── Failure message ── */}
 {job.status === "failed" && (job.message || (metrics.error as string)) && (
 <FadeIn delay={0.15}>
 <div className="p-5 rounded-xl border border-red-300/60 bg-gradient-to-br from-red-50 to-red-100/40 shadow-[0_0_15px_rgba(239,68,68,0.06)]">
 <div className="flex items-start gap-3">
 <XCircle className="size-5 text-red-500 shrink-0 mt-0.5"/>
 <p className="text-sm font-semibold text-red-800">נכשלה</p>
 </div>
 <pre className="text-xs text-red-700 mt-3 whitespace-pre-wrap break-words font-mono leading-relaxed" dir="ltr">
{(job.message ?? "")?.split(/(https?:\/\/[^\s]+)/g).map((part, i) =>
 /^https?:\/\//.test(part) ? <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="underline hover:text-red-900 transition-colors">{part}</a> : part
 )}
 </pre>
 {typeof metrics.error === "string" && !job.message?.includes(metrics.error) && (
 <pre className="text-xs text-red-700 mt-2 whitespace-pre-wrap break-words font-mono leading-relaxed border-t border-red-200 pt-2" dir="ltr">
{String(metrics.error).split(/(https?:\/\/[^\s]+)/g).map((part: string, i: number) =>
 /^https?:\/\//.test(part) ? <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="underline hover:text-red-900 transition-colors">{part}</a> : part
 )}
 </pre>
 )}
 </div>
 </FadeIn>
 )}

 {/* Old live view removed — live content now in tabbed overview */}

 {/* ── Cancelled banner ── */}
 {job.status === "cancelled" && (
 <FadeIn>
 <div className="flex items-center gap-3 p-4 rounded-xl border border-stone-300 bg-stone-50 text-stone-700">
 <XCircle className="size-5 shrink-0" />
 <div>
 <p className="text-sm font-semibold">האופטימיזציה בוטלה</p>
 <p className="text-xs text-stone-500 mt-0.5">{job.message || "המשימה בוטלה על ידי המשתמש."}</p>
 </div>
 </div>
 </FadeIn>
 )}

 {/* ── Export Bar (hidden when viewing a grid pair — pair has its own) ── */}
 {isTerminal && job.status !== "cancelled" && !(job.optimization_type === "grid_search" && activePairIndex !== null) && (optimizedPrompt || (job.logs && job.logs.length > 0) || job.result?.program_artifact?.program_pickle_base64 || job.grid_result?.best_pair?.program_artifact?.program_pickle_base64) && (
 <FadeIn delay={0.25}>
 <div className="flex items-center gap-3 p-5 rounded-xl border border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10 shadow-[0_0_20px_rgba(var(--primary),0.06)]">
 <div className="flex-1">
 <p className="text-sm font-medium">ייצוא תוצאות</p>
 </div>
 <ExportMenu job={job} optimizedPrompt={optimizedPrompt} />
 </div>
 </FadeIn>
 )}

 {/* ── Per-pair full view (grid search with ?pair=N) ── */}
 {isTerminal && job.optimization_type === "grid_search" && activePairIndex !== null && activePair && (() => {
 const prs = job.grid_result!.pair_results;
 const best = job.grid_result!.best_pair;
 const isBest = best?.pair_index === activePair.pair_index;
 const pairPrompt = activePair.program_artifact?.optimized_prompt;
 const tabCls = "relative px-4 py-2.5 rounded-none border-b-2 border-transparent data-[state=active]:border-transparent data-[state=active]:border-b-primary data-[state=active]:text-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none transition-all duration-200";
 return (
 <div className="space-y-4">
 {/* Back to grid overview banner */}
 <FadeIn>
 <div className="flex items-center justify-between rounded-xl border border-[#C8A882]/30 bg-gradient-to-l from-[#FAF8F5] to-[#F5F1EC] p-3">
  <div className="flex items-center gap-3">
   <button
    type="button"
    onClick={() => router.push(`/optimizations/${id}`)}
    className="inline-flex items-center gap-1.5 text-sm font-medium text-[#3D2E22] hover:text-[#3D2E22]/80 transition-colors cursor-pointer"
   >
    <ChevronRight className="size-4" />
    <span>חזרה לסקירת הסריקה</span>
   </button>
   <span className="text-[11px] text-muted-foreground/60">|</span>
   <div className="flex items-center gap-1.5">
    {isBest && <Crown className="size-3.5 text-[#C8A882]" />}
    <span className="text-sm font-semibold text-foreground">
     {activePair.generation_model.split("/").pop()} × {activePair.reflection_model.split("/").pop()}
    </span>
   </div>
  </div>
  {/* Prev/Next navigation */}
  <div className="flex items-center gap-1">
   <button
    type="button"
    disabled={activePairIndex <= 0}
    onClick={() => router.push(`/optimizations/${id}?pair=${activePairIndex - 1}`)}
    className="p-1.5 rounded-lg hover:bg-[#3D2E22]/5 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
    title="זוג קודם"
   >
    <ArrowRight className="size-4 text-[#3D2E22]" />
   </button>
   <span className="text-[11px] text-muted-foreground tabular-nums font-mono">{activePairIndex + 1}/{prs.length}</span>
   <button
    type="button"
    disabled={activePairIndex >= prs.length - 1}
    onClick={() => router.push(`/optimizations/${id}?pair=${activePairIndex + 1}`)}
    className="p-1.5 rounded-lg hover:bg-[#3D2E22]/5 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
    title="זוג הבא"
   >
    <ArrowLeft className="size-4 text-[#3D2E22]" />
   </button>
  </div>
 </div>
 </FadeIn>

 {/* Export bar for pair */}
 {!activePair.error && activePair.program_artifact && (
 <FadeIn delay={0.05}>
 <div className="flex items-center gap-3 p-4 rounded-xl border border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10">
  <div className="flex-1">
   <p className="text-sm font-medium">ייצוא תוצאות</p>
  </div>
  <ExportMenu job={job} optimizedPrompt={pairPrompt ?? null} />
 </div>
 </FadeIn>
 )}

 {/* Pair error display */}
 {activePair.error && (
 <FadeIn delay={0.05}>
  <div className="rounded-xl border border-[#B04030]/30 bg-[#B04030]/5 p-4">
   <div className="text-sm font-medium text-[#B04030] mb-1">שגיאה</div>
   <pre className="text-xs font-mono text-[#B04030]/80 whitespace-pre-wrap" dir="ltr">{activePair.error}</pre>
  </div>
 </FadeIn>
 )}

 {/* Per-pair tabs */}
 <Tabs defaultValue={initialTab} dir="rtl">
 <TabsList variant="line" className="border-b border-border/50 pb-0 gap-0">
 <TabsTrigger value="overview" className={tabCls}><TrendingUp className="size-3.5"/> סקירה</TabsTrigger>
 {pairPrompt?.formatted_prompt && <TabsTrigger value="prompt" className={tabCls}><Code2 className="size-3.5"/> פרומפט</TabsTrigger>}
 {serveInfo && <TabsTrigger value="playground" className={tabCls}><Send className="size-3.5"/> שימוש</TabsTrigger>}
 <TabsTrigger value="data" className={tabCls}><Database className="size-3.5"/> נתונים</TabsTrigger>
 <TabsTrigger value="logs" className={tabCls}><Terminal className="size-3.5"/> לוגים</TabsTrigger>
 </TabsList>

 {/* ── Pair overview tab ── */}
 <TabsContent value="overview" className="space-y-6 mt-4">
 {/* Score cards */}
 {!activePair.error && (
  <StaggerContainer className="grid grid-cols-1 sm:grid-cols-3 gap-4">
   <StaggerItem>
    <TiltCard className="rounded-xl border border-border/50 bg-card p-6 text-center">
     <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide"><HelpTip text="ציון המדידה לפני אופטימיזציה — התוכנית רצה ללא הנחיות או דוגמאות">ציון התחלתי</HelpTip></p>
     <p className="text-3xl font-mono font-bold tabular-nums">{formatPercent(activePair.baseline_test_metric)}</p>
    </TiltCard>
   </StaggerItem>
   <StaggerItem>
    <TiltCard className="rounded-xl border border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10 p-6 text-center shadow-[0_0_20px_rgba(var(--primary),0.08)]">
     <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide"><HelpTip text="ציון המדידה אחרי אופטימיזציה — התוכנית רצה עם ההנחיות והדוגמאות שנבחרו">ציון משופר</HelpTip></p>
     <p className="text-3xl font-mono font-bold text-primary tabular-nums">{formatPercent(activePair.optimized_test_metric)}</p>
    </TiltCard>
   </StaggerItem>
   <StaggerItem>
    <TiltCard className={`rounded-xl border p-6 text-center ${(activePair.metric_improvement ?? 0) >= 0 ? "border-stone-400/50 bg-gradient-to-br from-stone-100/50 to-stone-200/30" : "border-red-300/50 bg-gradient-to-br from-red-50/50 to-red-100/30"}`}>
     <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide"><HelpTip text="ההפרש בין הציון המשופר לציון ההתחלתי — ככל שגבוה יותר, האופטימיזציה הועילה יותר">שיפור</HelpTip></p>
     <p className={`text-3xl font-mono font-bold tabular-nums ${(activePair.metric_improvement ?? 0) >= 0 ? "text-stone-600" : "text-red-600"}`}>{formatImprovement(activePair.metric_improvement)}</p>
    </TiltCard>
   </StaggerItem>
  </StaggerContainer>
 )}

 {/* Pair model info */}
 <FadeIn delay={0.1}>
  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
   <InfoCard label="מודל יצירה" value={activePair.generation_model.split("/").pop()} icon={<Cpu className="size-3.5" />} />
   <InfoCard label="מודל רפלקציה" value={activePair.reflection_model.split("/").pop()} icon={<Lightbulb className="size-3.5" />} />
   {activePair.runtime_seconds != null && (
    <InfoCard label="זמן ריצה" value={formatDuration(activePair.runtime_seconds)} icon={<Clock className="size-3.5" />} />
   )}
   {activePair.num_lm_calls != null && (
    <InfoCard label="קריאות למודל" value={String(activePair.num_lm_calls)} icon={<MessageSquare className="size-3.5" />} />
   )}
   {activePair.avg_response_time_ms != null && (
    <InfoCard label="זמן תגובה ממוצע" value={`${(activePair.avg_response_time_ms / 1000).toFixed(1)}s`} icon={<Timer className="size-3.5" />} />
   )}
  </div>
 </FadeIn>

 {/* Score progression chart */}
 {pairScorePoints.length > 1 && (
  <Card>
   <CardHeader className="pb-2">
    <CardTitle className="text-base font-medium"><HelpTip text="שינוי הציון לאורך הניסיונות השונים של האופטימייזר">מהלך הציונים</HelpTip></CardTitle>
   </CardHeader>
   <CardContent className="pt-0">
    <div className="h-[260px]" dir="ltr">
     <ScoreChart data={pairScorePoints} />
    </div>
    <div className="flex flex-wrap justify-center gap-x-5 gap-y-1 mt-2">
     <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className="inline-block w-3 h-0.5 rounded-full" style={{ backgroundColor: "var(--color-chart-4)"}} />
      <span>ציון הניסיון</span>
     </div>
     <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className="inline-block w-3 h-[2px] rounded-full" style={{ backgroundColor: "var(--color-chart-2)"}} />
      <span>הציון הגבוה ביותר</span>
     </div>
    </div>
   </CardContent>
  </Card>
 )}

 </TabsContent>

 {/* ── Pair prompt tab ── */}
 {pairPrompt?.formatted_prompt && (
 <TabsContent value="prompt" className="space-y-4 mt-4">
 <FadeIn>
  {pairPrompt.demos && pairPrompt.demos.length > 0 && (
   <Card>
    <CardHeader className="pb-2">
     <CardTitle className="text-base font-medium"><HelpTip text="דוגמאות קלט-פלט שנבחרו מהדאטאסט ומוצגות למודל כהדגמה">{pairPrompt.demos.length} דוגמאות</HelpTip></CardTitle>
    </CardHeader>
    <CardContent className="space-y-2">
     {pairPrompt.demos.map((demo, di) => (
      <div key={di} className="rounded-lg border border-border/40 bg-muted/30 p-3 text-xs font-mono space-y-1" dir="ltr">
       {Object.entries(demo).map(([k, v]) => (
        <div key={k}><span className="text-muted-foreground">{k}:</span> {String(v)}</div>
       ))}
      </div>
     ))}
    </CardContent>
   </Card>
  )}
  <Card>
   <CardHeader className="pb-2">
    <CardTitle className="text-base font-medium"><HelpTip text="הפרומפט המלא שהאופטימייזר בנה — כולל הנחיות ודוגמאות שנבחרו">הפרומפט המאומן</HelpTip></CardTitle>
   </CardHeader>
   <CardContent>
    <div className="relative group">
     <pre className="text-sm font-mono bg-muted/50 rounded-lg p-4 pe-10 overflow-x-auto whitespace-pre-wrap leading-relaxed" dir="ltr">{pairPrompt.formatted_prompt}</pre>
     <CopyButton text={pairPrompt.formatted_prompt} className="absolute top-2 right-2 opacity-0 group-hover:opacity-100"/>
    </div>
   </CardContent>
  </Card>
 </FadeIn>
 </TabsContent>
 )}

 {/* ── Pair playground tab ── */}
 {serveInfo && (
 <TabsContent value="playground" className="space-y-4 mt-4">
 <FadeIn>
 <div className="flex items-center justify-between pb-3 border-b border-border/60">
 <p className="text-sm text-muted-foreground">הרצת התוכנית המאומנת של זוג זה — הזן קלט וקבל תשובה.</p>
 {runHistory.length > 0 && (
 <TooltipProvider>
 <UiTooltip>
 <TooltipTrigger asChild>
  <Button variant="ghost" size="icon" className="size-8" onClick={handleClearHistory} aria-label="נקה היסטוריה">
  <Trash2 className="size-4" />
  </Button>
 </TooltipTrigger>
 <TooltipContent side="bottom">נקה היסטוריה</TooltipContent>
 </UiTooltip>
 </TooltipProvider>
 )}
 </div>
 </FadeIn>
 <ServeChat
  serveInfo={serveInfo}
  runHistory={runHistory}
  setRunHistory={setRunHistory}
  streamingRun={streamingRun}
  serveLoading={serveLoading}
  serveError={serveError}
  setServeError={setServeError}
  textareaRefs={textareaRefs}
  chatScrollRef={chatScrollRef}
  handleServe={handleServe}
  demos={activePair.program_artifact?.optimized_prompt?.demos ?? []}
 />
 </TabsContent>
 )}

 {/* ── Pair data tab ── */}
 <TabsContent value="data">
 <DataTab job={job} pairIndex={activePairIndex} />
 </TabsContent>

 {/* ── Pair logs tab ── */}
 <TabsContent value="logs">
 <LogsTab logs={pairFilteredLogs} />
 </TabsContent>

 </Tabs>
 </div>
 );
 })()}

 {/* ── Tabbed sections (normal view / grid overview) ── */}
 {!(job.optimization_type === "grid_search" && activePairIndex !== null) && (() => {
 const tabCls = "relative px-4 py-2.5 rounded-none border-b-2 border-transparent data-[state=active]:border-transparent data-[state=active]:border-b-primary data-[state=active]:text-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none transition-all duration-200";
 return (
 <Tabs value={detailTab} onValueChange={setDetailTab} dir="rtl">
 <TabsList variant="line" className="border-b border-border/50 pb-0 gap-0" data-tutorial="detail-tabs">
 <TabsTrigger value="overview" className={tabCls}><TrendingUp className="size-3.5"/> סקירה{isActive && <span className="relative flex size-2 ms-1"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--warning)]/60"/><span className="relative inline-flex rounded-full size-2 bg-[var(--warning)]"/></span>}</TabsTrigger>
 {serveInfo && job.optimization_type !== "grid_search" && isTerminal && <TabsTrigger value="playground" className={tabCls} data-tutorial="playground-tab"><Send className="size-3.5"/> שימוש</TabsTrigger>}
 {job.optimization_type !== "grid_search" && isTerminal && <TabsTrigger value="data" className={tabCls} data-tutorial="data-tab-trigger"><Database className="size-3.5"/> נתונים</TabsTrigger>}
 <TabsTrigger value="code" className={tabCls}><Code className="size-3.5"/> קוד</TabsTrigger>
 <TabsTrigger value="logs" className={tabCls} data-tutorial="logs-tab-trigger"><Terminal className="size-3.5"/> לוגים{isActive && <span className="relative flex size-2 ms-1"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--warning)]/60"/><span className="relative inline-flex rounded-full size-2 bg-[var(--warning)]"/></span>}</TabsTrigger>
 <TabsTrigger value="config" className={tabCls} data-tutorial="config-tab-trigger"><Settings className="size-3.5"/> הגדרות</TabsTrigger>
 </TabsList>

 {/* ── Overview tab ── */}
 <TabsContent value="overview" className="space-y-6 mt-4" data-tutorial="overview-tab">
 <FadeIn>
 <p className="text-sm text-muted-foreground">
 {isActive ? "האופטימיזציה רצה כעת — ניתן לעקוב אחר ההתקדמות בזמן אמת." : job.status === "cancelled" ? "האופטימיזציה בוטלה — להלן מצב התהליך בעת הביטול." : job.status === "failed" ? "האופטימיזציה נכשלה." : "תוצאות האופטימיזציה, ציונים ומטריקות ביצוע."}
 </p>
 </FadeIn>

 {/* ── Live progress bar ── */}
 {isActive && (() => {
 const tqdmPercent = metrics.tqdm_percent as number | undefined;
 const tqdmDesc = metrics.tqdm_desc as string | undefined;
 const tqdmN = metrics.tqdm_n as number | undefined;
 const tqdmTotal = metrics.tqdm_total as number | undefined;
 return tqdmPercent != null ? (
 <FadeIn>
 <div className="space-y-1.5">
  <div className="flex items-center justify-between text-xs text-muted-foreground">
   <span>{tqdmDesc || "אופטימיזציה"}</span>
   <span className="font-mono tabular-nums">{tqdmN ?? 0}/{tqdmTotal ?? "?"} ({tqdmPercent.toFixed(0)}%)</span>
  </div>
  <div className="h-2 rounded-full bg-border/50 overflow-hidden">
   <div className="h-full bg-primary rounded-full transition-all duration-500" style={{ width: `${tqdmPercent}%` }} />
  </div>
 </div>
 </FadeIn>
 ) : null;
 })()}

 {/* ── Live metric cards ── */}
 {isActive && (() => {
 const tqdmN = metrics.tqdm_n as number | undefined;
 const tqdmTotal = metrics.tqdm_total as number | undefined;
 const tqdmElapsed = metrics.tqdm_elapsed as number | undefined;
 const tqdmRemaining = metrics.tqdm_remaining as number | undefined;
 const tqdmRate = metrics.tqdm_rate as number | undefined;
 const baselineEvent = job.progress_events?.find((e) => e.event === "baseline_evaluated");
 const baselineScore = baselineEvent?.metrics?.baseline_test_metric as number | undefined;
 const splitsEvent = job.progress_events?.find((e) => e.event === "dataset_splits_ready");
 const trainCount = (splitsEvent?.metrics?.train_examples ?? metrics.train_examples) as number | undefined;
 const valCount = (splitsEvent?.metrics?.val_examples ?? metrics.val_examples) as number | undefined;
 const testCount = (splitsEvent?.metrics?.test_examples ?? metrics.test_examples) as number | undefined;
 const hasAny = tqdmN != null || tqdmElapsed != null || baselineScore != null || trainCount != null;
 if (!hasAny) return null;
 return (
 <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(120px, 100%), 1fr))" }}>
  {tqdmN != null && tqdmTotal != null && (
   <InfoCard label="צעד" value={`${tqdmN}/${tqdmTotal}`} icon={<Activity className="size-3.5" />} />
  )}
  {tqdmElapsed != null && (
   <InfoCard label="זמן שעבר" value={formatDuration(tqdmElapsed)} icon={<Timer className="size-3.5" />} />
  )}
  {tqdmRemaining != null && (
   <InfoCard label="נותר" value={formatDuration(Number(tqdmRemaining))} icon={<Clock className="size-3.5" />} />
  )}
  {tqdmRate != null && (
   <InfoCard label="קצב" value={`${tqdmRate.toFixed(2)}/שנ׳`} icon={<Zap className="size-3.5" />} />
  )}
  {baselineScore != null && (
   <InfoCard label="ציון התחלתי" value={formatPercent(baselineScore)} icon={<TrendingUp className="size-3.5" />} />
  )}
  {trainCount != null && (
   <InfoCard label="נתונים" value={`${trainCount}/${valCount}/${testCount}`} icon={<Database className="size-3.5" />} />
  )}
 </div>
 );
 })()}

 {/* ── Completed pipeline timeline (single runs only) ── */}
 {job.optimization_type !== "grid_search" && (
 <FadeIn delay={0.05}>
 {(() => {
 const completedStageIdx = job.status === "success" ? PIPELINE_STAGES.length : detectStage(job) === "done" ? PIPELINE_STAGES.length : PIPELINE_STAGES.findIndex((s) => s.key === detectStage(job));
 const eventToStage: Record<string, PipelineStage> = {
 "validation_passed": "validating",
 "dataset_splits_ready": "splitting",
 "baseline_evaluated": "baseline",
 "grid_pair_started": "baseline",
 "optimizer_progress": "optimizing",
 "optimized_evaluated": "evaluating",
 "grid_pair_completed": "evaluating",
 };
 const stageTs: Partial<Record<PipelineStage, string>> = {};
 for (const ev of (job.progress_events ?? [])) {
 const sk = ev.event ? eventToStage[ev.event] : undefined;
 if (sk && ev.timestamp) {
 const d = new Date(ev.timestamp);
 stageTs[sk] = `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })}|${d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}`;
 }
 }
 if (job.started_at && !stageTs.validating) {
 const d = new Date(job.started_at);
 stageTs.validating = `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })}|${d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}`;
 }
 if (job.completed_at) {
 const d = new Date(job.completed_at);
 stageTs.evaluating = `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })}|${d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}`;
 }
 const isFailed = job.status === "failed" || job.status === "cancelled";
 return (
 <div className="relative flex items-start justify-between" dir="rtl" data-tutorial="pipeline-stages">
 {/* Track line */}
 <div className="absolute top-[14px] right-[14px] left-[14px] h-[2px] bg-border/50 rounded-full" />
 <div className={`absolute top-[14px] right-[14px] h-[2px] rounded-full transition-all duration-700 ease-out ${isFailed ? "bg-destructive/60" : "bg-[#3D2E22]"}`} style={{ width: `calc(${(Math.min(completedStageIdx, PIPELINE_STAGES.length - 1) / (PIPELINE_STAGES.length - 1)) * 100}% - 28px)` }} />

 {PIPELINE_STAGES.map((s, i) => {
 const isDone = i < completedStageIdx;
 const isCurrent = isActive && i === completedStageIdx;
 const isStopped = isFailed && i === completedStageIdx;
 const ts = stageTs[s.key];
 return (
 <div key={s.key} className="relative z-10 flex flex-col items-center gap-2 min-w-0 group/node cursor-pointer" onClick={() => setStageModal(s.key)}>
  <div className={`size-7 rounded-full flex items-center justify-center transition-all duration-300 group-hover/node:scale-125 group-hover/node:shadow-[0_0_0_6px_rgba(61,46,34,0.1)] ${
   isStopped
    ? "bg-destructive text-white shadow-[0_0_0_4px_rgba(176,64,48,0.15)]"
    : isCurrent
    ? "bg-[#3D2E22] text-white shadow-[0_0_0_4px_rgba(61,46,34,0.15)]"
    : isDone
    ? "bg-[#3D2E22] text-white"
    : "bg-[#E5DDD4] text-[#8C7A6B]"
  }`}>
   {isDone ? (
    <CheckCircle2 className="size-3.5"/>
   ) : isCurrent ? (
    <Loader2 className="size-3.5 animate-spin"/>
   ) : isStopped ? (
    <XCircle className="size-3.5"/>
   ) : (
    <Circle className="size-3"/>
   )}
  </div>
  <span className={`text-[11px] whitespace-nowrap transition-colors duration-200 group-hover/node:text-[#3D2E22] ${
   isCurrent ? "text-[#3D2E22] font-semibold" : isStopped ? "text-destructive font-semibold" : isDone ? "text-[#3D2E22]/80" : "text-muted-foreground/40"
  }`}>{s.label}</span>
  {ts && isDone && (() => {
   const [date, time] = ts.split("|");
   return (
    <div className="flex flex-col items-center -mt-0.5" dir="ltr">
     <span className="text-[10px] text-muted-foreground/50 tracking-wide uppercase">{date}</span>
     <span className="text-[11px] text-muted-foreground/70 font-mono tabular-nums">{time}</span>
    </div>
   );
  })()}
 </div>
 );
 })}
 </div>
 );
 })()}
 </FadeIn>
 )}

 {/* LM call metrics for single runs */}
 {job.status === "success" && job.optimization_type === "run" && job.result && (job.result.num_lm_calls || job.result.avg_response_time_ms) && (
 <FadeIn delay={0.1}>
 <div className="grid grid-cols-2 gap-2.5">
  {job.result.num_lm_calls != null && (
   <InfoCard label={<HelpTip text="מספר הפעמים שהמערכת פנתה למודל השפה במהלך האופטימיזציה">קריאות למודל שפה</HelpTip>} value={`${job.result.num_lm_calls} קריאות`} icon={<MessageSquare className="size-3.5" />} />
  )}
  {job.result.avg_response_time_ms != null && (
   <InfoCard label={<HelpTip text="משך זמן ממוצע לכל קריאה בודדת למודל השפה">זמן תגובה ממוצע לקריאה</HelpTip>} value={`${(job.result.avg_response_time_ms / 1000).toFixed(1)} שניות לקריאה`} icon={<Timer className="size-3.5" />} />
  )}
 </div>
 </FadeIn>
 )}

 {/* ── 3. Results ── */}
 {job.status ==="success"&& job.optimization_type ==="run"&& job.result && (
 <div data-tutorial="score-cards">
 <StaggerContainer className="grid grid-cols-1 sm:grid-cols-3 gap-4">
 <StaggerItem>
 <TiltCard className=" rounded-xl border border-border/50 bg-card p-6 text-center">
 <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide"><HelpTip text="ציון המדידה לפני אופטימיזציה — התוכנית רצה ללא הנחיות או דוגמאות">ציון התחלתי</HelpTip></p>
 <p className="text-3xl font-mono font-bold">
 {formatPercent(job.result.baseline_test_metric)}
 </p>
 </TiltCard>
 </StaggerItem>
 <StaggerItem>
 <TiltCard className="rounded-xl border border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10 p-6 text-center shadow-[0_0_20px_rgba(var(--primary),0.08)]">
 <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide"><HelpTip text="ציון המדידה אחרי אופטימיזציה — התוכנית רצה עם ההנחיות והדוגמאות שנבחרו">ציון משופר</HelpTip></p>
 <p className="text-3xl font-mono font-bold text-primary">
 {formatPercent(job.result.optimized_test_metric)}
 </p>
 </TiltCard>
 </StaggerItem>
 <StaggerItem>
 <TiltCard className={`rounded-xl border p-6 text-center ${(job.result.metric_improvement ?? 0) >= 0 ? "border-stone-400/50 bg-gradient-to-br from-stone-100/50 to-stone-200/30" : "border-red-300/50 bg-gradient-to-br from-red-50/50 to-red-100/30"}`}>
 <p className="text-[11px] text-muted-foreground mb-2 font-medium tracking-wide"><HelpTip text="ההפרש בין הציון המשופר לציון ההתחלתי — ככל שגבוה יותר, האופטימיזציה הועילה יותר">שיפור</HelpTip></p>
 <p className={`text-3xl font-mono font-bold ${(job.result.metric_improvement ?? 0) >= 0 ? "text-stone-600" : "text-red-600"}`}>
 {formatImprovement(job.result.metric_improvement)}
 </p>
 </TiltCard>
 </StaggerItem>
 </StaggerContainer>
 </div>
 )}

 {/* Score progression chart for single runs */}
 {job.optimization_type === "run" && scorePoints.length > 1 && (
 <FadeIn delay={0.1}>
 <Card className="relative overflow-hidden shadow-[0_1px_3px_rgba(28,22,18,0.04),inset_0_1px_0_rgba(255,255,255,0.5)]" data-tutorial="score-chart">
 <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-l from-transparent via-[#C8A882]/40 to-transparent" aria-hidden="true" />
 <CardHeader>
 <CardTitle className="text-base flex items-center gap-2">
 <TrendingUp className="size-4 text-[#7C6350]" aria-hidden="true" />
 <HelpTip text="שינוי הציון לאורך הניסיונות השונים של האופטימייזר"><span className="font-bold tracking-tight">מהלך הציונים</span></HelpTip>
 </CardTitle>
 </CardHeader>
 <CardContent>
 <div className="h-[220px]">
 <ScoreChart data={scorePoints} />
 </div>
 </CardContent>
 </Card>
 </FadeIn>
 )}

 {job.status ==="success"&& job.optimization_type ==="grid_search"&& job.grid_result && activePairIndex === null && (() => {
 const prs = job.grid_result!.pair_results;
 const best = job.grid_result!.best_pair;
 const completedPrs = prs.filter(p => !p.error);
 const failedPrs = prs.filter(p => p.error);
 const maxScore = Math.max(...completedPrs.map(p => p.optimized_test_metric ?? 0), 0.01);

 // ─── Aggregated stats ───
 const scores = completedPrs.map(p => p.optimized_test_metric ?? 0);
 const baselines = completedPrs.map(p => p.baseline_test_metric ?? 0);
 const improvements = completedPrs.map(p => p.metric_improvement ?? 0);
 const runtimes = completedPrs.filter(p => p.runtime_seconds).map(p => p.runtime_seconds!);
 const lmCalls = completedPrs.filter(p => p.num_lm_calls).map(p => p.num_lm_calls!);
 const avgRespTimes = completedPrs.filter(p => p.avg_response_time_ms).map(p => p.avg_response_time_ms!);

 const avg = (arr: number[]) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
 const bestScore = scores.length ? Math.max(...scores) : 0;
 const worstScore = scores.length ? Math.min(...scores) : 0;
 const avgScore = avg(scores);
 const avgBaseline = avg(baselines);
 const avgImprovement = avg(improvements);
 const bestImprovement = improvements.length ? Math.max(...improvements) : 0;
 const totalRuntime = runtimes.reduce((a, b) => a + b, 0);
 const avgRuntime = avg(runtimes);
 const totalLmCalls = lmCalls.reduce((a, b) => a + b, 0);
 const avgRespTime = avg(avgRespTimes);

 return (
 <div className="space-y-4" data-tutorial="grid-search">
 {/* Primary KPIs */}
 <StaggerContainer className="grid grid-cols-2 gap-3">
  <StaggerItem>
  <TiltCard className="rounded-xl border border-[#5C7A52]/30 bg-[#5C7A52]/5 p-4 text-center">
   <p className="text-[10px] text-[#5C7A52] mb-1">ציון מנצח</p>
   <p className="text-2xl font-mono font-bold tabular-nums text-[#5C7A52]">{formatPercent(bestScore)}</p>
  </TiltCard>
  </StaggerItem>
  <StaggerItem>
  <TiltCard className={`rounded-xl border border-border/50 bg-card/80 p-4 text-center`}>
   <p className="text-[10px] text-muted-foreground mb-1">שיפור ממוצע</p>
   <p className={`text-2xl font-mono font-bold tabular-nums ${avgImprovement > 0 ? "text-[#5C7A52]" : avgImprovement < 0 ? "text-[#B04030]" : ""}`}>{formatImprovement(avgImprovement)}</p>
  </TiltCard>
  </StaggerItem>
 </StaggerContainer>

 {/* Charts */}
 {completedPrs.length > 0 && (() => {
 const pairScoresData = completedPrs.map(p => ({
  name: `${p.generation_model.split("/").pop()} × ${p.reflection_model.split("/").pop()}`,
  התחלתי: Math.round((p.baseline_test_metric ?? 0) > 1 ? (p.baseline_test_metric ?? 0) : (p.baseline_test_metric ?? 0) * 100),
  משופר: Math.round((p.optimized_test_metric ?? 0) > 1 ? (p.optimized_test_metric ?? 0) : (p.optimized_test_metric ?? 0) * 100),
  isBest: best?.pair_index === p.pair_index,
 }));
 const pairImprovData = completedPrs.map(p => ({
  name: `${p.generation_model.split("/").pop()} × ${p.reflection_model.split("/").pop()}`,
  שיפור: +((p.metric_improvement ?? 0) > 1 ? (p.metric_improvement ?? 0) : (p.metric_improvement ?? 0) * 100).toFixed(1),
  isBest: best?.pair_index === p.pair_index,
 }));
 const pairRespTimeData = completedPrs.filter(p => p.avg_response_time_ms).map(p => ({
  name: `${p.generation_model.split("/").pop()} × ${p.reflection_model.split("/").pop()}`,
  זמן_תגובה: +(p.avg_response_time_ms! / 1000).toFixed(1),
  isBest: best?.pair_index === p.pair_index,
 }));
 const ScoreTip = ({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number; dataKey?: string; color?: string }>; label?: string }) => {
  if (!active || !payload?.length) return null;
  const nameMap: Record<string, string> = { "התחלתי": "ציון לפני אופטימיזציה", "משופר": "ציון אחרי אופטימיזציה" };
  return (
   <div className="rounded-xl border border-border/60 bg-background/95 backdrop-blur-sm p-3 shadow-lg" dir="rtl">
    {label && <p className="font-semibold mb-1.5 text-foreground text-xs">{label}</p>}
    {payload.map((p, i) => (
     <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
      {p.color && <span className="size-2 rounded-full shrink-0" style={{ backgroundColor: p.color }} />}
      <span>{nameMap[String(p.dataKey)] ?? String(p.dataKey)}</span>
      <span className="font-mono font-semibold text-foreground ms-auto">{p.value}%</span>
     </div>
    ))}
   </div>
  );
 };
 const ImprovTip = ({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number; color?: string }>; label?: string }) => {
  if (!active || !payload?.length) return null;
  const val = payload[0]!.value;
  return (
   <div className="rounded-xl border border-border/60 bg-background/95 backdrop-blur-sm p-3 shadow-lg" dir="rtl">
    {label && <p className="font-semibold mb-1.5 text-foreground text-xs">{label}</p>}
    <div className="flex items-center gap-2 text-xs">
     <span className="text-muted-foreground">שיפור ביצועים:</span>
     <span className={`font-mono font-semibold ms-auto ${val > 0 ? "text-[#5C7A52]" : val < 0 ? "text-[#B04030]" : "text-foreground"}`}>{val > 0 ? "+" : ""}{val}%</span>
    </div>
   </div>
  );
 };
 return (
 <FadeIn delay={0.1}>
 <div className="grid gap-4 md:grid-cols-2">
  {/* Scores per pair */}
  <Card>
   <CardHeader className="pb-2">
    <CardTitle className="text-sm font-semibold"><HelpTip text="השוואת ציוני הבסיס והציון המשופר לכל זוג מודלים">ציונים לפי זוג</HelpTip></CardTitle>
   </CardHeader>
   <CardContent className="pt-0">
    <div className="h-[220px]" dir="ltr">
     <ResponsiveContainer width="100%" height="100%">
      <BarChart data={pairScoresData} layout="vertical" margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
       <CartesianGrid horizontal={false} strokeDasharray="3 3" className="stroke-muted" />
       <XAxis type="number" domain={[0, 105]} tickLine={false} axisLine={false} tick={{ fontSize: 10 }} className="fill-muted-foreground" label={{ value: "ציון באחוזים", position: "insideBottom", offset: -2, fontSize: 10 }} />
       <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={100} className="fill-muted-foreground" tickLine={false} axisLine={false} label={{ value: "זוג מודלים", angle: -90, position: "insideLeft", offset: 15, fontSize: 10 }} />
       <Tooltip content={<ScoreTip />} />
       <Bar dataKey="התחלתי" name="התחלתי" fill="var(--color-chart-4)" radius={[0, 3, 3, 0]} barSize={12} animationDuration={400} />
       <Bar dataKey="משופר" name="משופר" fill="var(--color-chart-2)" radius={[0, 3, 3, 0]} barSize={12} animationDuration={400} />
      </BarChart>
     </ResponsiveContainer>
    </div>
    <div className="flex justify-center gap-4 mt-1">
     <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground"><span className="size-2 rounded-full" style={{ backgroundColor: "var(--color-chart-4)" }} /> התחלתי</div>
     <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground"><span className="size-2 rounded-full" style={{ backgroundColor: "var(--color-chart-2)" }} /> משופר</div>
    </div>
   </CardContent>
  </Card>

  {/* Improvement per pair */}
  <Card>
   <CardHeader className="pb-2">
    <CardTitle className="text-sm font-semibold"><HelpTip text="אחוז השיפור שכל זוג מודלים השיג ביחס לציון ההתחלתי">שיפור לפי זוג</HelpTip></CardTitle>
   </CardHeader>
   <CardContent className="pt-0">
    <div className="h-[220px]" dir="ltr">
     <ResponsiveContainer width="100%" height="100%">
      <BarChart data={pairImprovData} layout="vertical" margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
       <CartesianGrid horizontal={false} strokeDasharray="3 3" className="stroke-muted" />
       <XAxis type="number" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} className="fill-muted-foreground" label={{ value: "שיפור באחוזים", position: "insideBottom", offset: -2, fontSize: 10 }} />
       <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={100} className="fill-muted-foreground" tickLine={false} axisLine={false} label={{ value: "זוג מודלים", angle: -90, position: "insideLeft", offset: 15, fontSize: 10 }} />
       <Tooltip content={<ImprovTip />} />
       <Bar dataKey="שיפור" name="שיפור" radius={[0, 3, 3, 0]} barSize={14} animationDuration={400}>
        {pairImprovData.map((entry, i) => (
         <Cell key={i} fill={entry.isBest ? "#5C7A52" : entry.שיפור >= 0 ? "var(--color-chart-2)" : "#B04030"} />
        ))}
       </Bar>
      </BarChart>
     </ResponsiveContainer>
    </div>
   </CardContent>
  </Card>
 </div>

 {/* Response time per pair */}
 {pairRespTimeData.length > 0 && (
  <Card className="mt-4">
   <CardHeader className="pb-2">
    <CardTitle className="text-sm font-semibold"><HelpTip text="משך זמן ממוצע לכל קריאה למודל שפה, לפי זוג מודלים">זמן תגובה ממוצע לפי זוג</HelpTip></CardTitle>
   </CardHeader>
   <CardContent className="pt-0">
    <div className="h-[220px]" dir="ltr">
     <ResponsiveContainer width="100%" height="100%">
      <BarChart data={pairRespTimeData} layout="vertical" margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
       <CartesianGrid horizontal={false} strokeDasharray="3 3" className="stroke-muted" />
       <XAxis type="number" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} className="fill-muted-foreground" label={{ value: "זמן תגובה בשניות", position: "insideBottom", offset: -2, fontSize: 10 }} />
       <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={100} className="fill-muted-foreground" tickLine={false} axisLine={false} label={{ value: "זוג מודלים", angle: -90, position: "insideLeft", offset: 15, fontSize: 10 }} />
       <Tooltip content={({ active, payload, label }) => {
        if (!active || !payload?.length) return null;
        return (
         <div className="rounded-xl border border-border/60 bg-background/95 backdrop-blur-sm p-3 shadow-lg" dir="rtl">
          {label && <p className="font-semibold mb-1.5 text-foreground text-xs">{label}</p>}
          <div className="flex items-center gap-2 text-xs">
           <span className="text-muted-foreground">זמן תגובה ממוצע לקריאה:</span>
           <span className="font-mono font-semibold text-foreground ms-auto">{payload[0]!.value}s</span>
          </div>
         </div>
        );
       }} />
       <Bar dataKey="זמן_תגובה" name="זמן תגובה בשניות" radius={[0, 3, 3, 0]} barSize={14} animationDuration={400}>
        {pairRespTimeData.map((entry, i) => (
         <Cell key={i} fill={entry.isBest ? "#C8A882" : "var(--color-chart-4)"} />
        ))}
       </Bar>
      </BarChart>
     </ResponsiveContainer>
    </div>
   </CardContent>
  </Card>
 )}
 </FadeIn>
 );
 })()}

 {/* Pair cards */}
 <div className="space-y-2">
 {prs.map((pr) => {
 const isBest = best?.pair_index === pr.pair_index;
 const scoreRatio = (pr.optimized_test_metric ?? 0) / maxScore;
 const improv = pr.metric_improvement ?? 0;
 return (
 <div
  key={pr.pair_index}
  className={`group rounded-xl border p-4 transition-all duration-200 cursor-pointer hover:shadow-sm ${
   pr.error
    ? "border-[#B04030]/30 bg-[#B04030]/[0.02] hover:border-[#B04030]/50"
    : isBest
    ? "border-[#5C7A52]/40 bg-[#5C7A52]/[0.03] hover:border-[#5C7A52]/60"
    : "border-border/50 bg-card/80 hover:border-border"
  }`}
  onClick={() => router.push(`/optimizations/${id}?pair=${pr.pair_index}`)}
 >
  <div className="flex items-center gap-3">
   {isBest && <Crown className="size-4 text-[#C8A882] shrink-0" />}
   {pr.error && <XCircle className="size-4 text-[#B04030] shrink-0" />}

   <div className="flex items-center gap-2 min-w-0 flex-1">
    <span className="font-mono text-xs truncate" title={pr.generation_model}>{pr.generation_model.split("/").pop()}</span>
    <span className="text-[10px] text-muted-foreground/50">×</span>
    <span className="font-mono text-xs truncate" title={pr.reflection_model}>{pr.reflection_model.split("/").pop()}</span>
   </div>

   {!pr.error ? (
    <div className="flex items-center gap-4 shrink-0 tabular-nums font-mono text-xs" dir="rtl">
     <div className="text-center">
      <div className="text-[9px] text-foreground/50 mb-0.5">התחלתי</div>
      <div className="text-foreground">{formatPercent(pr.baseline_test_metric)}</div>
     </div>
     <div className="text-center">
      <div className="text-[9px] text-foreground/50 mb-0.5">משופר</div>
      <div className={isBest ? "font-bold text-[#5C7A52]" : "text-foreground"}>{formatPercent(pr.optimized_test_metric)}</div>
     </div>
     <div className={`text-center min-w-[48px] ${improv > 0 ? "text-[#5C7A52]" : improv < 0 ? "text-[#B04030]" : "text-foreground"}`}>
      <div className="text-[9px] text-foreground/50 mb-0.5">שיפור</div>
      <div>{formatImprovement(improv)}</div>
     </div>
    </div>
   ) : (
    <span className="text-[11px] text-[#B04030] truncate max-w-[280px]" title={pr.error}>{pr.error}</span>
   )}

   <ChevronLeft className="size-4 text-muted-foreground/30 group-hover:text-muted-foreground transition-colors shrink-0" />
  </div>

  {!pr.error && (
   <div className="mt-2.5 h-1 rounded-full bg-border/30 overflow-hidden">
    <div className="h-full rounded-full transition-all duration-500" style={{ width: `${scoreRatio * 100}%`, background: isBest ? "#5C7A52" : "#C8A882", opacity: isBest ? 0.6 : 0.3 }} />
   </div>
  )}
 </div>
 );
 })}
 </div>

 </div>
 ); })()}

 </TabsContent>

 {/* ── Playground tab ── */}
 {serveInfo && (
 <TabsContent value="playground" className="space-y-4 mt-4" data-tutorial="serve-playground">
 <FadeIn>
 <div className="flex items-center justify-between pb-3 border-b border-border/60">
 <p className="text-sm text-muted-foreground">הרצת התוכנית המאומנת בזמן אמת — הזן קלט וקבל תשובה.</p>
 {runHistory.length > 0 && (
 <TooltipProvider>
 <UiTooltip>
 <TooltipTrigger asChild>
  <Button variant="ghost" size="icon" className="size-8" onClick={handleClearHistory} aria-label="נקה היסטוריה">
  <Trash2 className="size-4" />
  </Button>
 </TooltipTrigger>
 <TooltipContent side="bottom">נקה היסטוריה</TooltipContent>
 </UiTooltip>
 </TooltipProvider>
 )}
 </div>
 </FadeIn>
 <ServeChat
  serveInfo={serveInfo}
  runHistory={runHistory}
  setRunHistory={setRunHistory}
  streamingRun={streamingRun}
  serveLoading={serveLoading}
  serveError={serveError}
  setServeError={setServeError}
  textareaRefs={textareaRefs}
  chatScrollRef={chatScrollRef}
  handleServe={handleServe}
  demos={job?.result?.program_artifact?.optimized_prompt?.demos
  ?? job?.grid_result?.best_pair?.program_artifact?.optimized_prompt?.demos
  ?? []}
 />

 {/* Endpoint + Code Snippets (merged) */}
 <Card>
 <CardHeader className="pb-2">
 <CardTitle className="text-sm"><HelpTip text="כתובת API וקוד לשילוב התוכנית המאומנת באפליקציה שלך">הרצה</HelpTip></CardTitle>
 </CardHeader>
 <CardContent className="space-y-4">
 <div className="space-y-1.5">
 <p className="text-[10px] text-muted-foreground uppercase tracking-wider"><HelpTip text="כתובת ה-API שאליה שולחים בקשות POST עם שדות הקלט כדי לקבל תשובה מהתוכנית המאומנת">כתובת שירות</HelpTip></p>
 <div className="rounded-lg bg-muted/40 p-2.5 pe-8 relative group" dir="ltr">
 <code className="text-xs font-mono break-all">POST {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/serve/{id}</code>
 <CopyButton text={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/serve/${id}`} className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100"/>
 </div>
 </div>

 <Separator />

 <div className="space-y-2">
 <p className="text-[10px] text-muted-foreground uppercase tracking-wider"><HelpTip text="דוגמאות קוד מוכנות להעתקה לשילוב התוכנית המאומנת באפליקציה שלך">קוד לשילוב</HelpTip></p>
 <ServeCodeSnippets serveInfo={serveInfo} optimizationId={id} />
 </div>
 </CardContent>
 </Card>
 </TabsContent>
 )}

 {/* ── Data tab ── */}
 <TabsContent value="data">
 <DataTab job={job} />
 </TabsContent>

 {/* ── Code tab ── */}
 <TabsContent value="code" className="space-y-6 mt-4">
 <FadeIn>
 <p className="text-sm text-muted-foreground">קוד המקור של החתימה, המטריקה, והפרומפט המאומן.</p>
 </FadeIn>
 {(signatureCode || metricCode) && (
 <Card>
 <CardHeader>
 <CardTitle className="flex items-center gap-2 text-base">
 <Code className="size-4"/>
 <HelpTip text="קוד המקור של החתימה והמטריקה שהוגדרו לאופטימיזציה זו">קוד</HelpTip>
 </CardTitle>
 </CardHeader>
 <CardContent>
 <Tabs defaultValue={signatureCode ?"signature":"metric"} dir="ltr" onValueChange={setActiveCodeTab}>
 <TabsList className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1 border-none shadow-none h-auto">
 {signatureCode && metricCode && (
 <div
 className="absolute top-1 bottom-1 w-[calc(50%-6px)] rounded-md bg-[#3D2E22] shadow-sm transition-[inset-inline-start] duration-200 ease-out"
 style={{ insetInlineStart: activeCodeTab === "signature" ? 4 : "calc(50% + 2px)" }}
 />
 )}
 {signatureCode && <TabsTrigger value="signature" className="relative z-10 rounded-md px-4 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5">חתימה (Signature)</TabsTrigger>}
 {metricCode && <TabsTrigger value="metric" className="relative z-10 rounded-md px-4 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5">מטריקה (Metric)</TabsTrigger>}
 </TabsList>
 {signatureCode && (
 <TabsContent value="signature">
 <CodeEditor value={signatureCode} onChange={() => {}} height={`${(signatureCode.split("\n").length + 1) * 19.6 + 8}px`} readOnly />
 </TabsContent>
 )}
 {metricCode && (
 <TabsContent value="metric">
 <CodeEditor value={metricCode} onChange={() => {}} height={`${(metricCode.split("\n").length + 1) * 19.6 + 8}px`} readOnly />
 </TabsContent>
 )}
 </Tabs>
 </CardContent>
 </Card>
 )}

 {optimizedPrompt && (
 <Card>
 <CardHeader>
 <CardTitle className="text-base flex items-center gap-2"><Sparkles className="size-4" /><HelpTip text="הפרומפט שנבנה אוטומטית ע״י האופטימייזר — כולל הנחיות ודוגמאות שנבחרו">פרומפט מאופטם</HelpTip></CardTitle>
 </CardHeader>
 <CardContent>
 <div className="relative group">
 <pre className="text-sm font-mono bg-muted/50 rounded-lg p-4 pe-10 overflow-x-auto whitespace-pre-wrap leading-relaxed" dir="ltr">{optimizedPrompt.formatted_prompt}</pre>
 <CopyButton text={optimizedPrompt.formatted_prompt} className="absolute top-2 right-2 opacity-0 group-hover:opacity-100"/>
 </div>
 {optimizedPrompt.demos && optimizedPrompt.demos.length > 0 && (
 <div className="mt-4 pt-4 border-t border-border">
 <p className="text-xs text-muted-foreground mb-2">{optimizedPrompt.demos.length} <HelpTip text="דוגמאות קלט-פלט שנבחרו מהדאטאסט ומוצגות למודל כדי ללמד אותו את הפורמט הרצוי">דוגמאות מובנות</HelpTip></p>
 <div className="space-y-2">
 {optimizedPrompt.demos.map((demo, i) => (
 <div key={i} className="text-xs font-mono bg-muted/50 rounded-lg p-3" dir="ltr">
 {Object.entries(demo.inputs).map(([k, v]) => (
 <div key={k}><span className="text-muted-foreground">{k}:</span> {String(v)}</div>
 ))}
 {Object.entries(demo.outputs).map(([k, v]) => (
 <div key={k}><span className="text-stone-600">{k}:</span> {String(v)}</div>
 ))}
 </div>
 ))}
 </div>
 </div>
 )}
 </CardContent>
 </Card>
 )}
 </TabsContent>

 {/* ── Logs tab ── */}
 <TabsContent value="logs" data-tutorial="live-logs">
 <LogsTab logs={job.logs} pairNames={job.optimization_type === "grid_search" && job.grid_result ? Object.fromEntries(job.grid_result.pair_results.map(p => [p.pair_index, `${p.generation_model.split("/").pop()} × ${p.reflection_model.split("/").pop()}`])) : undefined} live={isActive} />
 </TabsContent>

 {/* ── Config tab ── */}
 <TabsContent value="config" className="mt-4" data-tutorial="config-section">
 <FadeIn>
 <p className="text-sm text-muted-foreground mb-4">פרטי ההגדרות שנבחרו לאופטימיזציה זו — מודל, אופטימייזר, ופרמטרים.</p>
 {job.description && (
 <p className="text-sm text-foreground/70 leading-relaxed mb-4 border-s-2 border-[#C8A882]/40 ps-3">{job.description}</p>
 )}
 </FadeIn>
 {(() => {
 // Merge job-level data with full payload for richer config display
 const p = (payload?.payload ?? {}) as Record<string, unknown>;
 const splitFractions = (p.split_fractions ?? job.split_fractions ?? { train: 0.7, val: 0.15, test: 0.15 }) as { train: number; val: number; test: number };
 const shuffleVal = p.shuffle != null ? Boolean(p.shuffle) : job.shuffle != null ? job.shuffle : true;
 const seedVal = (p.seed ?? job.seed) as number | undefined;
 const optKw = (p.optimizer_kwargs ?? job.optimizer_kwargs ?? {}) as Record<string, unknown>;
 const compKw = (p.compile_kwargs ?? job.compile_kwargs ?? {}) as Record<string, unknown>;
 const modelCfg = (p.model_config ?? job.model_settings ?? null) as Record<string, unknown> | null;
 const reflCfg = (p.reflection_model_config ?? null) as Record<string, unknown> | null;
 const promptCfg = (p.prompt_model_config ?? null) as Record<string, unknown> | null;
 const taskCfg = (p.task_model_config ?? null) as Record<string, unknown> | null;

 // Helper to render a model config card — matches ModelChip style
 const ModelCard = ({ label, cfg }: { label: string; cfg: Record<string, unknown>; icon?: React.ReactNode }) => {
  const name = String(cfg.name || "—");
  const shortName = name.includes("/") ? name.split("/").pop()! : name;
  const temp = cfg.temperature as number | undefined;
  const maxTok = cfg.max_tokens as number | undefined;
  const extra = (cfg.extra ?? {}) as Record<string, unknown>;
  const reasoning = extra.reasoning_effort as string | undefined;
  return (
   <div className="flex items-center gap-2.5 rounded-lg border border-border/50 bg-card/80 px-3 py-2">
    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
     <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
     <span className="truncate text-sm text-foreground font-mono font-medium" dir="ltr">{shortName}</span>
     <div className="flex items-center gap-2.5 text-[10px] text-muted-foreground" dir="ltr">
      {temp != null && <span className="inline-flex items-center gap-0.5"><Thermometer className="size-2.5" />{temp.toFixed(1)}</span>}
      {maxTok != null && <span className="inline-flex items-center gap-0.5"><Coins className="size-2.5" />{maxTok}</span>}
      {reasoning && <span className="inline-flex items-center gap-0.5 text-primary/70"><Brain className="size-2.5" />{reasoning}</span>}
     </div>
    </div>
   </div>
  );
 };

 // Known optimizer param labels and tooltips (Hebrew)
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
 const labelWithTip = (key: string): React.ReactNode => {
  const label = OPT_PARAM_LABELS[key] || key;
  const tip = OPT_PARAM_TIPS[key];
  return tip ? <HelpTip text={tip}>{label}</HelpTip> : label;
 };
 const formatParamValue = (k: string, v: unknown): string => {
  if (typeof v === "boolean") return v ? "כן" : "לא";
  return String(v);
 };

 return (
 <div className="space-y-4">
 {/* Section 1: General + Optimizer Parameters */}
 <Card className="relative overflow-hidden shadow-[0_1px_3px_rgba(28,22,18,0.04),inset_0_1px_0_rgba(255,255,255,0.5)]">
 <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-l from-transparent via-[#C8A882]/40 to-transparent" aria-hidden="true" />
 <CardHeader className="pb-3">
  <CardTitle className="text-base flex items-center gap-2">
   <Settings className="size-4 text-[#7C6350]" aria-hidden="true" />
   <HelpTip text="המודול, האופטימייזר, והפרמטרים שנבחרו להרצה זו"><span className="font-bold tracking-tight">הגדרות אופטימיזציה</span></HelpTip>
  </CardTitle>
 </CardHeader>
 <CardContent>
  {(() => {
   const items: { label: React.ReactNode; value: string; icon: React.ReactNode }[] = [
    { label: <HelpTip text="אופן עיבוד הפרומפט — Predict שולח ישירות, CoT מוסיף שלב חשיבה">מודול</HelpTip>, value: job.module_name ?? "—", icon: <Component className="size-3.5" /> },
    { label: <HelpTip text="אלגוריתם האופטימיזציה שמשפר את הפרומפט">אופטימייזר</HelpTip>, value: job.optimizer_name ?? "—", icon: <Target className="size-3.5" /> },
    ...Object.entries(optKw).filter(([k]) => k !== "metric").map(([k, v]) => ({ label: labelWithTip(k), value: formatParamValue(k, v), icon: <Settings2 className="size-3.5" /> })),
    ...Object.entries(compKw).map(([k, v]) => ({ label: labelWithTip(k), value: formatParamValue(k, v), icon: <Layers className="size-3.5" /> })),
   ];
   return (
    <div className="divide-y divide-border/40">
     {items.map((item, i) => (
      <div key={i} className="flex items-center justify-between py-2.5 gap-3">
       <span className="flex items-center gap-2 text-xs text-muted-foreground shrink-0">
        <span className="text-[#A89680]">{item.icon}</span>
        {item.label}
       </span>
       <span className="text-sm font-semibold text-foreground font-mono truncate" dir="ltr">{item.value}</span>
      </div>
     ))}
    </div>
   );
  })()}
 </CardContent>
 </Card>

 {/* Section 2: Models */}
 <Card className="relative overflow-hidden shadow-[0_1px_3px_rgba(28,22,18,0.04),inset_0_1px_0_rgba(255,255,255,0.5)]">
 <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-l from-transparent via-[#C8A882]/40 to-transparent" aria-hidden="true" />
 <CardHeader className="pb-3">
  <CardTitle className="text-base flex items-center gap-2">
   <Cpu className="size-4 text-[#7C6350]" aria-hidden="true" />
   <HelpTip text="מודלי השפה שהוגדרו — יצירה לייצור תשובות, רפלקציה לניתוח שגיאות"><span className="font-bold tracking-tight">מודלים</span></HelpTip>
  </CardTitle>
 </CardHeader>
 <CardContent>
  {job.optimization_type !== "grid_search" ? (
   <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
    {modelCfg && <ModelCard label="מודל יצירה" cfg={modelCfg} icon={<Cpu className="size-3.5" />} />}
    {reflCfg && <ModelCard label="מודל רפלקציה" cfg={reflCfg} icon={<Lightbulb className="size-3.5" />} />}
    {promptCfg && <ModelCard label="מודל Prompt" cfg={promptCfg} icon={<Quote className="size-3.5" />} />}
    {taskCfg && <ModelCard label="מודל Task" cfg={taskCfg} icon={<ListTodo className="size-3.5" />} />}
    {!modelCfg && !reflCfg && !promptCfg && !taskCfg && job.model_name && (
     <>
      <ModelCard label="מודל יצירה" cfg={{ name: job.model_name, ...(job.model_settings || {}) }} icon={<Cpu className="size-3.5" />} />
      {job.reflection_model_name && <ModelCard label="מודל רפלקציה" cfg={{ name: job.reflection_model_name }} icon={<Lightbulb className="size-3.5" />} />}
     </>
    )}
   </div>
  ) : job.generation_models && job.reflection_models ? (
   <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div className="space-y-2">
     <p className="text-[10px] font-semibold tracking-[0.08em] uppercase text-[#A89680] mb-1"><HelpTip text="המודלים שמייצרים את התשובות — כל זוג נבדק עם מודל יצירה שונה">מודלי יצירה</HelpTip></p>
     {job.generation_models.map((m, i) => (
      <ModelCard key={i} label={`יצירה ${i + 1}`} cfg={m as unknown as Record<string, unknown>} icon={<Cpu className="size-3.5" />} />
     ))}
    </div>
    <div className="space-y-2">
     <p className="text-[10px] font-semibold tracking-[0.08em] uppercase text-[#A89680] mb-1"><HelpTip text="המודלים שמנתחים שגיאות ומציעים שיפורים — כל זוג נבדק עם מודל רפלקציה שונה">מודלי רפלקציה</HelpTip></p>
     {job.reflection_models.map((m, i) => (
      <ModelCard key={i} label={`רפלקציה ${i + 1}`} cfg={m as unknown as Record<string, unknown>} icon={<Lightbulb className="size-3.5" />} />
     ))}
    </div>
   </div>
  ) : null}
 </CardContent>
 </Card>

 {/* Section 3: Data & Splits */}
 <Card className="relative overflow-hidden shadow-[0_1px_3px_rgba(28,22,18,0.04),inset_0_1px_0_rgba(255,255,255,0.5)]">
 <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-l from-transparent via-[#C8A882]/40 to-transparent" aria-hidden="true" />
 <CardHeader className="pb-3">
  <CardTitle className="text-base flex items-center gap-2">
   <Database className="size-4 text-[#7C6350]" aria-hidden="true" />
   <HelpTip text="חלוקת הדאטאסט לאימון, אימות ובדיקה, והגדרות ערבוב"><span className="font-bold tracking-tight">נתונים</span></HelpTip>
  </CardTitle>
 </CardHeader>
 <CardContent className="space-y-4">
  {/* Split bar */}
  <div className="space-y-2">
   <p className="text-[10px] font-semibold tracking-[0.08em] uppercase text-[#A89680]"><HelpTip text="הנתונים מחולקים לשלוש קבוצות — אימון ללמידה, אימות לכיוונון, ובדיקה למדידת ביצועים סופיים">חלוקת דאטאסט</HelpTip></p>
   <div className="flex h-2.5 rounded-full overflow-hidden">
    <div className="bg-[#3D2E22] transition-all" style={{ width: `${splitFractions.train * 100}%` }} />
    <div className="bg-[#C8A882] transition-all" style={{ width: `${splitFractions.val * 100}%` }} />
    <div className="bg-[#8C7A6B] transition-all" style={{ width: `${splitFractions.test * 100}%` }} />
   </div>
   <div className="flex gap-4 text-xs">
    <span className="flex items-center gap-1.5"><span className="inline-block w-2 h-2 rounded-full bg-[#3D2E22]" />אימון <span className="font-mono tabular-nums text-muted-foreground" dir="ltr">{splitFractions.train}</span></span>
    <span className="flex items-center gap-1.5"><span className="inline-block w-2 h-2 rounded-full bg-[#C8A882]" />אימות <span className="font-mono tabular-nums text-muted-foreground" dir="ltr">{splitFractions.val}</span></span>
    <span className="flex items-center gap-1.5"><span className="inline-block w-2 h-2 rounded-full bg-[#8C7A6B]" />בדיקה <span className="font-mono tabular-nums text-muted-foreground" dir="ltr">{splitFractions.test}</span></span>
   </div>
  </div>
  {/* Shuffle + Seed */}
  <div className="grid grid-cols-2 gap-2.5">
   <InfoCard label={<HelpTip text="ערבוב סדר השורות בדאטאסט לפני החלוקה — מונע הטיה מסדר הנתונים">ערבוב</HelpTip>} value={shuffleVal ? "כן" : "לא"} icon={<Shuffle className="size-3.5" />} />
   {seedVal != null && <InfoCard label={<HelpTip text="מספר קבוע שמבטיח שהערבוב והחלוקה יהיו זהים בכל הרצה חוזרת">מספר התחלתי</HelpTip>} value={seedVal} icon={<Dices className="size-3.5" />} />}
  </div>
 </CardContent>
 </Card>

 </div>
 );
 })()}
 </TabsContent>

 </Tabs>
 );
 })()}

 {/* Stage info modal */}
 <Dialog open={stageModal !== null} onOpenChange={(open) => { if (!open) setStageModal(null); }}>
  <DialogContent className="max-w-md" dir="rtl">
   {stageModal && (() => {
    const info = STAGE_INFO[stageModal];
    if (!info) return null;
    const stageIndex = PIPELINE_STAGES.findIndex(s => s.key === stageModal);
    const sc = (job?.result as { split_counts?: { train: number; val: number; test: number } } | undefined)?.split_counts;
    return (
     <>
      <DialogHeader>
       <div className="flex items-center gap-3 mb-1">
        <div className="size-9 rounded-full bg-[#3D2E22] text-white flex items-center justify-center text-sm font-bold">{stageIndex + 1}</div>
        <div>
         <DialogTitle className="text-base">{info.title}</DialogTitle>
         <DialogDescription className="text-[13px] mt-0.5">{info.description}</DialogDescription>
        </div>
       </div>
      </DialogHeader>
      <div className="space-y-4 text-sm">
       <p className="text-muted-foreground leading-relaxed">{info.details}</p>

       {/* Concrete data from the job */}
       {/* no split counts for splitting stage */}

       {stageModal === "baseline" && job?.baseline_test_metric != null && (
        <div className="rounded-xl bg-muted/40 p-3">
         <div className="text-[11px] font-semibold text-[#3D2E22] mb-1">תוצאה</div>
         <div className="flex items-baseline gap-1">
          <span className="text-2xl font-bold tabular-nums">{(job.baseline_test_metric * 100).toFixed(1)}%</span>
          <span className="text-xs text-muted-foreground">ציון בסיס על סט הבדיקה</span>
         </div>
        </div>
       )}

       {/* no config details for optimizing stage */}

       {stageModal === "evaluating" && job?.optimized_test_metric != null && (
        <div className="rounded-xl bg-muted/40 p-3">
         <div className="text-[11px] font-semibold text-[#3D2E22] mb-1">תוצאה סופית</div>
         <div className="flex items-baseline gap-3">
          <div>
           <span className="text-2xl font-bold tabular-nums text-[#5C7A52]">{(job.optimized_test_metric * 100).toFixed(1)}%</span>
           <span className="text-[10px] text-muted-foreground ms-1">מאומנת</span>
          </div>
          {job.baseline_test_metric != null && (
           <div className="text-xs text-muted-foreground">
            מ-{(job.baseline_test_metric * 100).toFixed(1)}%
            <span className={`ms-1 font-semibold ${(job.metric_improvement ?? 0) >= 0 ? "text-[#5C7A52]" : "text-[#B04030]"}`}>
             ({(job.metric_improvement ?? 0) >= 0 ? "+" : ""}{((job.metric_improvement ?? 0) * 100).toFixed(1)}%)
            </span>
           </div>
          )}
         </div>
        </div>
       )}
      </div>
     </>
    );
   })()}
  </DialogContent>
 </Dialog>

 </div>
 );
}
