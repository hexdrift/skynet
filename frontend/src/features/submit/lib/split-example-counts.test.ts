import assert from "node:assert/strict";
import { test } from "node:test";
import { splitExampleCounts } from "./split-example-counts.ts";

test("every example lands in a split and each non-zero fraction gets at least one", () => {
  assert.deepEqual(splitExampleCounts(4, { train: 0.85, val: 0.15, test: 0 }), {
    train: 3,
    val: 1,
    test: 0,
  });
  assert.deepEqual(splitExampleCounts(4, { train: 0.9, val: 0.05, test: 0.05 }), {
    train: 2,
    val: 1,
    test: 1,
  });
  assert.deepEqual(splitExampleCounts(10, { train: 0.7, val: 0.15, test: 0.15 }), {
    train: 7,
    val: 2,
    test: 1,
  });
  assert.deepEqual(splitExampleCounts(7, { train: 0.6, val: 0.2, test: 0.2 }), {
    train: 4,
    val: 2,
    test: 1,
  });
  assert.deepEqual(splitExampleCounts(101, { train: 0.8, val: 0.2, test: 0 }), {
    train: 81,
    val: 20,
    test: 0,
  });
});

test("counts follow the edited ratios and the dataset size", () => {
  assert.deepEqual(splitExampleCounts(100, { train: 0.5, val: 0.3, test: 0.2 }), {
    train: 50,
    val: 30,
    test: 20,
  });
  assert.deepEqual(splitExampleCounts(20, { train: 1, val: 0, test: 0 }), {
    train: 20,
    val: 0,
    test: 0,
  });
  assert.deepEqual(splitExampleCounts(0, { train: 0.6, val: 0.2, test: 0.2 }), {
    train: 0,
    val: 0,
    test: 0,
  });
});

test("fewer examples than non-zero fractions leaves the smallest fractions without", () => {
  assert.deepEqual(splitExampleCounts(2, { train: 0.7, val: 0.15, test: 0.15 }), {
    train: 1,
    val: 1,
    test: 0,
  });
  assert.deepEqual(splitExampleCounts(1, { train: 0.7, val: 0.15, test: 0.15 }), {
    train: 1,
    val: 0,
    test: 0,
  });
});

test("unfinished edits preview each requested share with the same one-example floor", () => {
  assert.deepEqual(splitExampleCounts(100, { train: 0.8, val: 0.3, test: 0.2 }), {
    train: 80,
    val: 30,
    test: 20,
  });
  assert.deepEqual(splitExampleCounts(4, { train: 0.85, val: 0.15, test: 0.05 }), {
    train: 3,
    val: 1,
    test: 1,
  });
});
