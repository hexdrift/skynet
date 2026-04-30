"use client";

import * as React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { PanelLeftClose, RotateCcw, Sparkles, Wand2 } from "lucide-react";
import { msg } from "@/shared/lib/messages";

import { Popover, PopoverContent, PopoverTrigger } from "@/shared/ui/primitives/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/ui/primitives/tooltip";

import { AgentThread } from "@/shared/ui/agent/agent-thread";
import { AgentBubble } from "@/shared/ui/agent/agent-bubble";
import { Composer } from "@/shared/ui/agent/composer";
import { MessageActions } from "@/shared/ui/agent/message-actions";
import { UserBubble, UserBubbleEditor } from "@/shared/ui/agent/user-bubble";
import type { AgentMessage, AgentThinking, AgentToolCall } from "@/shared/ui/agent/types";
import { cn } from "@/shared/lib/utils";
import { formatMsg } from "@/shared/lib/messages";

import { formatShortcut, useUserPrefs } from "@/features/settings";

import { useFirstRunHint } from "../hooks/use-first-run-hint";
import { useGeneralistAgent } from "../hooks/use-generalist-agent";
import { useGeneralistPanelState } from "../hooks/use-panel-state";
import { TRUST_MODE_HUE, useTrustMode } from "../hooks/use-trust-mode";
import { extractWizardPatch, useWizardStateOptional } from "../hooks/use-wizard-state";
import type { WizardState } from "../lib/types";
import { registerTutorialHook } from "@/features/tutorial";

import { MAX_WIDTH, MIN_WIDTH, NARROW_VIEWPORT_QUERY } from "../constants";

import { ApprovalCard } from "./ApprovalCard";
import { FirstRunHint } from "./FirstRunHint";
import { MinimizedPill } from "./MinimizedPill";
import { PresenceStrip } from "./PresenceStrip";
import { ToolCallRow } from "./ToolCallRow";
import { ToolsCarousel } from "./ToolsCarousel";
import { TrustToggle } from "./TrustToggle";
import { getToolRenderer } from "./tool-renderers";

function getEffectiveMinWidth(): number {
  if (typeof window === "undefined") return MIN_WIDTH;
  return Math.max(MIN_WIDTH, Math.min(360, window.innerWidth - 200));
}

function clampWidth(n: number): number {
  const min = getEffectiveMinWidth();
  return Math.max(min, Math.min(MAX_WIDTH, Math.round(n)));
}

interface GeneralistPanelProps {
  /** Optional wizard-state override. Defaults to the shared context. */
  wizardState?: WizardState;
}

type Pair = {
  key: string;
  user: { msg: AgentMessage; index: number } | null;
  agent: AgentMessage | null;
};

/**
 * Docked generalist agent panel. Renders as a left-anchored aside that
 * the user can resize, minimize to a pill, and toggle with Ctrl+J.
 * Mounted once in the app shell so the thread survives route changes.
 */
export function GeneralistPanel({ wizardState }: GeneralistPanelProps = {}) {
  const { open, setOpen, width, setWidth } = useGeneralistPanelState();
  const { mode: trustMode, next: cycleTrust } = useTrustMode();
  const { prefs } = useUserPrefs();
  const shortcutLabel = formatShortcut(prefs.agentShortcut);
  const hint = useFirstRunHint();
  const reduceMotion = useReducedMotion();
  const hue = TRUST_MODE_HUE[trustMode];

  const openPanel = React.useCallback(() => {
    hint.dismiss();
    setOpen(true);
  }, [hint, setOpen]);

  const closePanel = React.useCallback(() => {
    hint.dismiss();
    setOpen(false);
  }, [hint, setOpen]);

  React.useEffect(() => {
    if (open && hint.visible) hint.dismiss();
  }, [open, hint]);

  React.useEffect(
    () => registerTutorialHook("setGeneralistPanelOpen", (next) => setOpen(next)),
    [setOpen],
  );

  // Auto-minimize when the viewport becomes too narrow to comfortably show
  // panel + sidebar + main content. Only flip on the wider→narrower edge so
  // we don't fight a user who explicitly opens at narrow sizes.
  const prevNarrowRef = React.useRef<boolean | null>(null);
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const mql = window.matchMedia(NARROW_VIEWPORT_QUERY);
    prevNarrowRef.current = mql.matches;
    const handleChange = (e: MediaQueryListEvent) => {
      const wasNarrow = prevNarrowRef.current;
      prevNarrowRef.current = e.matches;
      if (e.matches && wasNarrow === false && open) {
        setOpen(false);
      }
    };
    mql.addEventListener("change", handleChange);
    return () => mql.removeEventListener("change", handleChange);
  }, [open, setOpen]);

  const wizardCtx = useWizardStateOptional();
  const effectiveWizard: WizardState = (() => {
    const base = wizardCtx?.state ?? {};
    const merged = wizardState ? { ...base, ...wizardState } : base;
    return wizardCtx?.overriddenFields?.length
      ? { ...merged, overridden_fields: wizardCtx.overriddenFields }
      : merged;
  })();

  const handleToolEnd = React.useCallback(
    (ev: { result?: unknown }) => {
      if (!wizardCtx) return;
      const patch = extractWizardPatch(ev.result);
      if (Object.keys(patch).length > 0) wizardCtx.applyAgentPatch(patch);
    },
    [wizardCtx],
  );

  const agent = useGeneralistAgent({
    wizardState: effectiveWizard,
    trustMode,
    onToolEnd: handleToolEnd,
  });
  const streaming = agent.status === "streaming";

  const pairs = React.useMemo<Pair[]>(() => {
    const result: Pair[] = [];
    let currentUser: { msg: AgentMessage; index: number } | null = null;
    let seq = 0;
    agent.messages.forEach((m, idx) => {
      if (m.role === "user") {
        if (currentUser) {
          result.push({ key: `g-${seq++}`, user: currentUser, agent: null });
        }
        currentUser = { msg: m, index: idx };
      } else {
        result.push({ key: `g-${seq++}`, user: currentUser, agent: m });
        currentUser = null;
      }
    });
    if (currentUser) {
      result.push({ key: `g-${seq++}`, user: currentUser, agent: null });
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

  const thinking: AgentThinking = {
    reasoning: agent.reasoning,
    startedAt: agent.reasoningStartedAt,
    endedAt: agent.reasoningEndedAt,
    streaming,
  };

  const [draft, setDraft] = React.useState("");
  const [editingIndex, setEditingIndex] = React.useState<number | null>(null);
  const [editDraft, setEditDraft] = React.useState("");
  const isEditingAny = editingIndex !== null;

  const handleSubmit = React.useCallback(() => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    agent.send(trimmed);
    setDraft("");
  }, [agent, draft]);

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

  const handleRunCode = React.useCallback(
    (code: string, language: string) => {
      if (streaming) return;
      const prompt = formatMsg("shared.agent.run_code_prompt", {
        language: language || "code",
        code,
      });
      agent.send(prompt);
    },
    [agent, streaming],
  );

  const handleRegenerate = React.useCallback(
    (userIndex: number, userContent: string) => {
      if (streaming) return;
      agent.editAndResend(userIndex, userContent);
    },
    [agent, streaming],
  );

  const resizingRef = React.useRef(false);
  const startResize = React.useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      resizingRef.current = true;
      const onMove = (ev: MouseEvent) => {
        if (!resizingRef.current) return;
        setWidth(clampWidth(ev.clientX));
      };
      const onUp = () => {
        resizingRef.current = false;
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [setWidth],
  );

  const renderToolCall = React.useCallback((call: AgentToolCall, ctx: { isRetry: boolean }) => {
    const renderer = getToolRenderer(call.tool);
    if (renderer?.card && call.status !== "running") {
      return renderer.card(call);
    }
    const summary = renderer?.summary?.(call) ?? null;
    return <ToolCallRow call={call} isRetry={ctx.isRetry} summary={summary} />;
  }, []);

  const emptyState = (
    <div className="flex flex-col items-center justify-center py-12 px-6 text-center">
      <span className="inline-flex size-10 items-center justify-center rounded-full bg-[#3D2E22]/10 text-[#3D2E22]">
        <Sparkles className="size-5" />
      </span>
      <p className="mt-3 text-sm text-foreground">
        {msg("auto.features.agent.panel.components.generalistpanel.1")}
      </p>
    </div>
  );

  return (
    <>
      <AnimatePresence>
        {open && (
          <motion.aside
            key="generalist-panel"
            dir="ltr"
            initial={reduceMotion ? false : { x: -24, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={reduceMotion ? { opacity: 0 } : { x: -24, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.2, 0.8, 0.2, 1] }}
            style={{ width }}
            className={cn(
              "fixed start-0 inset-y-0 z-40 flex h-dvh shrink-0",
              "bg-background/95 backdrop-blur-xl border-e border-border/60",
              "shadow-[8px_0_32px_rgba(61,46,34,0.06)]",
            )}
            aria-label={msg("auto.features.agent.panel.components.generalistpanel.literal.1")}
          >
            <div dir="rtl" className="relative flex min-w-0 flex-1 flex-col" data-tutorial="agent-panel">
              <div className="flex items-center justify-between gap-2 border-b border-border/40 px-3 py-2.5 shrink-0">
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className="inline-flex size-6 items-center justify-center rounded-full text-[#FAF8F5]"
                    style={{ backgroundColor: hue }}
                  >
                    <Sparkles className="size-3" aria-hidden="true" />
                  </span>
                  <div className="min-w-0">
                    <div className="text-[0.8125rem] font-medium leading-tight">
                      {msg("auto.features.agent.panel.components.generalistpanel.3")}
                    </div>
                    {agent.statusLabel && (
                      <div className="text-[0.6875rem] text-muted-foreground truncate">
                        {agent.statusLabel}
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Popover>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <PopoverTrigger asChild>
                          <button
                            type="button"
                            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent/70 hover:text-foreground transition-colors cursor-pointer"
                            aria-label={msg(
                              "auto.features.agent.panel.components.generalistpanel.literal.2",
                            )}
                          >
                            <Wand2 className="size-3.5" />
                          </button>
                        </PopoverTrigger>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" dir="rtl">
                        {msg("auto.features.agent.panel.components.generalistpanel.4")}
                      </TooltipContent>
                    </Tooltip>
                    <PopoverContent side="bottom" align="center" sideOffset={8} className="p-0">
                      <ToolsCarousel />
                    </PopoverContent>
                  </Popover>
                  <TrustToggle mode={trustMode} onCycle={cycleTrust} />
                  {agent.messages.length > 0 && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          type="button"
                          onClick={agent.reset}
                          className="rounded-md p-1.5 text-muted-foreground hover:bg-accent/70 hover:text-foreground transition-colors cursor-pointer"
                          aria-label={msg(
                            "auto.features.agent.panel.components.generalistpanel.literal.3",
                          )}
                        >
                          <RotateCcw className="size-3.5" />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" dir="rtl">
                        {msg("auto.features.agent.panel.components.generalistpanel.5")}
                      </TooltipContent>
                    </Tooltip>
                  )}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={closePanel}
                        className="rounded-md p-1.5 text-muted-foreground hover:bg-accent/70 hover:text-foreground transition-colors cursor-pointer"
                        aria-label={msg(
                          "auto.features.agent.panel.components.generalistpanel.literal.4",
                        )}
                      >
                        <PanelLeftClose className="size-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" dir="rtl">
                      {msg("auto.features.agent.panel.components.generalistpanel.6")}{" "}
                      <span className="opacity-70 font-mono">({shortcutLabel})</span>
                    </TooltipContent>
                  </Tooltip>
                </div>
              </div>

              <AgentThread
                isEmpty={agent.messages.length === 0}
                emptyState={emptyState}
                scrollDeps={[
                  agent.messages.length,
                  agent.messages[agent.messages.length - 1]?.content,
                  agent.messages[agent.messages.length - 1]?.toolCalls?.length,
                  agent.reasoning,
                  agent.statusLabel,
                  agent.pendingApproval?.id ?? "",
                ]}
              >
                {pairs.map((pair) => {
                  const isEditing = pair.user !== null && editingIndex === pair.user.index;
                  const isAfterEdit =
                    isEditingAny &&
                    pair.user !== null &&
                    editingIndex !== null &&
                    pair.user.index > editingIndex;
                  if (isAfterEdit) return null;
                  const agentMsg = pair.agent;
                  const agentText = agentMsg?.content.trim() ?? "";
                  const isStreamingThisPair = streaming && pair.key === latestAgentKey;
                  const showActions =
                    !isEditing &&
                    agentMsg !== null &&
                    !isStreamingThisPair &&
                    (agentText.length > 0 || Boolean(agentMsg.model));
                  return (
                    <div key={pair.key} className="space-y-1.5">
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
                            onEdit={() =>
                              pair.user && startEdit(pair.user.index, pair.user.msg.content)
                            }
                          />
                        ))}

                      {agentMsg && !isEditing && (
                        <div className="flex justify-end">
                          <div className="flex flex-col items-end gap-1 max-w-[88%]">
                            <AgentBubble
                              msg={agentMsg}
                              thinking={pair.key === latestAgentKey ? thinking : undefined}
                              renderToolCall={renderToolCall}
                              onRunCode={handleRunCode}
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
                                        handleRegenerate(pair.user.index, pair.user.msg.content)
                                    : undefined
                                }
                              />
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}

                {agent.pendingApproval && (
                  <ApprovalCard payload={agent.pendingApproval} onResolve={agent.confirmApproval} />
                )}

                {agent.error && (
                  <div className="text-[0.75rem] text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                    {agent.error}
                  </div>
                )}
              </AgentThread>

              <Composer
                value={draft}
                onChange={setDraft}
                onSubmit={handleSubmit}
                onStop={agent.stop}
                placeholder={msg("auto.features.agent.panel.components.generalistpanel.literal.5")}
                streaming={streaming}
                sendAriaLabel={msg(
                  "auto.features.agent.panel.components.generalistpanel.literal.6",
                )}
                stopAriaLabel={msg(
                  "auto.features.agent.panel.components.generalistpanel.literal.7",
                )}
              />

              <PresenceStrip active={streaming} hue={hue} />
            </div>

            {/* Resize handle — physical right edge (inline-end in LTR outer) */}
            <button
              type="button"
              onMouseDown={startResize}
              aria-label={msg("auto.features.agent.panel.components.generalistpanel.literal.8")}
              tabIndex={-1}
              className={cn(
                "absolute top-0 end-0 h-full w-1 cursor-col-resize",
                "hover:bg-[#C8A882]/40 active:bg-[#C8A882]/60 transition-colors",
              )}
            />
          </motion.aside>
        )}
      </AnimatePresence>

      {!open && (
        <>
          <MinimizedPill
            onOpen={openPanel}
            active={streaming}
            statusLabel={agent.statusLabel}
            hue={hue}
          />
          {hint.visible && <FirstRunHint onDismiss={hint.dismiss} />}
        </>
      )}
    </>
  );
}
