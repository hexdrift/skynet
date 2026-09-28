"use client";

import { useState } from "react";
import { toast } from "react-toastify";
import { CaretLeft, CaretRight, CircleNotch, Copy, Crown, Trash, XCircle } from "@/shared/ui/icons";
import { Button } from "@/shared/ui/primitives/button";
import { Dialog, DialogContent, DialogFooter } from "@/shared/ui/primitives/dialog";
import { DialogTitleRow } from "@/shared/ui/dialog-title-row";
import { TooltipButton } from "@/shared/ui/tooltip-button";
import { FadeIn } from "@/shared/ui/motion";
import { BackLink } from "@/shared/ui/back-link";
import { ReasoningPill } from "./ui-primitives";
import { pairLabel } from "./grid-overview-helpers";
import { deleteGridPair } from "@/shared/lib/api";
import { msg } from "@/shared/lib/messages";
import { getActiveDir } from "@/shared/lib/runtime-locale";
import { arrowPageStep } from "@/shared/lib/arrow-paging";
import { useIsPhone } from "@/shared/hooks/use-device-class";
import type { OptimizationStatusResponse, PairResult } from "@/shared/types/api";

export interface PairSelectionStripProps {
  job: OptimizationStatusResponse;
  activePair: PairResult;
  activePairIndex: number;
  pairCount: number;
  isBest: boolean;
  jobActive: boolean;
  jobTerminal: boolean;
  onBack: () => void;
  onPrev: () => void;
  onNext: () => void;
  onClone: () => void;
  onCancel: () => void;
  onDeleted: () => void;
}

export function PairSelectionStrip({
  job,
  activePair,
  activePairIndex,
  pairCount,
  isBest,
  jobActive,
  jobTerminal,
  onBack,
  onPrev,
  onNext,
  onClone,
  onCancel,
  onDeleted,
}: PairSelectionStripProps) {
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // Clone opens the (desktop-only) submit wizard and delete is desk work;
  // phones keep only cancel + pair navigation.
  const isPhone = useIsPhone();

  const handleDeletePair = async () => {
    setDeleting(true);
    try {
      await deleteGridPair(job.optimization_id, activePair.pair_index);
      setDeleteOpen(false);
      window.dispatchEvent(new Event("optimizations-changed"));
      onDeleted();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("optimization.delete.failed"));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
      <FadeIn>
        <div
          data-tutorial="pair-detail-summary"
          className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[#C8A882]/30 bg-gradient-to-l from-[#FAF8F5] to-[#F5F1EC] p-3"
          onKeyDown={(event) => {
            const step = arrowPageStep(event, getActiveDir() === "rtl");
            if (step === 0) return;
            event.preventDefault();
            if (step > 0 && activePairIndex < pairCount - 1) onNext();
            if (step < 0 && activePairIndex > 0) onPrev();
          }}
        >
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
            <BackLink
              onClick={onBack}
              label={msg("auto.features.optimizations.components.pairdetailview.1")}
            />
            <span aria-hidden="true" className="h-4 w-px bg-[#C8A882]/30" />
            <div className="flex items-center gap-1.5 flex-wrap min-w-0">
              {isBest && <Crown className="size-3.5 text-[#C8A882]" />}
              <span className="text-sm font-semibold text-foreground truncate">
                {activePair.generation_model.split("/").pop()}
              </span>
              <ReasoningPill value={activePair.generation_reasoning_effort} size="sm" />
              <span className="text-[0.6875rem] text-muted-foreground/50">×</span>
              <span className="text-sm font-semibold text-foreground truncate">
                {activePair.reflection_model.split("/").pop()}
              </span>
              <ReasoningPill value={activePair.reflection_reasoning_effort} size="sm" />
            </div>
          </div>
          <div className="flex w-full items-center justify-end gap-1 sm:w-auto sm:shrink-0">
            {!isPhone && (
              <TooltipButton tooltip={msg("auto.app.optimizations.id.page.4")}>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={onClone}
                  aria-label={msg("auto.app.optimizations.id.page.literal.4")}
                >
                  <Copy className="size-4" />
                </Button>
              </TooltipButton>
            )}
            {jobActive && (
              <TooltipButton tooltip={msg("auto.app.optimizations.id.page.5")}>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                  onClick={onCancel}
                  aria-label={msg("auto.app.optimizations.id.page.literal.5")}
                >
                  <XCircle className="size-4" />
                </Button>
              </TooltipButton>
            )}
            {jobTerminal && !isPhone && (
              <TooltipButton
                tooltip={msg("auto.features.optimizations.components.gridoverview.18")}
              >
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                  onClick={() => setDeleteOpen(true)}
                  aria-label={msg("auto.features.optimizations.components.gridoverview.literal.29")}
                >
                  <Trash className="size-4" />
                </Button>
              </TooltipButton>
            )}
            <span className="mx-1 h-5 w-px bg-[#C8A882]/30" />
            <Button
              variant="outline"
              size="icon-sm"
              disabled={activePairIndex <= 0}
              onClick={onPrev}
              aria-label={msg("auto.features.optimizations.components.pairdetailview.literal.1")}
            >
              <CaretLeft className="size-4 rtl:rotate-180" />
            </Button>
            <span className="text-[0.6875rem] text-muted-foreground tabular-nums font-mono">
              {activePairIndex + 1}/{pairCount}
            </span>
            <Button
              variant="outline"
              size="icon-sm"
              disabled={activePairIndex >= pairCount - 1}
              onClick={onNext}
              aria-label={msg("auto.features.optimizations.components.pairdetailview.literal.2")}
            >
              <CaretRight className="size-4 rtl:rotate-180" />
            </Button>
          </div>
        </div>
      </FadeIn>

      <Dialog open={deleteOpen} onOpenChange={(open) => !open && setDeleteOpen(false)}>
        <DialogContent className="w-[min(28rem,92vw)] max-w-[min(28rem,92vw)] sm:max-w-md">
          <DialogTitleRow
            title={msg("auto.features.optimizations.components.gridoverview.19")}
            description={
              <>
                {msg("auto.features.optimizations.components.gridoverview.20")}{" "}
                <span className="font-mono font-semibold text-foreground break-all">
                  {pairLabel(activePair)}
                </span>
                {msg("auto.features.optimizations.components.gridoverview.21")}
              </>
            }
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)} disabled={deleting}>
              {msg("auto.features.optimizations.components.gridoverview.22")}
            </Button>
            <Button variant="destructive" onClick={handleDeletePair} disabled={deleting}>
              {deleting ? (
                <CircleNotch
                  className="animate-spin motion-reduce:animate-none"
                  aria-hidden="true"
                />
              ) : (
                msg("auto.features.optimizations.components.gridoverview.literal.30")
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
