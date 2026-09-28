"use client";

import * as React from "react";
import { CircleNotch } from "@/shared/ui/icons";
import { toast } from "react-toastify";
import { Button } from "@/shared/ui/primitives/button";
import { Dialog, DialogContent, DialogFooter } from "@/shared/ui/primitives/dialog";
import { Input } from "@/shared/ui/primitives/input";
import { DialogTitleRow } from "@/shared/ui/dialog-title-row";
import { renameDataset, type DatasetSummary } from "@/shared/lib/api";
import { msg } from "@/shared/lib/messages";

/**
 * Rename one library dataset. Shared by the card's rename button and the
 * library's selection bar; the field resets to the current name on each open.
 */
export function DatasetRenameDialog({
  dataset,
  open,
  onOpenChange,
  onRenamed,
}: {
  dataset: DatasetSummary;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRenamed: () => void;
}) {
  const [value, setValue] = React.useState(dataset.name);
  const [renaming, setRenaming] = React.useState(false);

  React.useEffect(() => {
    if (open) setValue(dataset.name);
  }, [open, dataset.name]);

  const handleRename = async () => {
    const name = value.trim();
    if (!name || renaming) return;
    setRenaming(true);
    try {
      await renameDataset(dataset.id, name);
      toast.success(msg("datasets.toast.renamed"));
      onOpenChange(false);
      onRenamed();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("datasets.toast.rename_failed"));
    } finally {
      setRenaming(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(28rem,92vw)] max-w-[min(28rem,92vw)] sm:max-w-md">
        <DialogTitleRow title={msg("datasets.rename.title")} />
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void handleRename();
            }
          }}
          aria-label={msg("datasets.rename.label")}
          autoFocus
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={renaming}>
            {msg("datasets.rename.cancel")}
          </Button>
          <Button onClick={handleRename} disabled={renaming || value.trim().length === 0}>
            {renaming ? (
              <CircleNotch className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
            ) : (
              msg("datasets.rename.save")
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
