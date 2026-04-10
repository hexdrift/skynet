"use client";

/**
 * Export menu — download buttons for program pickle, prompt, and logs.
 *
 * Extracted from app/optimizations/[id]/page.tsx. Keeps its open/close
 * state local to avoid re-rendering the heavy parent.
 */

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, Download, FileJson, FileSpreadsheet, Package } from "lucide-react";
import { toast } from "react-toastify";
import { Button } from "@/components/ui/button";
import { msg } from "@/features/shared/messages";
import type { OptimizationLogEntry, OptimizationStatusResponse, OptimizedPredictor } from "@/lib/types";

function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function exportPromptAsJson(prompt: OptimizedPredictor, optimizationId: string) {
  downloadFile(JSON.stringify(prompt, null, 2), `prompt_${optimizationId.slice(0, 8)}.json`, "application/json");
}

export function exportLogsAsCsv(logs: OptimizationLogEntry[], optimizationId: string) {
  const header = "timestamp,level,logger,message\n";
  const rows = logs.map((l) => {
    const escapedMsg = `"${l.message.replace(/"/g, '""')}"`;
    return `${l.timestamp},${l.level},${l.logger},${escapedMsg}`;
  }).join("\n");
  downloadFile(header + rows, `logs_${optimizationId.slice(0, 8)}.csv`, "text/csv");
}

export function ExportMenu({
  job,
  optimizedPrompt,
}: {
  job: OptimizationStatusResponse;
  optimizedPrompt: OptimizedPredictor | null;
}) {
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
                } catch { toast.error(msg("optimization.file.parse_error")); }
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
