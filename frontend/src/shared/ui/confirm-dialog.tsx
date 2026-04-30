"use client";

import * as React from "react";

import { Dialog, DialogContent, DialogFooter } from "@/shared/ui/primitives/dialog";
import { DialogTitleRow } from "@/shared/ui/dialog-title-row";
import { Button } from "@/shared/ui/primitives/button";
import { msg } from "@/shared/lib/messages";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void | Promise<void>;
  variant?: "default" | "destructive";
  loading?: boolean;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = msg("auto.shared.ui.confirm.dialog.literal.1"),
  cancelLabel = msg("auto.shared.ui.confirm.dialog.literal.2"),
  onConfirm,
  variant = "default",
  loading = false,
}: ConfirmDialogProps) {
  const [pending, setPending] = React.useState(false);
  const busy = loading || pending;

  const handleConfirm = async () => {
    setPending(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } catch (error) {
      console.error("Confirm action failed", error);
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" dir="rtl">
        <DialogTitleRow title={title} description={description} />
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button
            variant={variant === "destructive" ? "destructive" : "default"}
            onClick={handleConfirm}
            disabled={busy}
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
