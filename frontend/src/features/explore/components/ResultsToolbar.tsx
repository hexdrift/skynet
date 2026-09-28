"use client";

import * as React from "react";
import { ArrowsDownUp } from "@/shared/ui/icons";
import { msg, formatMsg } from "@/shared/lib/messages";
import { Segmented } from "@/shared/ui/segmented";
import type { SearchSort } from "@/shared/lib/api";

interface ResultsToolbarProps {
  total: number;
  sort: SearchSort;
  onSortChange: (sort: SearchSort) => void;
  /** Relevance is only offered when there's a query to rank against. */
  hasQuery: boolean;
}

/**
 * Thin bar above the results list: a live result count anchored to the
 * leading edge and the sort control on the trailing edge.
 */
export function ResultsToolbar({ total, sort, onSortChange, hasQuery }: ResultsToolbarProps) {
  const countLabel =
    total === 1
      ? msg("explore.results.count.one")
      : formatMsg("explore.results.count.many", { n: total });
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-1 pb-2">
      <span className="min-w-0 text-xs text-muted-foreground tabular-nums">{countLabel}</span>
      <SortControl sort={sort} onChange={onSortChange} hasQuery={hasQuery} />
    </div>
  );
}

const SORT_OPTIONS = [
  {
    value: "relevance" as const,
    label: () => msg("explore.sort.relevance"),
    tip: () => msg("explore.sort.relevance.tip"),
    queryOnly: true,
  },
  {
    value: "recent" as const,
    label: () => msg("explore.sort.recent"),
    tip: () => msg("explore.sort.recent.tip"),
    queryOnly: false,
  },
  {
    value: "oldest" as const,
    label: () => msg("explore.sort.oldest"),
    tip: () => msg("explore.sort.oldest.tip"),
    queryOnly: false,
  },
];

function SortControl({
  sort,
  onChange,
  hasQuery,
}: {
  sort: SearchSort;
  onChange: (sort: SearchSort) => void;
  hasQuery: boolean;
}) {
  const options = SORT_OPTIONS.filter((o) => !o.queryOnly || hasQuery);
  return (
    <div className="inline-flex items-center gap-1.5">
      <ArrowsDownUp className="size-3 text-foreground/35" aria-hidden="true" />
      <Segmented<SearchSort>
        size="sm"
        label={msg("explore.sort.aria")}
        value={sort}
        onChange={(next) => {
          if (next !== sort) onChange(next);
        }}
        options={options.map((o) => ({ value: o.value, label: o.label(), tip: o.tip() }))}
      />
    </div>
  );
}
