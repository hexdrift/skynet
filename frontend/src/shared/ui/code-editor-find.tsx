"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { Extension } from "@codemirror/state";
import { EditorView, keymap, runScopeHandlers, type KeyBinding } from "@codemirror/view";
import {
  SearchQuery,
  closeSearchPanel,
  findNext,
  findPrevious,
  getSearchQuery,
  openSearchPanel,
  replaceAll,
  replaceNext,
  search,
  searchKeymap,
  setSearchQuery,
} from "@codemirror/search";
import { formatMsg, msg } from "@/shared/lib/messages";
import { ArrowDown, ArrowUp, CaretDown, CaretRight, MagnifyingGlass, X } from "@/shared/ui/icons";
import { TooltipButton } from "@/shared/ui/tooltip-button";

const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.userAgent);

export const FIND_SHORTCUT = IS_MAC ? "⌘F" : "Ctrl+F";
const REPLACE_SHORTCUT = IS_MAC ? "⌘⌥F" : "Ctrl+H";

// Counting stops here so a pattern with thousands of hits never stalls the panel.
const MATCH_COUNT_CAP = 10_000;
// IDE-standard toggle glyphs (VS Code, JetBrains): not copy, so not translated.
const CASE_GLYPH = "Aa";
const WORD_GLYPH = "W";
const REGEX_GLYPH = ".*";

const ICON_BUTTON_CLASS =
  "flex shrink-0 items-center rounded p-0.5 text-[#7C6350] transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#C8B8A4] disabled:cursor-not-allowed disabled:opacity-40";
const TEXT_BUTTON_CLASS =
  "shrink-0 rounded px-1.5 py-0.5 font-medium text-[#7C6350] transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#C8B8A4] disabled:cursor-not-allowed disabled:opacity-40";
const FIELD_CLASS =
  "min-w-0 flex-1 bg-transparent py-1 font-mono text-[11.5px] text-[#3D2E22] outline-none placeholder:text-[#B09878]";

interface PanelHost {
  dom: HTMLElement;
  view: EditorView;
}

interface MatchCount {
  total: number;
  /** 1-based index of the match under the editor selection, 0 when the selection is elsewhere. */
  current: number;
}

function countMatches(view: EditorView, query: SearchQuery): MatchCount {
  if (!query.valid) return { total: 0, current: 0 };
  const { from, to } = view.state.selection.main;
  const cursor = query.getCursor(view.state);
  let total = 0;
  let current = 0;
  for (let step = cursor.next(); !step.done && total < MATCH_COUNT_CAP; step = cursor.next()) {
    total += 1;
    if (step.value.from === from && step.value.to === to) current = total;
  }
  return { total, current };
}

/* Incremental search: the editor selection follows the first match at or
   after the caret while the query is typed, wrapping to the top like an IDE. */
function selectFirstMatch(view: EditorView, query: SearchQuery): void {
  if (!query.valid) return;
  const { from } = view.state.selection.main;
  let step = query.getCursor(view.state, from).next();
  if (step.done) step = query.getCursor(view.state, 0, from).next();
  if (step.done) return;
  view.dispatch({
    selection: { anchor: step.value.from, head: step.value.to },
    scrollIntoView: true,
  });
}

interface ToggleProps {
  pressed: boolean;
  label: string;
  onClick: () => void;
  children: ReactNode;
}

function Toggle({ pressed, label, onClick, children }: ToggleProps) {
  return (
    <TooltipButton tooltip={label}>
      <button
        type="button"
        aria-pressed={pressed}
        aria-label={label}
        onClick={onClick}
        className={`rounded px-1 font-mono text-[10.5px] leading-4 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#C8B8A4] ${
          pressed ? "bg-[#E8DDD4] text-[#3D2E22]" : "text-[#8C7A6B] hover:bg-black/5"
        }`}
      >
        {children}
      </button>
    </TooltipButton>
  );
}

interface FindPanelProps {
  view: EditorView;
  listeners: Set<() => void>;
  replaceOpen: boolean;
  onReplaceOpenChange: (open: boolean) => void;
}

function FindPanel({ view, listeners, replaceOpen, onReplaceOpenChange }: FindPanelProps) {
  const initial = getSearchQuery(view.state);
  const [query, setQuery] = useState(initial.search);
  const [replacement, setReplacement] = useState(initial.replace);
  const [caseSensitive, setCaseSensitive] = useState(initial.caseSensitive);
  const [regexp, setRegexp] = useState(initial.regexp);
  const [wholeWord, setWholeWord] = useState(initial.wholeWord);
  const [count, setCount] = useState<MatchCount>({ total: 0, current: 0 });
  const findRef = useRef<HTMLInputElement>(null);
  const replaceRef = useRef<HTMLInputElement>(null);
  const readOnly = view.state.readOnly;
  const showReplace = replaceOpen && !readOnly;

  const spec = useMemo(
    () =>
      new SearchQuery({ search: query, replace: replacement, caseSensitive, regexp, wholeWord }),
    [query, replacement, caseSensitive, regexp, wholeWord],
  );
  const invalid = query !== "" && !spec.valid;

  useEffect(() => {
    const current = getSearchQuery(view.state);
    if (spec.eq(current)) return;
    view.dispatch({ effects: setSearchQuery.of(spec) });
    const searchChanged =
      spec.search !== current.search ||
      spec.caseSensitive !== current.caseSensitive ||
      spec.regexp !== current.regexp ||
      spec.wholeWord !== current.wholeWord;
    if (searchChanged) selectFirstMatch(view, spec);
  }, [view, spec]);

  useEffect(() => {
    const refresh = () => setCount(countMatches(view, getSearchQuery(view.state)));
    refresh();
    listeners.add(refresh);
    return () => {
      listeners.delete(refresh);
    };
  }, [view, listeners]);

  useEffect(() => {
    const field = findRef.current;
    field?.focus();
    field?.select();
  }, []);

  /* Cmd/Ctrl-F from inside the editor re-seeds the query from the selection
     and hands focus back here, so pick the new text up when focus arrives. */
  const syncFromEditor = useCallback(() => {
    const seeded = getSearchQuery(view.state).search;
    if (seeded === query) return;
    setQuery(seeded);
    requestAnimationFrame(() => findRef.current?.select());
  }, [view, query]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (runScopeHandlers(view, event.nativeEvent, "search-panel")) {
        event.preventDefault();
        return;
      }
      if (event.key !== "Enter") return;
      if (event.target === findRef.current) {
        event.preventDefault();
        (event.shiftKey ? findPrevious : findNext)(view);
      } else if (event.target === replaceRef.current) {
        event.preventDefault();
        replaceNext(view);
      }
    },
    [view],
  );

  let countLabel = "";
  if (invalid) countLabel = msg("shared.code_editor.find.invalid_regex");
  else if (query === "") countLabel = "";
  else if (count.total === 0) countLabel = msg("shared.code_editor.find.no_results");
  else if (count.current > 0)
    countLabel = formatMsg("shared.code_editor.find.count", {
      current: count.current,
      total: count.total,
    });
  else countLabel = formatMsg("shared.code_editor.find.total", { total: count.total });
  const nothingFound = query !== "" && (invalid || count.total === 0);

  return (
    <div
      dir="ltr"
      onKeyDown={handleKeyDown}
      className="flex flex-col gap-1 px-2 py-1.5 font-sans text-[11px] text-[#3D2E22]"
    >
      <div className="flex items-center gap-1">
        {!readOnly && (
          <TooltipButton
            tooltip={formatMsg("shared.code_editor.find.toggle_replace", {
              shortcut: REPLACE_SHORTCUT,
            })}
          >
            <button
              type="button"
              aria-expanded={showReplace}
              aria-label={formatMsg("shared.code_editor.find.toggle_replace", {
                shortcut: REPLACE_SHORTCUT,
              })}
              onClick={() => onReplaceOpenChange(!replaceOpen)}
              className={ICON_BUTTON_CLASS}
            >
              {showReplace ? <CaretDown className="size-3" /> : <CaretRight className="size-3" />}
            </button>
          </TooltipButton>
        )}
        <div
          className={`relative flex min-w-0 flex-1 items-center rounded-md border bg-[#FAF6F0] transition-colors focus-within:ring-1 ${
            invalid
              ? "border-[#B5654A] focus-within:ring-[#B5654A]/40"
              : "border-[#E5DDD4] focus-within:border-[#C8B8A4] focus-within:ring-[#C8B8A4]/50"
          }`}
        >
          <MagnifyingGlass
            className="pointer-events-none absolute left-1.5 size-3 text-[#8C7A6B]"
            aria-hidden="true"
          />
          <input
            ref={findRef}
            main-field="true"
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onFocus={syncFromEditor}
            placeholder={msg("shared.code_editor.find.placeholder")}
            aria-label={msg("shared.code_editor.find.placeholder")}
            aria-invalid={invalid || undefined}
            spellCheck={false}
            autoComplete="off"
            className={`${FIELD_CLASS} pl-6 pr-1`}
          />
          <div className="flex items-center gap-0.5 pr-1">
            <Toggle
              pressed={caseSensitive}
              label={msg("shared.code_editor.find.match_case")}
              onClick={() => setCaseSensitive((on) => !on)}
            >
              {CASE_GLYPH}
            </Toggle>
            <Toggle
              pressed={wholeWord}
              label={msg("shared.code_editor.find.whole_word")}
              onClick={() => setWholeWord((on) => !on)}
            >
              {WORD_GLYPH}
            </Toggle>
            <Toggle
              pressed={regexp}
              label={msg("shared.code_editor.find.regex")}
              onClick={() => setRegexp((on) => !on)}
            >
              {REGEX_GLYPH}
            </Toggle>
          </div>
        </div>
        <span
          aria-live="polite"
          className={`min-w-[5.5rem] text-center tabular-nums ${
            nothingFound ? "text-[#B5654A]" : "text-[#8C7A6B]"
          }`}
        >
          {countLabel}
        </span>
        <TooltipButton tooltip={msg("shared.code_editor.find.previous")}>
          <button
            type="button"
            aria-label={msg("shared.code_editor.find.previous")}
            disabled={count.total === 0}
            onClick={() => findPrevious(view)}
            className={ICON_BUTTON_CLASS}
          >
            <ArrowUp className="size-3" />
          </button>
        </TooltipButton>
        <TooltipButton tooltip={msg("shared.code_editor.find.next")}>
          <button
            type="button"
            aria-label={msg("shared.code_editor.find.next")}
            disabled={count.total === 0}
            onClick={() => findNext(view)}
            className={ICON_BUTTON_CLASS}
          >
            <ArrowDown className="size-3" />
          </button>
        </TooltipButton>
        <TooltipButton tooltip={msg("shared.code_editor.find.close")}>
          <button
            type="button"
            aria-label={msg("shared.code_editor.find.close")}
            onClick={() => closeSearchPanel(view)}
            className={ICON_BUTTON_CLASS}
          >
            <X className="size-3" />
          </button>
        </TooltipButton>
      </div>

      {showReplace && (
        <div className="flex items-center gap-1 pl-5">
          <div className="flex min-w-0 flex-1 items-center rounded-md border border-[#E5DDD4] bg-[#FAF6F0] transition-colors focus-within:border-[#C8B8A4] focus-within:ring-1 focus-within:ring-[#C8B8A4]/50">
            <input
              ref={replaceRef}
              type="text"
              value={replacement}
              onChange={(event) => setReplacement(event.target.value)}
              placeholder={msg("shared.code_editor.find.replace_placeholder")}
              aria-label={msg("shared.code_editor.find.replace_placeholder")}
              spellCheck={false}
              autoComplete="off"
              className={`${FIELD_CLASS} px-2`}
            />
          </div>
          <button
            type="button"
            disabled={count.total === 0}
            onClick={() => replaceNext(view)}
            className={TEXT_BUTTON_CLASS}
          >
            {msg("shared.code_editor.find.replace")}
          </button>
          <button
            type="button"
            disabled={count.total === 0}
            onClick={() => replaceAll(view)}
            className={TEXT_BUTTON_CLASS}
          >
            {msg("shared.code_editor.find.replace_all")}
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * IDE-style find/replace for the shared code editor: Cmd/Ctrl-F opens a panel
 * docked above the code, Enter/Shift+Enter step through matches, Esc closes.
 * CodeMirror owns the panel slot and the match highlighting; React renders the
 * controls into that slot through a portal.
 */
export function useEditorFind(): { extension: Extension; panel: ReactNode } {
  const [host, setHost] = useState<PanelHost | null>(null);
  const [replaceOpen, setReplaceOpen] = useState(false);
  const [listeners] = useState(() => new Set<() => void>());

  const extension = useMemo<Extension>(() => {
    const openReplace = (view: EditorView) => {
      if (!view.state.readOnly) setReplaceOpen(true);
      return openSearchPanel(view);
    };
    const replaceKeymap: KeyBinding[] = [
      { key: "Mod-Alt-f", run: openReplace, scope: "editor search-panel" },
      // Cmd-H is the macOS "hide app" key, so the VS Code-style Ctrl-H only binds elsewhere.
      { win: "Ctrl-h", linux: "Ctrl-h", run: openReplace, scope: "editor search-panel" },
    ];
    return [
      search({
        top: true,
        createPanel: (view) => {
          const dom = document.createElement("div");
          dom.className = "cm-find-panel";
          return {
            dom,
            top: true,
            mount: () => setHost({ dom, view }),
            destroy: () => setHost(null),
          };
        },
      }),
      keymap.of([...replaceKeymap, ...searchKeymap]),
      EditorView.updateListener.of((update) => {
        const queryChanged = update.transactions.some((tr) =>
          tr.effects.some((effect) => effect.is(setSearchQuery)),
        );
        if (update.docChanged || update.selectionSet || queryChanged) {
          for (const listener of listeners) listener();
        }
      }),
    ];
  }, [listeners]);

  const panel = host
    ? createPortal(
        <FindPanel
          view={host.view}
          listeners={listeners}
          replaceOpen={replaceOpen}
          onReplaceOpenChange={setReplaceOpen}
        />,
        host.dom,
      )
    : null;

  return { extension, panel };
}
