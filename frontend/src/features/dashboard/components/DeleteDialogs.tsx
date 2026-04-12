import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { DeleteTarget } from "../hooks/use-bulk-delete";

type DeleteDialogsProps = {
  deleteTarget: DeleteTarget;
  setDeleteTarget: (t: DeleteTarget) => void;
  deleting: boolean;
  confirmDelete: () => void;
  bulkDeleteOpen: boolean;
  setBulkDeleteOpen: (open: boolean) => void;
  bulkDeleting: boolean;
  confirmBulkDelete: () => void;
  selectedCount: number;
};

export function DeleteDialogs({
  deleteTarget,
  setDeleteTarget,
  deleting,
  confirmDelete,
  bulkDeleteOpen,
  setBulkDeleteOpen,
  bulkDeleting,
  confirmBulkDelete,
  selectedCount,
}: DeleteDialogsProps) {
  return (
    <>
      <Dialog
        open={bulkDeleteOpen}
        onOpenChange={(open) => {
          if (!open) setBulkDeleteOpen(false);
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {selectedCount === 1
                ? "מחיקת אופטימיזציה"
                : "מחיקת מספר אופטימיזציות"}
            </DialogTitle>
            <DialogDescription>
              {selectedCount === 1 ? (
                <>האם למחוק אופטימיזציה אחת? פעולה זו אינה הפיכה.</>
              ) : (
                <>
                  האם למחוק{" "}
                  <span className="font-semibold">{selectedCount}</span>{" "}
                  אופטימיזציות? פעולה זו אינה הפיכה.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="grid grid-cols-2 gap-2">
            <Button
              variant="outline"
              onClick={() => setBulkDeleteOpen(false)}
              disabled={bulkDeleting}
              className="w-full justify-center"
            >
              ביטול
            </Button>
            <Button
              variant="destructive"
              onClick={confirmBulkDelete}
              disabled={bulkDeleting}
              className="w-full justify-center"
            >
              {bulkDeleting ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                "מחק הכל"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>מחיקת אופטימיזציה</DialogTitle>
            <DialogDescription>
              האם למחוק את האופטימיזציה{" "}
              <span className="font-mono font-medium text-foreground break-all">
                {deleteTarget?.id}
              </span>
              ?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="grid grid-cols-2 gap-2">
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleting}
              className="w-full justify-center"
            >
              ביטול
            </Button>
            <Button
              variant="destructive"
              onClick={confirmDelete}
              disabled={deleting}
              className="w-full justify-center"
            >
              {deleting ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                "מחיקה"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
