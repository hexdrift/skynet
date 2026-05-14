"use client";

import { type ReactNode } from "react";

export interface Bone {
  x: number;
  y: number;
  w: number;
  h: number;
  r: number;
  c?: boolean;
}

export interface SkeletonResult {
  name: string;
  viewportWidth: number;
  width: number;
  height: number;
  bones: Bone[];
}

export interface ResponsiveBones {
  breakpoints: Record<number, SkeletonResult>;
}

interface SkeletonProps {
  name: string;
  loading: boolean;
  initialBones: ResponsiveBones;
  color?: string;
  animate?: "shimmer";
  children: ReactNode;
}

export function Skeleton({ loading, initialBones, color = "var(--muted)", children }: SkeletonProps) {
  if (!loading) return <>{children}</>;

  const result = selectLargestBreakpoint(initialBones);

  return (
    <div
      aria-busy="true"
      className="relative w-full overflow-hidden rounded-lg"
      style={{ minHeight: result.height }}
    >
      <div className="pointer-events-none absolute inset-0">
        {result.bones.map((bone, index) => (
          <div
            key={`${bone.x}-${bone.y}-${bone.w}-${bone.h}-${index}`}
            className="absolute overflow-hidden skeleton-shimmer"
            style={{
              left: bone.w < 0 ? undefined : bone.x,
              right: bone.w < 0 ? result.width - bone.x : undefined,
              top: bone.y,
              width: Math.abs(bone.w),
              height: bone.h,
              borderRadius: bone.r,
              background: color,
              opacity: bone.c ? 0.55 : 0.9,
            }}
          />
        ))}
      </div>
      <div className="invisible">{children}</div>
    </div>
  );
}

function selectLargestBreakpoint(responsiveBones: ResponsiveBones): SkeletonResult {
  const breakpoints = Object.keys(responsiveBones.breakpoints)
    .map(Number)
    .sort((a, b) => a - b);
  const largest = breakpoints[breakpoints.length - 1] ?? 0;
  return (
    responsiveBones.breakpoints[largest] ?? {
      name: "skeleton",
      viewportWidth: 0,
      width: 0,
      height: 0,
      bones: [],
    }
  );
}
