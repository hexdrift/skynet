import { test } from "node:test";
import assert from "node:assert/strict";
import { dispatchGeneralistEvent } from "./stream-events.ts";
import type { GeneralistAgentHandlers } from "./stream.ts";

type Call = [name: string, ...args: unknown[]];

/** Handlers that record every call, in order. */
function recorder(): { calls: Call[]; handlers: GeneralistAgentHandlers } {
  const calls: Call[] = [];
  const record =
    (name: string) =>
    (...args: unknown[]) => {
      calls.push([name, ...args]);
    };
  return {
    calls,
    handlers: {
      onReasoningPatch: record("reasoning"),
      onToolStart: record("toolStart"),
      onToolEnd: record("toolEnd"),
      onPendingApproval: record("pendingApproval"),
      onApprovalResolved: record("approvalResolved"),
      onMessagePatch: record("message"),
      onConversationMeta: record("conversationMeta"),
      onDone: record("done"),
      onError: record("error"),
    },
  };
}

function dispatch(events: [string, Record<string, unknown>][]): Call[] {
  const { calls, handlers } = recorder();
  for (const [event, data] of events) {
    dispatchGeneralistEvent(handlers, event, data, () => "unknown failure");
  }
  return calls;
}

test("text chunks reach the reasoning and reply handlers", () => {
  const calls = dispatch([
    ["reasoning_patch", { chunk: "hmm" }],
    ["message_patch", { chunk: "שלום" }],
    ["message_patch", {}],
  ]);
  assert.deepEqual(calls, [
    ["reasoning", "hmm"],
    ["message", "שלום"],
    ["message", ""],
  ]);
});

test("tool events carry their fields and default the missing ones", () => {
  const calls = dispatch([
    ["tool_start", { id: "c1", tool: "list_models", reason: "why", arguments: { q: 1 } }],
    ["tool_end", { id: "c1", tool: "list_models", result: { ok: true } }],
    ["tool_start", {}],
  ]);
  assert.deepEqual(calls, [
    ["toolStart", { id: "c1", tool: "list_models", reason: "why", arguments: { q: 1 } }],
    ["toolEnd", { id: "c1", tool: "list_models", status: "ok", result: { ok: true } }],
    ["toolStart", { id: "", tool: "", reason: "", arguments: {} }],
  ]);
});

test("server-worded status lines never reach the panel", () => {
  assert.deepEqual(dispatch([["status_patch", { chunk: "Calling tool…" }]]), []);
});

test("approval events reach their handlers", () => {
  const calls = dispatch([
    ["pending_approval", { id: "c2", tool: "delete_job", arguments: { id: "j" } }],
    ["approval_resolved", { id: "c2", tool: "delete_job", approved: 1 }],
  ]);
  assert.deepEqual(calls, [
    ["pendingApproval", { id: "c2", tool: "delete_job", arguments: { id: "j" } }],
    ["approvalResolved", { id: "c2", tool: "delete_job", approved: true }],
  ]);
});

test("conversation metadata reaches its handler", () => {
  assert.deepEqual(dispatch([["conversation_meta", { conversation_id: "k", title: "T" }]]), [
    ["conversationMeta", { conversation_id: "k", title: "T" }],
  ]);
});

test("done carries the assistant message, blank when missing", () => {
  const calls = dispatch([
    ["done", { assistant_message: "hi" }],
    ["done", {}],
  ]);
  assert.deepEqual(calls, [
    ["done", { assistant_message: "hi" }],
    ["done", { assistant_message: "" }],
  ]);
});

test("an error carries its code, and falls back to the generic text", () => {
  const calls = dispatch([
    ["error", { error: "context too long", code: "context_overflow" }],
    ["error", {}],
  ]);
  assert.deepEqual(calls, [
    ["error", "context too long", "context_overflow"],
    ["error", "unknown failure", undefined],
  ]);
});

test("an unknown event is ignored", () => {
  assert.deepEqual(dispatch([["turn_metadata", { allowed_tools: [] }]]), []);
});
