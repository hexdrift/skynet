import Link from "next/link";
import { toast } from "react-toastify";
import { ChevronLeft, ChevronRight, ExternalLink, Plus, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import {
  Tooltip as UiTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  ColumnHeader,
  ResetColumnsButton,
  useColumnResize,
  type SortDir,
} from "@/shared/ui/excel-filter";
import { formatDate, formatElapsed, formatId, formatRelativeTime } from "@/shared/lib";
import { ACTIVE_STATUSES } from "@/shared/constants/job-status";
import type { OptimizationSummaryResponse, PaginatedJobsResponse } from "@/shared/types/api";
import { msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";
import { FETCH_PAGE_SIZE } from "../constants";
import { formatScore, statusBadge, typeBadge } from "../lib/status-badges";
import type { DeleteTarget } from "../hooks/use-bulk-delete";

type ColResize = ReturnType<typeof useColumnResize>;

type JobsTabProps = {
  data: PaginatedJobsResponse | null;
  loading: boolean;
  error: string | null;
  filteredItems: OptimizationSummaryResponse[];
  activeCount: number;
  clearAllFilters: () => void;
  colResize: ColResize;
  sortKey: string;
  sortDir: SortDir;
  toggleSort: (key: string) => void;
  filters: Record<string, Set<string>>;
  setColumnFilter: (col: string, values: Set<string>) => void;
  openFilter: string | null;
  setOpenFilter: (col: string | null) => void;
  filterOptions: Record<string, { value: string; label: string }[]>;
  isAdmin: boolean;
  selectedIds: Set<string>;
  toggleRowSelected: (id: string) => void;
  selectablePageIds: string[];
  pageAllSelected: boolean;
  pageSomeSelected: boolean;
  togglePageSelection: () => void;
  pageOffset: number;
  setPageOffset: React.Dispatch<React.SetStateAction<number>>;
  onOpenJob: (id: string) => void;
  onRequestDelete: (target: { id: string; status: string }) => void;
};

export function JobsTab({
  data,
  loading,
  error,
  filteredItems,
  activeCount,
  clearAllFilters,
  colResize,
  sortKey,
  sortDir,
  toggleSort,
  filters,
  setColumnFilter,
  openFilter,
  setOpenFilter,
  filterOptions,
  isAdmin,
  selectedIds,
  toggleRowSelected,
  selectablePageIds,
  pageAllSelected,
  pageSomeSelected,
  togglePageSelection,
  pageOffset,
  setPageOffset,
  onOpenJob,
  onRequestDelete,
}: JobsTabProps) {
  return (
    <Card className="border-border/60">
      <CardContent className="pt-5">
        <div className="flex items-center gap-2 mb-3">
          {activeCount > 0 && (
            <>
              <Badge variant="secondary" className="text-xs">
                {activeCount} סינונים פעילים
              </Badge>
              <button
                type="button"
                onClick={clearAllFilters}
                className="text-xs text-muted-foreground hover:text-foreground cursor-pointer"
              >
                נקה הכל
              </button>
            </>
          )}
          <ResetColumnsButton resize={colResize} />
          {filteredItems.length > 0 && (
            <span className="text-[0.6875rem] text-muted-foreground tabular-nums ms-auto">
              {filteredItems.length} תוצאות
            </span>
          )}
        </div>

        {error && (
          <div className="rounded-lg border border-[var(--danger-border)] bg-[var(--danger-dim)] py-3 px-4 text-sm text-[var(--danger)] mb-4">
            {error}
          </div>
        )}

        {!loading && data && filteredItems.length === 0 && data.total === 0 && (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <p className="text-base font-medium">לא נמצאו {TERMS.optimizationPlural}</p>
            <p className="text-sm text-muted-foreground max-w-xs">
              העלה {TERMS.dataset}, הגדר {TERMS.signature} ו{TERMS.metric}, והמערכת תשפר אותו
              אוטומטית
            </p>
            <Button asChild className="group mt-2 gap-2">
              <Link href="/submit">
                <Plus className="size-4 transition-transform duration-200 group-hover:rotate-90" />
                {TERMS.notificationNewOpt}
              </Link>
            </Button>
          </div>
        )}

        {filteredItems.length > 0 && (
          <div className="overflow-x-auto" data-tutorial="dashboard-table">
            <Table style={{ minWidth: "800px" }}>
              <thead className="bg-muted/30 [&_tr]:border-b [&_tr]:border-border/50">
                <tr>
                  <th className="w-10 px-3">
                    <input
                      type="checkbox"
                      aria-label="בחר הכל בעמוד"
                      className="size-4 cursor-pointer accent-primary"
                      checked={pageAllSelected}
                      ref={(el) => {
                        if (el) el.indeterminate = pageSomeSelected;
                      }}
                      disabled={selectablePageIds.length === 0}
                      onChange={togglePageSelection}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </th>
                  <ColumnHeader
                    label={`מזהה ${TERMS.optimization}`}
                    sortKey="optimization_id"
                    currentSort={sortKey}
                    sortDir={sortDir}
                    onSort={toggleSort}
                    filterCol="optimization_id"
                    filterOptions={filterOptions.optimization_id}
                    filters={filters}
                    onFilter={setColumnFilter}
                    openFilter={openFilter}
                    setOpenFilter={setOpenFilter}
                    width={colResize.widths["optimization_id"]}
                    onResize={colResize.setColumnWidth}
                  />
                  <ColumnHeader
                    label="סוג"
                    sortKey="optimization_type"
                    currentSort={sortKey}
                    sortDir={sortDir}
                    onSort={toggleSort}
                    filterCol="optimization_type"
                    filterOptions={filterOptions.optimization_type}
                    filters={filters}
                    onFilter={setColumnFilter}
                    openFilter={openFilter}
                    setOpenFilter={setOpenFilter}
                    width={colResize.widths["optimization_type"]}
                    onResize={colResize.setColumnWidth}
                  />
                  <ColumnHeader
                    label="סטטוס"
                    sortKey="status"
                    currentSort={sortKey}
                    sortDir={sortDir}
                    onSort={toggleSort}
                    filterCol="status"
                    filterOptions={filterOptions.status}
                    filters={filters}
                    onFilter={setColumnFilter}
                    openFilter={openFilter}
                    setOpenFilter={setOpenFilter}
                    width={colResize.widths["status"]}
                    onResize={colResize.setColumnWidth}
                  />
                  <ColumnHeader
                    label="מודול"
                    sortKey="module_name"
                    currentSort={sortKey}
                    sortDir={sortDir}
                    onSort={toggleSort}
                    filterCol="module_name"
                    filterOptions={filterOptions.module_name}
                    filters={filters}
                    onFilter={setColumnFilter}
                    openFilter={openFilter}
                    setOpenFilter={setOpenFilter}
                    width={colResize.widths["module_name"]}
                    onResize={colResize.setColumnWidth}
                  />
                  <ColumnHeader
                    label={TERMS.optimizer}
                    sortKey="optimizer_name"
                    currentSort={sortKey}
                    sortDir={sortDir}
                    onSort={toggleSort}
                    filterCol="optimizer_name"
                    filterOptions={filterOptions.optimizer_name}
                    filters={filters}
                    onFilter={setColumnFilter}
                    openFilter={openFilter}
                    setOpenFilter={setOpenFilter}
                    width={colResize.widths["optimizer_name"]}
                    onResize={colResize.setColumnWidth}
                  />
                  <ColumnHeader
                    label="שורות"
                    sortKey="dataset_rows"
                    currentSort={sortKey}
                    sortDir={sortDir}
                    onSort={toggleSort}
                    width={colResize.widths["dataset_rows"]}
                    onResize={colResize.setColumnWidth}
                  />
                  <ColumnHeader
                    label="נוצר"
                    sortKey="created_at"
                    currentSort={sortKey}
                    sortDir={sortDir}
                    onSort={toggleSort}
                    width={colResize.widths["created_at"]}
                    onResize={colResize.setColumnWidth}
                  />
                  <ColumnHeader
                    label="זמן"
                    sortKey="elapsed_seconds"
                    currentSort={sortKey}
                    sortDir={sortDir}
                    onSort={toggleSort}
                    width={colResize.widths["elapsed_seconds"]}
                    onResize={colResize.setColumnWidth}
                  />
                  <ColumnHeader
                    label="ציון"
                    sortKey="optimized_test_metric"
                    currentSort={sortKey}
                    sortDir={sortDir}
                    onSort={toggleSort}
                    width={colResize.widths["optimized_test_metric"]}
                    onResize={colResize.setColumnWidth}
                  />
                  <th className="w-16" />
                </tr>
              </thead>
              <TableBody className="transition-opacity duration-200">
                {filteredItems.map((job, idx) => {
                  const isSelected = selectedIds.has(job.optimization_id);
                  return (
                    <TableRow
                      key={job.optimization_id}
                      data-selected={isSelected}
                      className="group border-border/40 transition-colors duration-150 data-[selected=true]:bg-primary/10 hover:bg-accent/30 data-[selected=true]:hover:bg-primary/15 cursor-pointer [&_td:first-child]:cursor-default [&_td:last-child]:cursor-default focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
                      style={{
                        animation: `fadeSlideIn 0.25s ease-out ${idx * 0.03}s both`,
                      }}
                      onClick={(e) => {
                        const td = (e.target as HTMLElement).closest("td");
                        if (!td) return;
                        const parent = td.parentElement;
                        if (td === parent?.lastElementChild) return;
                        if (td === parent?.firstElementChild) return;
                        const text = td.textContent?.trim();
                        if (text) {
                          navigator.clipboard.writeText(text);
                          toast.success(msg("clipboard.copied"));
                        }
                      }}
                      data-tutorial="job-link"
                    >
                      <TableCell className="w-10 px-3">
                        <input
                          type="checkbox"
                          aria-label={`בחר ${TERMS.optimization} ${job.optimization_id}`}
                          className="size-4 cursor-pointer accent-primary"
                          checked={isSelected}
                          onClick={(e) => e.stopPropagation()}
                          onChange={() => toggleRowSelected(job.optimization_id)}
                        />
                      </TableCell>
                      <TableCell
                        className="max-w-[180px] truncate overflow-hidden"
                        title={job.optimization_id}
                      >
                        <div className="flex items-center gap-1.5">
                          {ACTIVE_STATUSES.has(job.status) && (
                            <span className="relative flex size-2 shrink-0">
                              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--warning)]/60" />
                              <span className="relative inline-flex rounded-full size-2 bg-[var(--warning)]" />
                            </span>
                          )}
                          <span className="font-mono text-xs text-primary truncate">
                            {formatId(job.optimization_id)}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="truncate overflow-hidden">
                        {typeBadge(job.optimization_type)}
                      </TableCell>
                      <TableCell className="truncate overflow-hidden">
                        {statusBadge(job.status)}
                      </TableCell>
                      <TableCell
                        className="text-sm truncate overflow-hidden"
                        title={job.module_name ?? ""}
                      >
                        {job.module_name ?? "-"}
                      </TableCell>
                      <TableCell
                        className="text-sm truncate overflow-hidden"
                        title={job.optimizer_name ?? ""}
                      >
                        {job.optimizer_name ?? "-"}
                      </TableCell>
                      <TableCell
                        className="text-sm tabular-nums truncate overflow-hidden"
                        title={String(job.dataset_rows ?? "")}
                      >
                        {job.dataset_rows ?? "-"}
                      </TableCell>
                      <TableCell
                        className="text-xs text-muted-foreground truncate overflow-hidden"
                        title={formatDate(job.created_at)}
                      >
                        {formatRelativeTime(job.created_at)}
                      </TableCell>
                      <TableCell
                        className="text-xs tabular-nums truncate overflow-hidden"
                        title={formatElapsed(job.elapsed_seconds) ?? ""}
                      >
                        {formatElapsed(job.elapsed_seconds)}
                      </TableCell>
                      <TableCell className="truncate overflow-hidden">{formatScore(job)}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-0.5">
                          <TooltipProvider>
                            <UiTooltip>
                              <TooltipTrigger asChild>
                                <button
                                  type="button"
                                  onClick={() => onOpenJob(job.optimization_id)}
                                  className="p-1 rounded hover:bg-accent/60 text-muted-foreground hover:text-foreground transition-all cursor-pointer"
                                  aria-label={`פרטי ${TERMS.optimization}`}
                                >
                                  <ExternalLink className="size-3.5" />
                                </button>
                              </TooltipTrigger>
                              <TooltipContent side="bottom">פרטים</TooltipContent>
                            </UiTooltip>
                          </TooltipProvider>
                          {isAdmin && (
                            <TooltipProvider>
                              <UiTooltip>
                                <TooltipTrigger asChild>
                                  <button
                                    type="button"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      onRequestDelete({
                                        id: job.optimization_id,
                                        status: job.status,
                                      });
                                    }}
                                    className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-all cursor-pointer"
                                    aria-label={`מחק ${TERMS.optimization}`}
                                  >
                                    <Trash2 className="size-3.5" />
                                  </button>
                                </TooltipTrigger>
                                <TooltipContent side="bottom">מחיקה</TooltipContent>
                              </UiTooltip>
                            </TooltipProvider>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}

        {data && data.total > FETCH_PAGE_SIZE && (
          <div className="flex items-center justify-center gap-3 pt-5 border-t border-border/50 mt-4">
            <Button
              variant="outline"
              size="sm"
              disabled={pageOffset === 0 || loading}
              onClick={() => setPageOffset(Math.max(0, pageOffset - FETCH_PAGE_SIZE))}
              className="gap-1"
            >
              <ChevronRight className="size-3.5" />
              הקודם
            </Button>
            <span className="text-sm text-muted-foreground tabular-nums px-3 py-1 rounded-md bg-muted/50">
              {Math.floor(pageOffset / FETCH_PAGE_SIZE) + 1} /{" "}
              {Math.max(1, Math.ceil(data.total / FETCH_PAGE_SIZE))}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={pageOffset + FETCH_PAGE_SIZE >= data.total || loading}
              onClick={() => setPageOffset(pageOffset + FETCH_PAGE_SIZE)}
              className="gap-1"
            >
              הבא
              <ChevronLeft className="size-3.5" />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export type { DeleteTarget };
