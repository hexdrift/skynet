/**
 * Pure helpers behind the explore filter pickers' value lists.
 *
 * A filter dimension can hold thousands of distinct values (every model id
 * ever optimized against), so a picker never lists one in full. Each
 * dimension shows its busiest values up to a small cap, ranked by the number
 * of runs each would leave alongside the other active filters, and reports
 * how many distinct values exist so the user knows to search for the rest.
 * The backend does this ranking for the real corpora; these helpers apply the
 * same contract client-side to the tutorial's demo points, which have no
 * backend scope to ask.
 */

import type { CorpusFacets, FacetOption, PublicDashboardPoint } from "@/shared/lib/api";

/** Values shown per dimension before the user has to search or ask for more. */
export const FACET_LIMIT = 8;
/** Values added per "Show more"; the backend caps a single list at `FACET_LIMIT_MAX`. */
export const FACET_LIMIT_STEP = 24;
export const FACET_LIMIT_MAX = 50;

/**
 * Count occurrences of each non-empty value, busiest first (ties by value).
 */
export function countOccurrences(values: ReadonlyArray<string | null | undefined>): FacetOption[] {
  const counts = new Map<string, number>();
  for (const v of values) {
    if (typeof v !== "string" || v.length === 0) continue;
    counts.set(v, (counts.get(v) ?? 0) + 1);
  }
  return Array.from(counts, ([value, count]) => ({ value, count })).sort(
    (a, b) => b.count - a.count || a.value.localeCompare(b.value),
  );
}

/**
 * The slice of a ranked list a dimension shows: values containing `query`
 * (case-insensitive) with a positive count, capped at `limit`, plus how many
 * such values there are in total.
 */
export function topOptions(
  options: FacetOption[],
  query: string,
  limit: number = FACET_LIMIT,
): { options: FacetOption[]; total: number } {
  const needle = query.trim().toLowerCase();
  const matching = options.filter(
    (o) => o.count > 0 && (!needle || o.value.toLowerCase().includes(needle)),
  );
  return { options: matching.slice(0, limit), total: matching.length };
}

export interface PickerRow {
  value: string;
  /** Null when the value is selected but fell outside the ranked slice, so its count is unknown. */
  count: number | null;
  checked: boolean;
}

/**
 * The rows a picker lists: the selected values pinned first (so a choice
 * stays visible and removable even once it drops out of the top ranks or
 * stops matching the search), then the ranked options that are not selected.
 */
export function pickerRows(options: FacetOption[], selected: string[]): PickerRow[] {
  const counts = new Map(options.map((o) => [o.value, o.count]));
  const pinned = selected.map((value) => ({ value, count: counts.get(value) ?? null, checked: true }));
  const rest = options
    .filter((o) => !selected.includes(o.value))
    .map((o) => ({ value: o.value, count: o.count, checked: false }));
  return [...pinned, ...rest];
}

/**
 * Facets derived from the tutorial's demo points under the same contract as
 * the backend: ranked, capped, searchable, with totals. Counts are plain
 * totals rather than contextual ones. Legacy points with no explicit type are
 * plain runs.
 */
export function facetsFromPoints(
  points: PublicDashboardPoint[],
  query: string,
  limit: number = FACET_LIMIT,
): CorpusFacets {
  const models = topOptions(countOccurrences(points.map((p) => p.winning_model)), query, limit);
  const optimizers = topOptions(
    countOccurrences(points.map((p) => p.optimizer_name)),
    query,
    limit,
  );
  const modules = topOptions(
    countOccurrences(points.map((p) => p.module_name)),
    query,
    limit,
  );
  const types = topOptions(
    countOccurrences(points.map((p) => p.optimization_type ?? "run")),
    query,
    limit,
  );
  return {
    models: models.options,
    optimizers: optimizers.options,
    modules: modules.options,
    types: types.options,
    totals: {
      models: models.total,
      optimizers: optimizers.total,
      modules: modules.total,
      types: types.total,
    },
  };
}
