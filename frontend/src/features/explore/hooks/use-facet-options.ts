"use client";

import { useEffect, useState } from "react";
import {
  getCorpusFacets,
  type FacetContext,
  type FacetDimension,
  type FacetOption,
} from "@/shared/lib/api";
import { FACET_LIMIT } from "../lib/facet-options";
import type { ExploreCorpus } from "./use-semantic-search";

/** Keystrokes settle for this long before a value search hits the backend. */
const SEARCH_DEBOUNCE_MS = 180;

export interface FacetFilters {
  models: string[];
  optimizers: string[];
  types: string[];
  modules: string[];
  dateFrom: string | null;
  dateTo: string | null;
}

export interface FacetOptions {
  /** The busiest values (or, while `query` is non-empty, the matching ones), each with its contextual count. */
  options: FacetOption[];
  /** Distinct values available for the dimension in the current context. */
  total: number;
  loading: boolean;
}

const EMPTY: FacetOptions = { options: [], total: 0, loading: false };

/**
 * The values the open filter picker lists for the active corpus tab: the
 * busiest values of one dimension, each with the number of runs it would
 * leave alongside the other active filters, so each tab offers exactly the
 * values it can filter to — a model private to "mine" never shows under
 * "public". Nothing is fetched in full: the backend caps the list and
 * reports the total, and `query` turns the same request into a server-side
 * value search (debounced), and `limit` grows as the user asks for more of
 * the ranked list. Only the open picker (`dimension`) is fetched; `null`
 * means none is open and nothing loads. Refetches when the corpus,
 * signed-in user, dimension, query, or any structured filter changes (the
 * free-text run query is not part of the counts); the previous values stay
 * on screen while the new ones load so rows never flicker away. Signed-out
 * "mine"/"shared" have nothing to fetch and resolve to empty.
 */
export function useFacetOptions(
  corpus: ExploreCorpus,
  sessionUser: string,
  filters: FacetFilters,
  dimension: FacetDimension | null,
  query = "",
  limit: number = FACET_LIMIT,
): FacetOptions {
  const [state, setState] = useState<FacetOptions>(EMPTY);
  // One primitive dependency for the arrays and dates together: the URL-state
  // hook hands back fresh arrays on unrelated updates, and a serialized key
  // only changes when a filter value actually does.
  const filterKey = JSON.stringify([
    filters.models,
    filters.optimizers,
    filters.types,
    filters.modules,
    filters.dateFrom,
    filters.dateTo,
  ]);
  const trimmedQuery = query.trim();

  useEffect(() => {
    let cancelled = false;

    if (dimension === null || (corpus !== "public" && !sessionUser)) {
      setState(EMPTY);
      return;
    }

    const scope =
      corpus === "mine"
        ? { owner_username: sessionUser }
        : corpus === "shared"
          ? { shared_with_username: sessionUser }
          : {};
    const [models, optimizers, types, modules, dateFrom, dateTo] = JSON.parse(filterKey) as [
      string[],
      string[],
      string[],
      string[],
      string | null,
      string | null,
    ];
    const context: FacetContext = {
      models,
      optimizers,
      optimization_types: types,
      modules,
      date_from: dateFrom ?? undefined,
      date_to: dateTo ?? undefined,
    };

    setState((prev) => ({ ...prev, loading: true }));
    // Only typing is debounced; opening a picker and filter changes go out
    // immediately so the list follows a tick without lag.
    const timer = setTimeout(
      () => {
        void (async () => {
          try {
            const data = await getCorpusFacets(scope, context, {
              query: trimmedQuery,
              limit,
              dimension,
            });
            if (!cancelled) {
              setState({ options: data[dimension], total: data.totals[dimension], loading: false });
            }
          } catch {
            if (!cancelled) setState(EMPTY);
          }
        })();
      },
      trimmedQuery ? SEARCH_DEBOUNCE_MS : 0,
    );

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [corpus, sessionUser, filterKey, dimension, trimmedQuery, limit]);

  return state;
}
