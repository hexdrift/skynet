"use client";

import { EmptyState } from "@/shared/ui/empty-state";
import { LoadingState } from "@/shared/ui/loading-state";
import * as React from "react";
import { Database } from "@/shared/ui/icons";
import { Dialog, DialogContent } from "@/shared/ui/primitives/dialog";
import { DialogTitleRow } from "@/shared/ui/dialog-title-row";
import { Badge } from "@/shared/ui/primitives/badge";
import {
  LIST_ROW_CLASS,
  LIST_ROW_ICON_CLASS,
  LIST_ROW_META_CLASS,
  LIST_ROW_META_DOT_CLASS,
  LIST_ROW_TITLE_CLASS,
} from "@/shared/ui/list-row";
import type { DatasetSummary } from "@/shared/lib/api";
import { formatMsg, msg } from "@/shared/lib/messages";
import { formatBytes, formatRelativeTime } from "@/shared/lib/formatters";
import { cn } from "@/shared/lib/utils";
import { useDatasets } from "../hooks/use-datasets";
import { SearchInput } from "@/shared/ui/search-input";

/**
 * Submit-wizard consumer picker: a searchable list of the caller's library
 * datasets (owned + shared-in). Selecting one hands its summary back via
 * ``onPick`` — the wizard then loads its rows and saved column mapping by
 * reference. The library is fetched lazily, only while the dialog is open.
 */
export function DatasetPickerDialog({
  open,
  onOpenChange,
  onPick,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPick: (dataset: DatasetSummary) => void;
}) {
  const { datasets, loading, error } = useDatasets(open);
  const [search, setSearch] = React.useState("");

  const query = search.trim().toLowerCase();
  const filtered = query ? datasets.filter((d) => d.name.toLowerCase().includes(query)) : datasets;

  const handlePick = (dataset: DatasetSummary) => {
    onPick(dataset);
    onOpenChange(false);
  };

  // Fade the scroll edges so a long library reads as scrollable: the top fade
  // appears once scrolled away from the start, the bottom fade while more rows
  // remain below. Recomputed on scroll and whenever the rendered set changes.
  const listRef = React.useRef<HTMLDivElement>(null);
  const [edges, setEdges] = React.useState({ top: false, bottom: false });
  const updateEdges = React.useCallback(() => {
    const el = listRef.current;
    if (!el) return;
    const remaining = el.scrollHeight - el.clientHeight - el.scrollTop;
    setEdges({ top: el.scrollTop > 1, bottom: remaining > 1 });
  }, []);
  React.useEffect(() => {
    updateEdges();
  }, [updateEdges, filtered.length, loading, error]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(32rem,92vw)] max-w-[min(32rem,92vw)] sm:max-w-lg">
        <DialogTitleRow
          title={msg("submit.dataset.library_picker_title")}
          description={msg("submit.dataset.library_picker_subtitle")}
        />

        <SearchInput
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={msg("submit.dataset.library_search")}
          aria-label={msg("submit.dataset.library_search")}
        />

        <div className="relative">
          <div
            ref={listRef}
            onScroll={updateEdges}
            className="max-h-[min(24rem,55vh)] space-y-1.5 overflow-y-auto px-0.5 py-1"
          >
            {loading ? (
              <LoadingState />
            ) : error ? (
              <p className="py-10 text-center text-sm text-muted-foreground">
                {msg("submit.dataset.library_error")}
              </p>
            ) : filtered.length === 0 ? (
              <EmptyState
                variant="list"
                title={
                  query
                    ? msg("submit.dataset.library_search_empty")
                    : msg("submit.dataset.library_empty")
                }
              />
            ) : (
              filtered.map((dataset) => {
                return (
                  <button
                    key={dataset.id}
                    type="button"
                    onClick={() => handlePick(dataset)}
                    className={cn(LIST_ROW_CLASS, "w-full")}
                  >
                    <span className={LIST_ROW_ICON_CLASS}>
                      <Database className="size-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className={LIST_ROW_TITLE_CLASS}>{dataset.name}</p>
                        {dataset.role !== "owner" && (
                          <Badge variant="secondary" size="sm">
                            {msg("datasets.shared_badge")}
                          </Badge>
                        )}
                      </div>
                      <p className={LIST_ROW_META_CLASS}>
                        {[
                          formatMsg("datasets.count.rows", { count: dataset.row_count }),
                          formatMsg("datasets.count.columns", { count: dataset.column_count }),
                          formatBytes(dataset.byte_size),
                          formatRelativeTime(dataset.updated_at),
                        ].map((part, i) => (
                          <React.Fragment key={i}>
                            {i > 0 && (
                              <span aria-hidden="true" className={LIST_ROW_META_DOT_CLASS}>
                                ·
                              </span>
                            )}
                            <span className="shrink-0 last:min-w-0 last:shrink last:truncate">
                              {part}
                            </span>
                          </React.Fragment>
                        ))}
                      </p>
                    </div>
                  </button>
                );
              })
            )}
          </div>
          <div
            aria-hidden="true"
            className={`pointer-events-none absolute inset-x-0 top-0 h-6 bg-gradient-to-b from-background to-transparent transition-opacity duration-200 ${edges.top ? "opacity-100" : "opacity-0"}`}
          />
          <div
            aria-hidden="true"
            className={`pointer-events-none absolute inset-x-0 bottom-0 h-6 bg-gradient-to-t from-background to-transparent transition-opacity duration-200 ${edges.bottom ? "opacity-100" : "opacity-0"}`}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
