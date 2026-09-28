"use client";

import { useCallback, useState } from "react";
import { nextSort, type SortDir, type SortState } from "@/shared/lib/table-sort";

/**
 * Sort state for a table whose headers cycle ascending, descending, then back
 * to the table's original order (see {@link nextSort}).
 *
 * Args:
 *     initialKey: Column the table is ordered by before any click; an empty
 *         string (or any key no header uses) means the data's own order.
 *     initialDir: Direction of that original order.
 */
export function useTableSort<K extends string>(initialKey: K, initialDir: SortDir = "asc") {
  const [sort, setSort] = useState<SortState<K>>({ key: initialKey, dir: initialDir });
  const toggleSort = useCallback(
    (key: K) => setSort((current) => nextSort(current, key, { key: initialKey, dir: initialDir })),
    [initialKey, initialDir],
  );
  const resetSort = useCallback(
    () => setSort({ key: initialKey, dir: initialDir }),
    [initialKey, initialDir],
  );
  return { sortKey: sort.key, sortDir: sort.dir, toggleSort, resetSort };
}
