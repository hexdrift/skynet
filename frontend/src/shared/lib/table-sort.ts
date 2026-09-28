/**
 * Click cycle shared by every sortable table header.
 *
 * Kept import-free so the Node unit test can load it directly; the React
 * binding lives in `shared/hooks/use-table-sort.ts`.
 */

export type SortDir = "asc" | "desc";

export interface SortState<K extends string> {
  key: K;
  dir: SortDir;
}

/**
 * Advance a header click: a new column sorts ascending, a second click turns
 * it descending, and a third returns the table to its original order.
 *
 * Args:
 *     current: The sort in effect now.
 *     key: The column header that was clicked.
 *     initial: The table's original order, which the third click restores.
 */
export function nextSort<K extends string>(
  current: SortState<K>,
  key: K,
  initial: SortState<K>,
): SortState<K> {
  if (current.key !== key) return { key, dir: "asc" };
  if (current.dir === "asc") return { key, dir: "desc" };
  // The original order already sorts this column descending, so "restoring" it
  // would do nothing; flip instead so every click visibly changes the table.
  if (initial.key === key && initial.dir === "desc") return { key, dir: "asc" };
  return initial;
}
