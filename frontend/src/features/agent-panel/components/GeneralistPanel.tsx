"use client";

import * as React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { PanelLeftClose, RotateCcw, Sparkles, Wand2 } from "lucide-react";

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import { AgentThread } from "@/shared/ui/agent/agent-thread";
import { AssistantBubble } from "@/shared/ui/agent/assistant-bubble";
import { Composer } from "@/shared/ui/agent/composer";
import { UserBubble } from "@/shared/ui/agent/user-bubble";
import type { AgentThinking, AgentToolCall } from "@/shared/ui/agent/types";
import { cn } from "@/shared/lib/utils";

import { useFirstRunHint } from "../hooks/use-first-run-hint";
import { useGeneralistAgent } from "../hooks/use-generalist-agent";
import { useGeneralistPanelState } from "../hooks/use-panel-state";
import { TRUST_MODE_HUE, useTrustMode } from "../hooks/use-trust-mode";
import {
  extractWizardPatch,
  useWizardStateOptional,
} from "../hooks/use-wizard-state";
import { getToolRenderer } from "../lib/tool-renderers";
import type { WizardState } from "../lib/types";

import { ApprovalCard } from "./ApprovalCard";
import { FirstRunHint } from "./FirstRunHint";
import { MinimizedPill } from "./MinimizedPill";
import { PresenceStrip } from "./PresenceStrip";
import { ToolCallRow } from "./ToolCallRow";
import { ToolsCarousel } from "./ToolsCarousel";
import { TrustToggle } from "./TrustToggle";

const MIN_WIDTH = 360;
const MAX_WIDTH = 720;

function clampWidth(n: number): number {
  return Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, Math.round(n)));
}

interface GeneralistPanelProps {
  /** Optional wizard-state override. Defaults to the shared context. */
  wizardState?: WizardState;
}

/**
 * Docked generalist agent panel. Renders as a left-anchored aside that
 * the user can resize, minimize to a pill, and toggle with Ctrl+J.
 * Mounted once in the app shell so the thread survives route changes.
 */
export function GeneralistPanel({ wizardState }: GeneralistPanelProps = {}) {
  const { open, setOpen, width, setWidth } = useGeneralistPanelState();
  const { mode: trustMode, next: cycleTrust } = useTrustMode();
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

  const wizardCtx = useWizardStateOptional();
  const effectiveWizard = React.useMemo<WizardState>(() => {
    const base = wizardCtx?.state ?? {};
    const merged = wizardState ? { ...base, ...wizardState } : base;
    return wizardCtx?.overriddenFields?.length
      ? { ...merged, overridden_fields: wizardCtx.overriddenFields }
      : merged;
  }, [wizardCtx?.state, wizardCtx?.overriddenFields, wizardState]);

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
  const lastAssistantIdx = React.useMemo(() => {
    for (let i = agent.messages.length - 1; i >= 0; i--) {
      if (agent.messages[i]?.role === "assistant") return i;
    }
    return -1;
  }, [agent.messages]);

  const thinking: AgentThinking = {
    reasoning: agent.reasoning,
    startedAt: agent.reasoningStartedAt,
    endedAt: agent.reasoningEndedAt,
    streaming,
  };

  const [draft, setDraft] = React.useState("");
  const handleSubmit = () => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    agent.send(trimmed);
    setDraft("");
  };

  const resizingRef = React.useRef(false);
  const startResize = (e: React.MouseEvent) => {
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
  };

  const renderToolCall = React.useCallback(
    (call: AgentToolCall, ctx: { isRetry: boolean }) => {
      const renderer = getToolRenderer(call.tool);
      if (renderer?.card && call.status !== "running") {
        return renderer.card(call);
      }
      const summary = renderer?.summary?.(call) ?? null;
      return <ToolCallRow call={call} isRetry={ctx.isRetry} summary={summary} />;
    },
    [],
  );

  const emptyState = (
    <div className="flex flex-col items-center justify-center py-12 px-6 text-center">
      <span className="inline-flex size-10 items-center justify-center rounded-full bg-[#3D2E22]/10 text-[#3D2E22]">
        <Sparkles className="size-5" />
      </span>
      <p className="mt-3 text-sm text-foreground">שלום, איך אפשר לעזור?</p>
      <p className="mt-1 text-[0.75rem] text-muted-foreground leading-relaxed max-w-[28ch]">
        עוזר שיודע לקרוא את המערכת ולפעול בשמך. כתוב מה אתה מחפש.
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
            aria-label="סוכן גנרליסט"
          >
            <div
              dir="rtl"
              className="relative flex min-w-0 flex-1 flex-col"
            >
              {/* Header */}
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
                      עוזר
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
                            aria-label="מה אני יודע לעשות"
                          >
                            <Wand2 className="size-3.5" />
                          </button>
                        </PopoverTrigger>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" dir="rtl">
                        מה אני יודע לעשות
                      </TooltipContent>
                    </Tooltip>
                    <PopoverContent
                      side="bottom"
                      align="center"
                      sideOffset={8}
                      className="p-0"
                    >
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
                          aria-label="איפוס שיחה"
                        >
                          <RotateCcw className="size-3.5" />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" dir="rtl">
                        איפוס שיחה
                      </TooltipContent>
                    </Tooltip>
                  )}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={closePanel}
                        className="rounded-md p-1.5 text-muted-foreground hover:bg-accent/70 hover:text-foreground transition-colors cursor-pointer"
                        aria-label="כווץ את הפאנל"
                      >
                        <PanelLeftClose className="size-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" dir="rtl">
                      כווץ את הפאנל{" "}
                      <span className="opacity-70 font-mono">
                        (Ctrl+J)
                      </span>
                    </TooltipContent>
                  </Tooltip>
                </div>
              </div>

              {/* Messages */}
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
                {agent.messages.map((m, i) => {
                  if (m.role === "user") {
                    return <UserBubble key={i} content={m.content} editable={false} />;
                  }
                  return (
                    <div key={i} className="flex justify-end">
                      <AssistantBubble
                        msg={m}
                        thinking={i === lastAssistantIdx ? thinking : undefined}
                        renderToolCall={renderToolCall}
                      />
                    </div>
                  );
                })}

                {agent.pendingApproval && (
                  <ApprovalCard
                    payload={agent.pendingApproval}
                    onResolve={agent.confirmApproval}
                  />
                )}

                {agent.error && (
                  <div className="text-[0.75rem] text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                    {agent.error}
                  </div>
                )}
              </AgentThread>

              {/* Composer */}
              <Composer
                value={draft}
                onChange={setDraft}
                onSubmit={handleSubmit}
                onStop={agent.stop}
                placeholder="כתוב הודעה…"
                streaming={streaming}
                sendAriaLabel="שלח הודעה"
                stopAriaLabel="עצור"
              />

              <PresenceStrip active={streaming} hue={hue} />
            </div>

            {/* Resize handle — physical right edge (inline-end in LTR outer) */}
            <button
              type="button"
              onMouseDown={startResize}
              aria-label="שנה רוחב"
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
