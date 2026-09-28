import assert from "node:assert/strict";
import test from "node:test";

import { DEFAULT_SYNTHETIC_ROWS, initialAssistState, pendingDatasetSpec } from "./assist.ts";
import { prefillFreetextPredictions } from "./freetext-prefill.ts";

test("prefills generated free-text labels for a restored review round", () => {
  const annotations = prefillFreetextPredictions(
    {},
    {
      "1": { value: "82", confidence: 1 },
      "4": { value: "11", confidence: 1 },
    },
    ["1", "4"],
  );

  assert.deepEqual(annotations, { "1": "82", "4": "11" });
});

test("does not replace a human edit or insert an empty prediction", () => {
  const original = { "1": "eighty-two" };
  const annotations = prefillFreetextPredictions(
    original,
    {
      "1": { value: "82", confidence: 1 },
      "4": { value: "", confidence: 0 },
    },
    ["1", "4"],
  );

  assert.equal(annotations, original);
});

test("a synthetic session launches from the interview's dataset spec", () => {
  const spec = { brief: "Bank support chats", columns: ["text"], rows: 50 };
  assert.equal(pendingDatasetSpec({ ...initialAssistState("copilot"), datasetSpec: spec }), spec);
});

test("falls back to the user's answers when the interview returned no spec", () => {
  const assist = initialAssistState("autopilot");
  assist.interview.turns = [
    { role: "assistant", content: "What data do you need?" },
    { role: "user", content: " Hotel reviews " },
    { role: "user", content: "In Hebrew" },
  ];
  assert.deepEqual(pendingDatasetSpec(assist), {
    brief: "Hotel reviews\nIn Hebrew",
    columns: [],
    rows: DEFAULT_SYNTHETIC_ROWS,
  });
  assert.equal(pendingDatasetSpec(initialAssistState("copilot")), null);
});
