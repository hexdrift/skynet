"use client";

import { InlineErrorRow } from "@/shared/ui/inline-error-row";
import { Button } from "@/shared/ui/primitives/button";
import * as React from "react";
import { useSession } from "next-auth/react";
import { motion } from "framer-motion";
import {
  Clock,
  FunnelX,
  MagnifyingGlassMinus,
  PaperPlaneTilt,
  Plus,
  SignIn,
  Warning,
} from "@/shared/ui/icons";
import { logSearchQuery, type PublicDashboardPoint } from "@/shared/lib/api";
import { msg, formatMsg } from "@/shared/lib/messages";
import { sessionIdentity } from "@/shared/lib/session-identity";
import { EmptyState } from "@/shared/ui/empty-state";
import { registerTutorialHook } from "@/features/tutorial";
import { useIsPhone } from "@/shared/hooks/use-device-class";
import { usePublicDashboard } from "../hooks/use-public-dashboard";
import { useFacetOptions } from "../hooks/use-facet-options";
import {
  FACET_LIMIT,
  FACET_LIMIT_MAX,
  FACET_LIMIT_STEP,
  facetsFromPoints,
} from "../lib/facet-options";
import { useSemanticSearch } from "../hooks/use-semantic-search";
import { useRecentQueries } from "../hooks/use-recent-queries";
import { usePopularQueries } from "../hooks/use-popular-queries";
import { useResultKeyboardNav } from "../hooks/use-result-keyboard-nav";
import { ExploreSkeleton } from "./ExploreSkeleton";
import { SearchBar } from "./SearchBar";
import { FiltersDrawer, FilterSummary, type DrawerField } from "./FiltersDrawer";
import { ResultsList } from "./ResultsList";
import { ResultsToolbar } from "./ResultsToolbar";
import { ResultsSkeleton } from "./ResultsSkeleton";
import { Pagination } from "./Pagination";

/**
 * Top-level /explore page rendering a single ranked-list view driven by one
 * shared search input and filter set, with corpus toggle and pagination.
 */
export function ExploreView() {
  const { data: session, status } = useSession();
  const sessionUser = sessionIdentity(session);
  const isPhone = useIsPhone();
  const { points: realPoints, loading: corpusLoading, error: corpusError } = usePublicDashboard();
  const [demoPoints, setDemoPoints] = React.useState<PublicDashboardPoint[] | null>(null);
  const rawPoints = demoPoints ?? realPoints;
  const points = Array.isArray(rawPoints) ? rawPoints : [];

  React.useEffect(() => registerTutorialHook("setDemoExplorePoints", setDemoPoints), []);
  React.useEffect(() => {
    const onExit = () => setDemoPoints(null);
    window.addEventListener("tutorial-exited", onExit);
    return () => window.removeEventListener("tutorial-exited", onExit);
  }, []);

  const { query, response, actions, appliedFilterCount } = useSemanticSearch({
    sessionUser,
    sessionReady: status !== "loading",
  });
  // The filter panel (an aside beside the results on desktop, a sheet
  // below), the field expanded inside it (one at a time), that field's value
  // search, and how far its ranked list has been paged; search and paging
  // reset whenever a field or the panel closes so the next open starts from
  // the busiest values again.
  const filtersButtonRef = React.useRef<HTMLButtonElement>(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [openField, setOpenField] = React.useState<DrawerField | null>(null);
  const [facetQuery, setFacetQuery] = React.useState("");
  const [facetLimit, setFacetLimit] = React.useState(FACET_LIMIT);
  const onOpenFieldChange = React.useCallback((next: DrawerField | null) => {
    setOpenField(next);
    setFacetQuery("");
    setFacetLimit(FACET_LIMIT);
  }, []);
  const onFacetQueryChange = React.useCallback((next: string) => {
    setFacetQuery(next);
    setFacetLimit(FACET_LIMIT);
  }, []);
  const onShowMore = React.useCallback(
    () => setFacetLimit((limit) => Math.min(FACET_LIMIT_MAX, limit + FACET_LIMIT_STEP)),
    [],
  );
  const onDrawerOpenChange = React.useCallback((next: boolean) => {
    setDrawerOpen(next);
    if (!next) {
      setOpenField(null);
      setFacetQuery("");
      setFacetLimit(FACET_LIMIT);
      // The aside has no focus trap to hand focus back; the sheet's own
      // restore lands on the same button.
      filtersButtonRef.current?.focus();
    }
  }, []);
  // Only the facet dimensions are fetched; the date field has no values to list.
  const openDimension = openField === "date" ? null : openField;

  const { recent, push: pushRecent, clear: clearRecent } = useRecentQueries();

  // A query is recorded only when it leads to an opened optimization — a result
  // row clicked, or Enter pressed on a keyboard-highlighted row — never on a
  // bare Enter-to-search or debounced typing. Tying the signal to a click-through
  // keeps idle or mistyped queries out of recent and the trending counts. Recent
  // is personal and per-device, recorded for any corpus; trending is public-corpus
  // only and logged server-side. The consecutive-dedup ref guards against a
  // keyboard-open and the row's own click handler double-counting the same query.
  const lastLoggedRef = React.useRef("");
  const commitQuery = React.useCallback(
    (raw: string) => {
      const trimmed = raw.trim();
      if (!trimmed) return;
      pushRecent(trimmed);
      if (query.corpus !== "public") return;
      const normalized = trimmed.toLocaleLowerCase();
      if (normalized.length < 2 || normalized === lastLoggedRef.current) return;
      lastLoggedRef.current = normalized;
      logSearchQuery(trimmed);
    },
    [pushRecent, query.corpus],
  );

  const { activeIndex, onInputKeyDown } = useResultKeyboardNav(response.results, () =>
    commitQuery(query.text),
  );

  // The open field's values come from a per-corpus facets fetch so each tab
  // lists only the values it can filter to (a model private to "mine" never
  // shows under "public"); the backend caps the list and answers the value
  // search. The tutorial's demo corpus has no backend scope, so there the
  // same ranking is applied client-side to the injected demo points.
  const fetchedOptions = useFacetOptions(
    query.corpus,
    sessionUser,
    {
      models: query.models,
      optimizers: query.optimizers,
      types: query.types,
      modules: query.modules,
      dateFrom: query.dateFrom,
      dateTo: query.dateTo,
    },
    demoPoints ? null : openDimension,
    facetQuery,
    facetLimit,
  );
  const facetOptions = React.useMemo(() => {
    if (!demoPoints || !openDimension) return fetchedOptions;
    const demo = facetsFromPoints(demoPoints, facetQuery, facetLimit);
    return { options: demo[openDimension], total: demo.totals[openDimension], loading: false };
  }, [demoPoints, openDimension, facetQuery, facetLimit, fetchedOptions]);
  const canShowMore =
    facetLimit < FACET_LIMIT_MAX && facetOptions.total > facetOptions.options.length;
  // Popular searches for a blank field: real trending only — what people
  // actually searched (public corpus, logged server-side on explicit commit).
  // When the log has no data yet, this is empty and the section simply doesn't
  // render; showing nothing beats surfacing irrelevant filler.
  const trendingQueries = usePopularQueries();
  const popularSearches = React.useMemo<string[]>(
    () => trendingQueries.map((q) => q.query),
    [trendingQueries],
  );

  const corpusTotal = points.length;
  const isPublicCorpus = query.corpus === "public";
  // The dashed empty state only fires when the public corpus is genuinely
  // empty — we still want the corpus toggle visible so the user can pivot
  // to "Mine" without first creating a public job.
  const isTrulyEmpty = isPublicCorpus && !corpusLoading && !corpusError && corpusTotal === 0;

  if (status === "loading") {
    return <ExploreSkeleton />;
  }

  if (isPublicCorpus && corpusLoading && points.length === 0) {
    return <ExploreSkeleton />;
  }

  const panelProps = {
    open: drawerOpen,
    onOpenChange: onDrawerOpenChange,
    openField,
    onOpenFieldChange,
    facetQuery,
    onFacetQueryChange,
    options: facetOptions.options,
    total: facetOptions.total,
    loading: facetOptions.loading,
    canShowMore,
    onShowMore,
    selectedModels: query.models,
    selectedOptimizers: query.optimizers,
    selectedTypes: query.types,
    selectedModules: query.modules,
    dateFrom: query.dateFrom,
    dateTo: query.dateTo,
    resultTotal: response.total,
    resultsLoading: response.loading,
    onChangeModels: actions.setModels,
    onChangeOptimizers: actions.setOptimizers,
    onChangeTypes: actions.setTypes,
    onChangeModules: actions.setModules,
    onChangeDateRange: actions.setDateRange,
    onClearAll: actions.clearFilters,
  };

  return (
    <>
      <div className="flex flex-col gap-1.5 pb-16">
        {isPublicCorpus && corpusError && (
          <div
            className="flex items-start gap-3 rounded-lg border border-border bg-accent-muted/50 px-4 py-3 text-xs text-foreground"
            role="status"
          >
            <Warning className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <span>{corpusError}</span>
          </div>
        )}

        <div className="flex flex-col gap-3">
          <SearchBar
            text={query.text}
            onSubmit={actions.setText}
            corpus={query.corpus}
            onCorpusChange={actions.setCorpus}
            signedIn={sessionUser.length > 0}
            filtersCount={appliedFilterCount}
            filtersOpen={drawerOpen}
            filtersButtonRef={filtersButtonRef}
            onOpenFilters={() => onDrawerOpenChange(!drawerOpen)}
            onClearFilters={actions.clearFilters}
            loading={response.loading}
            onResultKeyDown={onInputKeyDown}
            activeResultIndex={activeIndex}
            recentQueries={recent}
            onClearRecent={clearRecent}
            suggestions={isPublicCorpus ? popularSearches : []}
          />
          <FilterSummary
            models={query.models}
            optimizers={query.optimizers}
            types={query.types}
            modules={query.modules}
            dateFrom={query.dateFrom}
            dateTo={query.dateTo}
            onOpen={() => onDrawerOpenChange(true)}
            onClearAll={actions.clearFilters}
          />
        </div>

        {isTrulyEmpty ? (
          <EmptyState
            icon={PaperPlaneTilt}
            iconWrap="tile"
            title={msg("explore.empty.title")}
            description={msg("explore.empty.hint")}
            action={
              isPhone ? undefined : { label: msg("explore.empty.cta"), href: "/submit", icon: Plus }
            }
            className="mt-3.5"
          />
        ) : (
          <ListPane
            query={query}
            response={response}
            activeIndex={activeIndex}
            onSetPage={actions.setPage}
            onSetSort={actions.setSort}
            onClearAll={actions.clearAll}
            onClearQuery={() => actions.setText("")}
            onResultOpen={() => commitQuery(query.text)}
            hasFilters={appliedFilterCount > 0}
            sessionUser={sessionUser}
          />
        )}
      </div>

      <FiltersDrawer {...panelProps} />
    </>
  );
}

function ListPane({
  query,
  response,
  activeIndex,
  onSetPage,
  onSetSort,
  onClearAll,
  onClearQuery,
  onResultOpen,
  hasFilters,
  sessionUser,
}: {
  query: ReturnType<typeof useSemanticSearch>["query"];
  response: ReturnType<typeof useSemanticSearch>["response"];
  activeIndex: number;
  onSetPage: ReturnType<typeof useSemanticSearch>["actions"]["setPage"];
  onSetSort: ReturnType<typeof useSemanticSearch>["actions"]["setSort"];
  onClearAll: () => void;
  onClearQuery: () => void;
  onResultOpen: () => void;
  hasFilters: boolean;
  sessionUser: string;
}) {
  const isPhone = useIsPhone();
  if (response.error) {
    return <InlineErrorRow message={msg("explore.results.error")} className="mx-auto max-w-2xl" />;
  }

  if (response.loading && response.results.length === 0) {
    return (
      <div className="flex flex-col gap-2">
        <div className="border-t border-border/55">
          <ResultsSkeleton rows={4} />
        </div>
      </div>
    );
  }

  if (!response.loading && response.results.length === 0) {
    // Distinct cases to keep the empty UI honest:
    //   1. Session-scoped (Mine/Shared) + signed out — no auth, no list to show
    //   2. Mine + no filters — user has zero jobs; clear-filters is misleading
    //   3. Shared + no filters — nothing has been shared with the user yet
    //   4. Otherwise — a real "no matches" state with clear-filters affordance
    const isMine = query.corpus === "mine";
    const isShared = query.corpus === "shared";
    if ((isMine || isShared) && !sessionUser) {
      return (
        <EmptyState
          variant="list"
          icon={SignIn}
          title={msg(
            isShared ? "explore.corpus.shared.signed_out" : "explore.corpus.mine.signed_out",
          )}
        />
      );
    }
    if (isMine && !response.isActive) {
      return (
        <EmptyState
          icon={PaperPlaneTilt}
          iconWrap="tile"
          title={msg("explore.corpus.mine.empty")}
          description={msg("explore.corpus.mine.empty.hint")}
          action={
            isPhone ? undefined : { label: msg("explore.empty.cta"), href: "/submit", icon: Plus }
          }
          className="mt-3.5"
        />
      );
    }
    if (isShared && !response.isActive) {
      return (
        <EmptyState
          variant="list"
          title={msg("explore.corpus.shared.empty")}
          description={msg("explore.corpus.shared.empty.hint")}
          className="pt-4"
        />
      );
    }
    return (
      <EmptyState
        variant="list"
        icon={MagnifyingGlassMinus}
        title={formatMsg("explore.results.empty.title", { query: query.text || "—" })}
        description={msg("explore.results.empty.hint")}
      >
        {(query.text.trim().length > 0 || hasFilters) && (
          <div className="flex flex-wrap items-center justify-center gap-2">
            {query.text.trim().length > 0 && (
              <Button type="button" variant="outline" size="sm" onClick={onClearQuery}>
                <Clock className="size-3.5" aria-hidden="true" />
                {msg("explore.results.empty.show_recent")}
              </Button>
            )}
            {hasFilters && (
              <Button type="button" variant="outline" size="sm" onClick={onClearAll}>
                <FunnelX className="size-3.5" aria-hidden="true" />
                {msg("explore.results.empty.clear_filters")}
              </Button>
            )}
          </div>
        )}
      </EmptyState>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <ResultsToolbar
        total={response.total}
        sort={query.sort}
        onSortChange={onSetSort}
        hasQuery={query.text.trim().length > 0}
      />
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.18, ease: [0.2, 0.8, 0.2, 1] }}
        className="border-t border-border/55"
      >
        <ResultsList
          results={response.results}
          highlight={query.text}
          searchType={response.searchType}
          activeIndex={activeIndex}
          onResultOpen={onResultOpen}
        />
      </motion.div>
      <Pagination
        page={query.page}
        size={query.size}
        total={response.total}
        onPageChange={onSetPage}
      />
    </div>
  );
}
