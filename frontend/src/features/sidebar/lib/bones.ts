/**
 * Boneyard skeleton bones for the sidebar's infinite-scroll "load more"
 * state. Rendered below the currently-visible jobs while the next page
 * is in flight. Each bone row mirrors the shape of a real ``JobRow``:
 * a small status dot plus a single text line.
 */

import type { Bone, ResponsiveBones } from "boneyard-js";

function bone(x: number, y: number, w: number, h: number, r: number): Bone {
  return { x, y, w, h, r };
}

// Inner width = sidebar column (~224px) minus ps-2/pe-2 padding (8px each side).
const W = 208;
const ROW_HEIGHT = 30;
const ROW_GAP = 4;
const ROW_COUNT = 3;

function rowBones(y: number): Bone[] {
  return [
    // Status dot, pinned to the right (RTL start).
    bone(W - 14, y + 12, 6, 6, 3),
    // Job-name line, filling most of the row width.
    bone(8, y + 9, W - 30, 12, 4),
  ];
}

const bones: Bone[] = [];
for (let i = 0; i < ROW_COUNT; i++) {
  bones.push(...rowBones(i * (ROW_HEIGHT + ROW_GAP)));
}

const HEIGHT = ROW_COUNT * (ROW_HEIGHT + ROW_GAP);

export const sidebarMoreBones: ResponsiveBones = {
  breakpoints: {
    240: {
      name: "sidebar-more",
      viewportWidth: 240,
      width: W,
      height: HEIGHT,
      bones,
    },
  },
};
