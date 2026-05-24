"use client";

import { motion, useReducedMotion } from "framer-motion";
import { Crown, Sprout } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import { TRAJECTORY_LAYOUT, type LayoutResult } from "../lib/layout";
import type { TrajectoryNode } from "../lib/types";
import { formatMsg, msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";

const STROKE_DEFAULT = "rgba(124, 99, 80, 0.32)";
const STROKE_SPINE = "rgba(124, 99, 80, 0.95)";
const STROKE_MERGE = "rgba(124, 99, 80, 0.55)";
const NODE_FILL_DEFAULT = "#fbf6ee";
const NODE_FILL_SPINE = "#f0e3cf";
const NODE_FILL_WINNER = "#1c1612";
const NODE_FILL_SEED = "#e9dec8";
const NODE_STROKE_DEFAULT = "rgba(28, 22, 18, 0.18)";
const NODE_STROKE_HOVER = "rgba(28, 22, 18, 0.55)";
const NODE_STROKE_SELECTED = "#1c1612";

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2.5;

export interface TrajectoryTreeProps {
  layout: LayoutResult;
  selectedId: string | null;
  newestId: string | null;
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
  hoveredId: string | null;
}

export function TrajectoryTree({
  layout,
  selectedId,
  newestId,
  onSelect,
  onHover,
  hoveredId,
}: TrajectoryTreeProps) {
  const reduceMotion = useReducedMotion();
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const { nodes, edges, width, height } = layout;
  const idIndex = useMemo(() => {
    const m = new Map<string, TrajectoryNode>();
    for (const n of nodes) m.set(n.candidate_id, n);
    return m;
  }, [nodes]);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      dragRef.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
    },
    [pan.x, pan.y],
  );
  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (dragRef.current === null) return;
    const dx = e.clientX - dragRef.current.x;
    const dy = e.clientY - dragRef.current.y;
    setPan({ x: dragRef.current.panX + dx, y: dragRef.current.panY + dy });
  }, []);
  const handleMouseUp = useCallback(() => {
    dragRef.current = null;
  }, []);
  const handleWheel = useCallback((e: React.WheelEvent) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    setZoom((z) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z - e.deltaY * 0.002)));
  }, []);
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (selectedId === null) return;
      const current = idIndex.get(selectedId);
      if (current === undefined) return;
      if (e.key === "ArrowUp" && current.parent_id !== null && idIndex.has(current.parent_id)) {
        e.preventDefault();
        onSelect(current.parent_id);
      } else if (e.key === "ArrowDown" && current.children.length > 0) {
        const child = current.children[0];
        if (child !== undefined) {
          e.preventDefault();
          onSelect(child.candidate_id);
        }
      } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        if (current.parent_id === null) return;
        const parent = idIndex.get(current.parent_id);
        if (parent === undefined) return;
        const idx = parent.children.findIndex((c) => c.candidate_id === selectedId);
        if (idx === -1) return;
        const dir = e.key === "ArrowLeft" ? -1 : 1;
        const next = parent.children[idx + dir];
        if (next !== undefined) {
          e.preventDefault();
          onSelect(next.candidate_id);
        }
      }
    },
    [idIndex, onSelect, selectedId],
  );

  if (nodes.length === 0) return null;

  const viewWidth = Math.max(width + 64, 320);
  const viewHeight = Math.max(height + 32, 200);

  return (
    <div
      className="relative overflow-hidden rounded-lg border border-border/40 bg-[#fbf8f3]/40"
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
      onKeyDown={handleKeyDown}
      role="tree"
      tabIndex={0}
      aria-label={msg("trajectory.a11y.tree_label")}
      style={{ cursor: dragRef.current !== null ? "grabbing" : "grab", minHeight: 280 }}
    >
      <div
        className="absolute top-2 right-2 z-10 flex items-center gap-1 rounded-md border border-border/40 bg-background/85 px-1 py-1 text-xs backdrop-blur"
        dir="rtl"
      >
        <button
          type="button"
          className="px-2 py-0.5 hover:bg-muted/60 rounded"
          aria-label={msg("trajectory.controls.zoom_out")}
          onClick={() => setZoom((z) => Math.max(ZOOM_MIN, z - 0.2))}
        >
          −
        </button>
        <button
          type="button"
          className="px-2 py-0.5 hover:bg-muted/60 rounded font-mono tabular-nums"
          aria-label={msg("trajectory.controls.zoom_reset")}
          onClick={() => {
            setZoom(1);
            setPan({ x: 0, y: 0 });
          }}
        >
          {Math.round(zoom * 100)}%
        </button>
        <button
          type="button"
          className="px-2 py-0.5 hover:bg-muted/60 rounded"
          aria-label={msg("trajectory.controls.zoom_in")}
          onClick={() => setZoom((z) => Math.min(ZOOM_MAX, z + 0.2))}
        >
          +
        </button>
      </div>

      <svg
        width="100%"
        height={Math.min(viewHeight * zoom + 40, 520)}
        viewBox={`${-pan.x / zoom} ${-pan.y / zoom} ${viewWidth / zoom} ${viewHeight / zoom}`}
        style={{ display: "block", direction: "ltr" }}
      >
        <defs>
          <pattern id="trajectory-grid" width="32" height="32" patternUnits="userSpaceOnUse">
            <path
              d="M 32 0 L 0 0 0 32"
              fill="none"
              stroke="rgba(124, 99, 80, 0.07)"
              strokeWidth="1"
            />
          </pattern>
        </defs>
        <rect
          x={-pan.x / zoom}
          y={-pan.y / zoom}
          width={viewWidth / zoom}
          height={viewHeight / zoom}
          fill="url(#trajectory-grid)"
        />

        <g>
          {edges.map((edge, i) => {
            const from = idIndex.get(edge.from);
            const to = idIndex.get(edge.to);
            if (from === undefined || to === undefined) return null;
            const isSpineEdge = from.isOnSpine && to.isOnSpine && !edge.isMerge;
            const stroke = edge.isMerge
              ? STROKE_MERGE
              : isSpineEdge
                ? STROKE_SPINE
                : STROKE_DEFAULT;
            const midY = (from.y + to.y) / 2;
            const d = `M ${from.x} ${from.y} C ${from.x} ${midY} ${to.x} ${midY} ${to.x} ${to.y}`;
            return (
              <motion.path
                key={`${edge.from}-${edge.to}-${i}`}
                d={d}
                fill="none"
                stroke={stroke}
                strokeWidth={isSpineEdge ? 2 : 1}
                strokeDasharray={edge.isMerge ? "3 3" : undefined}
                initial={reduceMotion ? false : { pathLength: 0, opacity: 0 }}
                animate={reduceMotion ? undefined : { pathLength: 1, opacity: 1 }}
                transition={
                  reduceMotion ? undefined : { duration: 0.5, ease: [0.2, 0.8, 0.2, 1] }
                }
              />
            );
          })}
        </g>

        <g>
          {nodes.map((node) => {
            const isSelected = node.candidate_id === selectedId;
            const isHovered = node.candidate_id === hoveredId;
            const isNewest = node.candidate_id === newestId;
            const fill = node.isWinner
              ? NODE_FILL_WINNER
              : node.isSeed
                ? NODE_FILL_SEED
                : node.isOnSpine
                  ? NODE_FILL_SPINE
                  : NODE_FILL_DEFAULT;
            const stroke = isSelected
              ? NODE_STROKE_SELECTED
              : isHovered
                ? NODE_STROKE_HOVER
                : NODE_STROKE_DEFAULT;
            const textFill = node.isWinner ? "#faf8f5" : "#1c1612";
            return (
              <motion.g
                key={node.candidate_id}
                role="treeitem"
                aria-label={formatMsg("trajectory.a11y.node_label", {
                  id: node.candidate_id,
                  gen: node.generation,
                  score: node.score.toFixed(2),
                })}
                aria-selected={isSelected}
                tabIndex={isSelected ? 0 : -1}
                onMouseEnter={() => onHover(node.candidate_id)}
                onMouseLeave={() => onHover(null)}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect(node.candidate_id);
                }}
                initial={
                  reduceMotion
                    ? false
                    : isNewest
                      ? { scale: 0, opacity: 0 }
                      : { scale: 0.7, opacity: 0 }
                }
                animate={reduceMotion ? undefined : { scale: 1, opacity: 1 }}
                transition={
                  reduceMotion ? undefined : { duration: 0.45, ease: [0.2, 0.8, 0.2, 1] }
                }
                style={{ cursor: "pointer" }}
              >
                {isNewest && !reduceMotion ? (
                  <motion.circle
                    cx={node.x}
                    cy={node.y}
                    r={TRAJECTORY_LAYOUT.nodeRadius}
                    fill="none"
                    stroke={STROKE_SPINE}
                    strokeWidth="2"
                    initial={{ r: TRAJECTORY_LAYOUT.nodeRadius, opacity: 0.7 }}
                    animate={{ r: TRAJECTORY_LAYOUT.nodeRadius * 2.2, opacity: 0 }}
                    transition={{ duration: 1.2, ease: "easeOut", repeat: 2 }}
                  />
                ) : null}
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={TRAJECTORY_LAYOUT.nodeRadius}
                  fill={fill}
                  stroke={stroke}
                  strokeWidth={isSelected ? 2 : 1}
                />
                {node.isSeed ? (
                  <g transform={`translate(${node.x - 7}, ${node.y - 14}) scale(0.6)`}>
                    <Sprout color="#7C6350" size={20} aria-hidden="true" />
                  </g>
                ) : null}
                {node.isWinner ? (
                  <g
                    transform={`translate(${node.x - 8}, ${node.y - TRAJECTORY_LAYOUT.nodeRadius - 18}) scale(0.7)`}
                  >
                    <Crown color="#1c1612" fill="#f4d68b" size={22} aria-hidden="true" />
                  </g>
                ) : null}
                <text
                  x={node.x}
                  y={node.y + 4}
                  textAnchor="middle"
                  fontFamily="var(--font-mono, monospace)"
                  fontSize="12"
                  fontWeight={node.isWinner || node.isSeed ? 700 : 500}
                  fill={textFill}
                  pointerEvents="none"
                >
                  {node.candidate_id}
                </text>
                <text
                  x={node.x}
                  y={node.y + TRAJECTORY_LAYOUT.nodeRadius + 14}
                  textAnchor="middle"
                  fontFamily="var(--font-mono, monospace)"
                  fontSize="10"
                  fill="rgba(28, 22, 18, 0.55)"
                  pointerEvents="none"
                >
                  {(node.score * 100).toFixed(0)}
                </text>
              </motion.g>
            );
          })}
        </g>
      </svg>

      <div
        className="absolute bottom-2 right-3 z-10 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground/80"
        dir="rtl"
      >
        <span className="flex items-center gap-1">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: NODE_FILL_SEED, border: "1px solid rgba(28,22,18,0.2)" }}
          />
          {TERMS.seedCandidate}
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: NODE_FILL_WINNER }}
          />
          {TERMS.winningCandidate}
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-px w-4" style={{ background: STROKE_SPINE }} />
          {TERMS.trajectory}
        </span>
      </div>
    </div>
  );
}
