import type { TurnStats } from "./types";

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Read the `stats` block of a `done` event or a persisted turn. */
export function parseTurnStats(raw: unknown): TurnStats | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  return {
    inputTokens: num(r.input_tokens),
    outputTokens: num(r.output_tokens),
    durationMs: num(r.duration_ms),
    ttftMs: num(r.ttft_ms),
  };
}
