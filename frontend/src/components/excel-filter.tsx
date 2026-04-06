"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowUp, ArrowDown, ArrowUpDown, Filter, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type SortDir = "asc" | "desc";
export type Filters = Record<string, Set<string>>;

/* ── Column header with sort + optional Excel-style filter dropdown ── */

export function ColumnHeader<K extends string>({
 label,
 sortKey,
 currentSort,
 sortDir,
 onSort,
 filterCol,
 filterOptions,
 filters,
 onFilter,
 openFilter,
 setOpenFilter,
}: {
 label: string;
 sortKey: K;
 currentSort: K;
 sortDir: SortDir;
 onSort: (key: K) => void;
 filterCol?: string;
 filterOptions?: { value: string; label: string }[];
 filters?: Filters;
 onFilter?: (col: string, values: Set<string>) => void;
 openFilter?: string | null;
 setOpenFilter?: (col: string | null) => void;
}) {
 const sortActive = currentSort === sortKey;
 const hasFilter = filterCol && filterOptions && filters && onFilter && setOpenFilter;
 const filterActive = hasFilter && filters[filterCol] && filters[filterCol].size > 0;
 const isOpen = hasFilter && openFilter === filterCol;
 const filterIconRef = useRef<HTMLButtonElement>(null);

 return (
 <th className={`relative select-none px-3 py-3 text-right text-[12px] font-semibold whitespace-nowrap ${sortActive ? "text-foreground" : "text-muted-foreground"}`}>
 <div className="flex items-center gap-0.5">
 <button
 type="button"
 onClick={() => onSort(sortKey)}
 className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 hover:bg-accent/60 hover:text-foreground cursor-pointer"
 aria-label={`מיין לפי ${label}`}
 >
 <span>{label}</span>
 {sortActive ? (
 sortDir === "asc" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />
 ) : (
 <ArrowUpDown className="size-3" />
 )}
 </button>
 {hasFilter ? (
 <button
 type="button"
 ref={filterIconRef}
 className={`rounded-full p-1 hover:bg-accent/60 hover:text-foreground cursor-pointer ${filterActive ? "text-primary" : "text-muted-foreground"}`}
 onClick={(e) => {
 e.stopPropagation();
 setOpenFilter(isOpen ? null : filterCol);
 }}
 aria-label={`סינון עמודת ${label}`}
 >
 <Filter className="size-3" />
 </button>
 ) : null}
 </div>
 {isOpen ? (
 <FilterDropdown
 options={filterOptions}
 selected={filters[filterCol] || new Set()}
 onApply={(values) => { onFilter(filterCol, values); setOpenFilter(null); }}
 onClose={() => setOpenFilter(null)}
 ignoreRef={filterIconRef}
 anchorRef={filterIconRef}
 />
 ) : null}
 </th>
 );
}

/* ── Excel-style filter dropdown: search + checkbox list + select all / clear ── */

function FilterDropdown({
 options,
 selected,
 onApply,
 onClose,
 ignoreRef,
 anchorRef,
}: {
 options: { value: string; label: string }[];
 selected: Set<string>;
 onApply: (values: Set<string>) => void;
 onClose: () => void;
 ignoreRef?: React.RefObject<HTMLElement | null>;
 anchorRef?: React.RefObject<HTMLElement | null>;
}) {
 // selected.size === 0 means "no filter" (all shown). We convert to explicit set for local editing.
 const [localSelected, setLocalSelected] = useState<Set<string>>(
 () => selected.size === 0 ? new Set(options.map((o) => o.value)) : new Set(selected),
 );
 const [search, setSearch] = useState("");
 const [pos, setPos] = useState<{ top: number; right: number } | null>(null);
 const ref = useRef<HTMLDivElement>(null);
 const searchRef = useRef<HTMLInputElement>(null);

 useLayoutEffect(() => {
 if (anchorRef?.current) {
 const rect = anchorRef.current.getBoundingClientRect();
 setPos({ top: rect.bottom + 6, right: window.innerWidth - rect.right });
 }
 }, [anchorRef]);

 useEffect(() => {
 searchRef.current?.focus();
 }, []);

 useEffect(() => {
 function handleClick(e: MouseEvent) {
 const target = e.target as Node;
 if (ref.current && !ref.current.contains(target) && !(ignoreRef?.current && ignoreRef.current.contains(target))) {
 onClose();
 }
 }
 document.addEventListener("mousedown", handleClick);
 return () => document.removeEventListener("mousedown", handleClick);
 }, [onClose, ignoreRef]);

 const allValues = new Set(options.map((o) => o.value));
 const allSelected = allValues.size > 0 && localSelected.size === allValues.size && [...allValues].every((v) => localSelected.has(v));

 const visibleOptions = search.trim()
 ? options.filter((o) => o.label.toLowerCase().includes(search.trim().toLowerCase()))
 : options;

 function toggleValue(val: string) {
 setLocalSelected((prev) => {
 const next = new Set(prev);
 if (next.has(val)) next.delete(val);
 else next.add(val);
 return next;
 });
 }

 function toggleSelectAll() {
 if (allSelected) {
 setLocalSelected(new Set());
 } else {
 setLocalSelected(new Set(options.map((o) => o.value)));
 }
 }

 const dropdown = (
 <div
 ref={ref}
 className="fixed z-50 min-w-[220px] rounded-[22px] border border-border/70 bg-popover/95 p-2 shadow-[var(--shadow-card)] backdrop-blur-xl"
 style={pos ? { top: pos.top, right: pos.right } : { visibility: "hidden" as const }}
 onClick={(e) => e.stopPropagation()}
 >
 {/* Search box */}
 <div className="relative mb-1.5">
 <div className="absolute end-2 top-1/2 -translate-y-1/2 text-muted-foreground">
 <Search className="size-3" />
 </div>
 <Input
 ref={searchRef}
 type="text"
 value={search}
 onChange={(e) => setSearch(e.target.value)}
 className="h-7 text-[11px] py-1.5 pe-7 ps-2 text-right"
 placeholder="חיפוש..."
 dir="rtl"
 />
 </div>

 {/* Select all */}
 <label className="flex cursor-pointer items-center gap-2 rounded-xl px-2 py-1.5 text-[12px] font-semibold text-muted-foreground hover:bg-muted/70">
 <input type="checkbox" checked={allSelected} onChange={toggleSelectAll} />
 בחר הכל
 </label>

 <div className="my-1 border-t border-border/70" />

 {/* Checkbox list */}
 <div className="max-h-[200px] overflow-y-auto">
 {visibleOptions.length === 0 ? (
 <p className="text-[11px] text-center py-2 text-muted-foreground">אין תוצאות</p>
 ) : (
 visibleOptions.map((opt) => (
 <label
 key={opt.value}
 className="flex cursor-pointer items-center gap-2 rounded-xl px-2 py-1.5 text-[12px] text-muted-foreground hover:bg-muted/70"
 >
 <input
 type="checkbox"
 checked={localSelected.has(opt.value)}
 onChange={() => toggleValue(opt.value)}
 />
 {opt.label}
 </label>
 ))
 )}
 </div>

 <div className="my-1 border-t border-border/70" />

 <div className="flex items-center gap-2 px-1">
 <Button
 type="button"
 variant="ghost"
 size="sm"
 className="flex-1 text-[11px] font-semibold"
 onClick={() => { onApply(new Set()); onClose(); }}
 >
 נקה
 </Button>
 <Button
 type="button"
 variant="default"
 size="sm"
 className="flex-1 text-[11px] font-semibold"
 onClick={() => {
 // If all options are selected, apply empty set (= no filter)
 const allVals = new Set(options.map((o) => o.value));
 const isAll = localSelected.size === allVals.size && [...allVals].every((v) => localSelected.has(v));
 onApply(isAll ? new Set() : localSelected);
 }}
 >
 החל
 </Button>
 </div>
 </div>
 );

 return createPortal(dropdown, document.body);
}

/* ── Hook for filter state management ── */

export function useColumnFilters() {
 const [filters, setFilters] = useState<Filters>({});
 const [openFilter, setOpenFilter] = useState<string | null>(null);

 const setColumnFilter = useCallback((col: string, values: Set<string>) => {
 setFilters((prev) => {
 const next = { ...prev };
 if (values.size === 0) {
 delete next[col];
 } else {
 next[col] = values;
 }
 return next;
 });
 }, []);

 const clearAll = useCallback(() => setFilters({}), []);

 const activeCount = Object.values(filters).filter((s) => s.size > 0).length;

 return { filters, setColumnFilter, openFilter, setOpenFilter, clearAll, activeCount };
}
