"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, Sprout, Crown } from "lucide-react";
import { useMemo } from "react";
import type { TrajectoryNode } from "../lib/types";
import { formatMsg, msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";
import { HelpTip } from "@/shared/ui/help-tip";

export interface TrajectoryDetailProps {
  node: TrajectoryNode | null;
  isOpen: boolean;
  onToggle: () => void;
}

export function TrajectoryDetail({ node, isOpen, onToggle }: TrajectoryDetailProps) {
  const promptEntries = useMemo(() => {
    if (node === null) return [] as Array<[string, string]>;
    return Object.entries(node.prompt);
  }, [node]);

  if (node === null) return null;

  const headerLabel = node.isSeed
    ? msg("trajectory.node.seed_label")
    : node.isWinner
      ? msg("trajectory.node.winning_label")
      : formatMsg("trajectory.node.generation_label", { gen: node.generation });

  return (
    <div className="rounded-lg border border-border/40 bg-[#fbf8f3]/60">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-right"
        aria-expanded={isOpen}
      >
        <div className="flex items-center gap-2 text-sm">
          {node.isSeed ? (
            <Sprout className="size-4 text-[#7C6350]" aria-hidden="true" />
          ) : node.isWinner ? (
            <Crown className="size-4 text-[#8a6a3a]" aria-hidden="true" />
          ) : null}
          <span className="font-semibold">
            {TERMS.candidate}{" "}
            <span dir="ltr" className="font-mono">
              {node.candidate_id}
            </span>
          </span>
          <span className="text-muted-foreground">·</span>
          <HelpTip text={msg("trajectory.explainer.generation")}>
            <span className="text-muted-foreground">{headerLabel}</span>
          </HelpTip>
          <span className="text-muted-foreground">·</span>
          <HelpTip text={msg("trajectory.explainer.score")}>
            <span className="font-mono tabular-nums">{(node.score * 100).toFixed(1)}%</span>
          </HelpTip>
        </div>
        <ChevronDown
          className={`size-4 text-muted-foreground transition-transform ${isOpen ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>

      <AnimatePresence initial={false}>
        {isOpen ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.2, 0.8, 0.2, 1] }}
            style={{ overflow: "hidden" }}
          >
            <div className="px-4 pb-4 space-y-4 border-t border-border/30 pt-3">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                {node.parent_id === null ? (
                  <span>{msg("trajectory.detail.no_parent")}</span>
                ) : (
                  <HelpTip text={msg("trajectory.explainer.parent")}>
                    <span>
                      {formatMsg("trajectory.detail.parent_link", {
                        parent: node.parent_id,
                      })}
                    </span>
                  </HelpTip>
                )}
                {node.parents_extra.length > 0 ? (
                  <span>
                    {formatMsg("trajectory.detail.parents_extra_link", {
                      parents: node.parents_extra.join(", "),
                    })}
                  </span>
                ) : null}
                <span>
                  {formatMsg("trajectory.detail.discovered_at", {
                    evals: node.discovered_at_evals,
                  })}
                </span>
              </div>

              {promptEntries.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-xs font-medium text-muted-foreground">
                    <HelpTip text={msg("trajectory.explainer.candidate")}>
                      <span>{msg("trajectory.detail.prompt_title")}</span>
                    </HelpTip>
                  </div>
                  <div className="space-y-2">
                    {promptEntries.map(([predictor, prompt]) => (
                      <div
                        key={predictor}
                        className="rounded-md border border-border/40 bg-background/60 p-3"
                      >
                        <div
                          className="text-[10px] font-mono text-muted-foreground mb-1.5"
                          dir="ltr"
                        >
                          {predictor}
                        </div>
                        <pre
                          className="text-xs whitespace-pre-wrap leading-relaxed font-mono text-foreground/90"
                          dir="auto"
                          style={{ wordBreak: "break-word" }}
                        >
                          {prompt}
                        </pre>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {node.per_example.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-xs font-medium text-muted-foreground">
                    {msg("trajectory.detail.per_example_title")}
                  </div>
                  <div
                    className="grid gap-1.5"
                    style={{
                      gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))",
                    }}
                  >
                    {node.per_example.map((ex) => (
                      <div
                        key={ex.id}
                        className="flex items-center justify-between gap-2 rounded border border-border/30 bg-background/40 px-2 py-1 text-xs"
                      >
                        <span className="font-mono text-muted-foreground truncate" dir="ltr">
                          {ex.id}
                        </span>
                        <span className="font-mono tabular-nums">
                          {(ex.score * 100).toFixed(0)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
