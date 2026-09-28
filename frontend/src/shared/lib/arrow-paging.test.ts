/** Tests for the shared arrow-key paging helpers. */

import assert from "node:assert/strict";
import test from "node:test";

import { arrowPageStep, isEditableTarget } from "./arrow-paging.ts";

function key(k: string, target: object | null = { tagName: "BUTTON" }) {
  return { key: k, target: target as EventTarget | null };
}

test("arrowPageStep follows the reading direction", () => {
  assert.equal(arrowPageStep(key("ArrowRight"), false), 1);
  assert.equal(arrowPageStep(key("ArrowLeft"), false), -1);
  assert.equal(arrowPageStep(key("ArrowRight"), true), -1);
  assert.equal(arrowPageStep(key("ArrowLeft"), true), 1);
});

test("arrowPageStep ignores every other key", () => {
  for (const k of ["ArrowUp", "ArrowDown", "Enter", "Tab", " ", "Home"]) {
    assert.equal(arrowPageStep(key(k), false), 0);
    assert.equal(arrowPageStep(key(k), true), 0);
  }
});

test("arrowPageStep never pages out of a text field", () => {
  for (const target of [
    { tagName: "INPUT" },
    { tagName: "TEXTAREA" },
    { tagName: "SELECT" },
    { tagName: "DIV", isContentEditable: true },
  ]) {
    assert.equal(arrowPageStep(key("ArrowRight", target), false), 0);
    assert.equal(arrowPageStep(key("ArrowLeft", target), true), 0);
  }
  assert.equal(arrowPageStep(key("ArrowRight", null), false), 1);
});

test("isEditableTarget leaves ordinary elements alone", () => {
  assert.equal(isEditableTarget({ tagName: "DIV" } as unknown as EventTarget), false);
  assert.equal(isEditableTarget({ tagName: "BUTTON" } as unknown as EventTarget), false);
  assert.equal(isEditableTarget(null), false);
});
