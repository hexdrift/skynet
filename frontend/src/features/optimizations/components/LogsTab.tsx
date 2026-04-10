"use client";

/**
 * Logs tab — filterable/sortable table of optimization log entries.
 *
 * Extracted from app/optimizations/[id]/page.tsx. Keeps its own filter and
 * sort state isolated from the heavy parent so re-renders stay local.
 */

import { useMemo, useState } from "react";
import { toast } from "react-toastify";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHeader, TableRow } from "@/components/ui/table";
import {
  ColumnHeader,
  useColumnFilters,
  useColumnResize,
  ResetColumnsButton,
  type SortDir,
} from "@/components/excel-filter";
import { FadeIn } from "@/components/motion";
import { msg } from "@/features/shared/messages";
import type { OptimizationLogEntry } from "@/lib/types";
import { formatLogTimestamp, logTimeBucket } from "../lib/formatters";

export function LogsTab({
  logs,
  pairNames,
  live,
}: {
  logs: OptimizationLogEntry[];
  pairNames?: Record<number, string>;
  live?: boolean;
}) {
  const showPairCol = !!pairNames && Object.keys(pairNames).length > 0;
  const logFilters = useColumnFilters();
  const logResize = useColumnResize();
  const [messageSearch, setMessageSearch] = useState("");
  const [sortKey, setSortKey] = useState<string>("timestamp");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const toggleSort = (key: string) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const filtered = useMemo(() => {
    const q = messageSearch.trim().toLowerCase();
    let result = logs.filter((l) => {
      if (q && !l.message.toLowerCase().includes(q)) return false;
      for (const [col, allowed] of Object.entries(logFilters.filters)) {
        if (allowed.size === 0) continue;
        const val =
          col === "timestamp"
            ? logTimeBucket(l.timestamp)
            : col === "pair_index"
              ? l.pair_index != null
                ? String(l.pair_index)
                : "—"
              : String((l as unknown as Record<string, unknown>)[col] ?? "");
        if (!allowed.has(val)) return false;
      }
      return true;
    });
    result = [...result].sort((a, b) => {
      const av = String((a as unknown as Record<string, unknown>)[sortKey] ?? "");
      const bv = String((b as unknown as Record<string, unknown>)[sortKey] ?? "");
      const cmp = av.localeCompare(bv, "he", { numeric: true });
      return sortDir === "asc" ? cmp : -cmp;
    });
    return result;
  }, [logs, logFilters.filters, sortKey, sortDir, messageSearch]);

  const filterOptions = useMemo(() => {
    const unique = (key: string) => {
      const vals = [
        ...new Set(logs.map((l) => String((l as unknown as Record<string, unknown>)[key] ?? ""))),
      ]
        .filter(Boolean)
        .sort();
      return vals.map((v) => ({ value: v, label: v }));
    };
    const timestampBuckets = [...new Set(logs.map((l) => logTimeBucket(l.timestamp)))]
      .filter(Boolean)
      .sort()
      .map((v) => ({ value: v, label: v }));
    const pairOpts = showPairCol
      ? [...new Set(logs.map((l) => (l.pair_index != null ? String(l.pair_index) : "—")))]
          .sort()
          .map((v) => ({
            value: v,
            label: v === "—" ? "כללי" : (pairNames?.[parseInt(v)] ?? `ריצה ${parseInt(v) + 1}`),
          }))
      : [];
    return {
      level: unique("level"),
      logger: unique("logger"),
      timestamp: timestampBuckets,
      pair_index: pairOpts,
    };
  }, [logs, showPairCol, pairNames]);

  return (
    <div className="mt-4">
      <FadeIn>
        <div className="flex items-center justify-between gap-3 mb-4">
          <p className="text-sm text-muted-foreground">
            {live ? "" : "לוגים מפורטים מתהליך האופטימיזציה — סננו לפי עמודה או חפשו בתוכן."}
          </p>
          <span className="text-xs text-muted-foreground shrink-0">{filtered.length} רשומות</span>
        </div>
      </FadeIn>
      <div className="flex items-center gap-3 mb-5">
        <Input
          type="text"
          value={messageSearch}
          onChange={(e) => setMessageSearch(e.target.value)}
          placeholder="Search log messages..."
          aria-label="Search log messages"
          dir="ltr"
          className="text-left w-full"
        />
        <ResetColumnsButton resize={logResize} />
      </div>
      {filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground py-8 text-center">אין לוגים</p>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="max-h-[600px] overflow-auto">
              <Table className={"table-fixed w-full"}>
                <colgroup>
                  {showPairCol && (
                    <col style={{ width: logResize.widths["pair_index"] ?? "12%" }} />
                  )}
                  <col
                    style={{
                      width: logResize.widths["timestamp"] ?? (showPairCol ? "13%" : "15%"),
                    }}
                  />
                  <col
                    style={{ width: logResize.widths["level"] ?? (showPairCol ? "10%" : "12%") }}
                  />
                  <col
                    style={{ width: logResize.widths["logger"] ?? (showPairCol ? "14%" : "17%") }}
                  />
                  <col />
                </colgroup>
                <TableHeader>
                  <TableRow>
                    {showPairCol && (
                      <ColumnHeader
                        label="ריצה"
                        sortKey="pair_index"
                        currentSort={sortKey}
                        sortDir={sortDir}
                        onSort={toggleSort}
                        filterCol="pair_index"
                        filterOptions={filterOptions.pair_index}
                        filters={logFilters.filters}
                        onFilter={logFilters.setColumnFilter}
                        openFilter={logFilters.openFilter}
                        setOpenFilter={logFilters.setOpenFilter}
                        width={logResize.widths["pair_index"]}
                        onResize={logResize.setColumnWidth}
                      />
                    )}
                    <ColumnHeader
                      label="זמן"
                      sortKey="timestamp"
                      currentSort={sortKey}
                      sortDir={sortDir}
                      onSort={toggleSort}
                      filterCol="timestamp"
                      filterOptions={filterOptions.timestamp}
                      filters={logFilters.filters}
                      onFilter={logFilters.setColumnFilter}
                      openFilter={logFilters.openFilter}
                      setOpenFilter={logFilters.setOpenFilter}
                      width={logResize.widths["timestamp"]}
                      onResize={logResize.setColumnWidth}
                    />
                    <ColumnHeader
                      label="רמה"
                      sortKey="level"
                      currentSort={sortKey}
                      sortDir={sortDir}
                      onSort={toggleSort}
                      filterCol="level"
                      filterOptions={filterOptions.level}
                      filters={logFilters.filters}
                      onFilter={logFilters.setColumnFilter}
                      openFilter={logFilters.openFilter}
                      setOpenFilter={logFilters.setOpenFilter}
                      width={logResize.widths["level"]}
                      onResize={logResize.setColumnWidth}
                    />
                    <ColumnHeader
                      label="לוגר"
                      sortKey="logger"
                      currentSort={sortKey}
                      sortDir={sortDir}
                      onSort={toggleSort}
                      filterCol="logger"
                      filterOptions={filterOptions.logger}
                      filters={logFilters.filters}
                      onFilter={logFilters.setColumnFilter}
                      openFilter={logFilters.openFilter}
                      setOpenFilter={logFilters.setOpenFilter}
                      width={logResize.widths["logger"]}
                      onResize={logResize.setColumnWidth}
                    />
                    <ColumnHeader
                      label="הודעה"
                      sortKey="message"
                      currentSort={sortKey}
                      sortDir={sortDir}
                      onSort={toggleSort}
                      width={logResize.widths["message"]}
                      onResize={logResize.setColumnWidth}
                    />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.slice(0, 300).map((log, i) => (
                    <TableRow
                      key={i}
                      className="cursor-pointer"
                      onClick={(e) => {
                        const td = (e.target as HTMLElement).closest("td");
                        if (!td) return;
                        const text = td.textContent?.trim();
                        if (text) {
                          navigator.clipboard.writeText(text);
                          toast.success(msg("clipboard.copied"));
                        }
                      }}
                    >
                      {showPairCol && (
                        <TableCell
                          className="text-xs font-mono truncate overflow-hidden"
                          style={
                            logResize.widths["pair_index"]
                              ? {
                                  width: logResize.widths["pair_index"],
                                  maxWidth: logResize.widths["pair_index"],
                                }
                              : undefined
                          }
                        >
                          {log.pair_index != null ? (
                            <Badge variant="secondary" className="text-[9px] font-mono">
                              {pairNames?.[log.pair_index] ?? `ריצה ${log.pair_index + 1}`}
                            </Badge>
                          ) : (
                            <span className="text-muted-foreground/40">—</span>
                          )}
                        </TableCell>
                      )}
                      <TableCell
                        className="text-xs font-mono text-muted-foreground truncate overflow-hidden"
                        style={
                          logResize.widths["timestamp"]
                            ? {
                                width: logResize.widths["timestamp"],
                                maxWidth: logResize.widths["timestamp"],
                              }
                            : undefined
                        }
                        dir="ltr"
                      >
                        {formatLogTimestamp(log.timestamp)}
                      </TableCell>
                      <TableCell
                        className="truncate overflow-hidden"
                        style={
                          logResize.widths["level"]
                            ? {
                                width: logResize.widths["level"],
                                maxWidth: logResize.widths["level"],
                              }
                            : undefined
                        }
                      >
                        <Badge
                          variant={
                            log.level === "ERROR"
                              ? "destructive"
                              : log.level === "WARNING"
                                ? "outline"
                                : "secondary"
                          }
                          className="text-[10px] font-mono"
                        >
                          {log.level}
                        </Badge>
                      </TableCell>
                      <TableCell
                        className="text-xs font-mono text-muted-foreground truncate overflow-hidden"
                        style={
                          logResize.widths["logger"]
                            ? {
                                width: logResize.widths["logger"],
                                maxWidth: logResize.widths["logger"],
                              }
                            : undefined
                        }
                        title={log.logger}
                      >
                        {log.logger}
                      </TableCell>
                      <TableCell
                        className="text-xs font-mono whitespace-pre-wrap break-all overflow-hidden hover:underline"
                        style={
                          logResize.widths["message"]
                            ? {
                                width: logResize.widths["message"],
                                maxWidth: logResize.widths["message"],
                              }
                            : undefined
                        }
                        title={log.message}
                      >
                        {log.message}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
                {filtered.length > 300 && (
                  <tfoot>
                    <tr>
                      <td
                        colSpan={showPairCol ? 5 : 4}
                        className="text-center py-3 text-[10px] text-muted-foreground"
                      >
                        מוצגות 300 מתוך {filtered.length} רשומות
                      </td>
                    </tr>
                  </tfoot>
                )}
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
