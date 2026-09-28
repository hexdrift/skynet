"use client";

import { ProgressBar } from "@/shared/ui/progress-bar";
import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Table, TableBody, TableCell, TableHeader, TableRow } from "@/shared/ui/primitives/table";
import {
  ColumnHeader,
  ResetColumnsButton,
  ResetFiltersButton,
  useColumnFilters,
  useColumnResize,
} from "@/shared/ui/excel-filter";
import type { SortDir } from "@/shared/ui/excel-filter";
import { ExportTableMenu } from "@/shared/ui/export-table-menu";
import { formatElapsed, modelDisplayName } from "@/shared/lib";
import type { DashboardAnalyticsJob } from "@/shared/lib/api";
import { msg } from "@/shared/lib/messages";
import { getActiveIntlLocale } from "@/shared/lib/runtime-locale";
import { TERMS } from "@/shared/lib/terms";
import { cn } from "@/shared/lib/utils";
import type { OptimizerRow } from "../lib/transform-chart-data";

// Same density overrides as the optimizations table (JobsTab) so the two
// dashboards read as one table family.
const TABLE_CLASS =
  "table-stack no-copy-underline [&_thead_th]:ps-1 [&_thead_th]:pe-2 [&_thead_th]:py-2 [&_thead_th]:text-[0.6875rem] [&_thead_th_button]:px-1 [&_thead_svg]:size-2.5 [&_tbody_td]:px-1.5";
const ROW_CLASS =
  "group cursor-pointer border-border/30 transition-colors duration-150 hover:bg-muted/50 focus-visible:outline-none focus-visible:bg-muted/50";

function pointsText(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function pointsClass(value: number | null | undefined): string {
  if (value == null || value === 0) return "";
  return value > 0 ? "text-[var(--success)]" : "text-[var(--danger)]";
}

// Leaderboard rows carry the raw metric delta; ratio-scale metrics (|delta| <= 1)
// are shown in percentage points like every other improvement figure here.
function improvementPoints(delta: number | null | undefined): number | null {
  if (delta == null) return null;
  return Math.abs(delta) <= 1 ? delta * 100 : delta;
}

function compare(a: unknown, b: unknown): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b));
}

function useTableSort<K extends string>(initial: K, initialDir: SortDir = "desc") {
  const [sortKey, setSortKey] = useState<K>(initial);
  const [sortDir, setSortDir] = useState<SortDir>(initialDir);
  const toggleSort = (key: K) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };
  return { sortKey, sortDir, toggleSort };
}

function sortRows<T>(rows: T[], key: keyof T, dir: SortDir): T[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => sign * compare(a[key], b[key]));
}

function Toolbar({
  count,
  filters,
  resize,
  exportData,
}: {
  count: number;
  filters: { activeCount: number; clearAll: () => void };
  resize: ReturnType<typeof useColumnResize>;
  exportData: () => { columns: string[]; rows: Array<Record<string, unknown>>; filename: string };
}) {
  return (
    <div className="mb-3 flex min-h-[44px] items-center gap-2 max-lg:[&_button]:size-[44px] lg:min-h-0">
      <span className="text-xs text-muted-foreground tabular-nums">
        {count}
        {msg("auto.features.dashboard.components.jobstab.3")}
      </span>
      <ResetFiltersButton filters={filters} />
      <ResetColumnsButton resize={resize} />
      {count > 0 && <ExportTableMenu iconOnly className="ms-auto" getData={exportData} />}
    </div>
  );
}

function TableFrame({ minWidth, children }: { minWidth: string; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-border/40 bg-card/60">
      <Table style={{ minWidth }} className={TABLE_CLASS}>
        {children}
      </Table>
    </div>
  );
}

function EmptyRow({ colSpan }: { colSpan: number }) {
  return (
    <TableRow>
      <TableCell colSpan={colSpan} className="py-6 text-center text-sm text-muted-foreground">
        {msg("auto.shared.charts.chart.utils.literal.1")}
      </TableCell>
    </TableRow>
  );
}

type OptimizerKey = keyof OptimizerRow;

const OPTIMIZER_WIDTHS: Partial<Record<OptimizerKey, number>> = {
  name: 200,
  count: 80,
  share: 90,
  successRate: 110,
  avgImprovement: 120,
  avgRuntimeMinutes: 120,
};

/**
 * Optimizer comparison on the shared table stack: sortable/filterable
 * headers, resizable columns and export, matching the optimizations table.
 * Clicking a row narrows the dashboard to that optimizer.
 */
export function OptimizerTable({
  rows,
  onSelect,
}: {
  rows: OptimizerRow[];
  onSelect: (name: string) => void;
}) {
  const { sortKey, sortDir, toggleSort } = useTableSort<OptimizerKey>("count");
  const columnFilters = useColumnFilters();
  const resize = useColumnResize();
  const { filters, setColumnFilter, openFilter, setOpenFilter } = columnFilters;

  const nameOptions = useMemo(
    () =>
      rows
        .map((r) => ({ value: r.name, label: r.name }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    [rows],
  );

  const visible = useMemo(() => {
    const active = filters.name;
    const kept = active && active.size > 0 ? rows.filter((r) => active.has(r.name)) : rows;
    return sortRows(kept, sortKey, sortDir);
  }, [rows, filters, sortKey, sortDir]);

  const header = (label: string, key: OptimizerKey, filterable = false) => (
    <ColumnHeader
      label={label}
      sortKey={key}
      currentSort={sortKey}
      sortDir={sortDir}
      onSort={toggleSort}
      filterCol={filterable ? key : undefined}
      filterOptions={filterable ? nameOptions : undefined}
      filters={filterable ? filters : undefined}
      onFilter={filterable ? setColumnFilter : undefined}
      openFilter={openFilter}
      setOpenFilter={setOpenFilter}
      width={resize.widths[key] ?? OPTIMIZER_WIDTHS[key]}
      onResize={resize.setColumnWidth}
    />
  );

  const labels = {
    name: TERMS.optimizer,
    count: msg("dashboard.analytics.runs"),
    share: msg("dashboard.analytics.col_share"),
    successRate: msg("auto.features.dashboard.components.analyticstab.4"),
    avgImprovement: msg("auto.features.dashboard.components.analyticstab.8"),
    avgRuntimeMinutes: msg("auto.features.dashboard.components.analyticstab.11"),
  };

  return (
    <div>
      <Toolbar
        count={visible.length}
        filters={columnFilters}
        resize={resize}
        exportData={() => ({
          columns: [
            "optimizer",
            "runs",
            "share_pct",
            "success_rate_pct",
            "avg_improvement_pts",
            "avg_runtime_minutes",
          ],
          rows: visible.map((r) => ({
            optimizer: r.name,
            runs: r.count,
            share_pct: r.share,
            success_rate_pct: r.successRate,
            avg_improvement_pts: r.avgImprovement,
            avg_runtime_minutes: r.avgRuntimeMinutes,
          })),
          filename: "optimizers",
        })}
      />
      <TableFrame minWidth="560px">
        <TableHeader>
          <TableRow>
            {header(labels.name, "name", true)}
            {header(labels.count, "count")}
            {header(labels.share, "share")}
            {header(labels.successRate, "successRate")}
            {header(labels.avgImprovement, "avgImprovement")}
            {header(labels.avgRuntimeMinutes, "avgRuntimeMinutes")}
          </TableRow>
        </TableHeader>
        <TableBody className="transition-opacity duration-200">
          {visible.length === 0 && <EmptyRow colSpan={6} />}
          {visible.map((row, idx) => (
            <TableRow
              key={row.name}
              tabIndex={0}
              className={ROW_CLASS}
              style={{ animation: `fadeSlideIn 0.25s ease-out ${idx * 0.03}s both` }}
              onClick={() => onSelect(row.name)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(row.name);
                }
              }}
            >
              <TableCell className="px-2 font-medium" data-label={labels.name}>
                <span dir="ltr">{row.name}</span>
              </TableCell>
              <TableCell className="px-2 tabular-nums font-semibold" data-label={labels.count}>
                {row.count}
              </TableCell>
              <TableCell className="px-2" data-label={labels.share}>
                <div className="flex items-center gap-2" dir="ltr">
                  <ProgressBar value={row.share} color="var(--color-chart-2)" className="w-16" />
                  <span className="text-[0.6875rem] tabular-nums text-muted-foreground">
                    {Math.round(row.share)}%
                  </span>
                </div>
              </TableCell>
              <TableCell className="px-2 tabular-nums" data-label={labels.successRate}>
                {Math.round(row.successRate)}%
              </TableCell>
              <TableCell
                className={cn("px-2 tabular-nums font-medium", pointsClass(row.avgImprovement))}
                data-label={labels.avgImprovement}
                dir="ltr"
              >
                {pointsText(row.avgImprovement)}
              </TableCell>
              <TableCell
                className="px-2 tabular-nums"
                data-label={labels.avgRuntimeMinutes}
                dir="ltr"
              >
                {row.avgRuntimeMinutes == null ? "—" : formatElapsed(row.avgRuntimeMinutes * 60)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </TableFrame>
    </div>
  );
}

type LeaderRow = {
  optimization_id: string;
  rank: number;
  name: string;
  optimizer_name: string;
  model_name: string;
  improvement: number | null;
  elapsed_seconds: number | null;
  created_at: string | null;
};

type LeaderKey = keyof Omit<LeaderRow, "optimization_id">;

const LEADER_WIDTHS: Partial<Record<LeaderKey, number>> = {
  rank: 48,
  name: 200,
  optimizer_name: 120,
  model_name: 160,
  improvement: 110,
  elapsed_seconds: 100,
  created_at: 110,
};

/**
 * Best-improvement leaderboard on the shared table stack. Rank is fixed to
 * the server order (best first); sort and per-column filters apply on top.
 * Clicking a row opens the run.
 */
export function Leaderboard({
  jobs,
  onOpenJob,
}: {
  jobs: DashboardAnalyticsJob[];
  onOpenJob: (optimizationId: string) => void;
}) {
  const locale = getActiveIntlLocale();
  const { sortKey, sortDir, toggleSort } = useTableSort<LeaderKey>("rank", "asc");
  const columnFilters = useColumnFilters();
  const resize = useColumnResize();
  const { filters, setColumnFilter, openFilter, setOpenFilter } = columnFilters;

  const rows = useMemo<LeaderRow[]>(
    () =>
      jobs.map((job, i) => ({
        optimization_id: job.optimization_id,
        rank: i + 1,
        name: job.name || "",
        optimizer_name: job.optimizer_name ?? "",
        model_name: job.model_name ?? "",
        improvement: improvementPoints(job.metric_improvement),
        elapsed_seconds: job.elapsed_seconds ?? null,
        created_at: job.created_at ?? null,
      })),
    [jobs],
  );

  const options = useMemo(() => {
    const unique = (key: "optimizer_name" | "model_name", labelFn?: (v: string) => string) =>
      [...new Set(rows.map((r) => r[key]))]
        .filter(Boolean)
        .sort()
        .map((v) => ({ value: v, label: labelFn ? labelFn(v) : v }));
    return {
      optimizer_name: unique("optimizer_name"),
      model_name: unique("model_name", modelDisplayName),
    };
  }, [rows]);

  const visible = useMemo(() => {
    const kept = rows.filter((r) =>
      (["optimizer_name", "model_name"] as const).every((col) => {
        const active = filters[col];
        return !active || active.size === 0 || active.has(r[col]);
      }),
    );
    return sortRows(kept, sortKey, sortDir);
  }, [rows, filters, sortKey, sortDir]);

  const header = (label: string, key: LeaderKey, filterCol?: "optimizer_name" | "model_name") => (
    <ColumnHeader
      label={label}
      sortKey={key}
      currentSort={sortKey}
      sortDir={sortDir}
      onSort={toggleSort}
      filterCol={filterCol}
      filterOptions={filterCol ? options[filterCol] : undefined}
      filters={filterCol ? filters : undefined}
      onFilter={filterCol ? setColumnFilter : undefined}
      openFilter={openFilter}
      setOpenFilter={setOpenFilter}
      width={resize.widths[key] ?? LEADER_WIDTHS[key]}
      onResize={resize.setColumnWidth}
    />
  );

  const labels = {
    rank: "#",
    name: msg("dashboard.analytics.col_name"),
    optimizer_name: TERMS.optimizer,
    model_name: TERMS.model,
    improvement: TERMS.scoreImprovement,
    elapsed_seconds: msg("auto.features.dashboard.components.analyticstab.11"),
    created_at: msg("dashboard.analytics.col_date"),
  };

  return (
    <div>
      <Toolbar
        count={visible.length}
        filters={columnFilters}
        resize={resize}
        exportData={() => ({
          columns: [
            "rank",
            "optimization_id",
            "name",
            "optimizer",
            "model",
            "improvement_pts",
            "elapsed_seconds",
            "created_at",
          ],
          rows: visible.map((r) => ({
            rank: r.rank,
            optimization_id: r.optimization_id,
            name: r.name,
            optimizer: r.optimizer_name,
            model: r.model_name,
            improvement_pts: r.improvement,
            elapsed_seconds: r.elapsed_seconds,
            created_at: r.created_at,
          })),
          filename: "leaderboard",
        })}
      />
      <TableFrame minWidth="640px">
        <TableHeader>
          <TableRow>
            {header(labels.rank, "rank")}
            {header(labels.name, "name")}
            {header(labels.optimizer_name, "optimizer_name", "optimizer_name")}
            {header(labels.model_name, "model_name", "model_name")}
            {header(labels.improvement, "improvement")}
            {header(labels.elapsed_seconds, "elapsed_seconds")}
            {header(labels.created_at, "created_at")}
          </TableRow>
        </TableHeader>
        <TableBody className="transition-opacity duration-200">
          {visible.length === 0 && <EmptyRow colSpan={7} />}
          {visible.map((row, idx) => (
            <TableRow
              key={row.optimization_id}
              tabIndex={0}
              aria-label={msg("dashboard.analytics.open_job")}
              className={ROW_CLASS}
              style={{ animation: `fadeSlideIn 0.25s ease-out ${idx * 0.03}s both` }}
              onClick={() => onOpenJob(row.optimization_id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onOpenJob(row.optimization_id);
                }
              }}
            >
              <TableCell
                className="px-2 tabular-nums text-muted-foreground/70"
                data-label={labels.rank}
              >
                {row.rank}
              </TableCell>
              <TableCell
                className="max-w-[16rem] truncate px-2 font-medium"
                title={row.name || undefined}
                data-label={labels.name}
              >
                {row.name || <span dir="ltr">{row.optimization_id.slice(0, 8)}…</span>}
              </TableCell>
              <TableCell className="px-2" data-label={labels.optimizer_name} dir="ltr">
                {row.optimizer_name || "—"}
              </TableCell>
              <TableCell
                className="max-w-[12rem] truncate px-2 font-mono text-xs"
                dir="ltr"
                title={row.model_name || undefined}
                data-label={labels.model_name}
              >
                {row.model_name ? modelDisplayName(row.model_name) : "—"}
              </TableCell>
              <TableCell
                className={cn("px-2 tabular-nums font-semibold", pointsClass(row.improvement))}
                dir="ltr"
                data-label={labels.improvement}
              >
                {pointsText(row.improvement)}
              </TableCell>
              <TableCell
                className="px-2 tabular-nums"
                dir="ltr"
                data-label={labels.elapsed_seconds}
              >
                {row.elapsed_seconds == null ? "—" : formatElapsed(row.elapsed_seconds)}
              </TableCell>
              <TableCell
                className="whitespace-nowrap px-2 tabular-nums"
                data-label={labels.created_at}
              >
                {row.created_at
                  ? new Date(row.created_at).toLocaleDateString(locale, {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })
                  : "—"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </TableFrame>
    </div>
  );
}
