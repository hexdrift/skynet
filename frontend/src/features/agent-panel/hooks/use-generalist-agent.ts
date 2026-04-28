"use client";

import * as React from "react";
import { formatMsg, msg } from "@/shared/lib/messages";

import type { AgentMessage, AgentStatus, AgentToolCall } from "@/shared/ui/agent/types";

import { confirmGeneralistApproval, streamGeneralistAgent } from "../lib/stream";
import type {
  ChatTurn,
  PendingApprovalPayload,
  ToolEndPayload,
  ToolStartPayload,
  TrustMode,
  WizardState,
} from "../lib/types";

export interface GeneralistAgentState {
  status: AgentStatus;
  statusLabel: string;
  messages: AgentMessage[];
  reasoning: string;
  reasoningStartedAt: number | null;
  reasoningEndedAt: number | null;
  error: string | null;
  pendingApproval: PendingApprovalPayload | null;
  send: (message: string) => void;
  stop: () => void;
  reset: () => void;
  confirmApproval: (approved: boolean) => Promise<void>;
}

export interface UseGeneralistAgentArgs {
  wizardState: WizardState;
  trustMode: TrustMode;
  onToolStart?: (ev: ToolStartPayload) => void;
  onToolEnd?: (ev: ToolEndPayload) => void;
}

// MCP tool names that mutate the user's optimization set. When one of these
// completes successfully inside the generalist agent, dispatch the same
// window event that manual UI flows (DeleteJobDialog, bulk delete, etc.) fire,
// so the sidebar and dashboard refresh without a page reload.
const OPTIMIZATION_MUTATING_TOOLS: ReadonlySet<string> = new Set([
  "delete_job_optimizations",
  "bulk_delete_jobs_optimizations_bulk_delete_post",
  "cancel_job_optimizations",
  "submit_job_run_post",
  "submit_grid_search_grid_search_post",
  "rename_job_optimizations",
  "toggle_pin_job_optimizations",
  "toggle_archive_job_optimizations",
  "clone_job_optimizations",
  "retry_job_optimizations",
  "bulk_pin_jobs_optimizations_bulk_pin_post",
  "bulk_archive_jobs_optimizations_bulk_archive_post",
]);

// MCP tool names that mutate the user's template library. A successful call
// dispatches ``templates-changed`` so the template picker re-fetches.
const TEMPLATE_MUTATING_TOOLS: ReadonlySet<string> = new Set([
  "create_template_templates_post",
  "update_template_templates",
  "delete_template_templates",
]);

// Sample-dataset staging. When this tool succeeds we broadcast the full
// result (rows + wizard_state patch) so the submit wizard can hydrate its
// ParsedDataset in one step.
const SAMPLE_DATASET_TOOL = "stage_sample_dataset_datasets_samples";

export function useGeneralistAgent(args: UseGeneralistAgentArgs): GeneralistAgentState {
  const { wizardState, trustMode } = args;

  const [status, setStatus] = React.useState<AgentStatus>("idle");
  const [statusLabel, setStatusLabel] = React.useState("");
  const [messages, setMessages] = React.useState<AgentMessage[]>([]);
  const [reasoning, setReasoning] = React.useState("");
  const [reasoningStartedAt, setReasoningStartedAt] = React.useState<number | null>(null);
  const [reasoningEndedAt, setReasoningEndedAt] = React.useState<number | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [pendingApproval, setPendingApproval] = React.useState<PendingApprovalPayload | null>(null);

  const abortRef = React.useRef<AbortController | null>(null);
  const reasoningBufRef = React.useRef("");
  const replyBufRef = React.useRef("");
  const messagesRef = React.useRef<AgentMessage[]>(messages);
  React.useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const snapshotRef = React.useRef({ wizardState, trustMode });
  React.useEffect(() => {
    snapshotRef.current = { wizardState, trustMode };
  }, [wizardState, trustMode]);

  const callbacksRef = React.useRef(args);
  React.useEffect(() => {
    callbacksRef.current = args;
  }, [args]);

  const appendReply = React.useCallback((chunk: string) => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (!last || last.role !== "assistant") return prev;
      const next = prev.slice();
      next[next.length - 1] = { ...last, content: last.content + chunk };
      return next;
    });
  }, []);

  const pushToolCall = React.useCallback((call: AgentToolCall) => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (!last || last.role !== "assistant") return prev;
      const next = prev.slice();
      next[next.length - 1] = { ...last, toolCalls: [...(last.toolCalls ?? []), call] };
      return next;
    });
  }, []);

  const finishToolCall = React.useCallback(
    (id: string, nextStatus: "done" | "error", result?: unknown) => {
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (!last || last.role !== "assistant" || !last.toolCalls?.length) return prev;
        const next = prev.slice();
        next[next.length - 1] = {
          ...last,
          toolCalls: last.toolCalls.map((t) =>
            t.id === id
              ? {
                  ...t,
                  status: nextStatus,
                  endedAt: Date.now(),
                  payload: { ...(t.payload ?? {}), result },
                }
              : t,
          ),
        };
        return next;
      });
    },
    [],
  );

  const runAgent = React.useCallback(
    (userMessage: string, history: AgentMessage[]) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      reasoningBufRef.current = "";
      replyBufRef.current = "";

      setStatus("streaming");
      setStatusLabel(msg("auto.features.agent.panel.hooks.use.generalist.agent.literal.1"));
      setReasoning("");
      setReasoningStartedAt(Date.now());
      setReasoningEndedAt(null);
      setError(null);
      setPendingApproval(null);

      setMessages((m) => [
        ...m,
        { role: "user", content: userMessage },
        { role: "assistant", content: "", toolCalls: [] },
      ]);

      const chatHistory: ChatTurn[] = history
        .filter((m) => m.content.trim().length > 0)
        .map((m) => ({ role: m.role, content: m.content }));
      const { wizardState: ws, trustMode: tm } = snapshotRef.current;

      void streamGeneralistAgent(
        {
          user_message: userMessage,
          chat_history: chatHistory,
          wizard_state: ws,
          trust_mode: tm,
        },
        {
          signal: controller.signal,
          onReasoningPatch: (chunk) => {
            if (reasoningBufRef.current === "") {
              setReasoningStartedAt(Date.now());
            }
            reasoningBufRef.current += chunk;
            setReasoning(reasoningBufRef.current);
          },
          onStatusPatch: (label) => {
            if (label) setStatusLabel(label);
          },
          onToolStart: (ev) => {
            setStatusLabel(
              formatMsg("auto.features.agent.panel.hooks.use.generalist.agent.template.1", {
                p1: ev.tool,
              }),
            );
            pushToolCall({
              id: ev.id,
              tool: ev.tool,
              reason: ev.reason,
              status: "running",
              startedAt: Date.now(),
              endedAt: null,
              payload: { arguments: ev.arguments },
            });
            callbacksRef.current.onToolStart?.(ev);
          },
          onToolEnd: (ev) => {
            finishToolCall(ev.id, ev.status === "ok" ? "done" : "error", ev.result);
            if (ev.status === "ok") {
              if (OPTIMIZATION_MUTATING_TOOLS.has(ev.tool)) {
                window.dispatchEvent(new Event("optimizations-changed"));
              }
              if (TEMPLATE_MUTATING_TOOLS.has(ev.tool)) {
                window.dispatchEvent(new Event("templates-changed"));
              }
              if (ev.tool === SAMPLE_DATASET_TOOL && ev.result) {
                window.dispatchEvent(
                  new CustomEvent("wizard:dataset-staged", { detail: ev.result }),
                );
              }
            }
            callbacksRef.current.onToolEnd?.(ev);
          },
          onPendingApproval: (ev) => {
            setPendingApproval(ev);
            setStatusLabel(msg("auto.features.agent.panel.hooks.use.generalist.agent.literal.2"));
          },
          onApprovalResolved: () => {
            setPendingApproval(null);
            setStatusLabel(msg("auto.features.agent.panel.hooks.use.generalist.agent.literal.3"));
          },
          onMessagePatch: (chunk) => {
            if (replyBufRef.current === "") {
              setStatusLabel(msg("auto.features.agent.panel.hooks.use.generalist.agent.literal.4"));
              if (reasoningBufRef.current) setReasoningEndedAt(Date.now());
            }
            replyBufRef.current += chunk;
            appendReply(chunk);
          },
          onDone: (result) => {
            setStatus("done");
            setStatusLabel("");
            if (reasoningBufRef.current) setReasoningEndedAt(Date.now());
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (!last || last.role !== "assistant") return prev;
              const fallback =
                last.content ||
                (last.toolCalls?.length
                  ? ""
                  : msg("auto.features.agent.panel.hooks.use.generalist.agent.literal.5"));
              const next = prev.slice();
              next[next.length - 1] = {
                ...last,
                content: result.assistant_message || fallback,
              };
              return next;
            });
          },
          onError: (message) => {
            if (controller.signal.aborted) return;
            setStatus("error");
            setStatusLabel(msg("auto.features.agent.panel.hooks.use.generalist.agent.literal.6"));
            setError(message);
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last && last.role === "assistant" && !last.content && !last.toolCalls?.length) {
                return prev.slice(0, -1);
              }
              return prev;
            });
          },
        },
      );
    },
    [appendReply, pushToolCall, finishToolCall],
  );

  const send = React.useCallback(
    (message: string) => {
      const trimmed = message.trim();
      if (!trimmed) return;
      runAgent(trimmed, messagesRef.current);
    },
    [runAgent],
  );

  const stop = React.useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStatus("idle");
    setStatusLabel("");
  }, []);

  const reset = React.useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    reasoningBufRef.current = "";
    replyBufRef.current = "";
    setMessages([]);
    setStatus("idle");
    setStatusLabel("");
    setReasoning("");
    setReasoningStartedAt(null);
    setReasoningEndedAt(null);
    setError(null);
    setPendingApproval(null);
  }, []);

  const confirmApproval = React.useCallback(
    async (approved: boolean) => {
      const pa = pendingApproval;
      if (!pa) return;
      setPendingApproval(null);
      await confirmGeneralistApproval(pa.id, approved);
    },
    [pendingApproval],
  );

  return {
    status,
    statusLabel,
    messages,
    reasoning,
    reasoningStartedAt,
    reasoningEndedAt,
    error,
    pendingApproval,
    send,
    stop,
    reset,
    confirmApproval,
  };
}
