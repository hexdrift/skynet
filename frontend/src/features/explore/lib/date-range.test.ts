import { test } from "node:test";
import assert from "node:assert/strict";
import { isoDay, lastDaysRange, matchingPreset } from "./date-range.ts";

const today = new Date(2026, 8, 19, 15, 30);

test("isoDay formats the local calendar day with zero padding", () => {
  assert.equal(isoDay(new Date(2026, 0, 5)), "2026-01-05");
});

test("lastDaysRange counts today as the last of the days", () => {
  assert.deepEqual(lastDaysRange(7, today), { from: "2026-09-13", to: "2026-09-19" });
  assert.deepEqual(lastDaysRange(1, today), { from: "2026-09-19", to: "2026-09-19" });
});

test("lastDaysRange crosses month and year boundaries", () => {
  assert.deepEqual(lastDaysRange(30, new Date(2026, 0, 10)), { from: "2025-12-12", to: "2026-01-10" });
});

test("matchingPreset recognizes a stored preset range and nothing else", () => {
  assert.equal(matchingPreset("2026-08-21", "2026-09-19", today), 30);
  assert.equal(matchingPreset("2026-08-21", "2026-09-18", today), null);
  assert.equal(matchingPreset("2026-08-21", null, today), null);
  assert.equal(matchingPreset(null, null, today), null);
});
