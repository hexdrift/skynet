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
  CLUSTER_LABEL_MIN_POINTS,
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
  colorForCluster,
  computeClusterHulls,
  formatScore,
  pointInPolygon,
  type View,
} from "../lib/format";

export type ExploreFilter = "all" | "run" | "grid_search";

interface ScatterCanvasProps {
  points: PublicDashboardPoint[];
  filter: ExploreFilter;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  // Index into each point's cluster_levels array. The backend returns
  // a fixed number of levels (typically 5), and the slider in ExploreView
  // chooses which one drives the coloring.
  granularityLevel: number;
  // The number of clusters present at the current granularity level —
  // used to spread colors evenly around the hue wheel.
  clusterCount: number;
  dimmed?: boolean;
  hideResetButton?: boolean;
  heightClass?: string;
  children?: React.ReactNode;
  // optimization_ids of leaders whose task has more than one variation
  // (same task_fingerprint, different splits). Rendered with a subtle
  // concentric ring and a hover hint pointing at the picker.
  multiVariationIds?: ReadonlySet<string>;
  // Number of variations per leader (when > 1). Used to format the
  // hover hint as "{n} גרסאות — לחצו לבחירה".
  variationCountById?: ReadonlyMap<string, number>;
}

interface ProjectedPoint {
  point: PublicDashboardPoint;
  basePx: number;
  basePy: number;
  radius: number;
  match: boolean;
  color: string;
}

const GRID_STEP = 44;
// Pushes hull vertices outward from the cluster centroid by this many
// screen pixels so the boundary sits clear of the point markers (whose
// radius is BASE_RADIUS / HOVER_RADIUS) at any zoom level.
const HULL_PIXEL_PADDING = 8;

interface HullShape {
  clusterId: number;
  color: string;
  vertices: ReadonlyArray<{ bx: number; by: number }>;
  centroid: { cx: number; cy: number };
}

function projectHullToScreen(
  hull: HullShape,
  view: View,
): Array<{ x: number; y: number }> {
  const cx = hull.centroid.cx * view.k + view.tx;
  const cy = hull.centroid.cy * view.k + view.ty;
  return hull.vertices.map((v) => {
    const sx = v.bx * view.k + view.tx;
    const sy = v.by * view.k + view.ty;
    const dx = sx - cx;
    const dy = sy - cy;
    const len = Math.hypot(dx, dy) || 1;
    return {
      x: sx + (dx / len) * HULL_PIXEL_PADDING,
      y: sy + (dy / len) * HULL_PIXEL_PADDING,
    };
  });
}

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
  granularityLevel,
  clusterCount,
  dimmed = false,
  hideResetButton = false,
  heightClass = "h-[64vh] min-h-[420px]",
  children,
  multiVariationIds,
  variationCountById,
}: ScatterCanvasProps) {
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const [size, setSize] = React.useState({ w: 0, h: 0 });
  const [hoveredId, setHoveredId] = React.useState<string | null>(null);
  const [hoveredClusterId, setHoveredClusterId] = React.useState<number | null>(null);
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
      const normX = (clampNorm(point.x) + 1) / 2;
      const normY = 1 - (clampNorm(point.y) + 1) / 2;
      // cluster_levels is required by the DTO but defensively fall back to 0
      // if the field is absent (older backend, half-rolled-back deploy) or
      // the slider points past the array — the page stays useful either way.
      const clusterId = (point.cluster_levels ?? [])[granularityLevel] ?? 0;
      return {
        point,
        basePx: PADDING + normX * plotW,
        basePy: PADDING + normY * plotH,
        radius: match ? BASE_RADIUS : BASE_RADIUS - 1,
        match,
        color: colorForCluster(clusterId, clusterCount, match),
      };
    });
  }, [points, filter, size, granularityLevel, clusterCount]);

  const clusterHulls = React.useMemo<HullShape[]>(() => {
    if (size.w < 2 || size.h < 2) return [];
    const plotW = Math.max(1, size.w - PADDING * 2);
    const plotH = Math.max(1, size.h - PADDING * 2);
    return computeClusterHulls(points, granularityLevel, CLUSTER_LABEL_MIN_POINTS).map((h) => {
      const vertices = h.hull.map((v) => {
        const normX = (v.x + 1) / 2;
        const normY = 1 - (v.y + 1) / 2;
        return {
          bx: PADDING + normX * plotW,
          by: PADDING + normY * plotH,
        };
      });
      let cxSum = 0;
      let cySum = 0;
      for (const v of vertices) {
        cxSum += v.bx;
        cySum += v.by;
      }
      const cx = cxSum / vertices.length;
      const cy = cySum / vertices.length;
      return {
        clusterId: h.clusterId,
        color: colorForCluster(h.clusterId, clusterCount, true),
        vertices,
        centroid: { cx, cy },
      };
    });
  }, [points, granularityLevel, clusterCount, size]);

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

    for (const hull of clusterHulls) {
      const polygon = projectHullToScreen(hull, view);
      if (polygon.length < 3) continue;
      const isHovered = hull.clusterId === hoveredClusterId;
      ctx.beginPath();
      for (let i = 0; i < polygon.length; i++) {
        const v = polygon[i]!;
        if (i === 0) ctx.moveTo(v.x, v.y);
        else ctx.lineTo(v.x, v.y);
      }
      ctx.closePath();
      ctx.fillStyle = hull.color;
      ctx.globalAlpha = dimmed ? 0.04 : isHovered ? 0.14 : 0.06;
      ctx.fill();
      ctx.strokeStyle = hull.color;
      ctx.lineWidth = isHovered ? 2 : 1;
      ctx.globalAlpha = dimmed ? 0.3 : isHovered ? 0.85 : 0.45;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

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
      if (selectedId === p.point.optimization_id || hoveredId === p.point.optimization_id) return 2;
      return p.match ? 1 : 0;
    };
    visible.sort((a, b) => rank(a.p) - rank(b.p));

    for (const { p, sx, sy } of visible) {
      const isHovered = hoveredId === p.point.optimization_id;
      const isSelected = selectedId === p.point.optimization_id;
      const isActive = isHovered || isSelected;
      const hasVariations = multiVariationIds?.has(p.point.optimization_id) ?? false;

      let alpha = p.match ? 1 : 0.35;
      if (dimmed && !isActive) alpha *= 0.35;

      ctx.beginPath();
      ctx.fillStyle = p.color;
      ctx.globalAlpha = alpha;
      ctx.arc(sx, sy, isActive ? HOVER_RADIUS : p.radius, 0, Math.PI * 2);
      ctx.fill();

      // Subtle concentric ring marks dots that hide additional task
      // variations (same task, different splits). Drawn at low opacity so it
      // reads as a secondary affordance, not a primary visual.
      if (hasVariations && !isSelected) {
        ctx.globalAlpha = (p.match ? 0.4 : 0.2) * (dimmed && !isActive ? 0.5 : 1);
        ctx.strokeStyle = p.color;
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
    clusterHulls,
    size,
    hoveredId,
    hoveredClusterId,
    selectedId,
    dimmed,
    view,
    multiVariationIds,
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

  const pickClusterAt = React.useCallback(
    (clientX: number, clientY: number): number | null => {
      const canvas = canvasRef.current;
      if (!canvas || clusterHulls.length === 0) return null;
      const rect = canvas.getBoundingClientRect();
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      for (const hull of clusterHulls) {
        const polygon = projectHullToScreen(hull, view);
        if (polygon.length < 3) continue;
        if (pointInPolygon(x, y, polygon)) return hull.clusterId;
      }
      return null;
    },
    [clusterHulls, view],
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
        setHoveredClusterId(null);
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
      const cid = (hit.point.cluster_levels ?? [])[granularityLevel];
      setHoveredClusterId(cid ?? null);
    } else {
      setHoveredId(null);
      setTooltipPos(null);
      setHoveredClusterId(pickClusterAt(e.clientX, e.clientY));
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
    setHoveredClusterId(null);
  };

  const handlePointerLeave = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (e.pointerType !== "mouse") return;
    setHoveredId(null);
    setTooltipPos(null);
    setHoveredClusterId(null);
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
