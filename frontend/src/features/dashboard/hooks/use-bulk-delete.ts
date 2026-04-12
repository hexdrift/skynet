import { useCallback, useEffect, useState } from "react";
import { toast } from "react-toastify";
import { cancelJob, deleteJob, bulkDeleteJobs } from "@/shared/lib/api";
import { ACTIVE_STATUSES } from "@/shared/constants/job-status";
import { msg } from "@/features/shared/messages";
import type {
  JobStatus,
  PaginatedJobsResponse,
} from "@/shared/types/api";

type UseBulkDeleteArgs = {
  data: PaginatedJobsResponse | null;
  setData: React.Dispatch<React.SetStateAction<PaginatedJobsResponse | null>>;
  setPageOffset: React.Dispatch<React.SetStateAction<number>>;
  fetchJobs: () => Promise<void> | void;
};

export type DeleteTarget = { id: string; status: string } | null;

export type UseBulkDeleteReturn = {
  deleteTarget: DeleteTarget;
  setDeleteTarget: React.Dispatch<React.SetStateAction<DeleteTarget>>;
  deleting: boolean;
  selectedIds: Set<string>;
  setSelectedIds: React.Dispatch<React.SetStateAction<Set<string>>>;
  toggleRowSelected: (id: string) => void;
  clearSelection: () => void;
  bulkDeleteOpen: boolean;
  setBulkDeleteOpen: React.Dispatch<React.SetStateAction<boolean>>;
  bulkDeleting: boolean;
  confirmDelete: () => Promise<void>;
  confirmBulkDelete: () => Promise<void>;
};

export function useBulkDelete({
  data,
  setData,
  setPageOffset,
  fetchJobs,
}: UseBulkDeleteArgs): UseBulkDeleteReturn {
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>(null);
  const [deleting, setDeleting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);

  const toggleRowSelected = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  // Drop selected IDs that no longer exist in the current dataset
  // (e.g. after another user deleted them or a status change removed them).
  useEffect(() => {
    if (!data || selectedIds.size === 0) return;
    const present = new Set(data.items.map((j) => j.optimization_id));
    let changed = false;
    const next = new Set<string>();
    for (const id of selectedIds) {
      if (present.has(id)) next.add(id);
      else changed = true;
    }
    if (changed) setSelectedIds(next);
  }, [data, selectedIds]);

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const targetId = deleteTarget.id;
    const targetStatus = deleteTarget.status;
    setDeleting(true);

    setData((prev) =>
      prev
        ? {
            ...prev,
            items: prev.items.filter((j) => j.optimization_id !== targetId),
            total: prev.total - 1,
          }
        : prev,
    );
    setDeleteTarget(null);

    try {
      if (ACTIVE_STATUSES.has(targetStatus as JobStatus)) {
        await cancelJob(targetId);
      }
      await deleteJob(targetId);
      window.dispatchEvent(new Event("optimizations-changed"));
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : msg("dashboard.delete_failed"),
      );
      fetchJobs();
    } finally {
      setDeleting(false);
    }
  };

  const confirmBulkDelete = async () => {
    if (bulkDeleting) return;
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    const idSet = new Set(ids);
    setBulkDeleting(true);

    // Single-delete cancels active jobs before deleting, so bulk
    // delete should too: cancel every non-terminal selected row in
    // parallel, then bulk-delete.
    const activeIds = data
      ? data.items
          .filter(
            (j) => idSet.has(j.optimization_id) && ACTIVE_STATUSES.has(j.status),
          )
          .map((j) => j.optimization_id)
      : [];

    setData((prev) =>
      prev
        ? {
            ...prev,
            items: prev.items.filter((j) => !idSet.has(j.optimization_id)),
            total: Math.max(0, prev.total - ids.length),
          }
        : prev,
    );
    setSelectedIds(new Set());
    setBulkDeleteOpen(false);
    // Jump back to page 1 so the user lands on the freshly-reduced
    // list instead of being stranded at an offset that just shifted
    // 50 different rows into view.
    setPageOffset(0);

    try {
      if (activeIds.length > 0) {
        await Promise.allSettled(activeIds.map((id) => cancelJob(id)));
      }
      const res = await bulkDeleteJobs(ids);
      // A "not_found" skip means the job was already gone from the
      // server — from the user's perspective that's identical to a
      // successful delete. Only real failures are surfaced.
      const realSkips = res.skipped.filter((s) => s.reason !== "not_found");
      const effectivelyDeleted =
        res.deleted.length + (res.skipped.length - realSkips.length);
      if (effectivelyDeleted > 0 && realSkips.length === 0) {
        toast.success(
          effectivelyDeleted === 1
            ? "נמחקה אופטימיזציה אחת"
            : `נמחקו ${effectivelyDeleted} אופטימיזציות`,
        );
      } else if (effectivelyDeleted > 0 && realSkips.length > 0) {
        const delPart =
          effectivelyDeleted === 1
            ? "נמחקה אופטימיזציה אחת"
            : `נמחקו ${effectivelyDeleted} אופטימיזציות`;
        const skipPart =
          realSkips.length === 1 ? "אחת לא נמחקה" : `${realSkips.length} לא נמחקו`;
        toast.warning(`${delPart}, ${skipPart}`);
      } else {
        toast.error(
          realSkips.length === 1
            ? "לא ניתן היה למחוק את האופטימיזציה"
            : `לא ניתן היה למחוק ${realSkips.length} אופטימיזציות`,
        );
      }
      // Always re-fetch after delete to reconcile with server truth.
      await fetchJobs();
      window.dispatchEvent(new Event("optimizations-changed"));
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : msg("dashboard.delete_failed"),
      );
      fetchJobs();
    } finally {
      setBulkDeleting(false);
    }
  };

  return {
    deleteTarget,
    setDeleteTarget,
    deleting,
    selectedIds,
    setSelectedIds,
    toggleRowSelected,
    clearSelection,
    bulkDeleteOpen,
    setBulkDeleteOpen,
    bulkDeleting,
    confirmDelete,
    confirmBulkDelete,
  };
}
