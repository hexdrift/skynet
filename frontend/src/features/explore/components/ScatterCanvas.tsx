"use client";

import * as React from "react";
import { LocateFixed, Minus, Plus, RotateCcw } from "lucide-react";
import type { PublicDashboardPoint } from "@/shared/lib/api";
import { getJobTypeLabel } from "@/shared/constants/job-status";
import { formatMsg, msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";
import {
  Tooltip as UiTooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/shared/ui/primitives/tooltip";
import {
  BASE_RADIUS,
  DRAG_THRESHOLD_PX,
  FOCUS_RING_COLOR,
  FOCUS_RING_OFFSET,
  GRID_AXIS_COLOR,
  GRID_LINE_COLOR,
  HOVER_RADIUS,
  MAX_SCALE,
  MIN_SCALE,
  PADDING,
  POINT_OUTLINE_COLOR,
  TOOLTIP_ABOVE_THRESHOLD,
  TOOLTIP_EDGE_INSET,
  TOOLTIP_MAX_WIDTH,
  ZOOM_DOUBLECLICK_IN,
  ZOOM_DOUBLECLICK_OUT,
  ZOOM_WHEEL_FACTOR,
} from "../constants";
import {
  clampNorm,
  clampView,
  formatScore,
  type View,
} from "../lib/format";

export type ExploreFilter = "all" | "run" | "grid_search";

interface ScatterCanvasProps {
  points: PublicDashboardPoint[];
  filter: ExploreFilter;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  dimmed?: boolean;
  hideResetButton?: boolean;
  heightClass?: string;
  children?: React.ReactNode;
  // optimization_ids of leaders whose task has more than one variation
  // (same task_fingerprint, different splits). Rendered with a subtle
  // concentric ring and a hover hint pointing at the picker.
  multiVariationIds?: ReadonlySet<string>;
  // Number of variations per leader (when > 1). Used to format the
  // hover hint via the `explore.canvas.variations_hint` catalog entry.
  variationCountById?: ReadonlyMap<string, number>;
  // When non-null, points whose id is not in this set fade to ~15%. Lets
  // the map act as a secondary view of an active semantic search — matches
  // pop, non-matches recede without disappearing entirely.
  matchedIds?: ReadonlySet<string> | null;
}

interface ProjectedPoint {
  point: PublicDashboardPoint;
  basePx: number;
  basePy: number;
  radius: number;
  match: boolean;
  // false when an active search excludes this point — drives an extra
  // alpha multiplier in the draw loop. True when no search is active.
  searchMatch: boolean;
}

const GRID_STEP = 44;

const POINT_FILL_MATCH = "oklch(0.3 0.05 40)";
const POINT_FILL_DIM = "oklch(0.3 0.01 40)";

function drawCanvasGrid(
  ctx: CanvasRenderingContext2D,
  size: { w: number; h: number },
  view: View,
) {
  const step = GRID_STEP * view.k;
  const offsetX = ((view.tx % step) + step) % step;
  const offsetY = ((view.ty % step) + step) % step;

  ctx.strokeStyle = GRID_LINE_COLOR;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = offsetX; x <= size.w; x += step) {
    ctx.moveTo(x, 0);
    ctx.lineTo(x, size.h);
  }
  for (let y = offsetY; y <= size.h; y += step) {
    ctx.moveTo(0, y);
    ctx.lineTo(size.w, y);
  }
  ctx.stroke();
}

export function ScatterCanvas({
  points,
  filter,
  selectedId,
  onSelect,
  dimmed = false,
  hideResetButton = false,
  heightClass = "h-[64vh] min-h-[420px]",
  children,
  multiVariationIds,
  variationCountById,
  matchedIds,
}: ScatterCanvasProps) {
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const [size, setSize] = React.useState({ w: 0, h: 0 });
  const [hoveredId, setHoveredId] = React.useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = React.useState<{ x: number; y: number } | null>(null);
  const [view, setView] = React.useState<View>({ k: 1, tx: 0, ty: 0 });
  const [isDragging, setIsDragging] = React.useState(false);
  const panStateRef = React.useRef<null | {
    pointerId: number;
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
      const searchMatch = matchedIds == null || matchedIds.has(point.optimization_id);
      const normX = (clampNorm(point.x) + 1) / 2;
      const normY = 1 - (clampNorm(point.y) + 1) / 2;
      return {
        point,
        basePx: PADDING + normX * plotW,
        basePy: PADDING + normY * plotH,
        radius: match ? BASE_RADIUS : BASE_RADIUS - 1,
        match,
        searchMatch,
      };
    });
  }, [points, filter, size, matchedIds]);

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
    drawCanvasGrid(ctx, size, view);

    const cx = (size.w / 2) * view.k + view.tx;
    const cy = (size.h / 2) * view.k + view.ty;
    ctx.strokeStyle = GRID_AXIS_COLOR;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx, PADDING);
    ctx.lineTo(cx, size.h - PADDING);
    ctx.moveTo(PADDING, cy);
    ctx.lineTo(size.w - PADDING, cy);
    ctx.stroke();

    // Viewport-cull before sorting — at 100k points only a fraction is
    // ever on screen, and the per-frame sort is what dominates otherwise.
    const cullMargin = HOVER_RADIUS + FOCUS_RING_OFFSET + 4;
    const visible: Array<{ p: ProjectedPoint; sx: number; sy: number }> = [];
    for (const p of projected) {
      const sx = p.basePx * view.k + view.tx;
      const sy = p.basePy * view.k + view.ty;
      if (sx < -cullMargin || sx > size.w + cullMargin) continue;
      if (sy < -cullMargin || sy > size.h + cullMargin) continue;
      visible.push({ p, sx, sy });
    }

    const rank = (p: ProjectedPoint) => {
      if (selectedId === p.point.optimization_id || hoveredId === p.point.optimization_id) return 3;
      if (!p.searchMatch) return 0;
      return p.match ? 2 : 1;
    };
    visible.sort((a, b) => rank(a.p) - rank(b.p));

    for (const { p, sx, sy } of visible) {
      const isHovered = hoveredId === p.point.optimization_id;
      const isSelected = selectedId === p.point.optimization_id;
      const isActive = isHovered || isSelected;
      const hasVariations = multiVariationIds?.has(p.point.optimization_id) ?? false;
      const fill = p.match ? POINT_FILL_MATCH : POINT_FILL_DIM;

      let alpha = p.match ? 1 : 0.35;
      if (!p.searchMatch && !isActive) alpha *= 0.15;
      if (dimmed && !isActive) alpha *= 0.35;

      ctx.beginPath();
      ctx.fillStyle = fill;
      ctx.globalAlpha = alpha;
      ctx.arc(sx, sy, isActive ? HOVER_RADIUS : p.radius, 0, Math.PI * 2);
      ctx.fill();

      // Subtle concentric ring marks dots that hide additional task
      // variations (same task, different splits). Drawn at low opacity so it
      // reads as a secondary affordance, not a primary visual.
      if (hasVariations && !isSelected) {
        ctx.globalAlpha = (p.match ? 0.4 : 0.2) * (dimmed && !isActive ? 0.5 : 1);
        ctx.strokeStyle = fill;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(sx, sy, (isActive ? HOVER_RADIUS : p.radius) + 3, 0, Math.PI * 2);
        ctx.stroke();
      }

      if (isSelected) {
        ctx.globalAlpha = 1;
        ctx.strokeStyle = FOCUS_RING_COLOR;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(sx, sy, HOVER_RADIUS + FOCUS_RING_OFFSET, 0, Math.PI * 2);
        ctx.stroke();
      } else if (isHovered) {
        ctx.globalAlpha = 1;
        ctx.strokeStyle = POINT_OUTLINE_COLOR;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(sx, sy, isActive ? HOVER_RADIUS : p.radius, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;

  }, [
    projected,
    size,
    hoveredId,
    selectedId,
    dimmed,
    view,
    multiVariationIds,
    matchedIds,
  ]);

  const pickNearest = React.useCallback(
    (clientX: number, clientY: number): ProjectedPoint | null => {
      const canvas = canvasRef.current;
      if (!canvas) return null;
      const rect = canvas.getBoundingClientRect();
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      // Bounding-box prefilter so the hover loop scales — at 100k points
      // checking distance against every one would block pointermove.
      const radius = HOVER_RADIUS + 4;
      let best: { p: ProjectedPoint; d: number } | null = null;
      for (const p of projected) {
        const sx = p.basePx * view.k + view.tx;
        if (sx < x - radius || sx > x + radius) continue;
        const sy = p.basePy * view.k + view.ty;
        if (sy < y - radius || sy > y + radius) continue;
        const d = Math.hypot(sx - x, sy - y);
        if (d < radius && (best === null || d < best.d)) {
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
    const container = containerRef.current;
    if (!container) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const rect = container.getBoundingClientRect();
      const factor = Math.exp(-e.deltaY * ZOOM_WHEEL_FACTOR);
      zoomAt(e.clientX - rect.left, e.clientY - rect.top, factor);
    };
    container.addEventListener("wheel", onWheel, { passive: false });
    return () => container.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  const handlePointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    panStateRef.current = {
      pointerId: e.pointerId,
      startClientX: e.clientX,
      startClientY: e.clientY,
      startTx: view.tx,
      startTy: view.ty,
      moved: false,
    };
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const ps = panStateRef.current;
    if (ps && ps.pointerId === e.pointerId) {
      const dx = e.clientX - ps.startClientX;
      const dy = e.clientY - ps.startClientY;
      if (!ps.moved && Math.hypot(dx, dy) > DRAG_THRESHOLD_PX) {
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
    if (e.pointerType !== "mouse") return;
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

  const handlePointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const ps = panStateRef.current;
    if (ps && ps.pointerId === e.pointerId) {
      panStateRef.current = null;
      e.currentTarget.releasePointerCapture(e.pointerId);
      if (ps.moved) {
        setIsDragging(false);
        return;
      }
    }
    const hit = pickNearest(e.clientX, e.clientY);
    if (!hit) {
      if (selectedId !== null) onSelect(null);
      return;
    }
    if (selectedId === hit.point.optimization_id) {
      onSelect(null);
    } else {
      onSelect(hit.point.optimization_id);
    }
  };

  const handlePointerCancel = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (panStateRef.current?.pointerId === e.pointerId) {
      panStateRef.current = null;
      setIsDragging(false);
    }
    setHoveredId(null);
    setTooltipPos(null);
  };

  const handlePointerLeave = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (e.pointerType !== "mouse") return;
    setHoveredId(null);
    setTooltipPos(null);
  };

  const handleDoubleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const factor = e.shiftKey ? ZOOM_DOUBLECLICK_OUT : ZOOM_DOUBLECLICK_IN;
    zoomAt(e.clientX - rect.left, e.clientY - rect.top, factor);
  };

  const resetView = () => setView({ k: 1, tx: 0, ty: 0 });
  const zoomFromCenter = (factor: number) => zoomAt(size.w / 2, size.h / 2, factor);
  const isTransformed = view.k !== 1 || view.tx !== 0 || view.ty !== 0;

  const hovered = projected.find((p) => p.point.optimization_id === hoveredId)?.point ?? null;
  const cursor = isDragging ? "cursor-grabbing" : "cursor-grab";
  const ariaLabel = formatMsg("explore.canvas.aria_label", { count: points.length });

  return (
    <div
      ref={containerRef}
      className={`relative ${heightClass} w-full overflow-hidden rounded-lg border border-border/50 bg-[radial-gradient(circle_at_50%_42%,hsl(var(--muted))_0,hsl(var(--background))_58%)]`}
    >
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={ariaLabel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
        onPointerLeave={handlePointerLeave}
        onDoubleClick={handleDoubleClick}
        className={`absolute inset-0 select-none touch-none ${cursor}`}
      />
      {children}
      {!hideResetButton && (
        <div className="absolute top-3 end-3 z-20 flex overflow-hidden rounded-lg border border-border/70 bg-background/90 shadow-sm backdrop-blur-sm">
          <MapControlButton
            label={msg("explore.map.zoom_in")}
            onClick={() => zoomFromCenter(1.25)}
          >
            <Plus className="size-3.5" aria-hidden="true" />
          </MapControlButton>
          <MapControlButton
            label={msg("explore.map.zoom_out")}
            onClick={() => zoomFromCenter(0.8)}
          >
            <Minus className="size-3.5" aria-hidden="true" />
          </MapControlButton>
          <MapControlButton label={msg("explore.map.reset")} onClick={resetView}>
            {isTransformed ? (
              <RotateCcw className="size-3.5" aria-hidden="true" />
            ) : (
              <LocateFixed className="size-3.5" aria-hidden="true" />
            )}
          </MapControlButton>
        </div>
      )}
      {hovered && tooltipPos && !isDragging && (
        <Tooltip
          point={hovered}
          x={tooltipPos.x}
          y={tooltipPos.y}
          containerWidth={size.w}
          variationCount={variationCountById?.get(hovered.optimization_id) ?? 1}
        />
      )}
    </div>
  );
}

function MapControlButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <UiTooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onClick}
          aria-label={label}
          className="inline-flex size-9 items-center justify-center border-s border-border/60 text-foreground transition-[background-color,color] first:border-s-0 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#C8A882]/45"
        >
          {children}
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" sideOffset={8}>
        {label}
      </TooltipContent>
    </UiTooltip>
  );
}

function Tooltip({
  point,
  x,
  y,
  containerWidth,
  variationCount,
}: {
  point: PublicDashboardPoint;
  x: number;
  y: number;
  containerWidth: number;
  variationCount: number;
}) {
  const primary = point.summary_text ?? point.task_name ?? "—";
  const typeLabel = point.optimization_type ? getJobTypeLabel(point.optimization_type) : null;
  const score = formatScore(point.optimized_metric);
  const above = y > TOOLTIP_ABOVE_THRESHOLD;
  const hasVariations = variationCount > 1;

  const half = TOOLTIP_MAX_WIDTH / 2;
  let shiftX = 0;
  const leftEdge = x - half;
  const rightEdge = x + half;
  if (leftEdge < TOOLTIP_EDGE_INSET) shiftX = TOOLTIP_EDGE_INSET - leftEdge;
  else if (rightEdge > containerWidth - TOOLTIP_EDGE_INSET)
    shiftX = containerWidth - TOOLTIP_EDGE_INSET - rightEdge;

  const style: React.CSSProperties = {
    left: x,
    top: y,
    transform: above
      ? `translate(calc(-50% + ${shiftX}px), calc(-100% - 12px))`
      : `translate(calc(-50% + ${shiftX}px), 12px)`,
    maxWidth: TOOLTIP_MAX_WIDTH,
  };

  return (
    <div
      dir="rtl"
      className="pointer-events-none absolute z-10 rounded-lg border border-border/70 bg-background/95 p-3 shadow-xl shadow-foreground/10 backdrop-blur-sm"
      style={style}
    >
      <p
        dir="auto"
        className="mb-2 text-[0.8125rem] font-semibold leading-snug tracking-tight text-foreground line-clamp-2"
      >
        {primary}
      </p>
      <div className="space-y-1 text-[0.6875rem] text-muted-foreground">
        {typeLabel && (
          <div className="flex items-baseline justify-between gap-4">
            <span>{TERMS.type}</span>
            <span className="text-foreground">{typeLabel}</span>
          </div>
        )}
        {score !== null && (
          <div className="flex items-baseline justify-between gap-4">
            <span>{msg("explore.detail.score")}</span>
            <span className="font-mono tabular-nums text-foreground" dir="ltr">
              {score}
            </span>
          </div>
        )}
        {point.winning_model && (
          <div className="flex items-baseline justify-between gap-4">
            <span className="shrink-0">{msg("explore.detail.model")}</span>
            <span
              className="min-w-0 truncate font-mono text-foreground"
              dir="ltr"
              title={point.winning_model}
            >
              {point.winning_model}
            </span>
          </div>
        )}
      </div>
      <p className="mt-2 border-t border-border/50 pt-1.5 text-[0.6875rem] font-medium text-muted-foreground/80">
        {hasVariations
          ? formatMsg("explore.canvas.variations_hint", { n: variationCount })
          : msg("explore.tooltip.open_hint")}
      </p>
    </div>
  );
}
