"use client";

import * as React from "react";
import { useTableSort } from "@/shared/hooks/use-table-sort";
import Link from "next/link";
import { toast } from "react-toastify";
import {
  ArrowLeft,
  ArrowUpRight,
  CaretLeft,
  CaretRight,
  Sparkle,
  Table as Table2,
  Tray,
} from "@/shared/ui/icons";
import { Button } from "@/shared/ui/primitives/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/primitives/dialog";
import { Table, TableBody, TableCell, TableHeader, TableRow } from "@/shared/ui/primitives/table";
import {
  ColumnHeader,
  ResetColumnsButton,
  ResetFiltersButton,
  useColumnFilters,
  useColumnResize,
} from "@/shared/ui/excel-filter";
import { StatusBadge } from "@/shared/ui/status-badge";
import { CopyButton } from "@/shared/ui/copy-button";
import { EmptyState } from "@/shared/ui/empty-state";
import { LoadingState } from "@/shared/ui/loading-state";
import { CountPill } from "@/shared/ui/count-badge";
import { Segmented } from "@/shared/ui/segmented";
import { notifyCopied } from "@/shared/lib/notify";
import { ExportTableMenu } from "@/shared/ui/export-table-menu";
import { FadeIn } from "@/shared/ui/motion";
import {
  getDatasetRows,
  listDatasetOptimizations,
  type DatasetOptimizationRef,
  type DatasetRowsResponse,
  type DatasetSummary,
} from "@/shared/lib/api";
import { formatMsg, msg } from "@/shared/lib/messages";
import { formatRelativeTime } from "@/shared/lib/formatters";
import { getActiveDir, getActiveIntlLocale } from "@/shared/lib/runtime-locale";
import { arrowPageStep } from "@/shared/lib/arrow-paging";

// The grid sorts/filters the full row set in memory, but caps the DOM at this
// many rows so a large dataset never renders tens of thousands of <tr>s.
const RENDER_ROW_CAP = 200;

type DetailTab = "rows" | "usage";

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

/** Render a value for the full-record reader: prose as-is, structures pretty-printed. */
function readerText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/**
 * Read-only detail sheet for one library dataset, split by a sliding segmented
 * toggle into two views: an interactive row grid (sort / per-column filter /
 * resize / click-to-copy, the same excel-filter toolkit the optimization Data
 * tab uses) and the reverse link — every optimization the caller can see that
 * was submitted from this dataset. Driven open by the parent (a card click or
 * the ``?open=`` deep-link from an optimization's source link).
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
  const [tab, setTab] = React.useState<DetailTab>("rows");
  // Index into the filtered row order; non-null swaps the grid for the reader.
  const [readerIndex, setReaderIndex] = React.useState<number | null>(null);
  const readerRef = React.useRef<HTMLDivElement>(null);
  const datasetId = dataset?.id ?? null;

  const colFilters = useColumnFilters();
  const colResize = useColumnResize();
  const { sortKey, sortDir, toggleSort, resetSort } = useTableSort<string>("");
  const { clearAll: clearFilters } = colFilters;
  const { resetAll: resetWidths } = colResize;

  React.useEffect(() => {
    if (!datasetId) return;
    let cancelled = false;
    setRows(null);
    setOptimizations(null);
    setTab("rows");
    setReaderIndex(null);
    resetSort();
    clearFilters();
    resetWidths();
    getDatasetRows(datasetId)
      .then((res) => !cancelled && setRows(res))
      .catch(
        () =>
          !cancelled &&
          setRows({ id: datasetId, columns: [], rows: [], row_count: 0, column_schema: {} }),
      );
    listDatasetOptimizations(datasetId)
      .then((res) => !cancelled && setOptimizations(res.optimizations))
      .catch(() => !cancelled && setOptimizations([]));
    return () => {
      cancelled = true;
    };
  }, [datasetId, resetSort, clearFilters, resetWidths]);

  const columns = rows?.columns ?? [];
  const allRows = React.useMemo(() => rows?.rows ?? [], [rows]);

  const filtered = React.useMemo(() => {
    let result = allRows.filter((r) => {
      for (const [col, allowed] of Object.entries(colFilters.filters)) {
        if (allowed.size === 0) continue;
        if (!allowed.has(cellText(r[col]))) return false;
      }
      return true;
    });
    if (sortKey) {
      const collLocale = getActiveIntlLocale();
      result = [...result].sort((a, b) => {
        const cmp = cellText(a[sortKey]).localeCompare(cellText(b[sortKey]), collLocale, {
          numeric: true,
        });
        return sortDir === "asc" ? cmp : -cmp;
      });
    }
    return result;
  }, [allRows, colFilters.filters, sortKey, sortDir]);

  const filterOptions = React.useMemo(() => {
    const opts: Record<string, Array<{ value: string; label: string }>> = {};
    for (const col of columns) {
      const vals = [...new Set(allRows.map((r) => cellText(r[col])))].filter(Boolean).sort();
      opts[col] = vals.map((v) => ({ value: v, label: v.length > 40 ? `${v.slice(0, 40)}…` : v }));
    }
    return opts;
  }, [allRows, columns]);

  const copyValue = React.useCallback((text: string) => {
    if (!text) return;
    navigator.clipboard
      .writeText(text)
      .then(notifyCopied)
      .catch(() => toast.error(msg("clipboard.copy_failed")));
  }, []);

  // A cell's single click copies its value, but the same spot double-clicked
  // opens the row reader — so the copy waits long enough to know no second
  // click is coming, and the double-click handler cancels it.
  const pendingCopy = React.useRef<number | null>(null);
  const cancelPendingCopy = React.useCallback(() => {
    if (pendingCopy.current !== null) {
      window.clearTimeout(pendingCopy.current);
      pendingCopy.current = null;
    }
  }, []);
  const scheduleCellCopy = React.useCallback(
    (text: string) => {
      cancelPendingCopy();
      pendingCopy.current = window.setTimeout(() => {
        pendingCopy.current = null;
        copyValue(text);
      }, 250);
    },
    [cancelPendingCopy, copyValue],
  );
  React.useEffect(() => cancelPendingCopy, [cancelPendingCopy]);

  const readerRow = readerIndex === null ? null : (filtered[readerIndex] ?? null);

  const stepReader = React.useCallback(
    (delta: number) => {
      setReaderIndex((cur) => {
        if (cur === null) return cur;
        const next = cur + delta;
        return next < 0 || next >= filtered.length ? cur : next;
      });
    },
    [filtered.length],
  );

  // The reader owns Arrow-key row navigation while it is open; focus lands on
  // its container so the keys work without clicking anything first.
  React.useEffect(() => {
    if (readerRow !== null) readerRef.current?.focus({ preventScroll: true });
  }, [readerRow]);

  const usageCount = optimizations?.length ?? 0;

  const segments: ReadonlyArray<{ value: DetailTab; label: string; icon: typeof Table2 }> = [
    { value: "rows", label: msg("datasets.detail.rows_title"), icon: Table2 },
    { value: "usage", label: msg("datasets.detail.tab.usage"), icon: Sparkle },
  ];

  return (
    <Dialog open={dataset !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        className="max-w-[min(72rem,94vw)] overflow-hidden p-0 sm:max-w-[min(72rem,94vw)]"
        aria-describedby={undefined}
        onEscapeKeyDown={(e) => {
          // Escape peels one layer: reader -> grid first, dialog second.
          if (readerIndex !== null) {
            e.preventDefault();
            setReaderIndex(null);
          }
        }}
      >
        <div className="flex max-h-[85vh] flex-col">
          <DialogHeader className="shrink-0 px-4 pb-4 pt-6 text-start sm:px-6">
            <DialogTitle className="truncate">{dataset?.name}</DialogTitle>
            {dataset && (
              <DialogDescription>
                {formatMsg("datasets.count.rows", { count: dataset.row_count })}
                {" · "}
                {formatMsg("datasets.count.columns", { count: dataset.column_count })}
              </DialogDescription>
            )}
          </DialogHeader>

          <div className="flex min-h-0 flex-1 flex-col">
            <div className="flex shrink-0 justify-center border-b border-border/40 px-4 pb-4 sm:px-6">
              <Segmented
                size="sm"
                label={msg("datasets.detail.view_aria")}
                value={tab}
                onChange={(value) => {
                  if (value !== tab) setTab(value);
                }}
                options={segments.map((seg) => {
                  const Icon = seg.icon;
                  return {
                    value: seg.value,
                    label: seg.label,
                    icon: <Icon className="size-3.5" aria-hidden="true" />,
                    trailing:
                      seg.value === "usage" && usageCount > 0 ? (
                        <CountPill>{usageCount}</CountPill>
                      ) : undefined,
                  };
                })}
              />
            </div>

            {tab === "rows" && readerRow !== null && readerIndex !== null ? (
              <div
                ref={readerRef}
                tabIndex={-1}
                role="group"
                aria-label={formatMsg("datasets.detail.row_reader.counter", {
                  index: readerIndex + 1,
                  total: filtered.length,
                })}
                className="flex min-h-0 flex-1 flex-col overflow-hidden px-4 py-4 focus-visible:outline-none sm:px-6"
                onKeyDown={(e) => {
                  // ↑/↓ walk the row list; ←/→ follow the prev/next carets,
                  // which mirror in RTL.
                  const step =
                    e.key === "ArrowUp"
                      ? -1
                      : e.key === "ArrowDown"
                        ? 1
                        : arrowPageStep(e, getActiveDir() === "rtl");
                  if (step === 0) return;
                  e.preventDefault();
                  stepReader(step);
                }}
              >
                <div className="mb-3 flex shrink-0 items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setReaderIndex(null)}
                    className="gap-1.5 text-muted-foreground hover:text-foreground"
                  >
                    <ArrowLeft className="size-4 rtl:rotate-180" />
                    {msg("datasets.detail.row_reader.back")}
                  </Button>
                  <div className="ms-auto flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => stepReader(-1)}
                      disabled={readerIndex === 0}
                      aria-label={msg("datasets.detail.row_reader.prev")}
                    >
                      <CaretLeft className="size-4 rtl:rotate-180" />
                    </Button>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {formatMsg("datasets.detail.row_reader.counter", {
                        index: readerIndex + 1,
                        total: filtered.length,
                      })}
                    </span>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => stepReader(1)}
                      disabled={readerIndex >= filtered.length - 1}
                      aria-label={msg("datasets.detail.row_reader.next")}
                    >
                      <CaretRight className="size-4 rtl:rotate-180" />
                    </Button>
                  </div>
                </div>
                <FadeIn key={readerIndex} className="min-h-0 flex-1 overflow-y-auto pe-1">
                  <dl className="flex flex-col gap-4 pb-2">
                    {columns.map((col) => {
                      const value = readerText(readerRow[col]);
                      const structured =
                        readerRow[col] != null && typeof readerRow[col] !== "string";
                      return (
                        <div key={col} className="group/field">
                          <div className="mb-1.5 flex items-center gap-2">
                            <dt className="text-[0.6875rem] font-semibold tracking-wide text-muted-foreground uppercase">
                              {col}
                            </dt>
                            <CopyButton
                              text={value}
                              ariaLabel={formatMsg("datasets.detail.row_reader.copy_field", {
                                column: col,
                              })}
                              onCopied={notifyCopied}
                              onCopyError={() => toast.error(msg("clipboard.copy_failed"))}
                              className="opacity-100 transition-opacity lg:opacity-0 lg:group-hover/field:opacity-100 lg:focus-visible:opacity-100"
                            />
                          </div>
                          <dd
                            dir="auto"
                            className={`rounded-lg border border-border/50 bg-muted/20 px-3.5 py-2.5 break-words whitespace-pre-wrap ${
                              structured
                                ? "font-mono text-xs leading-5 text-foreground/80"
                                : "text-[0.8125rem] leading-6 text-foreground/90"
                            }`}
                          >
                            {value || <span className="text-muted-foreground">—</span>}
                          </dd>
                        </div>
                      );
                    })}
                  </dl>
                </FadeIn>
              </div>
            ) : tab === "rows" ? (
              <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-4 py-4 sm:px-6">
                {rows === null ? (
                  <LoadingState
                    srLabel={msg("datasets.detail.loading")}
                    className="min-h-40 flex-1"
                  />
                ) : columns.length === 0 || allRows.length === 0 ? (
                  <div className="py-8">
                    <EmptyState
                      variant="list"
                      icon={Tray}
                      title={msg("datasets.detail.rows_empty")}
                    />
                  </div>
                ) : (
                  <FadeIn className="flex min-h-0 flex-1 flex-col">
                    <div className="mb-2 flex min-h-[44px] items-center justify-between gap-3 max-lg:[&_button]:size-[44px] lg:min-h-0">
                      <span className="min-w-0 truncate text-xs text-muted-foreground">
                        {msg("datasets.detail.row_reader.hint")}
                      </span>
                      <div className="flex items-center gap-2 shrink-0">
                        <ResetFiltersButton filters={colFilters} />
                        <ResetColumnsButton resize={colResize} />
                        <ExportTableMenu
                          iconOnly
                          disabled={filtered.length === 0}
                          getData={() => ({
                            columns,
                            rows: filtered.map((row) =>
                              Object.fromEntries(columns.map((col) => [col, row[col]])),
                            ),
                            filename: dataset?.name || "dataset",
                          })}
                        />
                      </div>
                    </div>
                    {filtered.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-border/60 py-8">
                        <EmptyState
                          variant="list"
                          icon={Tray}
                          title={msg("datasets.detail.rows_empty")}
                        />
                      </div>
                    ) : (
                      <div className="min-h-0 flex-1 overflow-y-auto rounded-2xl border border-border/40 bg-card/60">
                        {/* Per-column width floor: on narrow viewports the
                            fixed-layout table scrolls sideways (the Table
                            container is overflow-x-auto) instead of crushing
                            every column to an unreadable sliver. */}
                        <Table
                          className="table-fixed max-lg:[&_thead_th]:py-0 max-lg:[&_thead_th_div]:min-h-[44px] max-lg:[&_thead_button]:min-h-[44px] max-lg:[&_thead_button]:min-w-[44px]"
                          style={{ minWidth: `${columns.length * 6}rem` }}
                        >
                          <TableHeader>
                            <TableRow>
                              {columns.map((col) => (
                                <ColumnHeader
                                  key={col}
                                  label={col}
                                  sortKey={col}
                                  currentSort={sortKey}
                                  sortDir={sortDir}
                                  onSort={toggleSort}
                                  filterCol={col}
                                  filterOptions={filterOptions[col] ?? []}
                                  filters={colFilters.filters}
                                  onFilter={colFilters.setColumnFilter}
                                  openFilter={colFilters.openFilter}
                                  setOpenFilter={colFilters.setOpenFilter}
                                  width={colResize.widths[col]}
                                  onResize={colResize.setColumnWidth}
                                />
                              ))}
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {filtered.slice(0, RENDER_ROW_CAP).map((row, i) => (
                              <TableRow
                                key={i}
                                className="cursor-pointer transition-colors duration-150 hover:bg-muted/50"
                                onClick={() => {
                                  if (!window.matchMedia("(any-pointer: coarse)").matches) return;
                                  cancelPendingCopy();
                                  setReaderIndex(i);
                                }}
                                onDoubleClick={() => {
                                  cancelPendingCopy();
                                  setReaderIndex(i);
                                }}
                              >
                                {columns.map((col) => (
                                  <TableCell
                                    key={col}
                                    className="max-w-[280px] align-top text-xs text-foreground/80"
                                    style={
                                      colResize.widths[col]
                                        ? {
                                            width: colResize.widths[col],
                                            maxWidth: colResize.widths[col],
                                          }
                                        : undefined
                                    }
                                    title={cellText(row[col])}
                                    onClick={(e) => {
                                      if (e.detail !== 1) return;
                                      scheduleCellCopy(cellText(row[col]));
                                    }}
                                  >
                                    <span
                                      dir="auto"
                                      className="line-clamp-2 break-words whitespace-normal hover:underline underline-offset-2 decoration-foreground/40"
                                    >
                                      {cellText(row[col])}
                                    </span>
                                  </TableCell>
                                ))}
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    )}
                    {filtered.length > RENDER_ROW_CAP && (
                      <p className="mt-2 text-center text-[0.625rem] text-muted-foreground">
                        {formatMsg("datasets.detail.rows_more", {
                          shown: RENDER_ROW_CAP,
                          total: filtered.length,
                        })}
                      </p>
                    )}
                  </FadeIn>
                )}
              </div>
            ) : (
              <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6">
                {optimizations === null ? (
                  <LoadingState
                    srLabel={msg("datasets.detail.loading")}
                    className="min-h-40 flex-1"
                  />
                ) : optimizations.length === 0 ? (
                  <div className="py-8">
                    <EmptyState
                      variant="list"
                      icon={Sparkle}
                      title={msg("datasets.detail.used_by_empty")}
                    />
                  </div>
                ) : (
                  <FadeIn>
                    <ul className="divide-y divide-border/40 rounded-lg border border-border/50">
                      {optimizations.map((opt) => (
                        <li key={opt.optimization_id}>
                          <Link
                            href={`/optimizations/${opt.optimization_id}`}
                            className="group/link flex min-h-[44px] items-center gap-3 px-3 py-2.5 transition-colors hover:bg-accent/40"
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
                  </FadeIn>
                )}
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
