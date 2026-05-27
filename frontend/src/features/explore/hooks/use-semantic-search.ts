"use client";

import * as React from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { searchPublicDashboard, type SearchResult } from "@/shared/lib/api";

export type ExploreView = "list" | "map";
export type ExploreCorpus = "mine" | "public";
export type SearchType = "semantic" | "lexical";

export interface SearchQueryState {
  /** The text the user is typing — updates immediately, used to drive the input value. */
  text: string;
  /** Page-size selector. */
  size: number;
  /** 1-indexed page. */
  page: number;
  /** Active categorical filter values. */
  models: string[];
  optimizers: string[];
  types: string[];
  /** ISO date (YYYY-MM-DD), inclusive. */
  dateFrom: string | null;
  dateTo: string | null;
  /** Which view is shown: ranked list or scatter map. */
  view: ExploreView;
  /** Which corpus to search: the user's own jobs or other users' public jobs. */
  corpus: ExploreCorpus;
}

export interface SearchResponseState {
  results: SearchResult[];
  total: number;
  matchedIds: Set<string>;
  loading: boolean;
  error: string | null;
  /** True when the user has typed anything or applied any filter. */
  isActive: boolean;
  /** Which backend branch served this response — drives the per-row badge. */
  searchType: SearchType | null;
}

const VALID_SIZES = new Set([10, 30, 50]);
const VALID_VIEWS = new Set<ExploreView>(["list", "map"]);
const VALID_CORPORA = new Set<ExploreCorpus>(["mine", "public"]);

const DEFAULT_SIZE = 30;
const DEFAULT_PAGE = 1;
const DEFAULT_VIEW: ExploreView = "list";
const DEFAULT_CORPUS: ExploreCorpus = "public";

const DEBOUNCE_MS = 150;

function parseCsv(value: string | null): string[] {
  if (!value) return [];
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function readState(params: URLSearchParams): SearchQueryState {
  const sizeRaw = Number.parseInt(params.get("size") ?? "", 10);
  const pageRaw = Number.parseInt(params.get("page") ?? "", 10);
  const viewRaw = params.get("view") as ExploreView | null;
  const corpusRaw = params.get("corpus") as ExploreCorpus | null;
  return {
    text: params.get("q") ?? "",
    size: VALID_SIZES.has(sizeRaw) ? sizeRaw : DEFAULT_SIZE,
    page: Number.isFinite(pageRaw) && pageRaw > 0 ? pageRaw : DEFAULT_PAGE,
    models: parseCsv(params.get("models")),
    optimizers: parseCsv(params.get("optimizers")),
    types: parseCsv(params.get("types")),
    dateFrom: params.get("from"),
    dateTo: params.get("to"),
    view: viewRaw && VALID_VIEWS.has(viewRaw) ? viewRaw : DEFAULT_VIEW,
    corpus:
      corpusRaw && VALID_CORPORA.has(corpusRaw) ? corpusRaw : DEFAULT_CORPUS,
  };
}

function hasAnyFilter(state: SearchQueryState): boolean {
  if (state.text.trim().length > 0) return true;
  if (state.models.length > 0) return true;
  if (state.optimizers.length > 0) return true;
  if (state.types.length > 0) return true;
  if (state.dateFrom) return true;
  if (state.dateTo) return true;
  return false;
}

export interface SearchActions {
  setText: (value: string) => void;
  setPage: (page: number) => void;
  setSize: (size: number) => void;
  setView: (view: ExploreView) => void;
  setCorpus: (corpus: ExploreCorpus) => void;
  toggleModel: (model: string) => void;
  toggleOptimizer: (optimizer: string) => void;
  toggleType: (type: string) => void;
  setModels: (models: string[]) => void;
  setOptimizers: (optimizers: string[]) => void;
  setTypes: (types: string[]) => void;
  setDateRange: (from: string | null, to: string | null) => void;
  clearAll: () => void;
  removeFilter: (kind: "model" | "optimizer" | "type", value: string) => void;
}

export interface UseSemanticSearchOptions {
  /** Logged-in user's name; empty string when signed out. Drives Mine corpus fetch. */
  sessionUser: string;
}

export function useSemanticSearch(opts: UseSemanticSearchOptions): {
  query: SearchQueryState;
  response: SearchResponseState;
  actions: SearchActions;
  /** Cleared count for the "X filters active" pill — excludes free-text query. */
  appliedFilterCount: number;
} {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const sessionUser = opts.sessionUser;

  const query = React.useMemo<SearchQueryState>(
    () => readState(new URLSearchParams(searchParams?.toString() ?? "")),
    [searchParams],
  );

  const [response, setResponse] = React.useState<SearchResponseState>({
    results: [],
    total: 0,
    matchedIds: new Set(),
    loading: false,
    error: null,
    isActive: false,
    searchType: null,
  });

  const updateUrl = React.useCallback(
    (mutator: (params: URLSearchParams) => void, opts: { resetPage?: boolean } = {}) => {
      const params = new URLSearchParams(
        typeof window !== "undefined" ? window.location.search : "",
      );
      mutator(params);
      if (opts.resetPage) params.delete("page");
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router],
  );

  const writeList = React.useCallback(
    (key: string, values: string[]) => {
      updateUrl((p) => {
        if (values.length === 0) p.delete(key);
        else p.set(key, values.join(","));
      }, { resetPage: true });
    },
    [updateUrl],
  );

  const actions = React.useMemo<SearchActions>(
    () => ({
      setText: (value: string) =>
        updateUrl((p) => {
          const trimmed = value;
          if (!trimmed) p.delete("q");
          else p.set("q", trimmed);
        }, { resetPage: true }),

      setPage: (page: number) =>
        updateUrl((p) => {
          if (page <= 1) p.delete("page");
          else p.set("page", String(page));
        }),

      setSize: (size: number) =>
        updateUrl((p) => {
          if (size === DEFAULT_SIZE) p.delete("size");
          else p.set("size", String(size));
        }, { resetPage: true }),

      setView: (view: ExploreView) =>
        updateUrl((p) => {
          if (view === DEFAULT_VIEW) p.delete("view");
          else p.set("view", view);
        }),

      setCorpus: (corpus: ExploreCorpus) =>
        updateUrl((p) => {
          if (corpus === DEFAULT_CORPUS) p.delete("corpus");
          else p.set("corpus", corpus);
          // Mine doesn't have map projections — snap back to list view so a
          // returning user doesn't land on an empty map.
          if (corpus === "mine") p.delete("view");
        }, { resetPage: true }),

      toggleModel: (model: string) => {
        const current = new Set(query.models);
        if (current.has(model)) current.delete(model);
        else current.add(model);
        writeList("models", Array.from(current));
      },

      toggleOptimizer: (optimizer: string) => {
        const current = new Set(query.optimizers);
        if (current.has(optimizer)) current.delete(optimizer);
        else current.add(optimizer);
        writeList("optimizers", Array.from(current));
      },

      toggleType: (type: string) => {
        const current = new Set(query.types);
        if (current.has(type)) current.delete(type);
        else current.add(type);
        writeList("types", Array.from(current));
      },

      setModels: (models: string[]) => writeList("models", models),
      setOptimizers: (optimizers: string[]) => writeList("optimizers", optimizers),
      setTypes: (types: string[]) => writeList("types", types),

      setDateRange: (from: string | null, to: string | null) =>
        updateUrl((p) => {
          if (from) p.set("from", from);
          else p.delete("from");
          if (to) p.set("to", to);
          else p.delete("to");
        }, { resetPage: true }),

      clearAll: () =>
        updateUrl((p) => {
          for (const key of ["q", "models", "optimizers", "types", "from", "to", "page"]) {
            p.delete(key);
          }
        }),

      removeFilter: (kind: "model" | "optimizer" | "type", value: string) => {
        const map = {
          model: query.models,
          optimizer: query.optimizers,
          type: query.types,
        } as const;
        const next = map[kind].filter((v) => v !== value);
        const key = kind === "model" ? "models" : kind === "optimizer" ? "optimizers" : "types";
        writeList(key, next);
      },
    }),
    [query.models, query.optimizers, query.types, updateUrl, writeList],
  );

  const appliedFilterCount =
    query.models.length +
    query.optimizers.length +
    query.types.length +
    (query.dateFrom ? 1 : 0) +
    (query.dateTo ? 1 : 0);

  React.useEffect(() => {
    const active = hasAnyFilter(query);
    const controller = new AbortController();
    setResponse((prev) => ({ ...prev, loading: true, error: null, isActive: active }));

    const runSearch = async (ownerUsername: string | undefined) => {
      const data = await searchPublicDashboard(
        {
          query: query.text.trim() || undefined,
          models: query.models.length ? query.models : undefined,
          optimizers: query.optimizers.length ? query.optimizers : undefined,
          optimization_types: query.types.length ? query.types : undefined,
          date_from: query.dateFrom ?? undefined,
          date_to: query.dateTo ?? undefined,
          sort: "relevance",
          page: query.page,
          size: query.size,
          owner_username: ownerUsername,
        },
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      setResponse({
        results: data.results,
        total: data.total,
        matchedIds: new Set(data.matched_ids),
        loading: false,
        error: null,
        isActive: active,
        searchType: data.search_type ?? null,
      });
    };

    const runMineSignedOut = () => {
      setResponse({
        results: [],
        total: 0,
        matchedIds: new Set(),
        loading: false,
        error: null,
        isActive: active,
        searchType: null,
      });
    };

    const run = async () => {
      try {
        if (query.corpus === "public") {
          await runSearch(undefined);
        } else if (!sessionUser) {
          runMineSignedOut();
        } else {
          await runSearch(sessionUser);
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        const name = (err as Error | undefined)?.name;
        if (name === "AbortError") return;
        setResponse((prev) => ({
          ...prev,
          loading: false,
          error: err instanceof Error ? err.message : "search failed",
        }));
      }
    };

    const handle = window.setTimeout(run, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(handle);
      controller.abort();
    };
  }, [query, sessionUser]);

  return { query, response, actions, appliedFilterCount };
}
