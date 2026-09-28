import assert from "node:assert/strict";
import { test } from "node:test";

import { cloneWorkflowSpec } from "./clone-workflow.ts";

test("cloneWorkflowSpec returns a stored workflow graph", () => {
  const graph = { nodes: [{ id: "n1", kind: "signature" }], edges: [] };
  assert.equal(cloneWorkflowSpec({ workflow: graph }), graph);
  assert.equal(cloneWorkflowSpec({ workflow: { nodes: [], edges: [] } })?.nodes.length, 0);
});

test("cloneWorkflowSpec rejects a missing or malformed graph", () => {
  assert.equal(cloneWorkflowSpec({ signature_code: "class S: ..." }), null);
  assert.equal(cloneWorkflowSpec({}), null);
  assert.equal(cloneWorkflowSpec({ workflow: null }), null);
  assert.equal(cloneWorkflowSpec({ workflow: [] }), null);
  assert.equal(cloneWorkflowSpec({ workflow: "graph" }), null);
  assert.equal(cloneWorkflowSpec({ workflow: { nodes: [] } }), null);
  assert.equal(cloneWorkflowSpec({ workflow: { nodes: "x", edges: [] } }), null);
});
