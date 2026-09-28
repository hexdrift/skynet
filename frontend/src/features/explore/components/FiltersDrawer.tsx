"use client";

import { Skeleton } from "@/shared/ui/skeleton";
import { CountPill } from "@/shared/ui/count-badge";
import * as React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { CaretDown, Check, CircleNotch, MagnifyingGlass, X } from "@/shared/ui/icons";
import type { FacetDimension, FacetOption } from "@/shared/lib/api";
import { modelDisplayName } from "@/shared/lib/formatters";
import { msg, formatMsg } from "@/shared/lib/messages";
import { getActiveDir, getActiveIntlLocale } from "@/shared/lib/runtime-locale";
import { cn } from "@/shared/lib/utils";
import { useIsPhone } from "@/shared/hooks/use-device-class";
import { Button } from "@/shared/ui/primitives/button";
import { Sheet, SheetContent, SheetTitle } from "@/shared/ui/primitives/sheet";
import { TooltipButton } from "@/shared/ui/tooltip-button";
import { SkynetDatePicker } from "@/shared/ui/skynet-date-picker";
import { CheckboxIndicator } from "@/shared/ui/select-checkbox";
import { useIsWideViewport } from "../hooks/use-wide-viewport";
import { pickerRows } from "../lib/facet-options";
import { DATE_PRESETS, lastDaysRange, matchingPreset } from "../lib/date-range";
import { optimizerDisplayName } from "../lib/format";

/** A field in the panel; the facet dimensions plus the date range. */
export type DrawerField = FacetDimension | "date";

interface FiltersPanelProps {
  /** The field expanded in place; `null` when all are collapsed. */
  openField: DrawerField | null;
  onOpenFieldChange: (next: DrawerField | null) => void;
  /** The open field's value search; owned by the caller so it resets on close. */
  facetQuery: string;
  onFacetQueryChange: (next: string) => void;
  /** The open field's values: the busiest ones for the current context, or the ones matching `facetQuery`. */
  options: FacetOption[];
  /** Distinct values the open field's dimension holds in the current context. */
  total: number;
  loading: boolean;
  /** Whether the open field's ranked list can grow further before search is the only way on. */
  canShowMore: boolean;
  onShowMore: () => void;
  selectedModels: string[];
  selectedOptimizers: string[];
  selectedTypes: string[];
  selectedModules: string[];
  dateFrom: string | null;
  dateTo: string | null;
  /** Live result count for the current query + filters. */
  resultTotal: number;
  resultsLoading: boolean;
  onChangeModels: (next: string[]) => void;
  onChangeOptimizers: (next: string[]) => void;
  onChangeTypes: (next: string[]) => void;
  onChangeModules: (next: string[]) => void;
  onChangeDateRange: (from: string | null, to: string | null) => void;
  /** Wipes every structured filter (the free-text query stays). */
  onClearAll: () => void;
}

interface FiltersHostProps extends FiltersPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const TYPE_VALUES: ReadonlyArray<{
  value: string;
  labelKey: Parameters<typeof msg>[0];
}> = [
  { value: "run", labelKey: "explore.filter.run" },
  { value: "grid_search", labelKey: "explore.filter.grid" },
];

/** Display label for a run-type value; unknown values fall back to the raw id. */
function typeLabel(value: string): string {
  const entry = TYPE_VALUES.find((t) => t.value === value);
  return entry ? msg(entry.labelKey) : value;
}

const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/45";

const SEARCHABLE: ReadonlyArray<{
  dimension: Exclude<FacetDimension, "types">;
  displayName: (value: string) => string;
  /** Model and optimizer ids are Latin identifiers; module names are free text. */
  dir: "ltr" | "auto";
}> = [
  { dimension: "models", displayName: modelDisplayName, dir: "ltr" },
  { dimension: "modules", displayName: (v) => v, dir: "auto" },
  { dimension: "optimizers", displayName: optimizerDisplayName, dir: "ltr" },
];

function useNumberFormat() {
  return React.useMemo(() => new Intl.NumberFormat(getActiveIntlLocale()), []);
}

function useDayFormat() {
  return React.useMemo(() => {
    const formatter = new Intl.DateTimeFormat(getActiveIntlLocale(), {
      dateStyle: "medium",
      timeZone: "UTC",
    });
    return (iso: string) => formatter.format(new Date(`${iso}T00:00:00Z`));
  }, []);
}

/** The applied range as words: its preset's name when it is one, else the days. */
function dateSummary(
  from: string | null,
  to: string | null,
  formatDay: (iso: string) => string,
): string | null {
  const preset = matchingPreset(from, to);
  if (preset !== null) return msg(`explore.filters.date.preset.${preset}d`);
  if (from && to) {
    return formatMsg("explore.filters.date.range", { from: formatDay(from), to: formatDay(to) });
  }
  if (from) return `${msg("explore.filters.date.from")} ${formatDay(from)}`;
  if (to) return `${msg("explore.filters.date.to")} ${formatDay(to)}`;
  return null;
}

/**
 * Structured filtering as a panel of select-style fields, one per dimension,
 * built for dimensions that can hold thousands of distinct values (models,
 * above all). Each field shows only its value until opened; opening expands
 * it in place — no floating layer inside the panel, one scroll, the other
 * fields still in view — into a search box and the busiest values for the
 * current context ("Top 8 of 1,240"), ranked by the number of runs each
 * would leave alongside the other active filters. "Show more" pages the
 * ranked list in steps; typing searches the whole dimension server-side; and
 * the selection stays pinned at the top of its list however far it ranks.
 * Every pick applies immediately.
 *
 * The panel always lives in the shared sheet. On a wide desktop that sheet is
 * non-modal — no scrim, the results stay live beside it — so it needs no
 * footer. Narrower, the sheet is a modal takeover (a bottom sheet on phones)
 * whose footer button carries the live count out to the hidden results.
 */
function FiltersPanel({
  showFooter,
  onClose,
  openField,
  onOpenFieldChange,
  facetQuery,
  onFacetQueryChange,
  options,
  total,
  loading,
  canShowMore,
  onShowMore,
  selectedModels,
  selectedOptimizers,
  selectedTypes,
  selectedModules,
  dateFrom,
  dateTo,
  resultTotal,
  resultsLoading,
  onChangeModels,
  onChangeOptimizers,
  onChangeTypes,
  onChangeModules,
  onChangeDateRange,
  onClearAll,
}: FiltersPanelProps & {
  /** The footer with Reset + "Show N runs"; shown only when the results are hidden behind the sheet. */
  showFooter: boolean;
  onClose: () => void;
}) {
  const selectedBy: Record<FacetDimension, string[]> = {
    models: selectedModels,
    optimizers: selectedOptimizers,
    types: selectedTypes,
    modules: selectedModules,
  };
  const changeBy: Record<FacetDimension, (next: string[]) => void> = {
    models: onChangeModels,
    optimizers: onChangeOptimizers,
    types: onChangeTypes,
    modules: onChangeModules,
  };
  const dateCount = (dateFrom ? 1 : 0) + (dateTo ? 1 : 0);
  const totalActive =
    selectedModels.length +
    selectedOptimizers.length +
    selectedTypes.length +
    selectedModules.length +
    dateCount;
  // A field's empty list means "ruled out by the other filters" only when
  // there are other filters; with none active, it means the scope has none.
  const othersActive = (own: number) => totalActive - own > 0;
  const toggleField = (field: DrawerField) => onOpenFieldChange(openField === field ? null : field);
  const numberFormat = useNumberFormat();
  const formatDay = useDayFormat();
  const gutter = "px-6";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className={cn("flex flex-row items-center justify-between gap-3 pt-5 pb-3", gutter)}>
        <SheetTitle>{msg("explore.filters.title")}</SheetTitle>
        <button
          type="button"
          onClick={onClose}
          aria-label={msg("explore.filters.close")}
          className="close-button shrink-0"
        >
          <X aria-hidden="true" />
        </button>
      </div>

      <div className={cn("flex-1 overflow-y-auto pb-4", gutter)}>
        <div className="divide-y divide-border/60 border-y border-border/60">
          {SEARCHABLE.map(({ dimension, displayName, dir }) => (
            <FacetField
              key={dimension}
              dimension={dimension}
              displayName={displayName}
              dir={dir}
              open={openField === dimension}
              onToggle={() => toggleField(dimension)}
              query={facetQuery}
              onQueryChange={onFacetQueryChange}
              options={openField === dimension ? options : []}
              total={openField === dimension ? total : 0}
              loading={openField === dimension && loading}
              canShowMore={openField === dimension && canShowMore}
              onShowMore={onShowMore}
              selected={selectedBy[dimension]}
              onChange={changeBy[dimension]}
              othersActive={othersActive(selectedBy[dimension].length)}
            />
          ))}
          <TypeField
            open={openField === "types"}
            onToggle={() => toggleField("types")}
            options={openField === "types" ? options : []}
            selected={selectedTypes}
            onChange={onChangeTypes}
          />
          <DateField
            open={openField === "date"}
            onToggle={() => toggleField("date")}
            dateFrom={dateFrom}
            dateTo={dateTo}
            onChange={onChangeDateRange}
            formatDay={formatDay}
          />
        </div>
      </div>

      {showFooter && (
        <div
          className={cn(
            "flex items-center justify-between gap-3 border-t border-border/60 py-4",
            gutter,
          )}
        >
          <Button
            type="button"
            variant="ghost"
            size="lg"
            onClick={onClearAll}
            disabled={totalActive === 0}
          >
            {msg("explore.filters.reset")}
          </Button>
          <Button type="button" size="lg" onClick={onClose} className="min-w-[9.5rem]">
            {resultsLoading && <CircleNotch className="size-3.5 animate-spin" aria-hidden="true" />}
            <span className="tabular-nums">
              {resultTotal === 1
                ? msg("explore.filters.show_results_one")
                : formatMsg("explore.filters.show_results", {
                    n: numberFormat.format(resultTotal),
                  })}
            </span>
          </Button>
        </div>
      )}
    </div>
  );
}

/**
 * The panel's one host: the shared sheet. On a wide desktop it is non-modal —
 * no scrim, sitting below the header on the edge opposite the sidebar, so the
 * results stay live and interactive beside it and it commits every pick
 * immediately (no footer). On a phone it is a bottom sheet, and on a tablet a
 * side sheet; both are modal takeovers with the footer's "Show N runs" button.
 * Escape first collapses the open field, then closes the sheet.
 */
export function FiltersDrawer({ open, onOpenChange, ...panel }: FiltersHostProps) {
  const isRtl = getActiveDir() === "rtl";
  const isPhone = useIsPhone();
  const live = useIsWideViewport();

  return (
    <Sheet open={open} onOpenChange={onOpenChange} modal={!live}>
      <SheetContent
        side={isPhone ? "bottom" : isRtl ? "left" : "right"}
        showCloseButton={false}
        showOverlay={!live}
        aria-describedby={undefined}
        style={live ? { top: "var(--header-height, 53px)", height: "auto" } : undefined}
        onEscapeKeyDown={(event) => {
          if (panel.openField === null) return;
          event.preventDefault();
          panel.onOpenFieldChange(null);
        }}
        onInteractOutside={live ? (event) => event.preventDefault() : undefined}
        className={
          isPhone
            ? "max-h-[88dvh] w-full gap-0 rounded-t-2xl border-border bg-background p-0 pb-[env(safe-area-inset-bottom)]"
            : "w-full !max-w-md gap-0 border-border bg-background p-0"
        }
      >
        <FiltersPanel showFooter={!live} onClose={() => onOpenChange(false)} {...panel} />
      </SheetContent>
    </Sheet>
  );
}

/**
 * One line of plain text naming the applied filters, for when the panel is
 * closed: "Model gpt-4o +1 · Type Run", with a single clear action.
 */
export function FilterSummary({
  models,
  optimizers,
  types,
  modules,
  dateFrom,
  dateTo,
  onOpen,
  onClearAll,
}: {
  models: string[];
  optimizers: string[];
  types: string[];
  modules: string[];
  dateFrom: string | null;
  dateTo: string | null;
  onOpen: () => void;
  onClearAll: () => void;
}) {
  const formatDay = useDayFormat();
  const parts: Array<{ label: string; value: string; more: number }> = [];
  const push = (label: string, selected: string[], displayName: (v: string) => string) => {
    const [first] = selected;
    if (first === undefined) return;
    parts.push({ label, value: displayName(first), more: selected.length - 1 });
  };
  push(msg("explore.filters.trigger.models"), models, modelDisplayName);
  push(msg("explore.filters.trigger.modules"), modules, (v) => v);
  push(msg("explore.filters.trigger.optimizers"), optimizers, optimizerDisplayName);
  push(msg("explore.filters.trigger.types"), types, typeLabel);
  const date = dateSummary(dateFrom, dateTo, formatDay);
  if (date) parts.push({ label: msg("explore.filters.trigger.date"), value: date, more: 0 });
  if (parts.length === 0) return null;

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 px-1 text-[12px] text-foreground/55">
      <button
        type="button"
        onClick={onOpen}
        className={`flex min-w-0 max-w-full cursor-pointer flex-wrap items-center gap-x-2 gap-y-1 rounded-md text-start hover:text-foreground/80 ${FOCUS_RING}`}
      >
        {parts.map((part, index) => (
          <span key={part.label} className="inline-flex min-w-0 items-center gap-1">
            {index > 0 && (
              <span className="me-1 text-foreground/30" aria-hidden="true">
                ·
              </span>
            )}
            <span>{part.label}</span>
            <span className="max-w-[14rem] truncate font-medium text-foreground/80">
              {part.value}
            </span>
            {part.more > 0 && <span className="tabular-nums">+{part.more}</span>}
          </span>
        ))}
      </button>
      <button
        type="button"
        onClick={onClearAll}
        className={`cursor-pointer rounded-md underline-offset-2 hover:text-foreground hover:underline ${FOCUS_RING}`}
      >
        {msg("explore.filters.clear")}
      </button>
    </div>
  );
}

/**
 * A select-style row that expands in place: closed, it is the field's name
 * and its value ("Any" when unset); open, its controls unfold beneath.
 */
function FieldRow({
  label,
  summary,
  count = 0,
  onClear,
  open,
  onToggle,
  children,
}: {
  label: string;
  summary: string | null;
  /** How many values are selected in this field; drives the count chip. */
  count?: number;
  /** Clears the field's whole selection; the clear control shows only when set. */
  onClear?: () => void;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  const panelId = React.useId();
  const reduceMotion = useReducedMotion();
  const numberFormat = useNumberFormat();
  const buttonRef = React.useRef<HTMLButtonElement>(null);
  const wasOpen = React.useRef(open);
  // Collapsing unmounts whatever was focused inside (Escape from the search
  // box, say); land focus on the row rather than letting it fall to the body.
  React.useLayoutEffect(() => {
    if (wasOpen.current && !open && document.activeElement === document.body) {
      buttonRef.current?.focus();
    }
    wasOpen.current = open;
  }, [open]);

  return (
    <div className={cn("transition-colors", open && "-mx-3 rounded-lg bg-accent/40 px-3")}>
      <div className="flex h-[52px] w-full items-center gap-1.5 lg:h-12">
        <button
          ref={buttonRef}
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={onToggle}
          className={`flex h-full min-w-0 flex-1 cursor-pointer items-center gap-3 rounded-md text-start ${FOCUS_RING}`}
        >
          <span className="w-[5.5rem] shrink-0 text-[13px] text-foreground/60">{label}</span>
          <span
            className={cn(
              "min-w-0 flex-1 truncate text-[13.5px]",
              summary === null ? "text-foreground/40" : "font-medium text-foreground",
            )}
          >
            {summary ?? msg("explore.filters.field.any")}
          </span>
          {count > 1 && <CountPill className="shrink-0">{numberFormat.format(count)}</CountPill>}
        </button>
        {onClear && (
          <TooltipButton tooltip={msg("explore.filters.picker.clear")} side="top">
            <button
              type="button"
              onClick={onClear}
              aria-label={msg("explore.filters.picker.clear")}
              className="close-button [--close-btn-size:20px] [--close-btn-radius:6px] [--close-btn-icon:12px] shrink-0"
            >
              <X aria-hidden="true" />
            </button>
          </TooltipButton>
        )}
        <button
          type="button"
          tabIndex={-1}
          aria-hidden="true"
          onClick={onToggle}
          className="flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-md text-foreground/45"
        >
          <CaretDown
            className={cn("size-3 transition-transform duration-200", open && "rotate-180")}
            aria-hidden="true"
          />
        </button>
      </div>
      {/* Reveal on a height+opacity transition so the fields glide open and
          shut instead of snapping. The negative inline margin matches the
          list's own bleed so overflow-hidden clips the reveal vertically
          without shaving the row highlights at the sides. */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="content"
            id={panelId}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: reduceMotion ? 0 : 0.24, ease: [0.16, 1, 0.3, 1] }}
            className="-mx-3 overflow-hidden px-3"
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/**
 * A searchable multi-select over one dimension: a combobox input that drives
 * a listbox, with the arrow keys walking the rows, Enter toggling, and the
 * footer saying how much of the dimension is in view, with "Show more" while
 * the ranked list can still grow.
 */
function FacetField({
  dimension,
  displayName,
  dir,
  open,
  onToggle,
  query,
  onQueryChange,
  options,
  total,
  loading,
  canShowMore,
  onShowMore,
  selected,
  onChange,
  othersActive,
}: {
  dimension: Exclude<FacetDimension, "types">;
  displayName: (value: string) => string;
  dir: "ltr" | "auto";
  open: boolean;
  onToggle: () => void;
  query: string;
  onQueryChange: (next: string) => void;
  options: FacetOption[];
  total: number;
  loading: boolean;
  canShowMore: boolean;
  onShowMore: () => void;
  selected: string[];
  onChange: (next: string[]) => void;
  othersActive: boolean;
}) {
  const section = msg(`explore.filters.section.${dimension}`);
  const rows = React.useMemo(() => pickerRows(options, selected), [options, selected]);
  const [highlight, setHighlight] = React.useState(0);
  const activeIndex = rows.length === 0 ? -1 : Math.min(highlight, rows.length - 1);
  const listRef = React.useRef<HTMLUListElement>(null);
  const listId = React.useId();
  const optionId = (index: number) => `${listId}-${index}`;
  const searching = query.trim().length > 0;
  const numberFormat = useNumberFormat();
  // On a phone, focusing the search box on expand would raise the keyboard
  // over the very list the user opened; the top values are usually enough.
  const isPhone = useIsPhone();
  const [first] = selected;

  const toggle = (value: string) => {
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  };
  const moveHighlight = (next: number) => {
    setHighlight(next);
    listRef.current?.querySelector(`[data-index="${next}"]`)?.scrollIntoView({ block: "nearest" });
  };
  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (rows.length === 0) return;
    const last = rows.length - 1;
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        moveHighlight(activeIndex >= last ? 0 : activeIndex + 1);
        break;
      case "ArrowUp":
        event.preventDefault();
        moveHighlight(activeIndex <= 0 ? last : activeIndex - 1);
        break;
      case "Home":
        event.preventDefault();
        moveHighlight(0);
        break;
      case "End":
        event.preventDefault();
        moveHighlight(last);
        break;
      case "Enter":
        event.preventDefault();
        if (rows[activeIndex]) toggle(rows[activeIndex].value);
        break;
    }
  };

  // Beyond the listed slice there is more to find by paging or typing; say so
  // only when it is true, since "Top 8 of 8" would just be noise.
  const meta =
    total > options.length
      ? formatMsg(searching ? "explore.filters.group.matches" : "explore.filters.group.top", {
          shown: numberFormat.format(options.length),
          total: numberFormat.format(total),
        })
      : null;
  const emptyMessage = searching
    ? msg("explore.filters.section.no_search_match")
    : othersActive
      ? msg("explore.filters.section.none_in_selection")
      : msg("explore.filters.empty_section");

  return (
    <FieldRow
      label={msg(`explore.filters.trigger.${dimension}`)}
      summary={first === undefined ? null : displayName(first)}
      count={selected.length}
      onClear={selected.length > 0 ? () => onChange([]) : undefined}
      open={open}
      onToggle={onToggle}
    >
      <div className="flex flex-col pb-2">
        <div className="flex h-10 items-center gap-2 rounded-lg border border-border bg-background px-3">
          <MagnifyingGlass className="size-3.5 shrink-0 text-foreground/45" aria-hidden="true" />
          <input
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={activeIndex >= 0 ? optionId(activeIndex) : undefined}
            aria-autocomplete="list"
            aria-label={formatMsg("explore.filters.section.search", { section })}
            autoComplete="off"
            autoFocus={!isPhone}
            spellCheck={false}
            value={query}
            onChange={(event) => {
              onQueryChange(event.target.value);
              setHighlight(0);
            }}
            onKeyDown={onKeyDown}
            placeholder={msg(`explore.filters.picker.placeholder.${dimension}`)}
            className="h-full min-w-0 flex-1 bg-transparent text-[13px] text-foreground outline-none placeholder:text-foreground/40"
          />
          {searching && (
            <button
              type="button"
              onClick={() => {
                onQueryChange("");
                setHighlight(0);
              }}
              aria-label={msg("explore.filters.search.clear")}
              className="size-7 inline-flex shrink-0 cursor-pointer items-center justify-center rounded-lg text-foreground/55 transition-[background-color,color] hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/45"
            >
              <X className="size-3.5" aria-hidden="true" />
            </button>
          )}
        </div>

        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          aria-multiselectable="true"
          aria-label={section}
          aria-busy={loading}
          className="-mx-3 mt-1 max-h-[min(40vh,18rem)] overflow-y-auto py-1"
        >
          {rows.map((row, index) => (
            <li
              key={row.value}
              id={optionId(index)}
              role="option"
              aria-selected={row.checked}
              data-index={index}
              onMouseMove={() => setHighlight(index)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => toggle(row.value)}
              className={cn(
                "group flex h-11 cursor-pointer select-none items-center gap-2.5 px-3 text-[13px] lg:h-9",
                index === activeIndex && "bg-accent",
              )}
            >
              <CheckboxIndicator checked={row.checked} />
              <span dir={dir} className="min-w-0 flex-1 truncate text-foreground">
                {displayName(row.value)}
              </span>
              {row.count !== null && (
                <span className="shrink-0 text-[12px] tabular-nums text-foreground/45">
                  {numberFormat.format(row.count)}
                </span>
              )}
            </li>
          ))}
          {rows.length === 0 &&
            (loading ? (
              Array.from({ length: 5 }, (_, index) => (
                <li
                  key={index}
                  className="flex h-11 items-center gap-2.5 px-3 lg:h-9"
                  aria-hidden="true"
                >
                  <span className="size-5 shrink-0 rounded-md border border-border/70 bg-background" />
                  <Skeleton
                    height={10}
                    width={`${45 + ((index * 17) % 35)}%`}
                    containerClassName="flex-1 leading-none"
                  />
                </li>
              ))
            ) : (
              <li className="px-3 py-4 text-center text-[12.5px] text-foreground/50">
                {emptyMessage}
              </li>
            ))}
        </ul>

        {meta !== null && (
          <div className="flex h-8 items-center gap-2 text-[11.5px] text-foreground/50">
            <span className="tabular-nums">{meta}</span>
            {canShowMore && (
              <button
                type="button"
                onClick={onShowMore}
                disabled={loading}
                className={`inline-flex cursor-pointer items-center gap-1.5 rounded-md px-1 font-medium text-foreground/70 hover:text-foreground disabled:cursor-default disabled:opacity-60 ${FOCUS_RING}`}
              >
                {loading && options.length > 0 && (
                  <CircleNotch className="size-3 animate-spin" aria-hidden="true" />
                )}
                {msg("explore.filters.show_more")}
              </button>
            )}
          </div>
        )}
      </div>
    </FieldRow>
  );
}

/**
 * Run types are a fixed trio, so their field skips the search box and lists
 * all three in a stable order with the fetched counts attached. Until a fetch
 * has answered the counts are unknown rather than zero, and a type with no
 * runs in the current context is disabled instead of hidden.
 */
function TypeField({
  open,
  onToggle,
  options,
  selected,
  onChange,
}: {
  open: boolean;
  onToggle: () => void;
  options: FacetOption[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const numberFormat = useNumberFormat();
  const [first] = selected;
  const toggle = (value: string) => {
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  };
  return (
    <FieldRow
      label={msg("explore.filters.trigger.types")}
      summary={first === undefined ? null : typeLabel(first)}
      count={selected.length}
      onClear={selected.length > 0 ? () => onChange([]) : undefined}
      open={open}
      onToggle={onToggle}
    >
      <div className="flex flex-col pb-2">
        <div role="group" aria-label={msg("explore.filters.section.types")} className="-mx-3">
          {TYPE_VALUES.map((type) => {
            const checked = selected.includes(type.value);
            const count =
              options.length === 0
                ? null
                : (options.find((o) => o.value === type.value)?.count ?? 0);
            const disabled = count === 0 && !checked;
            return (
              <button
                key={type.value}
                type="button"
                role="checkbox"
                aria-checked={checked}
                disabled={disabled}
                onClick={() => toggle(type.value)}
                className={cn(
                  "group flex h-11 w-full cursor-pointer items-center gap-2.5 px-3 text-[13px] text-foreground hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent lg:h-9",
                  FOCUS_RING,
                )}
              >
                <CheckboxIndicator checked={checked} />
                <span className="min-w-0 flex-1 truncate text-start">{msg(type.labelKey)}</span>
                {count !== null && (
                  <span className="shrink-0 text-[12px] tabular-nums text-foreground/45">
                    {numberFormat.format(count)}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </FieldRow>
  );
}

/**
 * The date range: relative presets first, since "last 30 days" is what is
 * usually meant, then the two pickers for an exact range. A preset is a
 * toggle — picking the active one again clears the range — and it shows as
 * active only while the stored days still resolve to it today.
 */
function DateField({
  open,
  onToggle,
  dateFrom,
  dateTo,
  onChange,
  formatDay,
}: {
  open: boolean;
  onToggle: () => void;
  dateFrom: string | null;
  dateTo: string | null;
  onChange: (from: string | null, to: string | null) => void;
  formatDay: (iso: string) => string;
}) {
  const activePreset = matchingPreset(dateFrom, dateTo);
  const dateCount = (dateFrom ? 1 : 0) + (dateTo ? 1 : 0);
  return (
    <FieldRow
      label={msg("explore.filters.trigger.date")}
      summary={dateSummary(dateFrom, dateTo, formatDay)}
      onClear={dateCount > 0 ? () => onChange(null, null) : undefined}
      open={open}
      onToggle={onToggle}
    >
      <div className="flex flex-col pb-4">
        <div role="group" aria-label={msg("explore.filters.section.date")} className="-mx-3">
          {DATE_PRESETS.map((days) => {
            const active = activePreset === days;
            return (
              <button
                key={days}
                type="button"
                aria-pressed={active}
                onClick={() => {
                  if (active) {
                    onChange(null, null);
                  } else {
                    const range = lastDaysRange(days);
                    onChange(range.from, range.to);
                  }
                }}
                className={cn(
                  "flex h-11 w-full cursor-pointer items-center gap-2.5 px-3 text-[13px] text-foreground hover:bg-accent lg:h-9",
                  active && "font-medium",
                  FOCUS_RING,
                )}
              >
                <span className="min-w-0 flex-1 truncate text-start">
                  {msg(`explore.filters.date.preset.${days}d`)}
                </span>
                {active && <Check className="size-3.5 shrink-0" aria-hidden="true" />}
              </button>
            );
          })}
        </div>
        <span className="mt-3 mb-2 text-[11.5px] font-medium uppercase tracking-[0.08em] text-foreground/50">
          {msg("explore.filters.date.custom")}
        </span>
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-[11.5px] text-foreground/55">
              {msg("explore.filters.date.from")}
            </span>
            <SkynetDatePicker
              value={dateFrom}
              onChange={(next) => onChange(next, dateTo)}
              max={dateTo}
              ariaLabel={msg("explore.filters.date.from")}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[11.5px] text-foreground/55">
              {msg("explore.filters.date.to")}
            </span>
            <SkynetDatePicker
              value={dateTo}
              onChange={(next) => onChange(dateFrom, next)}
              min={dateFrom}
              ariaLabel={msg("explore.filters.date.to")}
            />
          </label>
        </div>
      </div>
    </FieldRow>
  );
}
