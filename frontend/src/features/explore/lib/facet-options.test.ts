import { test } from "node:test";
import assert from "node:assert/strict";
import type { PublicDashboardPoint } from "@/shared/lib/api";
import { FACET_LIMIT, countOccurrences, facetsFromPoints, pickerRows, topOptions } from "./facet-options.ts";

function options(...pairs: Array<[string, number]>) {
  return pairs.map(([value, count]) => ({ value, count }));
}

test("countOccurrences ranks busiest first, ties by value, and skips empty values", () => {
  const out = countOccurrences(["b", "a", "b", "", null, undefined, "c", "a", "b"]);
  assert.deepEqual(out, options(["b", 3], ["a", 2], ["c", 1]));
});

test("topOptions caps a long ranked list and reports the true total", () => {
  const ranked = options(
    ...Array.from({ length: FACET_LIMIT + 5 }, (_, i): [string, number] => [`m${i}`, 100 - i]),
  );
  const { options: shown, total } = topOptions(ranked, "");
  assert.equal(shown.length, FACET_LIMIT);
  assert.equal(shown[0]?.value, "m0");
  assert.equal(total, FACET_LIMIT + 5);
});

test("topOptions drops values the other filters ruled out", () => {
  const { options: shown, total } = topOptions(options(["a", 2], ["b", 0], ["c", 1]), "");
  assert.deepEqual(
    shown.map((o) => o.value),
    ["a", "c"],
  );
  assert.equal(total, 2);
});

test("topOptions matches the query case-insensitively on the raw value", () => {
  const ranked = options(["openai/gpt-4o", 5], ["anthropic/claude", 4], ["openai/GPT-4.1", 1]);
  const { options: shown, total } = topOptions(ranked, "  Gpt ");
  assert.deepEqual(
    shown.map((o) => o.value),
    ["openai/gpt-4o", "openai/GPT-4.1"],
  );
  assert.equal(total, 2);
});

test("facetsFromPoints treats legacy points as runs", () => {
  const point = (over: Partial<PublicDashboardPoint>): PublicDashboardPoint =>
    ({
      winning_model: "m",
      optimizer_name: "o",
      module_name: "predict",
      optimization_type: null,
      ...over,
    }) as PublicDashboardPoint;
  const facets = facetsFromPoints(
    [
      point({}),
      point({ optimization_type: "run" }),
      point({ optimization_type: "grid_search", module_name: "cot", optimizer_name: "gepa" }),
    ],
    "",
  );
  assert.deepEqual(facets.types, options(["run", 2], ["grid_search", 1]));
  assert.deepEqual(facets.modules, options(["predict", 2], ["cot", 1]));
  assert.equal(facets.totals.modules, 2);
  assert.deepEqual(facets.optimizers, options(["o", 2], ["gepa", 1]));
});

test("pickerRows pins the selection first, without a count when it is outside the ranked slice", () => {
  const rows = pickerRows(
    [
      { value: "gpt-4o", count: 9 },
      { value: "claude", count: 4 },
    ],
    ["rare-model", "claude"],
  );
  assert.deepEqual(rows, [
    { value: "rare-model", count: null, checked: true },
    { value: "claude", count: 4, checked: true },
    { value: "gpt-4o", count: 9, checked: false },
  ]);
});
