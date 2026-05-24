"use client";

import { motion } from "framer-motion";
import { GitBranch, Radio } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { OptimizationStatusResponse } from "@/shared/types/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/primitives/card";
import { FadeIn } from "@/shared/ui/motion";
import { HelpTip } from "@/shared/ui/help-tip";
import { msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";
import { extractCandidates } from "../lib/extract-events";
import { layoutTrajectory } from "../lib/layout";
import { TrajectoryTree } from "./TrajectoryTree";
import { TrajectoryDetail } from "./TrajectoryDetail";

const GEPA_OPTIMIZER = "gepa";
const NEWEST_HIGHLIGHT_MS = 2200;

function isGepa(job: OptimizationStatusResponse): boolean {
  const name = job.optimizer_name;
  if (typeof name !== "string") return false;
  return name.toLowerCase() === GEPA_OPTIMIZER;
}

function isLive(job: OptimizationStatusResponse): boolean {
  return job.status === "running" || job.status === "validating" || job.status === "pending";
}

export function TrajectoryPanel({ job }: { job: OptimizationStatusResponse }) {
  const isGepaJob = isGepa(job);
  const candidates = useMemo(
    () => (isGepaJob ? extractCandidates(job.progress_events ?? []) : []),
    [isGepaJob, job.progress_events],
  );
  const layout = useMemo(() => layoutTrajectory(candidates), [candidates]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [newestId, setNewestId] = useState<string | null>(null);
  const newestTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevCountRef = useRef(0);
  const liveRegionRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (candidates.length === 0) {
      setSelectedId(null);
      return;
    }
    if (selectedId !== null && candidates.some((c) => c.candidate_id === selectedId)) {
      return;
    }
    if (layout.winnerId !== null) {
      setSelectedId(layout.winnerId);
      return;
    }
    const first = candidates[0];
    if (first !== undefined) setSelectedId(first.candidate_id);
  }, [candidates, layout.winnerId, selectedId]);

  useEffect(() => {
    if (candidates.length <= prevCountRef.current) {
      prevCountRef.current = candidates.length;
      return;
    }
    const newest = candidates[candidates.length - 1];
    prevCountRef.current = candidates.length;
    if (newest === undefined) return;
    setNewestId(newest.candidate_id);
    if (liveRegionRef.current !== null) {
      liveRegionRef.current.textContent = msg("trajectory.live.new_candidate");
    }
    if (newestTimerRef.current !== null) clearTimeout(newestTimerRef.current);
    newestTimerRef.current = setTimeout(() => setNewestId(null), NEWEST_HIGHLIGHT_MS);
    return () => {
      if (newestTimerRef.current !== null) clearTimeout(newestTimerRef.current);
    };
  }, [candidates]);

  if (!isGepaJob) return null;

  const selectedNode =
    selectedId === null ? null : (layout.nodes.find((n) => n.candidate_id === selectedId) ?? null);

  const live = isLive(job);
  const showEmpty = candidates.length === 0;

  return (
    <FadeIn delay={0.12}>
      <Card
        className="relative overflow-hidden shadow-[0_1px_3px_rgba(28,22,18,0.04),inset_0_1px_0_rgba(255,255,255,0.5)]"
        data-tutorial="trajectory-panel"
      >
        <div
          className="absolute inset-x-0 top-0 h-px bg-gradient-to-l from-transparent via-[#C8A882]/40 to-transparent"
          aria-hidden="true"
        />
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle className="text-base flex items-center gap-2">
              <GitBranch className="size-4 text-[#7C6350]" aria-hidden="true" />
              <HelpTip text={msg("trajectory.explainer.trajectory")}>
                <span className="font-bold tracking-tight">{msg("trajectory.panel.title")}</span>
              </HelpTip>
            </CardTitle>
            <p className="text-xs text-muted-foreground">{msg("trajectory.panel.subtitle")}</p>
          </div>
          {live && !showEmpty ? (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-1.5 rounded-full border border-border/40 bg-background/80 px-2.5 py-1 text-[11px] text-muted-foreground"
            >
              <motion.span
                className="block h-1.5 w-1.5 rounded-full bg-[#a85a3b]"
                animate={{ opacity: [0.4, 1, 0.4] }}
                transition={{ duration: 1.4, repeat: Infinity }}
                aria-hidden="true"
              />
              <Radio className="size-3" aria-hidden="true" />
              <span>{msg("trajectory.live.indicator")}</span>
              <span className="font-mono tabular-nums text-foreground/80">
                {candidates.length}
              </span>
              <span>{TERMS.candidatePlural}</span>
            </motion.div>
          ) : !showEmpty ? (
            <span className="text-[11px] text-muted-foreground tabular-nums">
              {candidates.length} {TERMS.candidatePlural}
            </span>
          ) : null}
        </CardHeader>
        <CardContent className="space-y-3">
          {showEmpty ? (
            <div className="rounded-lg border border-dashed border-border/40 bg-background/30 px-6 py-10 text-center text-sm text-muted-foreground">
              {live
                ? msg("trajectory.empty.pre_first_iteration")
                : msg("trajectory.empty.no_candidates")}
            </div>
          ) : (
            <>
              <TrajectoryTree
                layout={layout}
                selectedId={selectedId}
                newestId={newestId}
                onSelect={(id) => {
                  setSelectedId(id);
                  setDetailOpen(true);
                }}
                onHover={setHoveredId}
                hoveredId={hoveredId}
              />
              <TrajectoryDetail
                node={selectedNode}
                isOpen={detailOpen}
                onToggle={() => setDetailOpen((v) => !v)}
              />
            </>
          )}
          <div
            ref={liveRegionRef}
            role="status"
            aria-live="polite"
            className="sr-only"
          />
        </CardContent>
      </Card>
    </FadeIn>
  );
}
