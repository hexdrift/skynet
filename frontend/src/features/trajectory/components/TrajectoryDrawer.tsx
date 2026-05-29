"use client";

import { ChevronLeft, ChevronRight, Hash, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  displayCandidateId,
  type CandidateMetrics,
  type MinibatchEntry,
  type PerExampleScore,
  type RejectedNode,
  type TrajectoryNode,
  type ValsetRow,
} from "../lib/types";
import { cn } from "@/shared/lib/utils";
import { formatMsg, msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";
import { HelpTip } from "@/shared/ui/help-tip";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/shared/ui/primitives/sheet";
import { Tabs, TabsList, TabsTrigger } from "@/shared/ui/primitives/tabs";

const PARETO_PASS = "#8a9a5b";
const PARETO_FAIL = "#a85a3b";
const PARETO_PASS_BG = "rgba(138, 154, 91, 0.28)";
const PARETO_FAIL_BG = "rgba(168, 90, 59, 0.22)";

const DIFF_VIEW_KEY = "skynet:trajectory:prompt-view";

export type DrawerSelection =
  | { kind: "candidate"; node: TrajectoryNode; parent: TrajectoryNode | null }
  | { kind: "rejected"; ghost: RejectedNode; parent: TrajectoryNode | null }
  | null;

export interface TrajectoryDrawerProps {
  selection: DrawerSelection;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelectCandidate: (id: string) => void;
  // Full lists (not generation-filtered). The unified body uses these to find
  // children and siblings adopted from the same parent.
  candidates: CandidateMetrics[];
  valsetRows: ValsetRow[];
  minibatch: MinibatchEntry[];
  // Per-candidate predictions on each valset example. Keyed by candidate_id →
  // example_id → prediction text. Sparse until each candidate's full eval
  // sweep arrives over the wire.
  valsetOutputs: Map<string, Map<string, string>>;
}

interface NodeView {
  kind: "accepted" | "rejected";
  rawId: string;
  displayId: string;
  iteration: number | null;
  score: number;
  scoreMode: "valset" | "minibatch";
  scoreN: number;
  parentScoreOnMinibatch: number | null;
  parentId: string | null;
  prompt: Record<string, string>;
  parentPrompt: Record<string, string>;
  // Populated for accepted candidates (full valset).
  perExample: PerExampleScore[];
}

function toNodeView(selection: NonNullable<DrawerSelection>): NodeView {
  if (selection.kind === "candidate") {
    const node = selection.node;
    return {
      kind: "accepted",
      rawId: node.candidate_id,
      displayId: displayCandidateId(node.candidate_id),
      iteration: node.iteration,
      score: node.score,
      scoreMode: "valset",
      scoreN: node.per_example.length,
      parentScoreOnMinibatch: null,
      parentId: node.parent_id,
      prompt: node.prompt,
      parentPrompt: selection.parent?.prompt ?? {},
      perExample: node.per_example,
    };
  }
  const ghost = selection.ghost;
  return {
    kind: "rejected",
    rawId: ghost.rejection_id,
    displayId: String(ghost.iteration),
    iteration: ghost.iteration,
    score: ghost.proposal_score,
    scoreMode: "minibatch",
    scoreN: ghost.subsample_size,
    parentScoreOnMinibatch: ghost.parent_score,
    parentId: ghost.parent_id,
    prompt: ghost.proposal_prompt,
    parentPrompt: ghost.parent_prompt,
    perExample: [],
  };
}

export function TrajectoryDrawer({
  selection,
  open,
  onOpenChange,
  onSelectCandidate,
  candidates,
  valsetRows,
  minibatch,
  valsetOutputs,
}: TrajectoryDrawerProps) {
  if (selection === null) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="right"
          className="w-full sm:max-w-md md:max-w-[520px] overflow-hidden bg-[#fbf8f3]"
        >
          <SheetHeader>
            <SheetTitle className="text-base">{TERMS.candidate}</SheetTitle>
          </SheetHeader>
        </SheetContent>
      </Sheet>
    );
  }

  const view = toNodeView(selection);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-md md:max-w-[520px] overflow-hidden bg-[#fbf8f3] flex flex-col"
      >
        <NodeBody
          view={view}
          parent={selection.parent}
          candidates={candidates}
          valsetRows={valsetRows}
          minibatch={minibatch}
          valsetOutputs={valsetOutputs}
          onSelectCandidate={onSelectCandidate}
        />
      </SheetContent>
    </Sheet>
  );
}

function NodeBody({
  view,
  parent,
  candidates,
  valsetRows,
  minibatch,
  valsetOutputs,
  onSelectCandidate,
}: {
  view: NodeView;
  parent: TrajectoryNode | null;
  candidates: CandidateMetrics[];
  valsetRows: ValsetRow[];
  minibatch: MinibatchEntry[];
  valsetOutputs: Map<string, Map<string, string>>;
  onSelectCandidate: (id: string) => void;
}) {
  const [pinnedExampleId, setPinnedExampleId] = useState<string | null>(null);
  const [promptViewMode, setPromptViewMode] = usePromptView();

  useEffect(() => {
    setPinnedExampleId(null);
  }, [view.rawId]);

  const promptEntries = useMemo(() => Object.entries(view.prompt), [view.prompt]);
  const valsetById = useMemo(() => {
    const m = new Map<string, ValsetRow>();
    for (const row of valsetRows) m.set(row.id, row);
    return m;
  }, [valsetRows]);
  const predictionsForView = useMemo(
    () => (view.kind === "accepted" ? valsetOutputs.get(view.rawId) ?? new Map<string, string>() : new Map<string, string>()),
    [valsetOutputs, view.kind, view.rawId],
  );

  const children = useMemo(
    () =>
      view.kind === "accepted"
        ? candidates.filter((c) => c.parent_id === view.rawId)
        : [],
    [candidates, view.kind, view.rawId],
  );
  const adoptedFromSameParent = useMemo(() => {
    if (view.parentId === null) return [];
    return candidates.filter(
      (c) => c.parent_id === view.parentId && c.candidate_id !== view.rawId,
    );
  }, [candidates, view.parentId, view.rawId]);
  const lineageNext = useMemo<
    | { kind: "child"; candidate: CandidateMetrics }
    | { kind: "sibling_adopted"; candidate: CandidateMetrics }
    | null
  >(() => {
    if (view.kind === "accepted") {
      const first = children[0];
      return first === undefined ? null : { kind: "child", candidate: first };
    }
    const adopted = adoptedFromSameParent
      .slice()
      .sort((a, b) => Number(a.candidate_id) - Number(b.candidate_id))[0];
    return adopted === undefined ? null : { kind: "sibling_adopted", candidate: adopted };
  }, [view.kind, children, adoptedFromSameParent]);

  const headerTitle =
    view.kind === "accepted"
      ? formatMsg("trajectory.node.header.accepted_title", { id: view.displayId })
      : msg("trajectory.node.header.rejected_title");
  const scoreLabel =
    view.scoreMode === "valset"
      ? msg("trajectory.node.header.label.score_valset")
      : msg("trajectory.node.header.label.score_minibatch");
  const examplesSub = formatMsg("trajectory.node.header.sub.examples", {
    n: view.scoreN,
  });

  return (
    <>
      <SheetHeader className="border-b border-border/30">
        <SheetTitle className="flex items-center gap-2 text-base">
          {view.kind === "rejected" ? (
            <XCircle className="size-4 text-[#a85a3b]" aria-hidden="true" />
          ) : null}
          <span>{headerTitle}</span>
        </SheetTitle>
        <SheetDescription asChild>
          <div className="mt-1.5 flex items-stretch rounded-md border border-border/40 bg-background/50 overflow-hidden">
            {view.iteration !== null ? (
              <StatTile
                label={msg("trajectory.node.header.label.iteration")}
                value={String(view.iteration)}
                icon={Hash}
              />
            ) : null}
            <StatTile
              label={scoreLabel}
              value={view.score.toFixed(2)}
              sub={examplesSub}
              tone={view.kind === "rejected" ? "rejected" : "accepted"}
              emphasis
            />
            {view.parentScoreOnMinibatch !== null ? (
              <StatTile
                label={msg("trajectory.node.header.label.parent_score")}
                value={view.parentScoreOnMinibatch.toFixed(2)}
                tone="muted"
              />
            ) : null}
          </div>
        </SheetDescription>
      </SheetHeader>

      <div className="flex-1 overflow-y-auto px-4 pb-6 space-y-5">
        <LineageNav
          parent={parent}
          next={lineageNext}
          onSelectCandidate={onSelectCandidate}
        />

        {view.kind === "accepted" && view.perExample.length > 0 ? (
          <Section
            title={msg("trajectory.node.section.score_detail.valset")}
            info={msg("trajectory.detail.pareto_title.explain")}
          >
            <ParetoGridSection
              examples={view.perExample}
              pinnedId={pinnedExampleId}
              onPin={(id) =>
                setPinnedExampleId((prev) => (prev === id ? null : id))
              }
              valsetById={valsetById}
              predictionsForCandidate={predictionsForView}
            />
          </Section>
        ) : null}

        {view.kind === "rejected" || promptEntries.length > 0 ? (
          <Section
            title={
              view.kind === "rejected"
                ? msg("trajectory.drawer.rejected.prompt_title")
                : msg("trajectory.node.section.prompt")
            }
            info={
              view.kind === "rejected"
                ? msg("trajectory.drawer.rejected.prompt_title.explain")
                : undefined
            }
          >
            {promptEntries.length === 0 ? (
              <EmptyHint text={msg("trajectory.drawer.rejected.prompt_unavailable")} />
            ) : (
              <div className="space-y-2">
                {Object.keys(view.parentPrompt).length > 0 ? (
                  <PromptViewToggle view={promptViewMode} onChange={setPromptViewMode} />
                ) : null}
                {promptEntries.map(([predictor, prompt]) => (
                  <div
                    key={predictor}
                    className="overflow-hidden rounded-md border border-border/40 bg-background/60 p-3"
                  >
                    {promptViewMode === "diff" && Object.keys(view.parentPrompt).length > 0 ? (
                      <PromptDiff
                        before={view.parentPrompt[predictor] ?? ""}
                        after={prompt}
                      />
                    ) : (
                      <pre
                        className="text-xs whitespace-pre-wrap leading-relaxed font-mono text-foreground/90"
                        dir="auto"
                        style={{ wordBreak: "break-word" }}
                      >
                        {prompt}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Section>
        ) : null}

        <Section
          title={msg("trajectory.drawer.section.minibatch")}
          info={msg("trajectory.drawer.section.minibatch.explain")}
        >
          <MinibatchPanel
            entries={minibatch}
            valsetRows={valsetRows}
            iteration={view.iteration}
          />
        </Section>
      </div>
    </>
  );
}

function LineageNav({
  parent,
  next,
  onSelectCandidate,
}: {
  parent: TrajectoryNode | null;
  next:
    | { kind: "child"; candidate: CandidateMetrics }
    | { kind: "sibling_adopted"; candidate: CandidateMetrics }
    | null;
  onSelectCandidate: (id: string) => void;
}) {
  if (parent === null && next === null) return null;
  return (
    <div className="grid grid-cols-2 gap-2">
      <LineageButton
        side="prev"
        disabled={parent === null}
        label={msg("trajectory.node.lineage.parent")}
        candidate={parent}
        onSelect={parent === null ? undefined : () => onSelectCandidate(parent.candidate_id)}
      />
      <LineageButton
        side="next"
        disabled={next === null}
        label={
          next === null
            ? msg("trajectory.node.lineage.next_child")
            : next.kind === "child"
              ? msg("trajectory.node.lineage.next_child")
              : msg("trajectory.node.lineage.next_sibling_adopted")
        }
        candidate={next === null ? null : next.candidate}
        onSelect={next === null ? undefined : () => onSelectCandidate(next.candidate.candidate_id)}
      />
    </div>
  );
}

function LineageButton({
  side,
  disabled,
  label,
  candidate,
  onSelect,
}: {
  side: "prev" | "next";
  disabled: boolean;
  label: string;
  candidate: { candidate_id: string; score: number } | null;
  onSelect?: () => void;
}) {
  const Icon = side === "prev" ? ChevronRight : ChevronLeft;
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onSelect}
      className={cn(
        "group flex items-center justify-between gap-2 rounded-md border border-border/40 bg-background/60 px-3 py-2 text-xs transition-colors",
        disabled
          ? "cursor-not-allowed opacity-50"
          : "hover:bg-background hover:text-foreground",
      )}
    >
      <span className="flex min-w-0 flex-col items-start gap-1">
        <span className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/85">
          {label}
        </span>
        {candidate === null ? (
          <span className="text-[11px] text-muted-foreground/70">
            {msg("trajectory.node.lineage.none")}
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-[11px]">
            <span className="text-foreground/80">
              {TERMS.candidate}{" "}
              <span dir="ltr" className="font-mono font-semibold">
                {displayCandidateId(candidate.candidate_id)}
              </span>
            </span>
            <ScoreChip value={candidate.score} tone="accepted" size="sm" />
          </span>
        )}
      </span>
      <Icon
        className="size-3.5 shrink-0 opacity-50 transition-opacity group-hover:opacity-90 group-disabled:opacity-30"
        aria-hidden="true"
      />
    </button>
  );
}

function EmptyHint({ text }: { text: string }) {
  return (
    <div className="rounded-md border border-dashed border-border/50 bg-background/40 px-3 py-2.5 text-[11px] text-muted-foreground">
      {text}
    </div>
  );
}

const TONE_COLORS = {
  accepted: { text: "#4a5a23", bg: "rgba(124, 139, 90, 0.14)" },
  rejected: { text: "#6e2e16", bg: "rgba(178, 107, 74, 0.16)" },
  muted: { text: "rgba(28, 22, 18, 0.62)", bg: "rgba(28, 22, 18, 0.05)" },
} as const;

type Tone = keyof typeof TONE_COLORS;

function StatTile({
  label,
  value,
  sub,
  icon: Icon,
  tone = "muted",
  emphasis = false,
}: {
  label: string;
  value: string;
  sub?: string;
  icon?: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  tone?: Tone;
  emphasis?: boolean;
}) {
  const palette = TONE_COLORS[tone];
  return (
    <div className="flex-1 min-w-0 px-2.5 py-1.5 border-s border-border/30 first:border-s-0">
      <div className="flex items-center gap-1 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/85">
        {Icon !== undefined ? (
          <Icon className="size-2.5 opacity-70" aria-hidden={true} />
        ) : null}
        <span className="truncate">{label}</span>
      </div>
      <div
        className={cn(
          "mt-0.5 font-mono tabular-nums leading-tight",
          emphasis ? "text-[15px] font-semibold" : "text-[13px] font-medium",
        )}
        style={{ color: palette.text }}
      >
        {value}
      </div>
      {sub !== undefined ? (
        <div className="mt-0.5 truncate text-[9px] tabular-nums text-muted-foreground/70">
          {sub}
        </div>
      ) : null}
      {emphasis ? (
        <div
          aria-hidden="true"
          className="mt-1 h-px w-6 rounded-full"
          style={{ background: palette.bg }}
        />
      ) : null}
    </div>
  );
}

function ScoreChip({
  value,
  tone = "accepted",
  size = "md",
}: {
  value: number;
  tone?: Tone;
  size?: "sm" | "md";
}) {
  const palette = TONE_COLORS[tone];
  const padding = size === "sm" ? "px-1.5 py-[1px]" : "px-2 py-0.5";
  const fontSize = size === "sm" ? "text-[10px]" : "text-[11px]";
  return (
    <span
      className={cn(
        "inline-flex items-baseline rounded-sm font-mono tabular-nums font-semibold",
        padding,
        fontSize,
      )}
      style={{ background: palette.bg, color: palette.text }}
    >
      {value.toFixed(2)}
    </span>
  );
}

function MinibatchPanel({
  entries,
  valsetRows,
  iteration,
}: {
  entries: MinibatchEntry[];
  valsetRows: ValsetRow[];
  // GEPA iteration of the selected node. When set, the panel shows only the
  // feedback events emitted while that iteration's propose() was running —
  // the 3-ish entries that actually informed accepting / rejecting the node.
  // null (seed candidate, or backend versions before iteration plumbing)
  // falls back to the run-wide most-recent view.
  iteration: number | null;
}) {
  const RECENT = 8;
  const recent = useMemo(() => {
    const filtered =
      iteration === null
        ? entries
        : entries.filter((e) => e.iteration === iteration);
    return filtered.slice(-RECENT).reverse();
  }, [entries, iteration]);
  const valsetById = useMemo(() => {
    const m = new Map<string, ValsetRow>();
    for (const row of valsetRows) m.set(row.id, row);
    return m;
  }, [valsetRows]);

  if (recent.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border/50 bg-background/40 px-3 py-3 text-[11px] text-muted-foreground">
        {msg("trajectory.minibatch.no_data")}
      </div>
    );
  }
  return (
    <ol className="space-y-2.5">
      {recent.map((entry) => (
        <MinibatchEntryCard
          key={entry.sequence}
          entry={entry}
          valsetRow={valsetById.get(entry.example_id) ?? null}
        />
      ))}
    </ol>
  );
}

function MinibatchEntryCard({
  entry,
  valsetRow,
}: {
  entry: MinibatchEntry;
  valsetRow: ValsetRow | null;
}) {
  const passed = entry.score > 0;
  const answerFields = useMemo(() => parsePredictionFields(entry.prediction), [entry.prediction]);
  const questionFields = useMemo(
    () => (valsetRow ? Object.entries(valsetRow.inputs) : []),
    [valsetRow],
  );

  return (
    <li className="overflow-hidden rounded-lg border border-[#DDD4C8]/60 bg-background/70 shadow-[0_1px_2px_rgba(28,22,18,0.02)]">
      <div className="flex items-center justify-between gap-2 border-b border-border/30 bg-[#F8F4EF]/60 px-3 py-2">
        <div className="flex items-center gap-2 text-[11px]">
          <StatusChip passed={passed} />
        </div>
        <HelpTip text={msg("trajectory.minibatch.score_label.explain")}>
          <span className="inline-flex items-baseline gap-1.5">
            <span className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
              {msg("trajectory.minibatch.score_label")}
            </span>
            <span
              className={cn(
                "font-mono tabular-nums text-[11px]",
                passed ? "font-semibold text-foreground" : "text-muted-foreground",
              )}
            >
              {entry.score.toFixed(2)}
            </span>
          </span>
        </HelpTip>
      </div>

      <div className="space-y-2.5 px-3 pb-3 pt-2.5">
        {questionFields.length > 0 ? (
          <FieldSection
            label={msg("trajectory.minibatch.question_label")}
            info={msg("trajectory.minibatch.question_label.explain")}
          >
            {questionFields.map(([key, value]) => (
              <FieldRow key={key} fieldName={key} value={value} />
            ))}
          </FieldSection>
        ) : null}

        {answerFields !== null && answerFields.length > 0 ? (
          <FieldSection
            label={msg("trajectory.minibatch.prediction_label")}
            info={msg("trajectory.minibatch.prediction_label.explain")}
          >
            {answerFields.map(([key, value]) => (
              <FieldRow key={key} fieldName={key} value={value} />
            ))}
          </FieldSection>
        ) : entry.prediction.length > 0 ? (
          <FieldSection
            label={msg("trajectory.minibatch.prediction_label")}
            info={msg("trajectory.minibatch.prediction_label.explain")}
          >
            <FieldRow value={entry.prediction} />
          </FieldSection>
        ) : null}

        {entry.feedback.length > 0 ? <FeedbackBlock body={entry.feedback} /> : null}
      </div>
    </li>
  );
}

function StatusChip({ passed }: { passed: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-[#DDD4C8]/70 bg-background/80 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-foreground/75">
      {passed
        ? msg("trajectory.minibatch.pass_label")
        : msg("trajectory.minibatch.fail_label")}
    </span>
  );
}

function FieldSection({
  label,
  info,
  children,
}: {
  label: string;
  info?: string;
  children: React.ReactNode;
}) {
  const labelNode = (
    <div className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
      {label}
    </div>
  );
  return (
    <div className="space-y-1">
      {info !== undefined ? <HelpTip text={info}>{labelNode}</HelpTip> : labelNode}
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function FieldRow({ fieldName, value }: { fieldName?: string; value: string }) {
  return (
    <div className="rounded border border-[#DDD4C8]/40 bg-background/80 px-2 py-1.5">
      {fieldName !== undefined ? (
        <div className="mb-0.5 text-[9px] font-mono text-muted-foreground/80" dir="ltr">
          {fieldName}
        </div>
      ) : null}
      <div
        className="text-[11px] leading-snug text-foreground/90 whitespace-pre-wrap"
        dir="auto"
        style={{ wordBreak: "break-word" }}
      >
        {value}
      </div>
    </div>
  );
}

function FeedbackBlock({ body }: { body: string }) {
  return (
    <div className="space-y-1">
      <HelpTip text={msg("trajectory.minibatch.feedback_label.explain")}>
        <div className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
          {msg("trajectory.minibatch.feedback_label")}
        </div>
      </HelpTip>
      <div
        className="rounded border border-[#DDD4C8]/40 bg-background/80 px-2.5 py-2 text-[11px] leading-relaxed text-foreground/90 whitespace-pre-wrap"
        dir="auto"
        style={{ wordBreak: "break-word" }}
      >
        {body}
      </div>
    </div>
  );
}

// Parses DSPy-style `Prediction(key='value', key2="value2", …)` reprs into
// [key, value] pairs. Returns null when the input isn't a recognizable
// `ClassName(...)` call so the caller can fall back to rendering raw text.
function parsePredictionFields(raw: string): Array<[string, string]> | null {
  const trimmed = raw.trim();
  if (trimmed.length === 0) return null;
  const m = /^[A-Za-z_][A-Za-z0-9_]*\((.*)\)$/s.exec(trimmed);
  if (m === null) return null;
  const body = m[1] ?? "";
  const pairs: Array<[string, string]> = [];
  let i = 0;
  const n = body.length;
  while (i < n) {
    while (i < n && /\s/.test(body[i] ?? "")) i += 1;
    const keyStart = i;
    while (i < n && /[A-Za-z0-9_]/.test(body[i] ?? "")) i += 1;
    const key = body.slice(keyStart, i);
    if (key.length === 0) return null;
    while (i < n && /\s/.test(body[i] ?? "")) i += 1;
    if (body[i] !== "=") return null;
    i += 1;
    while (i < n && /\s/.test(body[i] ?? "")) i += 1;
    const value = readValue(body, i);
    if (value === null) return null;
    pairs.push([key, value.text]);
    i = value.next;
    while (i < n && /\s/.test(body[i] ?? "")) i += 1;
    if (i < n && body[i] === ",") i += 1;
  }
  return pairs.length > 0 ? pairs : null;
}

function readValue(s: string, start: number): { text: string; next: number } | null {
  const ch = s[start];
  if (ch === "'" || ch === '"') {
    let i = start + 1;
    let out = "";
    while (i < s.length) {
      const c = s[i] ?? "";
      if (c === "\\" && i + 1 < s.length) {
        const next = s[i + 1] ?? "";
        out += next === "n" ? "\n" : next === "t" ? "\t" : next === "r" ? "\r" : next;
        i += 2;
        continue;
      }
      if (c === ch) return { text: out, next: i + 1 };
      out += c;
      i += 1;
    }
    return null;
  }
  // Unquoted value (number, None, True, nested call) — read until top-level
  // comma; balance brackets so nested calls don't terminate early.
  let depth = 0;
  let i = start;
  while (i < s.length) {
    const c = s[i] ?? "";
    if (depth === 0 && c === ",") break;
    if (c === "(" || c === "[" || c === "{") depth += 1;
    else if (c === ")" || c === "]" || c === "}") depth -= 1;
    i += 1;
  }
  const text = s.slice(start, i).trim();
  return text.length === 0 ? null : { text, next: i };
}

function Section({
  title,
  info,
  action,
  children,
}: {
  title: string;
  info?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  const titleNode = (
    <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
      {title}
    </div>
  );
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        {info !== undefined ? <HelpTip text={info}>{titleNode}</HelpTip> : titleNode}
        {action}
      </div>
      {children}
    </div>
  );
}

type View = "prompt" | "diff";

function usePromptView(): readonly [View, (v: View) => void] {
  const [view, setViewState] = useState<View>("diff");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(DIFF_VIEW_KEY);
    if (stored === "prompt" || stored === "diff") setViewState(stored);
  }, []);

  const setView = (v: View) => {
    setViewState(v);
    try {
      window.localStorage.setItem(DIFF_VIEW_KEY, v);
    } catch {
      /* private mode, etc. */
    }
  };

  return [view, setView] as const;
}

const PROMPT_TOGGLE_TRIGGER_CLASS =
  "relative z-10 w-full min-w-0 whitespace-nowrap text-center text-[10px] leading-none rounded-sm px-2.5 py-1 font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none";

function PromptViewToggle({ view, onChange }: { view: View; onChange: (v: View) => void }) {
  const tabCount = 2;
  const tabIndex = view === "prompt" ? 0 : 1;
  const indicatorOffset =
    tabIndex === 0
      ? "2px"
      : `calc(${((tabIndex * 100) / tabCount).toFixed(3)}% + ${(2 - (tabIndex * 2) / tabCount).toFixed(3)}px)`;
  return (
    <Tabs value={view} onValueChange={(v) => onChange(v as View)} dir="rtl">
      <TabsList
        className="relative grid w-full rounded-md bg-muted p-0.5 gap-0.5 border-none shadow-none h-auto items-stretch"
        style={{ gridTemplateColumns: `repeat(${tabCount}, minmax(0, 1fr))` }}
      >
        <div
          className="absolute top-0.5 bottom-0.5 rounded-sm bg-[#3D2E22] shadow-sm transition-[inset-inline-start] duration-200 ease-out"
          style={{
            width: `calc(${(100 / tabCount).toFixed(3)}% - 3px)`,
            insetInlineStart: indicatorOffset,
          }}
        />
        <TabsTrigger value="prompt" className={PROMPT_TOGGLE_TRIGGER_CLASS}>
          {msg("trajectory.drawer.toggle.prompt")}
        </TabsTrigger>
        <TabsTrigger value="diff" className={PROMPT_TOGGLE_TRIGGER_CLASS}>
          {msg("trajectory.drawer.toggle.diff")}
        </TabsTrigger>
      </TabsList>
    </Tabs>
  );
}

interface DiffLine {
  text: string;
  kind: "same" | "added" | "removed";
}

function diffLines(before: string, after: string): DiffLine[] {
  const a = before.split("\n");
  const b = after.split("\n");
  const m = a.length;
  const n = b.length;
  const stride = n + 1;
  const dp = new Int32Array((m + 1) * stride);
  for (let i = m - 1; i >= 0; i -= 1) {
    for (let j = n - 1; j >= 0; j -= 1) {
      if (a[i] === b[j]) {
        dp[i * stride + j] = (dp[(i + 1) * stride + (j + 1)] ?? 0) + 1;
      } else {
        const down = dp[(i + 1) * stride + j] ?? 0;
        const right = dp[i * stride + (j + 1)] ?? 0;
        dp[i * stride + j] = down > right ? down : right;
      }
    }
  }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    const ai = a[i] ?? "";
    const bj = b[j] ?? "";
    if (ai === bj) {
      out.push({ text: ai, kind: "same" });
      i += 1;
      j += 1;
    } else {
      const down = dp[(i + 1) * stride + j] ?? 0;
      const right = dp[i * stride + (j + 1)] ?? 0;
      if (down >= right) {
        out.push({ text: ai, kind: "removed" });
        i += 1;
      } else {
        out.push({ text: bj, kind: "added" });
        j += 1;
      }
    }
  }
  while (i < m) {
    out.push({ text: a[i] ?? "", kind: "removed" });
    i += 1;
  }
  while (j < n) {
    out.push({ text: b[j] ?? "", kind: "added" });
    j += 1;
  }
  return out;
}

function PromptDiff({ before, after }: { before: string; after: string }) {
  const lines = useMemo(() => diffLines(before, after), [before, after]);
  const changed = lines.some((s) => s.kind !== "same");
  if (!changed) {
    return (
      <div className="rounded border border-dashed border-border/50 bg-background/40 px-3 py-2 text-[11px] text-muted-foreground">
        {msg("trajectory.detail.diff_unchanged")}
      </div>
    );
  }
  const addedCount = lines.reduce((n, l) => n + (l.kind === "added" ? 1 : 0), 0);
  const removedCount = lines.reduce((n, l) => n + (l.kind === "removed" ? 1 : 0), 0);
  return (
    <div dir="ltr" className="font-mono text-xs leading-relaxed">
      <div className="mb-1.5 flex items-center justify-end gap-3 text-[10px] tabular-nums opacity-80">
        <span style={{ color: "#3f4d1f" }}>+{addedCount}</span>
        <span style={{ color: "#6e2e16" }}>−{removedCount}</span>
      </div>
      <div className="-mx-3">
        {lines.map((line, idx) => {
          const isAdded = line.kind === "added";
          const isRemoved = line.kind === "removed";
          const bg = isAdded ? PARETO_PASS_BG : isRemoved ? PARETO_FAIL_BG : "transparent";
          const color = isAdded ? "#3f4d1f" : isRemoved ? "#6e2e16" : "rgba(28, 22, 18, 0.78)";
          const prefix = isAdded ? "+" : isRemoved ? "−" : " ";
          return (
            <div
              key={idx}
              className="flex items-start gap-2 px-3 py-0.5"
              style={{ background: bg, color }}
            >
              <span
                aria-hidden="true"
                className="select-none tabular-nums opacity-60"
                style={{ width: "0.9rem", textAlign: "center", flexShrink: 0 }}
              >
                {prefix}
              </span>
              <span
                className="whitespace-pre-wrap"
                style={{ wordBreak: "break-word", flex: 1 }}
              >
                {line.text.length === 0 ? "​" : line.text}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface ParetoGridSectionProps {
  examples: PerExampleScore[];
  pinnedId: string | null;
  onPin: (id: string) => void;
  valsetById: Map<string, ValsetRow>;
  predictionsForCandidate: Map<string, string>;
}

function ParetoGridSection({
  examples,
  pinnedId,
  onPin,
  valsetById,
  predictionsForCandidate,
}: ParetoGridSectionProps) {
  const focused = pinnedId === null ? null : examples.find((e) => e.id === pinnedId) ?? null;
  const focusedRow = focused === null ? null : valsetById.get(focused.id) ?? null;
  const focusedPrediction =
    focused === null ? null : predictionsForCandidate.get(focused.id) ?? null;
  const passed = examples.filter((e) => e.score > 0).length;

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-[10px] text-muted-foreground tabular-nums">
          {formatMsg("trajectory.detail.pareto_passed", {
            count: passed,
            total: examples.length,
          })}
        </div>
      </div>
      <div
        className="flex flex-wrap gap-1"
        dir="rtl"
        role="grid"
        aria-label={msg("trajectory.detail.pareto_title")}
      >
        {examples.map((ex, idx) => {
          const ok = ex.score > 0;
          const isPinned = pinnedId === ex.id;
          return (
            <button
              key={ex.id}
              type="button"
              onClick={() => onPin(ex.id)}
              aria-label={formatMsg("trajectory.detail.pareto_example_label", {
                id: ex.id,
                score: ex.score.toFixed(2),
              })}
              aria-pressed={isPinned}
              className="relative rounded-sm font-mono text-[9px] tabular-nums leading-none transition-transform hover:scale-110 focus:scale-110 focus:outline-none"
              style={{
                width: 24,
                height: 24,
                background: ok ? PARETO_PASS : PARETO_FAIL,
                color: ok ? "#2a3812" : "#4a1c0a",
                outline: isPinned ? "2px solid #1c1612" : "none",
                outlineOffset: isPinned ? "1px" : undefined,
                boxShadow: isPinned
                  ? "inset 0 0 0 1px rgba(28, 22, 18, 0.45)"
                  : undefined,
              }}
            >
              <span
                aria-hidden="true"
                className="absolute inset-0 flex items-center justify-center font-semibold opacity-70"
              >
                {idx + 1}
              </span>
            </button>
          );
        })}
      </div>
      {focused !== null ? (
        <div className="overflow-hidden rounded-lg border border-[#DDD4C8]/60 bg-background/70 shadow-[0_1px_2px_rgba(28,22,18,0.02)]">
          <div className="flex items-center justify-between gap-2 border-b border-border/30 bg-[#F8F4EF]/60 px-3 py-2">
            <div className="flex items-center gap-2 text-[11px]">
              <StatusChip passed={focused.score > 0} />
              <span className="font-mono text-[10px] text-muted-foreground" dir="ltr">
                #{focused.id}
              </span>
            </div>
            <HelpTip text={msg("trajectory.minibatch.score_label.explain")}>
              <span className="inline-flex items-baseline gap-1.5">
                <span className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {msg("trajectory.minibatch.score_label")}
                </span>
                <span
                  className={cn(
                    "font-mono tabular-nums text-[11px]",
                    focused.score > 0 ? "font-semibold text-foreground" : "text-muted-foreground",
                  )}
                >
                  {focused.score.toFixed(2)}
                </span>
              </span>
            </HelpTip>
          </div>
          <div className="space-y-2.5 px-3 pb-3 pt-2.5">
            {focusedRow === null ? (
              <div className="text-[11px] text-muted-foreground italic">
                {msg("trajectory.pareto.cell_detail_pending")}
              </div>
            ) : (
              <ValsetFieldGroups row={focusedRow} prediction={focusedPrediction} />
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ValsetFieldGroups({
  row,
  prediction,
}: {
  row: ValsetRow;
  prediction: string | null;
}) {
  const inputs = Object.entries(row.inputs);
  const outputs = Object.entries(row.outputs);
  const predictionFields = useMemo(
    () => (prediction === null ? null : parsePredictionFields(prediction)),
    [prediction],
  );
  return (
    <div className="space-y-2">
      {inputs.length > 0 ? (
        <ValsetFieldGroup
          label={msg("trajectory.pareto.cell.inputs_label")}
          info={msg("trajectory.pareto.cell.inputs_label.explain")}
          entries={inputs}
        />
      ) : null}
      {prediction === null ? (
        <PendingPredictionRow />
      ) : predictionFields !== null && predictionFields.length > 0 ? (
        <ValsetFieldGroup
          label={msg("trajectory.pareto.cell.prediction_label")}
          info={msg("trajectory.pareto.cell.prediction_label.explain")}
          entries={predictionFields}
        />
      ) : prediction.length > 0 ? (
        <ValsetFieldGroup
          label={msg("trajectory.pareto.cell.prediction_label")}
          info={msg("trajectory.pareto.cell.prediction_label.explain")}
          entries={[["", prediction]]}
        />
      ) : null}
      {outputs.length > 0 ? (
        <ValsetFieldGroup
          label={msg("trajectory.pareto.cell.outputs_label")}
          info={msg("trajectory.pareto.cell.outputs_label.explain")}
          entries={outputs}
        />
      ) : null}
    </div>
  );
}

function PendingPredictionRow() {
  return (
    <div className="space-y-1">
      <SectionLabel
        label={msg("trajectory.pareto.cell.prediction_label")}
        info={msg("trajectory.pareto.cell.prediction_label.explain")}
      />
      <div className="rounded border border-dashed border-[#DDD4C8]/50 bg-background/60 px-2 py-1.5 text-[11px] italic text-muted-foreground">
        {msg("trajectory.pareto.cell.prediction_unavailable")}
      </div>
    </div>
  );
}

function SectionLabel({ label, info }: { label: string; info?: string }) {
  const node = (
    <div className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
      {label}
    </div>
  );
  return info === undefined ? node : <HelpTip text={info}>{node}</HelpTip>;
}

function ValsetFieldGroup({
  label,
  info,
  entries,
}: {
  label: string;
  info?: string;
  entries: Array<[string, string]>;
}) {
  return (
    <div className="space-y-1">
      <SectionLabel label={label} info={info} />
      <div className="space-y-1">
        {entries.map(([key, value], idx) => (
          <div
            key={key.length === 0 ? `__raw_${idx}` : key}
            className="rounded border border-[#DDD4C8]/40 bg-background/80 px-2 py-1.5"
          >
            {key.length > 0 ? (
              <div
                className="mb-0.5 text-[9px] font-mono text-muted-foreground/80"
                dir="ltr"
              >
                {key}
              </div>
            ) : null}
            <div
              className="text-[11px] leading-snug text-foreground/90 whitespace-pre-wrap"
              dir="auto"
              style={{ wordBreak: "break-word" }}
            >
              {value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
