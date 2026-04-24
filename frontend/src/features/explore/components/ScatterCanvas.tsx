"use client";

import * as React from "react";
import { RotateCcw } from "lucide-react";
import type { PublicDashboardPoint } from "@/shared/lib/api";
import { getJobTypeLabel } from "@/shared/constants/job-status";
import { msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";

export type ExploreFilter = "all" | "run" | "grid_search";

interface ScatterCanvasProps {
  points: PublicDashboardPoint[];
  filter: ExploreFilter;
  selectedId: string | null;
  focusId?: string | null;
  onSelect: (id: string | null) => void;
  dimmed?: boolean;
  heightClass?: string;
  children?: React.ReactNode;
}

interface ProjectedPoint {
  point: PublicDashboardPoint;
  basePx: number;
  basePy: number;
  radius: number;
  match: boolean;
  color: string;
}

interface View {
  k: number;
  tx: number;
  ty: number;
}

const PADDING = 48;
const BASE_RADIUS = 4;
const HOVER_RADIUS = 7;
const FOCUS_RING_COLOR = "#C8A882";
const MIN_SCALE = 1;
const MAX_SCALE = 24;
const DRAG_THRESHOLD = 4;

function colorForPoint(match: boolean): string {
  const chroma = match ? 0.05 : 0.01;
  return `oklch(0.3 ${chroma} 40)`;
}

function formatScore(value: number | null): string | null {
  if (value === null || !Number.isFinite(value)) return null;
  const v = value > 1.5 ? value : value * 100;
  return v.toFixed(1);
}

function clampView(v: View, size: { w: number; h: number }): View {
  const maxPan = Math.max(size.w, size.h) * Math.max(0, v.k - 1);
  return {
    k: v.k,
    tx: Math.max(-maxPan, Math.min(maxPan, v.tx)),
    ty: Math.max(-maxPan, Math.min(maxPan, v.ty)),
  };
}

export function ScatterCanvas({
  points,
  filter,
  selectedId,
  focusId = null,
  onSelect,
  dimmed = false,
  heightClass = "h-[64vh] min-h-[420px]",
  children,
}: ScatterCanvasProps) {
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const [size, setSize] = React.useState({ w: 0, h: 0 });
  const [hoveredId, setHoveredId] = React.useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = React.useState<{ x: number; y: number } | null>(null);
  const [view, setView] = React.useState<View>({ k: 1, tx: 0, ty: 0 });
  const [isDragging, setIsDragging] = React.useState(false);
  const panStateRef = React.useRef<null | {
    startClientX: number;
    startClientY: number;
    startTx: number;
    startTy: number;
    moved: boolean;
  }>(null);

  React.useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        const { width, height } = e.contentRect;
        setSize({ w: width, h: height });
      }
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const projected = React.useMemo<ProjectedPoint[]>(() => {
    if (size.w < 2 || size.h < 2 || points.length === 0) return [];
    const plotW = Math.max(1, size.w - PADDING * 2);
    const plotH = Math.max(1, size.h - PADDING * 2);
    return points.map((point) => {
      const match = filter === "all" || point.optimization_type === filter;
      const normX = (point.x + 1) / 2;
      const normY = 1 - (point.y + 1) / 2;
      return {
        point,
        basePx: PADDING + normX * plotW,
        basePy: PADDING + normY * plotH,
        radius: match ? BASE_RADIUS : BASE_RADIUS - 1,
        match,
        color: colorForPoint(match),
      };
    });
  }, [points, filter, size]);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size.w * dpr;
    canvas.height = size.h * dpr;
    canvas.style.width = `${size.w}px`;
    canvas.style.height = `${size.h}px`;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.w, size.h);

    const cx = (size.w / 2) * view.k + view.tx;
    const cy = (size.h / 2) * view.k + view.ty;
    ctx.strokeStyle = "oklch(0.94 0.005 50)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx, PADDING);
    ctx.lineTo(cx, size.h - PADDING);
    ctx.moveTo(PADDING, cy);
    ctx.lineTo(size.w - PADDING, cy);
    ctx.stroke();

    const rank = (p: ProjectedPoint) => {
      if (
        focusId === p.point.optimization_id ||
        selectedId === p.point.optimization_id ||
        hoveredId === p.point.optimization_id
      )
        return 2;
      return p.match ? 1 : 0;
    };
    const sorted = [...projected].sort((a, b) => rank(a) - rank(b));

    for (const p of sorted) {
      const isHovered = hoveredId === p.point.optimization_id;
      const isSelected = selectedId === p.point.optimization_id;
      const isFocused = focusId === p.point.optimization_id;
      const isActive = isHovered || isSelected || isFocused;

      let alpha = p.match ? 1 : 0.35;
      if (dimmed && !isActive) alpha *= 0.35;

      const sx = p.basePx * view.k + view.tx;
      const sy = p.basePy * view.k + view.ty;

      ctx.beginPath();
      ctx.fillStyle = p.color;
      ctx.globalAlpha = alpha;
      ctx.arc(sx, sy, isActive ? HOVER_RADIUS : p.radius, 0, Math.PI * 2);
      ctx.fill();

      if (isFocused) {
        ctx.globalAlpha = 1;
        ctx.strokeStyle = FOCUS_RING_COLOR;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(sx, sy, HOVER_RADIUS + 3, 0, Math.PI * 2);
        ctx.stroke();
      } else if (isSelected || isHovered) {
        ctx.globalAlpha = 1;
        ctx.strokeStyle = "oklch(0.2 0.02 40)";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
  }, [projected, size, hoveredId, selectedId, focusId, dimmed, view]);

  const pickNearest = React.useCallback(
    (clientX: number, clientY: number): ProjectedPoint | null => {
      const canvas = canvasRef.current;
      if (!canvas) return null;
      const rect = canvas.getBoundingClientRect();
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      let best: { p: ProjectedPoint; d: number } | null = null;
      for (const p of projected) {
        const sx = p.basePx * view.k + view.tx;
        const sy = p.basePy * view.k + view.ty;
        const d = Math.hypot(sx - x, sy - y);
        if (d < HOVER_RADIUS + 4 && (best === null || d < best.d)) {
          best = { p, d };
        }
      }
      return best ? best.p : null;
    },
    [projected, view],
  );

  const zoomAt = React.useCallback(
    (cx: number, cy: number, factor: number) => {
      setView((v) => {
        const nextK = Math.max(MIN_SCALE, Math.min(MAX_SCALE, v.k * factor));
        if (nextK === v.k) return v;
        const mapX = (cx - v.tx) / v.k;
        const mapY = (cy - v.ty) / v.k;
        return clampView({ k: nextK, tx: cx - mapX * nextK, ty: cy - mapY * nextK }, size);
      });
    },
    [size],
  );

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const factor = Math.exp(-e.deltaY * 0.0015);
      zoomAt(e.clientX - rect.left, e.clientY - rect.top, factor);
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    panStateRef.current = {
      startClientX: e.clientX,
      startClientY: e.clientY,
      startTx: view.tx,
      startTy: view.ty,
      moved: false,
    };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const ps = panStateRef.current;
    if (ps) {
      const dx = e.clientX - ps.startClientX;
      const dy = e.clientY - ps.startClientY;
      if (!ps.moved && Math.hypot(dx, dy) > DRAG_THRESHOLD) {
        ps.moved = true;
        setIsDragging(true);
        setHoveredId(null);
        setTooltipPos(null);
      }
      if (ps.moved) {
        setView((v) => clampView({ k: v.k, tx: ps.startTx + dx, ty: ps.startTy + dy }, size));
      }
      return;
    }
    const hit = pickNearest(e.clientX, e.clientY);
    if (hit) {
      const sx = hit.basePx * view.k + view.tx;
      const sy = hit.basePy * view.k + view.ty;
      setHoveredId(hit.point.optimization_id);
      setTooltipPos({ x: sx, y: sy });
    } else {
      setHoveredId(null);
      setTooltipPos(null);
    }
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const ps = panStateRef.current;
    panStateRef.current = null;
    if (ps?.moved) {
      setIsDragging(false);
      return;
    }
    const hit = pickNearest(e.clientX, e.clientY);
    if (!hit) {
      onSelect(null);
      return;
    }
    if (selectedId === hit.point.optimization_id) {
      onSelect(null);
    } else {
      onSelect(hit.point.optimization_id);
    }
  };

  const handleMouseLeave = () => {
    panStateRef.current = null;
    setIsDragging(false);
    setHoveredId(null);
    setTooltipPos(null);
  };

  const handleDoubleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const factor = e.shiftKey ? 1 / 1.8 : 1.8;
    zoomAt(e.clientX - rect.left, e.clientY - rect.top, factor);
  };

  const resetView = () => setView({ k: 1, tx: 0, ty: 0 });
  const isTransformed = view.k !== 1 || view.tx !== 0 || view.ty !== 0;

  const hovered = projected.find((p) => p.point.optimization_id === hoveredId)?.point ?? null;
  const cursor = isDragging ? "cursor-grabbing" : hoveredId ? "cursor-pointer" : "cursor-grab";

  return (
    <div
      ref={containerRef}
      className={`relative ${heightClass} w-full overflow-hidden rounded-lg border border-[#DDD6CC]/50 bg-[#FAF8F5]`}
    >
      <canvas
        ref={canvasRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onDoubleClick={handleDoubleClick}
        className={`absolute inset-0 select-none ${cursor}`}
      />
      {children}
      {isTransformed && (
        <button
          type="button"
          onClick={resetView}
          aria-label={msg("explore.map.reset")}
          className="absolute top-3 start-3 z-10 inline-flex items-center gap-1.5 rounded-md border border-[#DDD6CC]/70 bg-[#FAF8F5]/90 px-2.5 py-1.5 text-[0.75rem] font-medium text-[#3D2E22] backdrop-blur-sm transition-colors cursor-pointer hover:bg-[#EDE7DD] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3D2E22]/25"
        >
          <RotateCcw className="size-3.5" aria-hidden="true" />
          <span>{msg("explore.map.reset")}</span>
        </button>
      )}
      {hovered && tooltipPos && !isDragging && (
        <Tooltip point={hovered} x={tooltipPos.x} y={tooltipPos.y} containerWidth={size.w} />
      )}
    </div>
  );
}

function Tooltip({
  point,
  x,
  y,
  containerWidth,
}: {
  point: PublicDashboardPoint;
  x: number;
  y: number;
  containerWidth: number;
}) {
  const primary = point.summary_text ?? point.task_name ?? "—";
  const typeLabel = point.optimization_type ? getJobTypeLabel(point.optimization_type) : null;
  const score = formatScore(point.optimized_metric);
  const above = y > 120;

  const MAX_WIDTH = 260;
  const HALF = MAX_WIDTH / 2;
  const EDGE = 12;

  let shiftX = 0;
  const leftEdge = x - HALF;
  const rightEdge = x + HALF;
  if (leftEdge < EDGE) shiftX = EDGE - leftEdge;
  else if (rightEdge > containerWidth - EDGE) shiftX = containerWidth - EDGE - rightEdge;

  const style: React.CSSProperties = {
    left: x,
    top: y,
    transform: above
      ? `translate(calc(-50% + ${shiftX}px), calc(-100% - 12px))`
      : `translate(calc(-50% + ${shiftX}px), 12px)`,
    maxWidth: MAX_WIDTH,
  };

  return (
    <div
      dir="rtl"
      role="tooltip"
      className="pointer-events-none absolute z-10 rounded-xl border border-[#DDD6CC]/70 bg-[#FAF8F5]/95 p-3 shadow-lg backdrop-blur-sm"
      style={style}
    >
      <p
        dir="auto"
        className="mb-2 text-[0.8125rem] font-semibold leading-snug tracking-tight text-[#3D2E22] line-clamp-2"
      >
        {primary}
      </p>
      <div className="space-y-1 text-[0.6875rem] text-[#8C7A6B]">
        {typeLabel && (
          <div className="flex items-baseline justify-between gap-4">
            <span>{TERMS.type}</span>
            <span className="text-[#3D2E22]">{typeLabel}</span>
          </div>
        )}
        {score !== null && (
          <div className="flex items-baseline justify-between gap-4">
            <span>{msg("explore.detail.score")}</span>
            <span className="font-mono tabular-nums text-[#3D2E22]" dir="ltr">
              {score}
            </span>
          </div>
        )}
        {point.winning_model && (
          <div className="flex items-baseline justify-between gap-4">
            <span className="shrink-0">{msg("explore.detail.model")}</span>
            <span
              className="min-w-0 truncate font-mono text-[#3D2E22]"
              dir="ltr"
              title={point.winning_model}
            >
              {point.winning_model}
            </span>
          </div>
        )}
      </div>
      <p className="mt-2 border-t border-[#DDD6CC]/50 pt-1.5 text-[0.6875rem] text-[#8C7A6B]/80">
        {msg("explore.tooltip.open_hint")}
      </p>
    </div>
  );
}
