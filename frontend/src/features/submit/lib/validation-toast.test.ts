import assert from "node:assert/strict";
import { test } from "node:test";

import { beginValidationToast, type ToastApi, type ToastUpdate } from "./validation-toast.ts";

function fakeToast() {
  const calls: Array<{
    kind: "loading" | "update" | "dismiss";
    id: string | number;
    payload: unknown;
  }> = [];
  const api: ToastApi = {
    loading: (content, options) => {
      const id = options?.toastId ?? "auto";
      calls.push({ kind: "loading", id, payload: content });
      return id;
    },
    update: (id, options: ToastUpdate) => {
      calls.push({ kind: "update", id, payload: options });
    },
    dismiss: (id) => {
      calls.push({ kind: "dismiss", id, payload: null });
    },
  };
  return { api, calls };
}

test("a validation toast opens loading and settles once as success", () => {
  const { api, calls } = fakeToast();
  const t = beginValidationToast(api, "attempt-1", "Validating setup…");
  t.phase("Testing evaluator with gpt-4o");
  t.succeed("Setup validated");
  t.fail("ignored");
  assert.equal(t.settled, true);
  assert.deepEqual(calls, [
    { kind: "loading", id: "attempt-1", payload: "Validating setup…" },
    {
      kind: "update",
      id: "attempt-1",
      payload: { render: "Validating setup… Testing evaluator with gpt-4o", isLoading: true },
    },
    {
      kind: "update",
      id: "attempt-1",
      payload: { render: "Setup validated", type: "success", isLoading: false, autoClose: 2500 },
    },
  ]);
});

test("obsolete and failure are terminal and never turn into success", () => {
  const { api, calls } = fakeToast();
  const t = beginValidationToast(api, "attempt-2", "Validating setup…");
  t.obsolete("Setup changed — press Continue again");
  t.succeed("Setup validated");
  t.phase("late phase");
  const updates = calls.filter((c) => c.kind === "update");
  assert.equal(updates.length, 1);
  assert.deepEqual(updates[0]?.payload, {
    render: "Setup changed — press Continue again",
    type: "info",
    isLoading: false,
    autoClose: 4000,
  });

  const second = fakeToast();
  const f = beginValidationToast(second.api, "attempt-3", "Validating setup…");
  f.fail("Scorer failed: boom");
  f.succeed("Setup validated");
  assert.deepEqual(
    second.calls.filter((c) => c.kind === "update").map((c) => (c.payload as ToastUpdate).type),
    ["error"],
  );
});

test("dismiss closes the loading line once and blocks later outcomes", () => {
  const { api, calls } = fakeToast();
  const t = beginValidationToast(api, "attempt-4", "Validating setup…");
  t.dismiss();
  t.succeed("Setup validated");
  t.dismiss();
  assert.equal(t.settled, true);
  assert.deepEqual(
    calls.map((c) => c.kind),
    ["loading", "dismiss"],
  );
});
