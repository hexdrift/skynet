"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CircleDot, FilterX, Grid2x2, Layers, Plus, SearchX, X } from "lucide-react";
import type { PublicDashboardPoint } from "@/shared/lib/api";
import { msg, formatMsg } from "@/shared/lib/messages";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/shared/ui/primitives/tooltip";
import { registerTutorialHook } from "@/features/tutorial";
import { usePublicDashboard } from "../hooks/use-public-dashboard";
import { useSemanticSearch } from "../hooks/use-semantic-search";
import { buildVariationGroups } from "../lib/groups";
import { ExploreSkeleton } from "./ExploreSkeleton";
import { SearchBar } from "./SearchBar";
import { FiltersDrawer } from "./FiltersDrawer";
import { ResultsList } from "./ResultsList";
import { ResultsSkeleton } from "./ResultsSkeleton";
import { Pagination } from "./Pagination";
import { ScatterCanvas, type ExploreFilter } from "./ScatterCanvas";
import { ExploreDetailPanel } from "./ExploreDetailPanel";
import { formatDisplayDate } from "./SkynetDatePicker";

const FILTERS: Array<{
  value: ExploreFilter;
  labelKey: Parameters<typeof msg>[0];
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" }>;
}> = [
  { value: "all", labelKey: "explore.filter.all", icon: Layers },
  { value: "run", labelKey: "explore.filter.run", icon: CircleDot },
  { value: "grid_search", labelKey: "explore.filter.grid", icon: Grid2x2 },
];

function isExploreFilter(v: string | null): v is ExploreFilter {
  return v === "all" || v === "run" || v === "grid_search";
}

/**
 * Top-level /explore page. Two views — ranked list (Google-style) and the
 * existing scatter map — share one search input and one set of filters.
 * The map dims non-matches when a search is active; the list shows ranked
 * hits with pagination.
 */
export function ExploreView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { data: session } = useSession();
  const sessionUser = session?.user?.name ?? "";
  const { points: realPoints, loading: corpusLoading, error: corpusError } = usePublicDashboard();
  const [demoPoints, setDemoPoints] = React.useState<PublicDashboardPoint[] | null>(null);
  const points = demoPoints ?? realPoints;

  React.useEffect(() => registerTutorialHook("setDemoExplorePoints", setDemoPoints), []);
  React.useEffect(() => {
    const onExit = () => setDemoPoints(null);
    window.addEventListener("tutorial-exited", onExit);
    return () => window.removeEventListener("tutorial-exited", onExit);
  }, []);

  const { query, response, actions, appliedFilterCount } = useSemanticSearch({
    sessionUser,
  });
  const [drawerOpen, setDrawerOpen] = React.useState(false);

  const focusId = searchParams.get("focus");
  const urlFilter = searchParams.get("filter");
  const filter: ExploreFilter = isExploreFilter(urlFilter) ? urlFilter : "all";

  const setFocus = React.useCallback(
    (next: string | null) => {
      const params = new URLSearchParams(
        typeof window !== "undefined" ? window.location.search : "",
      );
      if (next) params.set("focus", next);
      else params.delete("focus");
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router],
  );

  const setFilter = React.useCallback(
    (next: ExploreFilter) => {
      const params = new URLSearchParams(
        typeof window !== "undefined" ? window.location.search : "",
      );
      if (next === "all") params.delete("filter");
      else params.set("filter", next);
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router],
  );

  const { leaders, byLeaderId } = React.useMemo(
    () => buildVariationGroups(points),
    [points],
  );
  // Unembedded jobs share the same payload shape but have no projected
  // coordinates — they should appear in the corpus count and the lexical
  // result list, but never on the scatter map.
  const mapLeaders = React.useMemo(
    () => leaders.filter((p) => p.has_coordinates !== false),
    [leaders],
  );
  const filterCounts: Record<ExploreFilter, number> = React.useMemo(() => {
    const c: Record<ExploreFilter, number> = {
      all: mapLeaders.length,
      run: 0,
      grid_search: 0,
    };
    for (const p of mapLeaders) {
      if (p.optimization_type === "run") c.run += 1;
      else if (p.optimization_type === "grid_search") c.grid_search += 1;
    }
    return c;
  }, [mapLeaders]);
  const multiVariationIds = React.useMemo(() => {
    const ids = new Set<string>();
    for (const [leaderId, variations] of byLeaderId) {
      if (variations.length > 1) ids.add(leaderId);
    }
    return ids;
  }, [byLeaderId]);
  const variationCountById = React.useMemo(() => {
    const m = new Map<string, number>();
    for (const [leaderId, variations] of byLeaderId) {
      m.set(leaderId, variations.length);
    }
    return m;
  }, [byLeaderId]);

  const pointsById = React.useMemo(() => {
    const m = new Map<string, PublicDashboardPoint>();
    for (const p of leaders) m.set(p.optimization_id, p);
    return m;
  }, [leaders]);

  const focused = focusId ? (pointsById.get(focusId) ?? null) : null;
  const focusedVariations = focused
    ? (byLeaderId.get(focused.optimization_id) ?? [focused])
    : [];

  const modelOptions = React.useMemo(() => collectDistinct(points, "winning_model"), [points]);
  const optimizerOptions = React.useMemo(
    () => collectDistinct(points, "optimizer_name"),
    [points],
  );

  React.useEffect(() => {
    if (corpusLoading) return;
    if (!focusId) return;
    if (pointsById.has(focusId)) return;
    setFocus(null);
  }, [corpusLoading, focusId, pointsById, setFocus]);

  const corpusTotal = leaders.length;
  const isPublicCorpus = query.corpus === "public";
  // The dashed empty state only fires when the public corpus is genuinely
  // empty — we still want the corpus toggle visible so the user can pivot
  // to "Mine" without first creating a public job.
  const isTrulyEmpty =
    isPublicCorpus && !corpusLoading && !corpusError && corpusTotal === 0;

  if (isPublicCorpus && corpusLoading && points.length === 0) {
    return <ExploreSkeleton />;
  }

  const showMap = isPublicCorpus && query.view === "map";
  const searchActive = response.isActive;
  const matchedIds = searchActive ? response.matchedIds : null;

  return (
    <div dir="rtl" className="pb-16">
      <div className="flex flex-col gap-3">
        {isPublicCorpus && corpusError && (
          <div
            className="flex items-start gap-3 rounded-lg border border-border bg-accent-muted/50 px-4 py-3 text-xs text-foreground"
            role="status"
          >
            <AlertTriangle
              className="mt-0.5 size-4 shrink-0 text-muted-foreground"
              aria-hidden="true"
            />
            <span>{corpusError}</span>
          </div>
        )}

        <div className="flex flex-col gap-3">
          <SearchBar
            text={query.text}
            onSubmit={actions.setText}
            view={query.view}
            onViewChange={actions.setView}
            corpus={query.corpus}
            onCorpusChange={actions.setCorpus}
            mineEnabled={sessionUser.length > 0}
            filtersCount={appliedFilterCount}
            onOpenFilters={() => setDrawerOpen(true)}
          />
          <ActiveFilterChips
            models={query.models}
            optimizers={query.optimizers}
            types={query.types}
            dateFrom={query.dateFrom}
            dateTo={query.dateTo}
            onRemove={actions.removeFilter}
            onClearDates={() => actions.setDateRange(null, null)}
            onClearAll={actions.clearAll}
          />
        </div>

        {isTrulyEmpty ? (
          <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 rounded-lg border border-dashed border-border bg-background px-6 py-10 text-center">
            <p className="max-w-[40ch] text-sm text-foreground/80">
              {msg("explore.empty.title")}
            </p>
            <Link
              href="/submit"
              className="inline-flex items-center gap-1.5 rounded-md bg-foreground px-3 py-1.5 text-xs font-medium text-background transition-colors hover:bg-foreground/85"
            >
              <Plus className="size-3.5" />
              {msg("explore.empty.cta")}
            </Link>
          </div>
        ) : showMap ? (
          <MapPane
            leaders={mapLeaders}
            focusId={focusId}
            focused={focused}
            focusedVariations={focusedVariations}
            multiVariationIds={multiVariationIds}
            variationCountById={variationCountById}
            matchedIds={matchedIds}
            onSelect={setFocus}
            filter={filter}
            filterCounts={filterCounts}
            onFilterChange={(next) => {
              if (next !== "all" && focused && focused.optimization_type !== next) {
                setFocus(null);
              }
              setFilter(next);
            }}
          />
        ) : (
          <ListPane
            query={query}
            response={response}
            onSetPage={actions.setPage}
            onClearAll={actions.clearAll}
            sessionUser={sessionUser}
          />
        )}
      </div>

      <FiltersDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        modelOptions={modelOptions}
        optimizerOptions={optimizerOptions}
        selectedModels={query.models}
        selectedOptimizers={query.optimizers}
        selectedTypes={query.types}
        dateFrom={query.dateFrom}
        dateTo={query.dateTo}
        onChangeModels={actions.setModels}
        onChangeOptimizers={actions.setOptimizers}
        onChangeTypes={actions.setTypes}
        onChangeDateRange={actions.setDateRange}
        onClearAll={actions.clearAll}
      />
    </div>
  );
}

function ListPane({
  query,
  response,
  onSetPage,
  onClearAll,
  sessionUser,
}: {
  query: ReturnType<typeof useSemanticSearch>["query"];
  response: ReturnType<typeof useSemanticSearch>["response"];
  onSetPage: ReturnType<typeof useSemanticSearch>["actions"]["setPage"];
  onClearAll: () => void;
  sessionUser: string;
}) {
  if (response.error) {
    return (
      <div
        role="status"
        className="mx-auto flex max-w-2xl items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-[13px] text-destructive"
      >
        <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{msg("explore.results.error")}</span>
      </div>
    );
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
    // Three distinct cases to keep the empty UI honest:
    //   1. Mine + signed out — no auth, no list to show
    //   2. Mine + no filters — user has zero jobs; clear-filters is misleading
    //   3. Otherwise — a real "no matches" state with clear-filters affordance
    const isMine = query.corpus === "mine";
    if (isMine && !sessionUser) {
      return (
        <div className="mx-auto flex max-w-xl flex-col items-start gap-3 px-2 py-8">
          <p className="text-[13.5px] text-foreground/65">
            {msg("explore.corpus.mine.signed_out")}
          </p>
        </div>
      );
    }
    if (isMine && !response.isActive) {
      return (
        <div className="mx-auto flex max-w-xl flex-col items-start gap-3 px-2 py-8">
          <p className="text-[13.5px] text-foreground/65">
            {msg("explore.corpus.mine.empty")}
          </p>
          <Link
            href="/submit"
            className="inline-flex items-center gap-1.5 rounded-md bg-foreground px-3 py-1.5 text-xs font-medium text-background transition-colors hover:bg-foreground/85"
          >
            <Plus className="size-3.5" />
            {msg("explore.empty.cta")}
          </Link>
        </div>
      );
    }
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center gap-3 px-2 py-12 text-center">
        <SearchX className="size-6 text-foreground/30" strokeWidth={1.5} aria-hidden="true" />
        <h3 className="mt-1 text-[17px] font-medium leading-tight tracking-tight text-foreground">
          {formatMsg("explore.results.empty.title", { query: query.text || "—" })}
        </h3>
        <p className="max-w-md text-[13.5px] leading-relaxed text-foreground/55">
          {msg("explore.results.empty.hint")}
        </p>
        <button
          type="button"
          onClick={onClearAll}
          className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3.5 py-2 text-[12.5px] text-foreground/75 transition-colors cursor-pointer hover:border-foreground/30 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/45"
        >
          <FilterX className="size-3.5" aria-hidden="true" />
          {msg("explore.results.empty.clear_filters")}
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
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

function MapPane({
  leaders,
  focusId,
  focused,
  focusedVariations,
  multiVariationIds,
  variationCountById,
  matchedIds,
  onSelect,
  filter,
  filterCounts,
  onFilterChange,
}: {
  leaders: PublicDashboardPoint[];
  focusId: string | null;
  focused: PublicDashboardPoint | null;
  focusedVariations: PublicDashboardPoint[];
  multiVariationIds: ReadonlySet<string>;
  variationCountById: ReadonlyMap<string, number>;
  matchedIds: Set<string> | null;
  onSelect: (id: string | null) => void;
  filter: ExploreFilter;
  filterCounts: Record<ExploreFilter, number>;
  onFilterChange: (next: ExploreFilter) => void;
}) {
  return (
    <section className="relative overflow-hidden rounded-xl border border-border/60 bg-card/70 p-2 shadow-sm">
      <ScatterCanvas
        points={leaders}
        filter={filter}
        selectedId={focusId}
        onSelect={onSelect}
        dimmed={focused !== null}
        multiVariationIds={multiVariationIds}
        variationCountById={variationCountById}
        matchedIds={matchedIds}
      >
        <AnimatePresence>
          {filterCounts[filter] === 0 && filterCounts.all > 0 && focused === null && (
            <FilteredEmptyOverlay onClear={() => onFilterChange("all")} />
          )}
        </AnimatePresence>
      </ScatterCanvas>
      <AnimatePresence>
        {!focused && (
          <motion.div
            key="filter-rail"
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 8 }}
            transition={{ duration: 0.16, ease: [0.2, 0.8, 0.2, 1] }}
            className="absolute inset-y-2 start-2 z-20 overflow-hidden rounded-lg"
          >
            <FilterTabs
              value={filter}
              onChange={onFilterChange}
              counts={filterCounts}
            />
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {focused && (
          <motion.div
            key="detail-panel"
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 12 }}
            transition={{ duration: 0.18, ease: [0.2, 0.8, 0.2, 1] }}
            className="pointer-events-none absolute inset-y-3 start-3 z-20 w-[min(340px,calc(100%-1.5rem))]"
          >
            <div className="pointer-events-auto h-full">
              <ExploreDetailPanel
                point={focused}
                variations={focusedVariations}
                onClose={() => onSelect(null)}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

function FilterTabs({
  value,
  onChange,
  counts,
}: {
  value: ExploreFilter;
  onChange: (next: ExploreFilter) => void;
  counts: Record<ExploreFilter, number>;
}) {
  const buttonRefs = React.useRef<Array<HTMLButtonElement | null>>([]);

  const handleKeyDown = (e: React.KeyboardEvent, currentIdx: number) => {
    let delta = 0;
    if (e.key === "ArrowDown" || e.key === "ArrowLeft") delta = 1;
    else if (e.key === "ArrowUp" || e.key === "ArrowRight") delta = -1;
    else if (e.key === "Home") {
      e.preventDefault();
      onChange(FILTERS[0]!.value);
      buttonRefs.current[0]?.focus();
      return;
    } else if (e.key === "End") {
      e.preventDefault();
      const last = FILTERS.length - 1;
      onChange(FILTERS[last]!.value);
      buttonRefs.current[last]?.focus();
      return;
    } else {
      return;
    }
    e.preventDefault();
    const len = FILTERS.length;
    const nextIdx = (currentIdx + delta + len) % len;
    const next = FILTERS[nextIdx]!;
    onChange(next.value);
    buttonRefs.current[nextIdx]?.focus();
  };

  return (
    <aside
      className="pointer-events-auto flex h-full w-14 shrink-0 flex-col border-e border-border/60 bg-background/90 shadow-sm backdrop-blur-sm"
      aria-label={msg("explore.filter.aria")}
    >
      <div
        role="radiogroup"
        aria-label={msg("explore.filter.aria")}
        className="flex flex-1 flex-col items-center gap-1 p-2"
      >
        {FILTERS.map((f, idx) => {
          const active = f.value === value;
          const count = counts[f.value];
          const Icon = f.icon;
          const label = `${msg(f.labelKey)} · ${count}`;
          return (
            <Tooltip key={f.value}>
              <TooltipTrigger asChild>
                <button
                  ref={(el) => {
                    buttonRefs.current[idx] = el;
                  }}
                  type="button"
                  role="radio"
                  aria-label={label}
                  aria-checked={active}
                  tabIndex={active ? 0 : -1}
                  onClick={() => onChange(f.value)}
                  onKeyDown={(e) => handleKeyDown(e, idx)}
                  className={`group relative inline-flex size-10 items-center justify-center rounded-md transition-[background-color,color,box-shadow,transform] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/45 ${
                    active
                      ? "bg-background text-foreground shadow-sm"
                      : "cursor-pointer text-muted-foreground hover:bg-background/60 hover:text-foreground"
                  }`}
                >
                  <Icon className="size-4" aria-hidden="true" />
                  <span
                    className={`absolute -end-1 -top-1 inline-flex min-w-4 items-center justify-center rounded-full border border-background px-1 text-[9px] font-bold tabular-nums ${
                      active
                        ? "bg-[#3D2E22] text-background"
                        : "bg-muted text-muted-foreground"
                    }`}
                    dir="ltr"
                  >
                    {count}
                  </span>
                </button>
              </TooltipTrigger>
              <TooltipContent side="left" sideOffset={8}>
                {label}
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </aside>
  );
}

function FilteredEmptyOverlay({ onClear }: { onClear: () => void }) {
  return (
    <motion.div
      dir="rtl"
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 4 }}
      transition={{ duration: 0.18, ease: [0.2, 0.8, 0.2, 1] }}
      className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center"
    >
      <div className="pointer-events-auto flex flex-col items-center gap-3 rounded-md border border-border/70 bg-background/95 px-5 py-4 backdrop-blur-sm">
        <p className="text-xs text-foreground/80">{msg("explore.filter.no_match")}</p>
        <button
          type="button"
          onClick={onClear}
          className="inline-flex items-center gap-1.5 rounded-sm border border-border bg-transparent px-3 py-1 text-[11px] text-foreground transition-colors cursor-pointer hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/25 focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          {msg("explore.filter.clear")}
        </button>
      </div>
    </motion.div>
  );
}

function ActiveFilterChips({
  models,
  optimizers,
  types,
  dateFrom,
  dateTo,
  onRemove,
  onClearDates,
  onClearAll,
}: {
  models: string[];
  optimizers: string[];
  types: string[];
  dateFrom: string | null;
  dateTo: string | null;
  onRemove: (kind: "model" | "optimizer" | "type", value: string) => void;
  onClearDates: () => void;
  onClearAll: () => void;
}) {
  const total =
    models.length +
    optimizers.length +
    types.length +
    (dateFrom ? 1 : 0) +
    (dateTo ? 1 : 0);
  if (total === 0) return null;

  const typeLabels: Record<string, string> = {
    run: msg("explore.filter.run"),
    grid_search: msg("explore.filter.grid"),
  };
  const dateRangeLabel = formatDateRangeLabel(dateFrom, dateTo);

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center gap-1.5 px-1">
      {models.map((v) => (
        <FilterChip
          key={`m:${v}`}
          label={v}
          dir="ltr"
          onRemove={() => onRemove("model", v)}
        />
      ))}
      {optimizers.map((v) => (
        <FilterChip
          key={`o:${v}`}
          label={v}
          dir="ltr"
          onRemove={() => onRemove("optimizer", v)}
        />
      ))}
      {types.map((v) => (
        <FilterChip
          key={`t:${v}`}
          label={typeLabels[v] ?? v}
          dir="rtl"
          onRemove={() => onRemove("type", v)}
        />
      ))}
      {dateRangeLabel && (
        <FilterChip
          label={dateRangeLabel}
          dir="ltr"
          onRemove={onClearDates}
        />
      )}
      {total > 1 && (
        <button
          type="button"
          onClick={onClearAll}
          className="ms-1 rounded-md px-1.5 py-0.5 text-[12px] text-foreground/55 underline-offset-4 transition-colors cursor-pointer hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/45"
        >
          {msg("explore.filters.clear")}
        </button>
      )}
    </div>
  );
}

function formatDateRangeLabel(
  from: string | null,
  to: string | null,
): string | null {
  if (!from && !to) return null;
  const fromLabel = (from && formatDisplayDate(from)) ?? "…";
  const toLabel = (to && formatDisplayDate(to)) ?? "…";
  return `${fromLabel} – ${toLabel}`;
}

function FilterChip({
  label,
  dir,
  onRemove,
}: {
  label: string;
  dir: "ltr" | "rtl";
  onRemove: () => void;
}) {
  return (
    <span
      dir={dir}
      className="group inline-flex items-center gap-1 rounded-full border border-border bg-background py-1 ps-2.5 pe-1 text-[12px] text-foreground/80 transition-colors hover:border-foreground/30"
    >
      <span className="tabular-nums">{label}</span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={formatMsg("explore.filters.chip.remove", { label })}
        className="inline-flex size-5 items-center justify-center rounded-full text-foreground/45 transition-colors cursor-pointer hover:bg-foreground/10 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/45"
      >
        <X className="size-3" aria-hidden="true" />
      </button>
    </span>
  );
}

function collectDistinct(
  points: PublicDashboardPoint[],
  key: "winning_model" | "optimizer_name",
): string[] {
  const set = new Set<string>();
  for (const p of points) {
    const v = p[key];
    if (typeof v === "string" && v.length > 0) set.add(v);
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}
