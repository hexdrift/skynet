import { test } from "node:test";
import assert from "node:assert/strict";
import { parseTurnStats } from "./turn-stats.ts";

test("parseTurnStats reads the backend's snake_case stats block", () => {
  assert.deepEqual(
    parseTurnStats({ input_tokens: 120, output_tokens: 30, duration_ms: 2400, ttft_ms: 600 }),
    { inputTokens: 120, outputTokens: 30, durationMs: 2400, ttftMs: 600 },
  );
});

test("parseTurnStats nulls fields that are missing or not finite numbers", () => {
  assert.deepEqual(parseTurnStats({ input_tokens: "12", output_tokens: Number.NaN }), {
    inputTokens: null,
    outputTokens: null,
    durationMs: null,
    ttftMs: null,
  });
});

test("parseTurnStats returns null when there is no stats block", () => {
  assert.equal(parseTurnStats(null), null);
  assert.equal(parseTurnStats(undefined), null);
  assert.equal(parseTurnStats("stats"), null);
});
