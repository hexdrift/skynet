"use client";

/**
 * Delete-confirmation dialog for a single optimization.
 *
 * Extracted from app/optimizations/[id]/page.tsx. Owns its open/loading
 * state internally and dispatches `optimizations-changed` on success so
 * the sidebar + dashboard stay in sync.
 */

import { useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { toast } from "react-toastify";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip as UiTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { deleteJob } from "@/shared/lib/api";
import { msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";

export function DeleteJobDialog({
  optimizationId,
  onDeleted,
}: {
  optimizationId: string;
  onDeleted: () => void;
}) {
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
      toast.error(err instanceof Error ? err.message : msg("optimization.delete.failed"));
    } finally {
      setLoading(false);
    }
  };
  return (
    <>
      <TooltipProvider>
        <UiTooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="size-8 text-muted-foreground hover:text-red-600"
              onClick={() => setOpen(true)}
              aria-label="מחיקה"
            >
              <Trash2 className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">מחיקה</TooltipContent>
        </UiTooltip>
      </TooltipProvider>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>מחיקת {TERMS.optimization}</DialogTitle>
            <DialogDescription>
              האם למחוק את ה{TERMS.optimization}{" "}
              <span className="font-mono font-medium text-foreground break-all">
                {optimizationId}
              </span>
              ?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="grid grid-cols-2 gap-2">
            <Button
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={loading}
              className="w-full justify-center"
            >
              ביטול
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={loading}
              className="w-full justify-center"
            >
              {loading ? <Loader2 className="size-4 animate-spin" /> : "מחיקה"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
