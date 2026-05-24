import type { ProgressEvent } from "@/shared/types/api";
import type { CandidateMetrics } from "./types";

const CANDIDATE_EVENT = "candidate";

function coerceCandidate(metrics: Record<string, unknown>): CandidateMetrics | null {
  const candidate_id = metrics.candidate_id;
  const generation = metrics.generation;
  const score = metrics.score;
  if (typeof candidate_id !== "string") return null;
  if (typeof generation !== "number") return null;
  if (typeof score !== "number") return null;

  const parent_id = metrics.parent_id;
  const parents_extra_raw = metrics.parents_extra;
  const per_example_raw = metrics.per_example;
  const prompt_raw = metrics.prompt;
  const discovered_at_evals = metrics.discovered_at_evals;

  return {
    candidate_id,
    parent_id: typeof parent_id === "string" ? parent_id : null,
    parents_extra: Array.isArray(parents_extra_raw)
      ? parents_extra_raw.filter((v): v is string => typeof v === "string")
      : [],
    generation,
    score,
    per_example: Array.isArray(per_example_raw)
      ? per_example_raw
          .map((entry): { id: string; score: number } | null => {
            if (!entry || typeof entry !== "object") return null;
            const e = entry as Record<string, unknown>;
            if (typeof e.id !== "string") return null;
            if (typeof e.score !== "number") return null;
            return { id: e.id, score: e.score };
          })
          .filter((v): v is { id: string; score: number } => v !== null)
      : [],
    prompt:
      prompt_raw && typeof prompt_raw === "object"
        ? Object.fromEntries(
            Object.entries(prompt_raw as Record<string, unknown>).filter(
              (entry): entry is [string, string] => typeof entry[1] === "string",
            ),
          )
        : {},
    discovered_at_evals: typeof discovered_at_evals === "number" ? discovered_at_evals : 0,
  };
}

export function extractCandidates(events: ProgressEvent[]): CandidateMetrics[] {
  const out: CandidateMetrics[] = [];
  const seen = new Set<string>();
  for (const event of events) {
    if (event.event !== CANDIDATE_EVENT) continue;
    const parsed = coerceCandidate(event.metrics ?? {});
    if (parsed === null) continue;
    if (seen.has(parsed.candidate_id)) continue;
    seen.add(parsed.candidate_id);
    out.push(parsed);
  }
  return out.sort((a, b) => Number(a.candidate_id) - Number(b.candidate_id));
}
