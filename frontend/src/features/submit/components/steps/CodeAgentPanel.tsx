"use client";

import * as React from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bot,
  XCircle,
  RotateCcw,
  Check,
  ChevronRight,
  ChevronLeft,
  Ruler,
  FileCode2,
  Loader2,
  MessageSquarePlus,
} from "lucide-react";
import { formatMsg, msg } from "@/shared/lib/messages";

import { cn } from "@/shared/lib/utils";
import { TERMS } from "@/shared/lib/terms";
import {
  AgentThread,
  AgentBubble,
  Composer,
  MessageActions,
  UserBubble,
  UserBubbleEditor,
} from "@/shared/ui/agent";
import type { AgentToolCall as SharedAgentToolCall } from "@/shared/ui/agent";
import { ToolCallRow } from "@/features/agent-panel";

import type { AgentMessage, AgentToolCall, CodeAgentState } from "../../hooks/use-code-agent";

interface Props {
  agent: CodeAgentState;
  disabled?: boolean;
  disabledReason?: string;
  className?: string;
}

type Pair = {
  key: string;
  user: { msg: AgentMessage; index: number } | null;
  agent: AgentMessage | null;
};

const COMPOSER_PLACEHOLDER = msg("auto.features.submit.components.steps.codeagentpanel.literal.1");

export function CodeAgentPanel({ agent, disabled, disabledReason, className }: Props) {
  const [draft, setDraft] = React.useState("");
  const [editingIndex, setEditingIndex] = React.useState<number | null>(null);
  const [editDraft, setEditDraft] = React.useState("");

  const streaming = agent.status === "streaming";
  const isEditingAny = editingIndex !== null;

  const pairs = React.useMemo<Pair[]>(() => {
    const result: Pair[] = [];
    let currentUser: { msg: AgentMessage; index: number } | null = null;
    let seq = 0;
    agent.messages.forEach((msg, i) => {
      if (msg.role === "user") {
        if (currentUser) {
          result.push({ key: `p-${seq++}`, user: currentUser, agent: null });
        }
        currentUser = { msg, index: i };
      } else {
        result.push({ key: `p-${seq++}`, user: currentUser, agent: msg });
        currentUser = null;
      }
    });
    if (currentUser) {
      result.push({ key: `p-${seq++}`, user: currentUser, agent: null });
    }
    return result;
  }, [agent.messages]);

  const latestAgentKey = React.useMemo(() => {
    for (let i = pairs.length - 1; i >= 0; i--) {
      const p = pairs[i];
      if (p && p.agent) return p.key;
    }
    return null;
  }, [pairs]);

  const handleSend = () => {
    if (!agent.canSend || !draft.trim() || disabled) return;
    agent.send(draft);
    setDraft("");
  };

  const startEdit = (index: number, content: string) => {
    setEditingIndex(index);
    setEditDraft(content);
  };

  const cancelEdit = () => {
    setEditingIndex(null);
    setEditDraft("");
  };

  const submitEdit = () => {
    if (editingIndex === null) return;
    const trimmed = editDraft.trim();
    if (!trimmed) return;
    agent.editAndResend(editingIndex, trimmed);
    setEditingIndex(null);
    setEditDraft("");
  };

  const hasConversation =
    agent.messages.length > 0 ||
    agent.signatureVersions.length > 0 ||
    agent.metricVersions.length > 0;

  const handleNewChat = () => {
    if (!hasConversation || disabled) return;
    agent.reset();
    setDraft("");
    setEditingIndex(null);
    setEditDraft("");
  };

  const renderToolCall = React.useCallback(
    (call: SharedAgentToolCall, { isRetry }: { isRetry: boolean }) => (
      <ToolCallCard call={call} isRetry={isRetry} />
    ),
    [],
  );

  return (
    <div dir="rtl" className={cn("flex h-full min-h-0 flex-col overflow-hidden", className)}>
      {hasConversation && !disabled && (
        <div className="border-b border-[#3D2E22]/10 px-3 py-2 shrink-0">
          <button
            type="button"
            onClick={handleNewChat}
            className={cn(
              "group flex w-full items-center justify-center gap-1.5 rounded-full",
              "border border-[#3D2E22]/10 bg-[#3D2E22]/[0.02]",
              "px-2.5 py-1.5 text-[0.6875rem] font-medium text-[#3D2E22]/75",
              "shadow-[inset_0_-1px_0_rgba(61,46,34,0.04)]",
              "transition-[color,background-color,border-color,box-shadow,transform] duration-150 ease-out",
              "hover:border-[#3D2E22]/20 hover:bg-[#3D2E22]/[0.06] hover:text-[#3D2E22]",
              "active:scale-[0.99] active:bg-[#3D2E22]/[0.08]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]/60 focus-visible:ring-offset-1 focus-visible:ring-offset-[#FAF8F5]",
              "cursor-pointer",
            )}
            title={msg("auto.features.submit.components.steps.codeagentpanel.literal.2")}
            aria-label={msg("auto.features.submit.components.steps.codeagentpanel.literal.3")}
          >
            <MessageSquarePlus
              className="size-3.5 opacity-75 transition-opacity duration-150 ease-out group-hover:opacity-100"
              strokeWidth={2}
              aria-hidden
            />
            <span>{msg("auto.features.submit.components.steps.codeagentpanel.1")}</span>
          </button>
        </div>
      )}
      <AgentThread
        scrollDeps={[agent.messages, agent.status]}
        isEmpty={agent.messages.length === 0 && !streaming}
        emptyState={<EmptyState disabled={disabled} disabledReason={disabledReason} />}
      >
        <AnimatePresence initial={false}>
          {pairs.map((pair) => {
            const isEditing = pair.user !== null && editingIndex === pair.user.index;
            const isAfterEdit =
              isEditingAny &&
              pair.user !== null &&
              editingIndex !== null &&
              pair.user.index > editingIndex;
            if (isAfterEdit) return null;
            return (
              <motion.div
                key={pair.key}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18, ease: [0.2, 0.8, 0.2, 1] }}
                className="space-y-1.5"
              >
                {pair.user &&
                  (isEditing ? (
                    <UserBubbleEditor
                      value={editDraft}
                      onChange={setEditDraft}
                      onSubmit={submitEdit}
                      onCancel={cancelEdit}
                      disabled={streaming}
                    />
                  ) : (
                    <UserBubble
                      content={pair.user.msg.content}
                      editable={!streaming}
                      onEdit={() => pair.user && startEdit(pair.user.index, pair.user.msg.content)}
                    />
                  ))}

                {pair.agent &&
                  !isEditing &&
                  (() => {
                    const agentMsg = pair.agent;
                    const agentText = agentMsg.content.trim();
                    const isStreamingThisPair = streaming && pair.key === latestAgentKey;
                    const showActions =
                      !isStreamingThisPair && (agentText.length > 0 || Boolean(agentMsg.model));
                    return (
                      <div className="flex justify-end">
                        <div className="flex flex-col items-end gap-1 max-w-[88%]">
                          <AgentBubble
                            msg={agentMsg}
                            thinking={
                              pair.key === latestAgentKey
                                ? {
                                    reasoning: agent.reasoning,
                                    startedAt: agent.reasoningStartedAt,
                                    endedAt: agent.reasoningEndedAt,
                                    streaming,
                                  }
                                : undefined
                            }
                            renderToolCall={renderToolCall}
                            className="max-w-full"
                          />
                          {showActions && (
                            <MessageActions
                              text={agentMsg.content}
                              model={agentMsg.model}
                              onRegenerate={
                                pair.user
                                  ? () =>
                                      pair.user &&
                                      agent.editAndResend(pair.user.index, pair.user.msg.content)
                                  : undefined
                              }
                            />
                          )}
                        </div>
                      </div>
                    );
                  })()}
              </motion.div>
            );
          })}
        </AnimatePresence>

        {!isEditingAny && streaming && agent.mode === "seed" && (
          <div className="flex items-center justify-center pt-1">
            <ActivityBreadcrumb agent={agent} />
          </div>
        )}

        {agent.error && agent.status === "error" && (
          <div className="rounded-lg bg-red-50 border border-red-100 px-2.5 py-2 text-xs text-red-600 space-y-1.5">
            <div className="flex items-start gap-1.5">
              <XCircle className="size-3 shrink-0 mt-0.5" />
              <span className="flex-1 break-words min-w-0" dir="auto">
                {agent.error}
              </span>
            </div>
            <div className="flex gap-1.5 ps-4">
              <button
                type="button"
                onClick={agent.retry}
                className="inline-flex items-center gap-1 text-[0.6875rem] text-red-700 bg-red-100 hover:bg-red-200 px-2 py-0.5 rounded cursor-pointer transition-colors"
              >
                <RotateCcw className="size-3" />
                {msg("auto.features.submit.components.steps.codeagentpanel.2")}
              </button>
              <button
                type="button"
                onClick={agent.fallbackToManual}
                className="text-[0.6875rem] text-red-700 hover:bg-red-100 px-2 py-0.5 rounded cursor-pointer transition-colors"
              >
                {msg("auto.features.submit.components.steps.codeagentpanel.3")}
              </button>
            </div>
          </div>
        )}
      </AgentThread>

      <Composer
        value={draft}
        onChange={setDraft}
        onSubmit={handleSend}
        onStop={agent.stop}
        placeholder={
          disabled
            ? disabledReason ||
              msg("auto.features.submit.components.steps.codeagentpanel.literal.4")
            : COMPOSER_PLACEHOLDER
        }
        disabled={disabled}
        streaming={streaming}
      />
    </div>
  );
}

export function VersionStepper({
  agent,
  artifact,
}: {
  agent: CodeAgentState;
  artifact: "signature" | "metric";
}) {
  const versions = artifact === "signature" ? agent.signatureVersions : agent.metricVersions;
  const versionIndex =
    artifact === "signature" ? agent.signatureVersionIndex : agent.metricVersionIndex;
  const goTo = artifact === "signature" ? agent.goToSignatureVersion : agent.goToMetricVersion;
  if (versions.length < 2) return null;
  const atFirst = versionIndex <= 0;
  const atLast = versionIndex >= versions.length - 1;
  return (
    <div
      dir="ltr"
      className="inline-flex items-center gap-0.5 rounded-full border border-border/50 bg-background/60 p-0.5 text-[0.75rem]"
    >
      <button
        type="button"
        onClick={() => goTo(versionIndex - 1)}
        disabled={atFirst}
        className="inline-flex size-7 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors"
        title="Previous version"
        aria-label="Previous version"
      >
        <ChevronLeft className="size-4" />
      </button>
      <span className="font-mono tabular-nums px-1.5 min-w-[2.25rem] text-center text-foreground/80 select-none">
        {versionIndex + 1}/{versions.length}
      </span>
      <button
        type="button"
        onClick={() => goTo(versionIndex + 1)}
        disabled={atLast}
        className="inline-flex size-7 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors"
        title="Next version"
        aria-label="Next version"
      >
        <ChevronRight className="size-4" />
      </button>
    </div>
  );
}

type StepState = "pending" | "active" | "done";

function ActivityBreadcrumb({ agent }: { agent: CodeAgentState }) {
  const steps = React.useMemo<Array<{ label: string; state: StepState }>>(() => {
    const sig = agent.signatureStatus;
    const met = agent.metricStatus;
    const readingState: StepState = sig === "waiting" && met === "waiting" ? "active" : "done";
    const sigState: StepState = sig === "writing" ? "active" : sig === "done" ? "done" : "pending";
    const metState: StepState = met === "writing" ? "active" : met === "done" ? "done" : "pending";
    return [
      {
        label: formatMsg("auto.features.submit.components.steps.codeagentpanel.template.1", {
          p1: TERMS.dataset,
        }),
        state: readingState,
      },
      {
        label: msg("auto.features.submit.components.steps.codeagentpanel.literal.5"),
        state: sigState,
      },
      { label: TERMS.metric, state: metState },
    ];
  }, [agent.signatureStatus, agent.metricStatus]);

  const lastReachedIdx = steps.reduce((acc, s, i) => (s.state === "pending" ? acc : i), -1);
  const fillPct = lastReachedIdx < 0 ? 0 : (lastReachedIdx / (steps.length - 1)) * 100;

  return (
    <div
      className="relative flex w-full max-w-[240px] items-start justify-between"
      aria-live="polite"
    >
      <div className="absolute top-[9px] start-[9px] end-[9px] h-px bg-border/70" />
      <div
        className="absolute top-[9px] start-[9px] h-px bg-[#3D2E22]/55 transition-[width] duration-500 ease-out"
        style={{ width: `calc(${fillPct}% - 18px)` }}
        aria-hidden
      />
      {steps.map((step) => (
        <div key={step.label} className="relative z-[1] flex min-w-0 flex-col items-center gap-1.5">
          <StepNode state={step.state} />
          <span
            className={cn(
              "whitespace-nowrap text-[0.625rem] leading-none tracking-wide transition-colors duration-200",
              step.state === "pending" && "text-muted-foreground/45",
              step.state === "active" && "text-[#3D2E22] font-semibold",
              step.state === "done" && "text-[#3D2E22]/75",
            )}
          >
            {step.label}
          </span>
        </div>
      ))}
    </div>
  );
}

function StepNode({ state }: { state: StepState }) {
  if (state === "done") {
    return (
      <span className="inline-flex size-[18px] items-center justify-center rounded-full bg-[#3D2E22] text-white transition-colors">
        <Check className="size-2.5" strokeWidth={3.5} />
      </span>
    );
  }
  if (state === "active") {
    return (
      <span className="inline-flex size-[18px] items-center justify-center rounded-full bg-[#3D2E22] text-white shadow-[0_0_0_3px_rgba(61,46,34,0.12)] transition-colors motion-reduce:shadow-none">
        <Loader2 className="size-2.5 animate-spin motion-reduce:animate-none" strokeWidth={3} />
      </span>
    );
  }
  return (
    <span className="inline-flex size-[18px] items-center justify-center rounded-full bg-[#E5DDD4] transition-colors">
      <span className="size-1 rounded-full bg-[#8C7A6B]/70" />
    </span>
  );
}

type DiffLine = { kind: "add" | "del" | "ctx"; text: string };

function computeLineDiff(oldText: string, newText: string): DiffLine[] {
  const a = oldText.split("\n");
  const b = newText.split("\n");
  const m = a.length;
  const n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      const ai = a[i];
      const bj = b[j];
      const below = dp[i + 1];
      const same = dp[i];
      if (!below || !same) continue;
      dp[i] = same;
      if (ai === bj) {
        same[j] = (below[j + 1] ?? 0) + 1;
      } else {
        same[j] = Math.max(below[j] ?? 0, same[j + 1] ?? 0);
      }
    }
  }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    const ai = a[i];
    const bj = b[j];
    if (ai === undefined || bj === undefined) break;
    if (ai === bj) {
      out.push({ kind: "ctx", text: ai });
      i++;
      j++;
      continue;
    }
    const down = dp[i + 1]?.[j] ?? 0;
    const right = dp[i]?.[j + 1] ?? 0;
    if (down >= right) {
      out.push({ kind: "del", text: ai });
      i++;
    } else {
      out.push({ kind: "add", text: bj });
      j++;
    }
  }
  while (i < m) {
    const ai = a[i++];
    if (ai !== undefined) out.push({ kind: "del", text: ai });
  }
  while (j < n) {
    const bj = b[j++];
    if (bj !== undefined) out.push({ kind: "add", text: bj });
  }
  return out;
}

function ToolCallCard({ call, isRetry = false }: { call: SharedAgentToolCall; isRetry?: boolean }) {
  const codeCall = call as AgentToolCall;
  const isSignature = codeCall.tool === "edit_signature";
  const Icon = isSignature ? FileCode2 : Ruler;
  const title = isSignature
    ? msg("submit.code.agent.tool.signature.title")
    : msg("submit.code.agent.tool.metric.title");

  const diff = React.useMemo<DiffLine[]>(() => {
    if (!codeCall.newCode) return [];
    return computeLineDiff(codeCall.prevCode ?? "", codeCall.newCode);
  }, [codeCall.prevCode, codeCall.newCode]);

  const addCount = diff.filter((d) => d.kind === "add").length;
  const delCount = diff.filter((d) => d.kind === "del").length;

  const summary = React.useMemo<string | null>(() => {
    if (addCount === 0 && delCount === 0) return null;
    const parts: string[] = [];
    if (addCount > 0) parts.push(`+${addCount}`);
    if (delCount > 0) parts.push(`-${delCount}`);
    const noun =
      addCount + delCount === 1
        ? msg("auto.features.submit.components.steps.codeagentpanel.literal.12")
        : msg("auto.features.submit.components.steps.codeagentpanel.literal.13");
    return `${parts.join(" ")} ${noun}`;
  }, [addCount, delCount]);

  const customBody = codeCall.newCode ? (
    <div dir="ltr" className="overflow-hidden rounded-md border border-border/40 bg-background/70">
      <div className="max-h-64 overflow-auto font-mono text-[0.6875rem] leading-[1.55]">
        {diff.length === 0 ? (
          <pre className="px-3 py-2.5 text-foreground whitespace-pre">{codeCall.newCode}</pre>
        ) : (
          <div className="py-1">
            {diff.map((line, idx) => (
              <DiffRow key={idx} line={line} />
            ))}
          </div>
        )}
      </div>
    </div>
  ) : null;

  return (
    <ToolCallRow
      call={call}
      isRetry={isRetry}
      title={title}
      icon={Icon}
      summary={summary}
      customBody={customBody}
    />
  );
}

function DiffRow({ line }: { line: DiffLine }) {
  const marker = line.kind === "add" ? "+" : line.kind === "del" ? "-" : " ";
  const bg =
    line.kind === "add" ? "bg-[#3D2E22]/[0.06]" : line.kind === "del" ? "bg-[#3D2E22]/[0.03]" : "";
  const markerColor =
    line.kind === "add"
      ? "text-[#3D2E22]"
      : line.kind === "del"
        ? "text-[#3D2E22]/45"
        : "text-muted-foreground/40";
  const textColor =
    line.kind === "del"
      ? "text-[#3D2E22]/55 line-through decoration-[#3D2E22]/30"
      : "text-[#3D2E22]/85";
  return (
    <div className={cn("flex gap-2 px-3 whitespace-pre", bg)}>
      <span aria-hidden className={cn("select-none shrink-0 w-3 text-center", markerColor)}>
        {marker}
      </span>
      <span className={cn("min-w-0 break-all whitespace-pre-wrap", textColor)}>
        {line.text || "\u00A0"}
      </span>
    </div>
  );
}

function EmptyState({ disabled, disabledReason }: { disabled?: boolean; disabledReason?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-12 text-center">
      <div className="size-12 rounded-2xl bg-[#3D2E22]/8 flex items-center justify-center">
        <Bot className="size-5 text-[#3D2E22]/40" />
      </div>
      <div className="space-y-1.5 max-w-[260px]">
        <p className="text-sm font-medium text-foreground/70">
          {disabled
            ? msg("auto.features.submit.components.steps.codeagentpanel.literal.14")
            : msg("auto.features.submit.components.steps.codeagentpanel.literal.15")}
        </p>
        <p className="text-xs text-muted-foreground/60 leading-relaxed">
          {disabled
            ? disabledReason ||
              msg("auto.features.submit.components.steps.codeagentpanel.literal.16")
            : formatMsg("auto.features.submit.components.steps.codeagentpanel.template.2", {
                p1: TERMS.dataset,
                p2: TERMS.signature,
                p3: TERMS.metric,
              })}
        </p>
      </div>
    </div>
  );
}
