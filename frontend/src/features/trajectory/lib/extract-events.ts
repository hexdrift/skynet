import type { ProgressEvent } from "@/shared/types/api";
import type {
  CandidateMetrics,
  MinibatchEntry,
  PerExampleScore,
  RejectedMetrics,
  ValsetOutputsEvent,
  ValsetPrediction,
  ValsetRow,
} from "./types";

const CANDIDATE_EVENT = "candidate";
const REJECTED_EVENT = "candidate_rejected";
const VALSET_EVENT = "valset_rows";
const VALSET_OUTPUTS_EVENT = "valset_outputs";
const MINIBATCH_EVENT = "minibatch_feedback";

function coercePerExample(raw: unknown): PerExampleScore[] {
  if (!Array.isArray(raw)) return [];
  const out: PerExampleScore[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") continue;
    const e = entry as Record<string, unknown>;
    if (typeof e.id !== "string") continue;
    if (typeof e.score !== "number") continue;
    out.push({ id: e.id, score: e.score });
  }
  return out;
}

function coercePrompt(raw: unknown): Record<string, string> {
  if (!raw || typeof raw !== "object") return {};
  return Object.fromEntries(
    Object.entries(raw as Record<string, unknown>).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}

function coerceCandidate(
  metrics: Record<string, unknown>,
  timestamp: string,
): CandidateMetrics | null {
  const candidate_id = metrics.candidate_id;
  const generation = metrics.generation;
  const score = metrics.score;
  if (typeof candidate_id !== "string") return null;
  if (typeof generation !== "number") return null;
  if (typeof score !== "number") return null;

  const parent_id = metrics.parent_id;
  const parents_extra_raw = metrics.parents_extra;
  const discovered_at_evals = metrics.discovered_at_evals;
  const iteration = metrics.iteration;

  return {
    candidate_id,
    parent_id: typeof parent_id === "string" ? parent_id : null,
    parents_extra: Array.isArray(parents_extra_raw)
      ? parents_extra_raw.filter((v): v is string => typeof v === "string")
      : [],
    generation,
    score,
    per_example: coercePerExample(metrics.per_example),
    prompt: coercePrompt(metrics.prompt),
    discovered_at_evals: typeof discovered_at_evals === "number" ? discovered_at_evals : 0,
    iteration: typeof iteration === "number" ? iteration : null,
    timestamp,
  };
}

export function extractCandidates(events: ProgressEvent[]): CandidateMetrics[] {
  const out: CandidateMetrics[] = [];
  const seen = new Set<string>();
  for (const event of events) {
    if (event.event !== CANDIDATE_EVENT) continue;
    const parsed = coerceCandidate(event.metrics ?? {}, event.timestamp);
    if (parsed === null) continue;
    if (seen.has(parsed.candidate_id)) continue;
    seen.add(parsed.candidate_id);
    out.push(parsed);
  }
  return out.sort((a, b) => Number(a.candidate_id) - Number(b.candidate_id));
}

function coerceRejected(metrics: Record<string, unknown>): RejectedMetrics | null {
  const rejection_id = metrics.rejection_id;
  const iteration = metrics.iteration;
  const parent_id = metrics.parent_id;
  const parent_score = metrics.parent_score;
  const proposal_score = metrics.proposal_score;
  const subsample_size = metrics.subsample_size;
  if (typeof rejection_id !== "string") return null;
  if (typeof iteration !== "number") return null;
  if (typeof parent_id !== "string") return null;
  if (typeof parent_score !== "number") return null;
  if (typeof proposal_score !== "number") return null;
  if (typeof subsample_size !== "number") return null;
  const subsample_ids_raw = metrics.subsample_ids;
  return {
    rejection_id,
    iteration,
    parent_id,
    parent_score,
    proposal_score,
    subsample_size,
    proposal_prompt: coercePrompt(metrics.proposal_prompt),
    parent_prompt: coercePrompt(metrics.parent_prompt),
    subsample_ids: Array.isArray(subsample_ids_raw)
      ? subsample_ids_raw.filter((v): v is string => typeof v === "string")
      : [],
    per_example_parent: coercePerExample(metrics.per_example_parent),
    per_example_proposal: coercePerExample(metrics.per_example_proposal),
  };
}

export function extractRejected(events: ProgressEvent[]): RejectedMetrics[] {
  const out: RejectedMetrics[] = [];
  const seen = new Set<string>();
  for (const event of events) {
    if (event.event !== REJECTED_EVENT) continue;
    const parsed = coerceRejected(event.metrics ?? {});
    if (parsed === null) continue;
    if (seen.has(parsed.rejection_id)) continue;
    seen.add(parsed.rejection_id);
    out.push(parsed);
  }
  return out.sort((a, b) => a.iteration - b.iteration);
}

function coerceStringMap(value: unknown): Record<string, string> {
  if (value === null || typeof value !== "object") return {};
  const out: Record<string, string> = {};
  for (const [key, raw] of Object.entries(value as Record<string, unknown>)) {
    if (typeof raw === "string") out[key] = raw;
  }
  return out;
}

function coerceValsetRow(raw: unknown): ValsetRow | null {
  if (raw === null || typeof raw !== "object") return null;
  const entry = raw as Record<string, unknown>;
  if (typeof entry.id !== "string") return null;
  return {
    id: entry.id,
    inputs: coerceStringMap(entry.inputs),
    outputs: coerceStringMap(entry.outputs),
  };
}

// Valset rows are universal across grid pairs (one split for the whole run),
// so this extractor ignores pair_index and returns the last-seen snapshot.
export function extractValset(events: ProgressEvent[]): ValsetRow[] {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = events[i];
    if (event === undefined) continue;
    if (event.event !== VALSET_EVENT) continue;
    const rows = event.metrics?.rows;
    if (!Array.isArray(rows)) continue;
    const parsed: ValsetRow[] = [];
    for (const row of rows) {
      const r = coerceValsetRow(row);
      if (r !== null) parsed.push(r);
    }
    return parsed;
  }
  return [];
}

function coerceMinibatch(
  metrics: Record<string, unknown>,
  sequence: number,
): MinibatchEntry | null {
  const example_id = metrics.example_id;
  const score = metrics.score;
  const feedback = metrics.feedback;
  const prediction = metrics.prediction;
  if (typeof example_id !== "string") return null;
  if (typeof score !== "number") return null;
  if (typeof feedback !== "string") return null;
  return {
    example_id,
    score,
    feedback,
    prediction: typeof prediction === "string" ? prediction : "",
    sequence,
  };
}

export function extractMinibatch(events: ProgressEvent[]): MinibatchEntry[] {
  const out: MinibatchEntry[] = [];
  let seq = 0;
  for (const event of events) {
    if (event.event !== MINIBATCH_EVENT) continue;
    const parsed = coerceMinibatch(event.metrics ?? {}, seq);
    if (parsed === null) continue;
    out.push(parsed);
    seq += 1;
  }
  return out;
}

function coerceValsetOutputs(metrics: Record<string, unknown>): ValsetOutputsEvent | null {
  const candidate_index = metrics.candidate_index;
  const raw_predictions = metrics.predictions;
  if (typeof candidate_index !== "number") return null;
  if (!Array.isArray(raw_predictions)) return null;
  const predictions: ValsetPrediction[] = [];
  for (const row of raw_predictions) {
    if (!row || typeof row !== "object") continue;
    const r = row as Record<string, unknown>;
    if (typeof r.example_id !== "string") continue;
    if (typeof r.prediction !== "string") continue;
    const score = typeof r.score === "number" ? r.score : 0;
    predictions.push({ example_id: r.example_id, prediction: r.prediction, score });
  }
  return { candidate_index, predictions };
}

// Builds a (candidate_id -> example_id -> prediction text) lookup.
// candidate_id is the string form of candidate_index, matching CandidateMetrics.candidate_id.
// If the same candidate fires twice (shouldn't, but defensive), later events win.
export function extractValsetOutputs(
  events: ProgressEvent[],
): Map<string, Map<string, string>> {
  const out = new Map<string, Map<string, string>>();
  for (const event of events) {
    if (event.event !== VALSET_OUTPUTS_EVENT) continue;
    const parsed = coerceValsetOutputs(event.metrics ?? {});
    if (parsed === null) continue;
    const key = String(parsed.candidate_index);
    const inner = new Map<string, string>();
    for (const p of parsed.predictions) {
      inner.set(p.example_id, p.prediction);
    }
    out.set(key, inner);
  }
  return out;
}
