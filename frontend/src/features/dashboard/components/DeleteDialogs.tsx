import { Loader2 } from "lucide-react";
import { Button } from "@/shared/ui/primitives/button";
import { Dialog, DialogContent, DialogFooter } from "@/shared/ui/primitives/dialog";
import { DialogTitleRow } from "@/shared/ui/dialog-title-row";
import { TERMS } from "@/shared/lib/terms";
import type { DeleteTarget } from "../hooks/use-bulk-delete";
import { formatMsg, msg } from "@/shared/lib/messages";

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
          <DialogTitleRow
            title={
              selectedCount === 1
                ? formatMsg("auto.features.dashboard.components.deletedialogs.template.1", {
                    p1: TERMS.optimization,
                  })
                : formatMsg("auto.features.dashboard.components.deletedialogs.template.2", {
                    p1: TERMS.optimizationPlural,
                  })
            }
            description={
              selectedCount === 1 ? (
                <>
                  {msg("auto.features.dashboard.components.deletedialogs.1")}
                  {TERMS.optimization}
                  {msg("auto.features.dashboard.components.deletedialogs.2")}
                </>
              ) : (
                <>
                  {msg("auto.features.dashboard.components.deletedialogs.3")}
                  <span className="font-semibold">{selectedCount}</span> {TERMS.optimizationPlural}
                  {msg("auto.features.dashboard.components.deletedialogs.4")}
                </>
              )
            }
          />
          <DialogFooter className="grid grid-cols-2 gap-2">
            <Button
              variant="outline"
              onClick={() => setBulkDeleteOpen(false)}
              disabled={bulkDeleting}
              className="w-full justify-center"
            >
              {msg("auto.features.dashboard.components.deletedialogs.5")}
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
                msg("auto.features.dashboard.components.deletedialogs.literal.1")
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
          <DialogTitleRow
            title={
              <>
                {msg("auto.features.dashboard.components.deletedialogs.6")}
                {TERMS.optimization}
              </>
            }
            description={
              <>
                {msg("auto.features.dashboard.components.deletedialogs.7")}
                {TERMS.optimization}{" "}
                <span className="font-mono font-medium text-foreground break-all">
                  {deleteTarget?.id}
                </span>
                ?
              </>
            }
          />
          <DialogFooter className="grid grid-cols-2 gap-2">
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleting}
              className="w-full justify-center"
            >
              {msg("auto.features.dashboard.components.deletedialogs.8")}
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
                msg("auto.features.dashboard.components.deletedialogs.literal.2")
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
