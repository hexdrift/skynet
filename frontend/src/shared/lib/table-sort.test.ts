/** Contract: header clicks cycle ascending, descending, then the original order. */

import assert from "node:assert/strict";
import test from "node:test";

import { nextSort, type SortState } from "./table-sort.ts";

const unsorted: SortState<string> = { key: "", dir: "asc" };

test("three clicks sort, reverse, then unsort", () => {
  const first = nextSort(unsorted, "confidence", unsorted);
  assert.deepEqual(first, { key: "confidence", dir: "asc" });
  const second = nextSort(first, "confidence", unsorted);
  assert.deepEqual(second, { key: "confidence", dir: "desc" });
  assert.deepEqual(nextSort(second, "confidence", unsorted), unsorted);
});

test("a different column starts ascending", () => {
  assert.deepEqual(nextSort({ key: "a", dir: "desc" }, "b", unsorted), { key: "b", dir: "asc" });
});

test("a click on the column the table defaults to always changes the order", () => {
  const initial: SortState<string> = { key: "created_at", dir: "desc" };
  const flipped = nextSort(initial, "created_at", initial);
  assert.deepEqual(flipped, { key: "created_at", dir: "asc" });
  assert.deepEqual(nextSort(flipped, "created_at", initial), initial);
});

test("unsorting another column restores the table default", () => {
  const initial: SortState<string> = { key: "created_at", dir: "desc" };
  assert.deepEqual(nextSort({ key: "name", dir: "desc" }, "name", initial), initial);
});
