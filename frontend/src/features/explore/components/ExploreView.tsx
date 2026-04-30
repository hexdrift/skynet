"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CircleDot, Grid2x2, Layers, Plus } from "lucide-react";
import type { PublicDashboardPoint } from "@/shared/lib/api";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/shared/ui/primitives/tooltip";
import { usePublicDashboard } from "../hooks/use-public-dashboard";
import { ScatterCanvas, type ExploreFilter } from "./ScatterCanvas";
import { ExploreDetailPanel } from "./ExploreDetailPanel";
import { GranularitySlider } from "./GranularitySlider";
import { deriveLevelCounts } from "../lib/format";
import { msg } from "@/shared/lib/messages";
import { registerTutorialHook } from "@/features/tutorial";

// Default slider position when ?cluster= is absent. Index 1 corresponds to
// the second-coarsest cut (typically 4 clusters) — coarse enough to read
// at a glance, fine enough to see structure.
const DEFAULT_GRANULARITY_LEVEL = 1;

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
  const selectableIndices = React.useMemo(() => FILTERS.map((f, i) => ({ f, i })), []);

  const handleKeyDown = (e: React.KeyboardEvent, currentIdx: number) => {
    let delta = 0;
    if (e.key === "ArrowLeft" || e.key === "ArrowDown") delta = 1;
    else if (e.key === "ArrowRight" || e.key === "ArrowUp") delta = -1;
    else if (e.key === "Home") {
      e.preventDefault();
      const first = selectableIndices[0];
      if (first) {
        onChange(first.f.value);
        buttonRefs.current[first.i]?.focus();
      }
      return;
    } else if (e.key === "End") {
      e.preventDefault();
      const last = selectableIndices[selectableIndices.length - 1];
      if (last) {
        onChange(last.f.value);
        buttonRefs.current[last.i]?.focus();
      }
      return;
    } else {
      return;
    }
    e.preventDefault();
    const currentSelectablePos = selectableIndices.findIndex(({ i }) => i === currentIdx);
    if (currentSelectablePos === -1 || selectableIndices.length === 0) return;
    const len = selectableIndices.length;
    const nextPos = (currentSelectablePos + delta + len) % len;
    const nextEntry = selectableIndices[nextPos];
    if (!nextEntry) return;
    onChange(nextEntry.f.value);
    buttonRefs.current[nextEntry.i]?.focus();
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

export function ExploreView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { points: realPoints, meta, loading, error } = usePublicDashboard();
  const [demoPoints, setDemoPoints] = React.useState<PublicDashboardPoint[] | null>(null);
  const points = demoPoints ?? realPoints;

  React.useEffect(() => registerTutorialHook("setDemoExplorePoints", setDemoPoints), []);
  React.useEffect(() => {
    const onExit = () => setDemoPoints(null);
    window.addEventListener("tutorial-exited", onExit);
    return () => window.removeEventListener("tutorial-exited", onExit);
  }, []);

  const levelCounts = React.useMemo(
    () => meta?.level_cluster_counts ?? deriveLevelCounts(points),
    [meta, points],
  );
  const maxLevelIdx = Math.max(0, levelCounts.length - 1);

  const urlFilter = searchParams.get("filter");
  const urlFocus = searchParams.get("focus");
  const urlCluster = searchParams.get("cluster");
  const filter: ExploreFilter = isExploreFilter(urlFilter) ? urlFilter : "all";
  const selectedId = urlFocus ?? null;
  const parsedCluster = urlCluster !== null ? parseInt(urlCluster, 10) : NaN;
  const granularityLevel = Number.isFinite(parsedCluster)
    ? Math.max(0, Math.min(maxLevelIdx, parsedCluster))
    : Math.min(DEFAULT_GRANULARITY_LEVEL, maxLevelIdx);
  const clusterCount = levelCounts[granularityLevel] ?? 1;

  const updateQuery = React.useCallback(
    (patch: {
      filter?: ExploreFilter | null;
      focus?: string | null;
      cluster?: number | null;
    }) => {
      // Read URL state from the live address bar so back-to-back updates in the
      // same render don't clobber each other (the searchParams hook value is
      // only refreshed between renders).
      const params = new URLSearchParams(
        typeof window !== "undefined" ? window.location.search : "",
      );
      if (patch.filter !== undefined) {
        if (patch.filter && patch.filter !== "all") params.set("filter", patch.filter);
        else params.delete("filter");
      }
      if (patch.focus !== undefined) {
        if (patch.focus) params.set("focus", patch.focus);
        else params.delete("focus");
      }
      if (patch.cluster !== undefined) {
        if (patch.cluster !== null) params.set("cluster", String(patch.cluster));
        else params.delete("cluster");
      }
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router],
  );

  const pointsById = React.useMemo(() => {
    const m = new Map<string, PublicDashboardPoint>();
    for (const p of points) m.set(p.optimization_id, p);
    return m;
  }, [points]);

  const selected = selectedId ? (pointsById.get(selectedId) ?? null) : null;

  const counts: Record<ExploreFilter, number> = React.useMemo(() => {
    const c: Record<ExploreFilter, number> = { all: points.length, run: 0, grid_search: 0 };
    for (const p of points) {
      if (p.optimization_type === "run") c.run += 1;
      else if (p.optimization_type === "grid_search") c.grid_search += 1;
    }
    return c;
  }, [points]);

  const setFilter = React.useCallback(
    (next: ExploreFilter) => {
      const focused = selectedId ? (pointsById.get(selectedId) ?? null) : null;
      const focusOutOfSubset =
        focused && next !== "all" && focused.optimization_type !== next;
      updateQuery(focusOutOfSubset ? { filter: next, focus: null } : { filter: next });
    },
    [selectedId, pointsById, updateQuery],
  );
  const setSelected = React.useCallback(
    (next: string | null) => updateQuery({ focus: next }),
    [updateQuery],
  );
  const setGranularity = React.useCallback(
    (next: number) =>
      updateQuery({ cluster: next === DEFAULT_GRANULARITY_LEVEL ? null : next }),
    [updateQuery],
  );

  React.useEffect(() => {
    if (loading) return;
    if (!selectedId) return;
    if (pointsById.has(selectedId)) return;
    updateQuery({ focus: null });
  }, [loading, selectedId, pointsById, updateQuery]);

  const corpusTotal = points.length;
  const isTrulyEmpty = !loading && !error && corpusTotal === 0;

  return (
    <div dir="rtl" className="pb-16">
      <div className="space-y-6" data-tutorial="explore-canvas">
      {error && (
        <div
          className="flex items-start gap-3 rounded-lg border border-border bg-accent-muted/50 px-4 py-3 text-xs text-foreground"
          role="status"
        >
          <AlertTriangle
            className="mt-0.5 size-4 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
          <span>{error}</span>
        </div>
      )}

      {isTrulyEmpty ? (
        <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 rounded-lg border border-dashed border-border bg-background px-6 py-10 text-center">
          <p className="max-w-[40ch] text-sm text-foreground/80">{msg("explore.empty.title")}</p>
          <Link
            href="/submit"
            className="inline-flex items-center gap-1.5 rounded-md bg-foreground px-3 py-1.5 text-xs font-medium text-background transition-colors hover:bg-foreground/85"
          >
            <Plus className="size-3.5" />
            {msg("explore.empty.cta")}
          </Link>
        </div>
      ) : (
        <section className="space-y-4">
          <div className="relative overflow-hidden rounded-xl border border-border/60 bg-card/70 p-2 shadow-sm">
            <AnimatePresence>
              {!selected && (
                <motion.div
                  key="filter-rail"
                  initial={{ opacity: 0, x: 8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 8 }}
                  transition={{ duration: 0.16, ease: [0.2, 0.8, 0.2, 1] }}
                  className="absolute inset-y-2 start-2 z-20 overflow-hidden rounded-lg"
                >
                  <FilterTabs value={filter} onChange={setFilter} counts={counts} />
                </motion.div>
              )}
            </AnimatePresence>
            <ScatterCanvas
              points={points}
              filter={filter}
              selectedId={selectedId}
              onSelect={setSelected}
              granularityLevel={granularityLevel}
              clusterCount={clusterCount}
              dimmed={selected !== null}
            >
              <AnimatePresence>
                {counts[filter] === 0 && corpusTotal > 0 && selected === null && (
                  <FilteredEmptyOverlay onClear={() => setFilter("all")} />
                )}
              </AnimatePresence>
              {!selected && levelCounts.length >= 2 && (
                <GranularitySlider
                  value={granularityLevel}
                  onChange={setGranularity}
                  levels={levelCounts}
                />
              )}
            </ScatterCanvas>
            <AnimatePresence>
              {selected && (
                <motion.div
                  key="detail-panel"
                  initial={{ opacity: 0, x: 12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 12 }}
                  transition={{ duration: 0.18, ease: [0.2, 0.8, 0.2, 1] }}
                  className="pointer-events-none absolute inset-y-3 start-3 z-20 w-[min(340px,calc(100%-1.5rem))]"
                >
                  <div className="pointer-events-auto h-full">
                    <ExploreDetailPanel point={selected} onClose={() => setSelected(null)} />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </section>
      )}
      </div>
    </div>
  );
}
