"use client";

/**
 * Chat-style playground for the serve tab.
 *
 * Extracted from app/optimizations/[id]/page.tsx. Owns its edit/cancel
 * state locally and receives refs + history via props from the parent
 * (which controls the actual /serve request).
 */

import { useRef, useState } from "react";
import { Loader2, MessageSquare, Pencil, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ServeInfoResponse } from "@/lib/types";
import { CopyButton } from "./ui-primitives";
import { formatOutput } from "../lib/formatters";

export interface ServeChatProps {
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

export function ServeChat({
  serveInfo,
  runHistory,
  setRunHistory,
  streamingRun,
  serveLoading,
  serveError,
  setServeError,
  textareaRefs,
  chatScrollRef,
  handleServe,
  demos,
}: ServeChatProps) {
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
