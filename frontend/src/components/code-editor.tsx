"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { EditorView } from "@codemirror/view";
import { Extension } from "@codemirror/state";
import { tags } from "@lezer/highlight";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { highlightSelectionMatches } from "@codemirror/search";
import { autocompletion, acceptCompletion, CompletionContext, type CompletionResult } from "@codemirror/autocomplete";
import { indentWithTab } from "@codemirror/commands";
import { Prec } from "@codemirror/state";
import { keymap } from "@codemirror/view";
import {
  Copy,
  Check,
  ChevronUp,
  ChevronDown,
  Play,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  X,
  Eraser,
} from "lucide-react";

/* ── Light beige theme matching the app's warm palette ── */

const beigeEditorTheme = EditorView.theme(
  {
    "&": {
      backgroundColor: "#FAF6F0",
      color: "#3D2E22",
    },
    ".cm-content": {
      caretColor: "#7C6350",
      fontFamily: "ui-monospace, 'Cascadia Code', 'Source Code Pro', Menlo, monospace",
    },
    ".cm-cursor, .cm-dropCursor": {
      borderLeftColor: "#7C6350",
    },
    /* Raise selection layer above the editor background (default is z-index:-2) */
    ".cm-selectionLayer": {
      zIndex: "1 !important",
    },
    /* Selection highlight — must be visually stronger than matches */
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground": {
      backgroundColor: "rgba(140, 105, 50, 0.40) !important",
    },
    /* Other occurrences of the selected word */
    ".cm-selectionMatch": {
      backgroundColor: "rgba(160, 120, 70, 0.15) !important",
      borderRadius: "2px",
      outline: "1px solid rgba(160, 120, 70, 0.35)",
    },
    ".cm-focused .cm-cursor": {
      borderLeftColor: "#3D2E22",
      borderLeftWidth: "2px",
    },
    ".cm-activeLine": {
      backgroundColor: "rgba(245, 237, 228, 0.3)",
    },
    ".cm-gutters": {
      backgroundColor: "#F3ECE3",
      color: "#B09878",
      border: "none",
      borderRight: "1px solid #E5DDD4",
    },
    ".cm-activeLineGutter": {
      backgroundColor: "#EDE4D8",
      color: "#7C6350",
    },
    ".cm-foldPlaceholder": {
      backgroundColor: "#E8DDD4",
      border: "none",
      color: "#7C6350",
    },
    ".cm-matchingBracket": {
      backgroundColor: "#E8DDD4",
      outline: "1px solid #C8B8A4",
    },
    /* ── Autocomplete tooltip ── */
    ".cm-tooltip": {
      backgroundColor: "#FAF6F0",
      border: "1px solid #E5DDD4",
      borderRadius: "8px",
      boxShadow: "0 4px 12px rgba(60, 46, 34, 0.1)",
    },
    ".cm-tooltip.cm-tooltip-autocomplete": {
      backgroundColor: "#FAF6F0",
    },
    ".cm-tooltip-autocomplete > ul": {
      fontFamily: "ui-monospace, 'Cascadia Code', 'Source Code Pro', Menlo, monospace",
      fontSize: "12px",
    },
    ".cm-tooltip-autocomplete > ul > li": {
      padding: "3px 8px",
      color: "#3D2E22",
    },
    ".cm-tooltip-autocomplete > ul > li[aria-selected]": {
      backgroundColor: "#E8DDD4",
      color: "#3D2E22",
    },
    ".cm-completionIcon": {
      color: "#8C7A6B",
    },
    ".cm-completionLabel": {
      color: "#3D2E22",
    },
    ".cm-completionMatchedText": {
      color: "#8B5E3C",
      fontWeight: "bold",
      textDecoration: "none",
    },
  },
  { dark: false }
);

const beigeHighlightStyle = HighlightStyle.define([
  { tag: tags.keyword, color: "#8B5E3C", fontWeight: "bold" },
  { tag: tags.operator, color: "#7C6350" },
  { tag: tags.special(tags.variableName), color: "#6B4226" },
  { tag: tags.typeName, color: "#8B6914" },
  { tag: tags.atom, color: "#8B6914" },
  { tag: tags.number, color: "#986832" },
  { tag: tags.definition(tags.variableName), color: "#3D2E22" },
  { tag: tags.string, color: "#5A7247" },
  { tag: tags.special(tags.string), color: "#5A7247" },
  { tag: tags.comment, color: "#B09878", fontStyle: "italic" },
  { tag: tags.variableName, color: "#3D2E22" },
  { tag: tags.bracket, color: "#8C7A6B" },
  { tag: tags.tagName, color: "#8B5E3C" },
  { tag: tags.attributeName, color: "#8B6914" },
  { tag: tags.propertyName, color: "#6B4226" },
  { tag: tags.className, color: "#6B4226" },
  { tag: tags.function(tags.variableName), color: "#7C5030" },
  { tag: tags.bool, color: "#8B6914" },
  { tag: tags.null, color: "#8B6914" },
  { tag: tags.self, color: "#8B5E3C", fontStyle: "italic" },
  { tag: tags.punctuation, color: "#8C7A6B" },
]);

const beigeTheme: Extension = [beigeEditorTheme, syntaxHighlighting(beigeHighlightStyle)];

/* ── Python/DSPy autocomplete ── */

const dspyCompletions = [
  { label: "dspy.Signature", type: "class", detail: "Base signature class" },
  { label: "dspy.InputField", type: "function", detail: "Declare an input field" },
  { label: "dspy.OutputField", type: "function", detail: "Declare an output field" },
  { label: "dspy.Example", type: "class", detail: "DSPy example" },
  { label: "dspy.Prediction", type: "class", detail: "DSPy prediction" },
  { label: "dspy.Module", type: "class", detail: "Base module class" },
  { label: "dspy.ChainOfThought", type: "class", detail: "Chain of thought module" },
  { label: "dspy.Predict", type: "class", detail: "Predict module" },
  { label: "import dspy", type: "keyword", detail: "Import DSPy" },
  { label: "def metric(example, pred, trace=None):", type: "function", detail: "Metric function template" },
  { label: "with_inputs", type: "method", detail: "Set input fields on Example" },
  { label: "with_outputs", type: "method", detail: "Set output fields on Example" },
];

function dspyCompletion(context: CompletionContext): CompletionResult | null {
  const word = context.matchBefore(/[\w.]+/);
  if (!word || (word.from === word.to && !context.explicit)) return null;
  return {
    from: word.from,
    options: dspyCompletions,
    validFor: /^[\w.]*$/,
  };
}

/* ── Extensions ── */

const pyExtensions = [
  python(),
  highlightSelectionMatches(),
  Prec.highest(keymap.of([{ key: "Tab", run: acceptCompletion }])),
  keymap.of([indentWithTab]),
  autocompletion({
    override: [dspyCompletion],
    activateOnTyping: true,
    maxRenderedOptions: 15,
  }),
];

/* ── Types ── */

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  signature_fields?: { inputs: string[]; outputs: string[] };
}

interface CodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  height?: string;
  readOnly?: boolean;
  onRun?: () => Promise<ValidationResult | null>;
  runLabel?: string;
  runningLabel?: string;
  label?: React.ReactNode;
  /** External validation result — synced into the internal state so callers
   *  (e.g. the Next button) can trigger the inline error panel without
   *  going through the editor's own Run button. */
  validationResult?: ValidationResult | null;
}

/* ── Component ── */

export function CodeEditor({
  value,
  onChange,
  height = "200px",
  readOnly = false,
  onRun,
  runLabel = "בדוק",
  runningLabel = "בודק...",
  label = "Python",
  validationResult,
}: CodeEditorProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [copied, setCopied] = useState(false);
  const [running, setRunning] = useState(false);
  const [formatting, setFormatting] = useState(false);
  const [result, setResult] = useState<ValidationResult | null>(null);

  // Sync externally-provided validation result into internal state
  useEffect(() => {
    if (validationResult !== undefined) setResult(validationResult);
  }, [validationResult]);

  const lineCount = value.split("\n").length;

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [value]);

  const handleRun = useCallback(async () => {
    if (!onRun || running) return;
    setRunning(true);
    setResult(null);
    try {
      const res = await onRun();
      setResult(res);
    } catch {
      setResult({ valid: false, errors: ["Validation failed"], warnings: [] });
    } finally {
      setRunning(false);
    }
  }, [onRun, running]);

  const handleFormat = useCallback(async () => {
    if (formatting || !value.trim()) return;
    setFormatting(true);
    try {
      const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const res = await fetch(`${API}/format-code`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: value }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.changed) onChange(data.code);
      }
    } catch { /* silent */ }
    finally { setFormatting(false); }
  }, [value, formatting, onChange]);

  // Clear result when code changes
  const handleChange = useCallback((v: string) => {
    onChange(v);
    if (result) setResult(null);
  }, [onChange, result]);

  const hasOutput = result !== null || running;

  return (
    <div className="rounded-xl border border-border/60 overflow-hidden flex flex-col shadow-sm" dir="ltr">
      {/* ── Toolbar ── */}
      <div className="flex items-center gap-1 px-3 py-1.5 bg-[#F3ECE3] text-[11px] text-[#8C7A6B] border-b border-[#E5DDD4]">
        <span className="flex-1 font-semibold text-[#7C6350] tracking-wide flex items-center gap-1.5">
          {label}
        </span>

        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-black/5 transition-colors cursor-pointer"
        >
          {collapsed ? <ChevronDown className="size-3" /> : <ChevronUp className="size-3" />}
          {collapsed ? `${lineCount} שורות` : "כווץ"}
        </button>

        {onRun && (
          <button
            type="button"
            onClick={handleRun}
            disabled={running || !value.trim()}
            className="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-black/5 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {running ? <Loader2 className="size-3 animate-spin" /> : <Play className="size-3" />}
            {running ? runningLabel : runLabel}
          </button>
        )}

        <button
          type="button"
          onClick={handleFormat}
          disabled={formatting || !value.trim()}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-black/5 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {formatting ? <Loader2 className="size-3 animate-spin" /> : <Eraser className="size-3" />}
          סדר
        </button>

        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-black/5 transition-colors cursor-pointer"
        >
          {copied ? <Check className="size-3 text-[#5A7247]" /> : <Copy className="size-3" />}
          {copied ? "הועתק" : "העתק"}
        </button>
      </div>

      {/* ── Editor ── */}
      <AnimatePresence initial={false}>
        {!collapsed && (
          <motion.div
            key="editor"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="relative [&_.cm-editor]:!outline-none">
              <CodeMirror
                value={value}
                height={height}
                theme={beigeTheme}
                extensions={pyExtensions}
                onChange={handleChange}
                readOnly={readOnly}
                basicSetup={{
                  lineNumbers: true,
                  foldGutter: true,
                  bracketMatching: true,
                  autocompletion: true,
                  completionKeymap: true,
                  searchKeymap: false,
                  highlightActiveLine: true,
                  highlightSelectionMatches: false,
                  indentOnInput: true,
                  tabSize: 4,
                }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      {collapsed && (
        <div className="bg-[#FAF6F0] text-[#B09878] text-xs italic px-4 py-2">
          {lineCount} lines hidden
        </div>
      )}

      {/* ── Output panel (validation results) ── */}
      {hasOutput && (
        <div className="bg-[#F5EDE4] border-t border-[#E5DDD4] px-4 py-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-[#8C7A6B] uppercase tracking-wider font-semibold">Validation</span>
            {!running && result && (
              <button
                type="button"
                onClick={() => setResult(null)}
                className="p-0.5 rounded hover:bg-black/5 text-[#8C7A6B] cursor-pointer"
                aria-label="סגור"
              >
                <X className="size-3" />
              </button>
            )}
          </div>
          {running && (
            <div className="flex items-center gap-2 text-xs text-[#8C7A6B]">
              <Loader2 className="size-3.5 animate-spin" />
              Validating code against dataset...
            </div>
          )}
          {result && result.valid && result.errors.length === 0 && (
            <div className="flex items-start gap-2 text-xs">
              <CheckCircle2 className="size-3.5 text-[#5A7247] shrink-0 mt-0.5" />
              <div className="space-y-1">
                <span className="font-medium text-[#5A7247]">Valid</span>
                {result.signature_fields && (
                  <div className="text-[#7C6350] font-mono text-[11px] space-y-0.5" dir="ltr">
                    <div><span className="text-[#8C7A6B]">Inputs:</span> {result.signature_fields.inputs.join(", ")}</div>
                    <div><span className="text-[#8C7A6B]">Outputs:</span> {result.signature_fields.outputs.join(", ")}</div>
                  </div>
                )}
              </div>
            </div>
          )}
          {result?.errors.map((err, i) => (
            <div key={`e${i}`} className="flex items-start gap-2 text-xs">
              <XCircle className="size-3.5 text-red-500 shrink-0 mt-0.5" />
              <span className="text-red-700">{err.split(/(https?:\/\/[^\s]+)/g).map((part, j) =>
                /^https?:\/\//.test(part) ? <a key={j} href={part} target="_blank" rel="noopener noreferrer" className="underline hover:text-red-900 transition-colors">{part}</a> : part
              )}</span>
            </div>
          ))}
          {result?.warnings.map((w, i) => (
            <div key={`w${i}`} className="flex items-start gap-2 text-xs">
              <AlertTriangle className="size-3.5 text-amber-500 shrink-0 mt-0.5" />
              <span className="text-amber-700">{w}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
