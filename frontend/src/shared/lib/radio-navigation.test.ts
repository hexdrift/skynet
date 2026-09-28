import assert from "node:assert/strict";
import { test } from "node:test";
import { radioNavigationIndex } from "./radio-navigation.ts";

test("radio arrow navigation follows reading direction and wraps without trapping Tab", () => {
  assert.equal(radioNavigationIndex("ArrowRight", 0, 3, false), 1);
  assert.equal(radioNavigationIndex("ArrowRight", 0, 3, true), 2);
  assert.equal(radioNavigationIndex("ArrowDown", 2, 3, true), 0);
  assert.equal(radioNavigationIndex("Home", 2, 3, false), 0);
  assert.equal(radioNavigationIndex("End", 0, 3, true), 2);
  assert.equal(radioNavigationIndex("Tab", 0, 3, false), null);
});
