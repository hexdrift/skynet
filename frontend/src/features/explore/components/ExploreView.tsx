"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Plus } from "lucide-react";
import { usePublicDashboard } from "../hooks/use-public-dashboard";
import { ScatterCanvas, type ExploreFilter } from "./ScatterCanvas";
import { ExploreDetailPanel } from "./ExploreDetailPanel";
import { msg } from "@/shared/lib/messages";

const COLD_CUTOFF = 1;

const FILTERS: Array<{ value: ExploreFilter; labelKey: Parameters<typeof msg>[0] }> = [
  { value: "all", labelKey: "explore.filter.all" },
  { value: "run", labelKey: "explore.filter.run" },
  { value: "grid_search", labelKey: "explore.filter.grid" },
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
  const selectableIndices = React.useMemo(
    () =>
      FILTERS.map((f, i) => ({ f, i })).filter(
        ({ f }) => !(counts[f.value] === 0 && f.value !== value),
      ),
    [counts, value],
  );

  const handleKeyDown = (e: React.KeyboardEvent, currentIdx: number) => {
    let delta = 0;
    if (e.key === "ArrowLeft" || e.key === "ArrowDown")
      delta = 1; // RTL: left = next
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

  const showing = value !== "all";
  const showingText = showing
    ? msg("explore.filter.showing")
        .replace("{count}", String(counts[value]))
        .replace("{total}", String(counts.all))
    : "";

  return (
    <div className="flex items-end justify-between gap-4 border-b border-[#DDD6CC]/60">
      <div
        role="radiogroup"
        aria-label={msg("explore.filter.aria")}
        className="flex items-end gap-7"
      >
        {FILTERS.map((f, idx) => {
          const active = f.value === value;
          const count = counts[f.value];
          const empty = count === 0 && !active;
          return (
            <button
              key={f.value}
              ref={(el) => {
                buttonRefs.current[idx] = el;
              }}
              type="button"
              role="radio"
              aria-checked={active}
              tabIndex={active ? 0 : -1}
              disabled={empty}
              onClick={() => onChange(f.value)}
              onKeyDown={(e) => handleKeyDown(e, idx)}
              className={`group relative -mb-px pb-2 pt-0.5 cursor-pointer transition-colors disabled:cursor-default focus-visible:outline-none focus-visible:after:absolute focus-visible:after:-inset-x-2 focus-visible:after:-inset-y-1 focus-visible:after:rounded-sm focus-visible:after:ring-2 focus-visible:after:ring-[#3D2E22]/25 focus-visible:after:content-[''] ${
                active
                  ? "text-[#3D2E22]"
                  : empty
                    ? "text-[#C8BFB1]"
                    : "text-[#8C7A6B] hover:text-[#3D2E22]"
              }`}
            >
              <span className="flex items-baseline gap-2">
                <span className="text-[12px] font-medium tracking-tight">{msg(f.labelKey)}</span>
                <span
                  className={`tabular-nums text-[10px] ${
                    active ? "text-[#3D2E22]/55" : empty ? "text-[#C8BFB1]" : "text-[#8C7A6B]"
                  }`}
                  dir="ltr"
                >
                  {count}
                </span>
              </span>
              {active ? (
                <motion.span
                  layoutId="filter-tab-underline"
                  aria-hidden="true"
                  className="absolute inset-x-0 -bottom-px h-[2px] bg-[#3D2E22]"
                  transition={{ duration: 0.25, ease: [0.2, 0.8, 0.2, 1] }}
                />
              ) : (
                <span
                  aria-hidden="true"
                  className="absolute inset-x-0 -bottom-px h-[2px] bg-transparent transition-colors group-hover:bg-[#3D2E22]/20 group-disabled:group-hover:bg-transparent"
                />
              )}
            </button>
          );
        })}
      </div>
      <p
        aria-live="polite"
        className={`pb-2 text-[11px] text-[#8C7A6B] transition-opacity ${
          showing ? "opacity-100" : "opacity-0"
        }`}
      >
        {showingText}
      </p>
    </div>
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
      <div className="pointer-events-auto flex flex-col items-center gap-3 rounded-md border border-[#DDD6CC]/70 bg-[#FAF8F5]/95 px-5 py-4 backdrop-blur-sm">
        <p className="text-xs text-[#3D2E22]/80">{msg("explore.filter.no_match")}</p>
        <button
          type="button"
          onClick={onClear}
          className="inline-flex items-center gap-1.5 rounded-sm border border-[#DDD6CC] bg-transparent px-3 py-1 text-[11px] text-[#3D2E22] transition-colors cursor-pointer hover:bg-[#EDE7DD] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3D2E22]/25 focus-visible:ring-offset-2 focus-visible:ring-offset-[#FAF8F5]"
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
  const { points, loading, error } = usePublicDashboard();

  const urlFilter = searchParams.get("filter");
  const urlFocus = searchParams.get("focus");
  const filter: ExploreFilter = isExploreFilter(urlFilter) ? urlFilter : "all";
  const selectedId = urlFocus ?? null;

  const updateQuery = React.useCallback(
    (patch: { filter?: ExploreFilter | null; focus?: string | null }) => {
      const params = new URLSearchParams(searchParams.toString());
      if (patch.filter !== undefined) {
        if (patch.filter && patch.filter !== "all") params.set("filter", patch.filter);
        else params.delete("filter");
      }
      if (patch.focus !== undefined) {
        if (patch.focus) params.set("focus", patch.focus);
        else params.delete("focus");
      }
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const setFilter = React.useCallback(
    (next: ExploreFilter) => updateQuery({ filter: next }),
    [updateQuery],
  );
  const setSelected = React.useCallback(
    (next: string | null) => updateQuery({ focus: next }),
    [updateQuery],
  );

  const counts: Record<ExploreFilter, number> = React.useMemo(() => {
    const c: Record<ExploreFilter, number> = { all: points.length, run: 0, grid_search: 0 };
    for (const p of points) {
      if (p.optimization_type === "run") c.run += 1;
      else if (p.optimization_type === "grid_search") c.grid_search += 1;
    }
    return c;
  }, [points]);

  const selected = React.useMemo(
    () => points.find((p) => p.optimization_id === selectedId) ?? null,
    [points, selectedId],
  );

  const corpusTotal = points.length;
  const isTrulyEmpty = !loading && !error && corpusTotal === 0;
  const isColdCorpus = !loading && !error && corpusTotal > 0 && corpusTotal < COLD_CUTOFF;

  return (
    <div dir="rtl" className="space-y-10 pb-16" data-tutorial="explore-canvas">
      {error && (
        <div
          className="flex items-start gap-3 rounded-lg border border-[#DDD6CC] bg-[#EDE7DD]/50 px-4 py-3 text-xs text-[#3D2E22]"
          role="status"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[#8C7A6B]" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {isTrulyEmpty ? (
        <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 rounded-lg border border-dashed border-[#DDD6CC] bg-[#FAF8F5] px-6 py-10 text-center">
          <p className="max-w-[40ch] text-sm text-[#3D2E22]/80">{msg("explore.empty.title")}</p>
          <Link
            href="/submit"
            className="inline-flex items-center gap-1.5 rounded-md bg-[#3D2E22] px-3 py-1.5 text-xs font-medium text-[#FAF8F5] transition-colors hover:bg-[#5C4A3A]"
          >
            <Plus className="size-3.5" />
            {msg("explore.empty.cta")}
          </Link>
        </div>
      ) : isColdCorpus ? (
        <div className="flex min-h-[28vh] flex-col items-center justify-center gap-4 rounded-lg border border-dashed border-[#DDD6CC] bg-[#FAF8F5] px-6 py-10 text-center">
          <p className="max-w-[40ch] text-sm text-[#3D2E22]/80">{msg("explore.cold_corpus")}</p>
          <Link
            href="/submit"
            className="inline-flex items-center gap-1.5 rounded-md bg-[#3D2E22] px-3 py-1.5 text-xs font-medium text-[#FAF8F5] transition-colors hover:bg-[#5C4A3A]"
          >
            <Plus className="size-3.5" />
            {msg("explore.empty.cta")}
          </Link>
        </div>
      ) : (
        <section className="space-y-3">
          <FilterTabs value={filter} onChange={setFilter} counts={counts} />
          <div className="relative">
            <ScatterCanvas
              points={points}
              filter={filter}
              selectedId={selectedId}
              focusId={selectedId}
              onSelect={setSelected}
              dimmed={selected !== null}
            >
              <AnimatePresence>
                {counts[filter] === 0 && corpusTotal > 0 && selected === null && (
                  <FilteredEmptyOverlay onClear={() => setFilter("all")} />
                )}
              </AnimatePresence>
            </ScatterCanvas>
            <AnimatePresence mode="wait">
              {selected && (
                <div className="pointer-events-none absolute inset-y-3 start-3 z-10 w-[min(340px,calc(100%-1.5rem))]">
                  <div className="pointer-events-auto h-full">
                    <ExploreDetailPanel point={selected} onClose={() => setSelected(null)} />
                  </div>
                </div>
              )}
            </AnimatePresence>
          </div>
        </section>
      )}
    </div>
  );
}
