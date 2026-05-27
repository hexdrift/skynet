"use client";

import * as React from "react";
import {
  Globe,
  List,
  Map,
  SlidersHorizontal,
  User,
  X,
} from "lucide-react";
import { msg } from "@/shared/lib/messages";
import type { ExploreCorpus, ExploreView } from "../hooks/use-semantic-search";

interface SearchBarProps {
  /** The committed query — what's actually being searched (mirrors the URL). */
  text: string;
  /** Fires on explicit submit (button click or Enter), or on clear. */
  onSubmit: (next: string) => void;
  view: ExploreView;
  onViewChange: (next: ExploreView) => void;
  corpus: ExploreCorpus;
  onCorpusChange: (next: ExploreCorpus) => void;
  /** Hides Mine when no logged-in user — server-rendered fallback. */
  mineEnabled: boolean;
  filtersCount: number;
  onOpenFilters: () => void;
}

/**
 * The page's center of gravity. A segmented corpus toggle sits on top so the
 * user can pick where to search (their own jobs vs other users' public ones),
 * and the rounded input surface below carries the free-text query, view
 * toggle, and filters affordance. Keyboard: pressing "/" anywhere focuses
 * the input; Enter submits.
 *
 * The input keeps a local draft so typing doesn't fire a backend request per
 * keystroke (which rate-limits the embedding API). Search only runs when the
 * user explicitly submits or clears the input.
 */
export function SearchBar({
  text,
  onSubmit,
  view,
  onViewChange,
  corpus,
  onCorpusChange,
  mineEnabled,
  filtersCount,
  onOpenFilters,
}: SearchBarProps) {
  const inputRef = React.useRef<HTMLInputElement | null>(null);
  const [draft, setDraft] = React.useState(text);
  React.useEffect(() => {
    setDraft(text);
  }, [text]);
  const inputDir = detectInputDir(draft);
  const isActive = text.trim().length > 0 || filtersCount > 0;

  const submitDraft = React.useCallback(() => {
    onSubmit(draft);
  }, [draft, onSubmit]);

  const clearAll = React.useCallback(() => {
    setDraft("");
    onSubmit("");
    inputRef.current?.focus();
  }, [onSubmit]);

  // "/" focuses the input from anywhere on the page (Google's shortcut).
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "/") return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) return;
      e.preventDefault();
      inputRef.current?.focus();
      inputRef.current?.select();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // When the corpus is "mine", the scatter map has no projected coordinates,
  // so hiding the view toggle keeps the user out of a guaranteed-empty state.
  const showViewToggle = corpus === "public";

  return (
    <div dir="rtl" data-tutorial="explore-search" className="mx-auto flex w-full max-w-3xl flex-col gap-2.5">
      <div className="flex items-center justify-center">
        <CorpusToggle
          value={corpus}
          onChange={onCorpusChange}
          mineEnabled={mineEnabled}
        />
      </div>
      <div
        className={`group relative flex items-center gap-1 rounded-2xl border border-border bg-background ps-4 pe-1 py-1.5 transition-[border-color,box-shadow] duration-150 ease-out focus-within:border-foreground/40 focus-within:shadow-[0_2px_24px_-12px_oklch(0.25_0.04_45/.18)] ${
          isActive ? "border-foreground/25" : ""
        }`}
      >
        <input
          ref={inputRef}
          dir={inputDir}
          type="text"
          inputMode="search"
          autoComplete="off"
          spellCheck={false}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submitDraft();
            }
          }}
          placeholder={msg("explore.search.placeholder")}
          aria-label={msg("explore.search.aria")}
          style={{ textAlign: inputDir === "rtl" ? "right" : "left" }}
          className="min-w-0 flex-1 bg-transparent px-2 py-1.5 text-[15px] tracking-tight text-foreground placeholder:text-foreground/40 focus:outline-none"
        />
        {draft.length > 0 && (
          <button
            type="button"
            onClick={clearAll}
            aria-label={msg("explore.search.clear")}
            className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-foreground/55 transition-[background-color,color] cursor-pointer hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/45"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        )}
        <button
          type="button"
          onClick={onOpenFilters}
          aria-label={msg("explore.filters.button")}
          className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-[13px] text-foreground/70 transition-[background-color,color] cursor-pointer hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/45"
        >
          <SlidersHorizontal className="size-[1.125rem]" aria-hidden="true" />
          {filtersCount > 0 && (
            <span
              dir="ltr"
              className="inline-flex min-w-5 items-center justify-center rounded-full bg-foreground px-1.5 text-[10px] font-semibold leading-tight text-background tabular-nums"
            >
              {filtersCount}
            </span>
          )}
        </button>
        {showViewToggle && (
          <>
            <span aria-hidden="true" className="mx-1 h-6 w-px bg-border/80" />
            <ViewToggle value={view} onChange={onViewChange} />
          </>
        )}
      </div>
      <div className="mx-1 flex items-center justify-end gap-3 text-[12px] text-foreground/55">
        <span className="hidden text-[11px] text-foreground/40 md:inline">
          {msg("explore.search.kbd_hint")}
        </span>
      </div>
    </div>
  );
}

/**
 * Walk the typed text and return "rtl" or "ltr" based on the first strong
 * directional character. Defaults to "rtl" when the value is empty so the
 * Hebrew placeholder renders correctly. More reliable than `dir="auto"`,
 * which falls back to the parent direction inconsistently across browsers
 * when the input is empty or starts with whitespace/punctuation.
 */
function detectInputDir(text: string): "rtl" | "ltr" {
  for (const ch of text) {
    const code = ch.codePointAt(0);
    if (code === undefined) continue;
    if (
      (code >= 0x0590 && code <= 0x05ff) ||
      (code >= 0x0600 && code <= 0x06ff) ||
      (code >= 0x0700 && code <= 0x074f) ||
      (code >= 0xfb1d && code <= 0xfdff) ||
      (code >= 0xfe70 && code <= 0xfeff)
    ) {
      return "rtl";
    }
    if (
      (code >= 0x0041 && code <= 0x005a) ||
      (code >= 0x0061 && code <= 0x007a) ||
      (code >= 0x00c0 && code <= 0x024f) ||
      (code >= 0x0250 && code <= 0x02af)
    ) {
      return "ltr";
    }
  }
  return "rtl";
}

function CorpusToggle({
  value,
  onChange,
  mineEnabled,
}: {
  value: ExploreCorpus;
  onChange: (next: ExploreCorpus) => void;
  mineEnabled: boolean;
}) {
  const segments: ReadonlyArray<{
    value: ExploreCorpus;
    label: string;
    icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" }>;
    aria: string;
    disabled?: boolean;
  }> = [
    {
      value: "mine",
      label: msg("explore.corpus.mine"),
      icon: User,
      aria: msg("explore.corpus.mine.aria"),
      disabled: !mineEnabled,
    },
    {
      value: "public",
      label: msg("explore.corpus.public"),
      icon: Globe,
      aria: msg("explore.corpus.public.aria"),
    },
  ];

  return (
    <div
      role="radiogroup"
      aria-label={msg("explore.corpus.aria")}
      className="relative inline-flex items-center rounded-full border border-border/80 bg-muted/40 p-0.5"
    >
      {segments.map((seg) => {
        const active = seg.value === value;
        const Icon = seg.icon;
        const disabled = seg.disabled === true;
        return (
          <button
            key={seg.value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={seg.aria}
            disabled={disabled}
            onClick={() => {
              if (disabled) return;
              if (!active) onChange(seg.value);
            }}
            className={`relative inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12.5px] font-medium transition-[background-color,color,box-shadow] duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/45 ${
              active
                ? "bg-background text-foreground shadow-[0_1px_2px_oklch(0.25_0.04_45/.12)]"
                : disabled
                ? "cursor-not-allowed text-foreground/30"
                : "cursor-pointer text-foreground/60 hover:text-foreground"
            }`}
          >
            <Icon className="size-3.5" aria-hidden="true" />
            <span>{seg.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function ViewToggle({
  value,
  onChange,
}: {
  value: ExploreView;
  onChange: (next: ExploreView) => void;
}) {
  return (
    <div
      role="group"
      aria-label={msg("explore.view.aria")}
      className="relative inline-flex shrink-0 items-center rounded-lg bg-muted/55 p-0.5"
    >
      <ViewToggleButton
        active={value === "list"}
        onClick={() => onChange("list")}
        label={msg("explore.view.list")}
      >
        <List className="size-4" aria-hidden="true" />
      </ViewToggleButton>
      <ViewToggleButton
        active={value === "map"}
        onClick={() => onChange("map")}
        label={msg("explore.view.map")}
      >
        <Map className="size-4" aria-hidden="true" />
      </ViewToggleButton>
    </div>
  );
}

function ViewToggleButton({
  active,
  onClick,
  label,
  children,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={label}
      className={`relative inline-flex size-8 items-center justify-center rounded-md transition-[background-color,color,box-shadow] duration-150 ease-out cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/45 ${
        active
          ? "bg-background text-foreground shadow-sm"
          : "text-foreground/55 hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}
