"use client";

/**
 * Stage-info modal shown when the user clicks a pipeline stage node.
 *
 * Extracted from app/optimizations/[id]/page.tsx. Pure display — receives
 * the active stage and the job, and the parent owns the open/close state.
 */

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { OptimizationStatusResponse } from "@/shared/types/api";
import { PIPELINE_STAGES, STAGE_INFO, type PipelineStage } from "../constants";

export function StageInfoModal({
  stage,
  job,
  onClose,
}: {
  stage: PipelineStage | null;
  job: OptimizationStatusResponse | null;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={stage !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="max-w-md" dir="rtl">
        {stage &&
          (() => {
            const info = STAGE_INFO[stage];
            if (!info) return null;
            const stageIndex = PIPELINE_STAGES.findIndex((s) => s.key === stage);
            return (
              <>
                <DialogHeader>
                  <div className="flex items-center gap-3 mb-1">
                    <div className="size-9 rounded-full bg-[#3D2E22] text-white flex items-center justify-center text-sm font-bold">
                      {stageIndex + 1}
                    </div>
                    <div>
                      <DialogTitle className="text-base">{info.title}</DialogTitle>
                      <DialogDescription className="text-[13px] mt-0.5">
                        {info.description}
                      </DialogDescription>
                    </div>
                  </div>
                </DialogHeader>
                <div className="space-y-4 text-sm">
                  <p className="text-muted-foreground leading-relaxed">{info.details}</p>

                  {stage === "baseline" && job?.baseline_test_metric != null && (
                    <div className="rounded-xl bg-muted/40 p-3">
                      <div className="text-[11px] font-semibold text-[#3D2E22] mb-1">תוצאה</div>
                      <div className="flex items-baseline gap-1">
                        <span className="text-2xl font-bold tabular-nums">
                          {(job.baseline_test_metric * 100).toFixed(1)}%
                        </span>
                        <span className="text-xs text-muted-foreground">
                          ציון בסיס על סט הבדיקה
                        </span>
                      </div>
                    </div>
                  )}

                  {stage === "evaluating" && job?.optimized_test_metric != null && (
                    <div className="rounded-xl bg-muted/40 p-3">
                      <div className="text-[11px] font-semibold text-[#3D2E22] mb-1">
                        תוצאה סופית
                      </div>
                      <div className="flex items-baseline gap-3">
                        <div>
                          <span className="text-2xl font-bold tabular-nums text-[#5C7A52]">
                            {(job.optimized_test_metric * 100).toFixed(1)}%
                          </span>
                          <span className="text-[10px] text-muted-foreground ms-1">מאומנת</span>
                        </div>
                        {job.baseline_test_metric != null && (
                          <div className="text-xs text-muted-foreground">
                            מ-{(job.baseline_test_metric * 100).toFixed(1)}%
                            <span
                              className={`ms-1 font-semibold ${(job.metric_improvement ?? 0) >= 0 ? "text-[#5C7A52]" : "text-[#B04030]"}`}
                            >
                              ({(job.metric_improvement ?? 0) >= 0 ? "+" : ""}
                              {((job.metric_improvement ?? 0) * 100).toFixed(1)}%)
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
  );
}
