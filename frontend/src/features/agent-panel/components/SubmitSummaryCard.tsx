"use client";

import * as React from "react";
import { CheckCircle2, CircleAlert, ExternalLink } from "lucide-react";

import { cn } from "@/shared/lib/utils";
import { TERMS } from "@/shared/lib/terms";

import type { AgentToolCall } from "@/shared/ui/agent/types";

interface SubmitSummaryCardProps {
  call: AgentToolCall;
  className?: string;
}

interface SubmitResult {
  id?: string;
  job_name?: string;
  status?: string;
  detail?: string;
}

function extractResult(call: AgentToolCall): SubmitResult | null {
  const payload = (call.payload ?? {}) as Record<string, unknown>;
  const result = (payload.result ?? null) as SubmitResult | null;
  if (result && typeof result === "object") return result;
  const top = payload as Record<string, unknown>;
  const hasKeys = ["id", "job_name", "status", "detail"].some((k) => k in top);
  if (!hasKeys) return null;
  return {
    id: typeof top.id === "string" ? top.id : undefined,
    job_name: typeof top.job_name === "string" ? top.job_name : undefined,
    status: typeof top.status === "string" ? top.status : undefined,
    detail: typeof top.detail === "string" ? top.detail : undefined,
  };
}

/**
 * Summary card rendered after a successful `submit_optimization` call.
 * Replaces the generic tool chip so the user immediately sees the
 * resulting job and can jump to it.
 */
export function SubmitSummaryCard({ call, className }: SubmitSummaryCardProps) {
  const result = extractResult(call);
  const isError = call.status === "error";
  const jobId = result?.id;
  const jobName = result?.job_name ?? TERMS.notificationNewOpt;

  return (
    <div
      className={cn(
        "rounded-2xl border shadow-sm overflow-hidden",
        isError ? "border-red-200 bg-red-50" : "border-[#5E7A5E]/25 bg-[#F0F4EC]",
        className,
      )}
    >
      <div
        className={cn(
          "flex items-start gap-2.5 px-4 py-3 border-b",
          isError ? "border-red-200" : "border-[#5E7A5E]/15",
        )}
      >
        <span
          className={cn(
            "inline-flex size-7 shrink-0 items-center justify-center rounded-full",
            isError ? "bg-red-100 text-red-700" : "bg-[#5E7A5E]/20 text-[#3E5240]",
          )}
        >
          {isError ? (
            <CircleAlert className="size-3.5" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="size-3.5" aria-hidden="true" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <div
            className={cn(
              "text-[0.8125rem] font-medium leading-tight",
              isError ? "text-red-800" : "text-[#2F3E32]",
            )}
          >
            {isError ? "הגשה נכשלה" : `ה${TERMS.optimization} הוגשה`}
          </div>
          <div className="text-[0.75rem] text-foreground/80 mt-0.5 truncate">{jobName}</div>
        </div>
      </div>

      {!isError && jobId && (
        <a
          href={`/optimizations/${jobId}`}
          className={cn(
            "flex items-center justify-between gap-2 px-4 py-2.5",
            "text-[0.75rem] text-[#3D2E22] hover:bg-[#DFE7D9]/50 transition-colors",
          )}
        >
          <span className="font-mono truncate text-muted-foreground">{jobId}</span>
          <span className="inline-flex items-center gap-1 text-[#3D2E22] shrink-0">
            פתח
            <ExternalLink className="size-3" aria-hidden="true" />
          </span>
        </a>
      )}

      {isError && result?.detail && (
        <div className="px-4 py-2.5 text-[0.75rem] text-red-800 leading-relaxed">
          {result.detail}
        </div>
      )}
    </div>
  );
}
