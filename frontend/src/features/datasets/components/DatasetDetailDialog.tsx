"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowUpRight, Loader2, Table2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/primitives/dialog";
import { StatusBadge } from "@/shared/ui/status-badge";
import {
  getDatasetRows,
  listDatasetOptimizations,
  type DatasetOptimizationRef,
  type DatasetRowsResponse,
  type DatasetSummary,
} from "@/shared/lib/api";
import { formatMsg, msg } from "@/shared/lib/messages";
import { formatRelativeTime } from "@/shared/lib/formatters";

const PREVIEW_ROW_LIMIT = 10;

/** Render any cell value as a short, single-line string for the preview grid. */
function cellText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/**
 * Read-only detail sheet for one library dataset: a capped row preview plus the
 * reverse link — every optimization the caller can see that was submitted from
 * this dataset, each navigating to its run page. Driven open by the parent (a
 * card click or the ``?open=`` deep-link from an optimization's source link).
 */
export function DatasetDetailDialog({
  dataset,
  onClose,
}: {
  dataset: DatasetSummary | null;
  onClose: () => void;
}) {
  const [rows, setRows] = React.useState<DatasetRowsResponse | null>(null);
  const [optimizations, setOptimizations] = React.useState<DatasetOptimizationRef[] | null>(null);
  const datasetId = dataset?.id ?? null;

  React.useEffect(() => {
    if (!datasetId) return;
    let cancelled = false;
    setRows(null);
    setOptimizations(null);
    getDatasetRows(datasetId)
      .then((res) => !cancelled && setRows(res))
      .catch(() => !cancelled && setRows({ id: datasetId, columns: [], rows: [], row_count: 0, column_schema: {} }));
    listDatasetOptimizations(datasetId)
      .then((res) => !cancelled && setOptimizations(res.optimizations))
      .catch(() => !cancelled && setOptimizations([]));
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  const previewRows = rows?.rows.slice(0, PREVIEW_ROW_LIMIT) ?? [];

  return (
    <Dialog open={dataset !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        className="w-[min(56rem,94vw)] max-w-[min(56rem,94vw)] p-0 overflow-hidden"
        aria-describedby={undefined}
      >
        <div className="flex max-h-[85vh] flex-col" dir="rtl">
          <DialogHeader className="shrink-0 border-b border-border/40 px-6 pt-6 pb-4 text-start">
            <DialogTitle className="truncate">{dataset?.name}</DialogTitle>
            {dataset && (
              <DialogDescription>
                {formatMsg("datasets.count.rows", { count: dataset.row_count })}
                {" · "}
                {formatMsg("datasets.count.columns", { count: dataset.column_count })}
              </DialogDescription>
            )}
          </DialogHeader>

          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-5">
            <section className="space-y-2">
              <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                <Table2 className="size-4 text-muted-foreground" />
                {msg("datasets.detail.rows_title")}
              </h3>
              {rows === null ? (
                <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  {msg("datasets.detail.loading")}
                </div>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-border/50">
                  <table className="w-full text-start text-xs">
                    <thead className="bg-muted/40">
                      <tr>
                        {rows.columns.map((col) => (
                          <th
                            key={col}
                            className="whitespace-nowrap px-3 py-2 text-start font-semibold text-foreground/80"
                          >
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {previewRows.map((row, i) => (
                        <tr key={i} className="border-t border-border/40">
                          {rows.columns.map((col) => (
                            <td
                              key={col}
                              className="max-w-[260px] truncate px-3 py-1.5 text-foreground/70"
                              title={cellText(row[col])}
                            >
                              {cellText(row[col])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {rows && rows.row_count > previewRows.length && (
                <p className="text-xs text-muted-foreground">
                  {formatMsg("datasets.detail.rows_more", {
                    shown: previewRows.length,
                    total: rows.row_count,
                  })}
                </p>
              )}
            </section>

            <section className="space-y-2">
              <h3 className="text-sm font-semibold text-foreground">
                {msg("datasets.detail.used_by")}
                {optimizations && optimizations.length > 0 && (
                  <span className="ms-1.5 text-xs font-normal tabular-nums text-muted-foreground">
                    {optimizations.length}
                  </span>
                )}
              </h3>
              {optimizations === null ? (
                <div className="flex items-center gap-2 py-3 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  {msg("datasets.detail.loading")}
                </div>
              ) : optimizations.length === 0 ? (
                <p className="py-2 text-sm text-muted-foreground">
                  {msg("datasets.detail.used_by_empty")}
                </p>
              ) : (
                <ul className="divide-y divide-border/40 rounded-lg border border-border/50">
                  {optimizations.map((opt) => (
                    <li key={opt.optimization_id}>
                      <Link
                        href={`/optimizations/${opt.optimization_id}`}
                        className="group/link flex items-center gap-3 px-3 py-2.5 transition-colors hover:bg-accent/40"
                      >
                        <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">
                          {opt.name || opt.optimization_id}
                        </span>
                        {opt.status && <StatusBadge status={opt.status} />}
                        {opt.created_at && (
                          <span className="shrink-0 text-xs text-muted-foreground">
                            {formatRelativeTime(opt.created_at)}
                          </span>
                        )}
                        <ArrowUpRight className="size-4 shrink-0 text-muted-foreground/60 transition-colors group-hover/link:text-foreground" />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
