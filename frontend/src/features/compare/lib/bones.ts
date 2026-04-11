/**
 * Boneyard skeleton bones for the compare page.
 * Matches: breadcrumb + two side-by-side metric cards + result sections.
 */

import type { Bone, ResponsiveBones } from "boneyard-js";

function bone(x: number, y: number, w: number, h: number, r: number, container = false): Bone {
  return container ? { x, y, w, h, r, c: true } : { x, y, w, h, r };
}

/* ── Desktop ── */
const dW = 1000;
const halfW = (dW - 16) / 2;

const desktopBones: Bone[] = [
  // Breadcrumb
  bone(dW - 100, 0, 48, 14, 4),
  bone(dW - 170, 0, 56, 14, 4),

  // Title
  bone(dW - 200, 32, 180, 24, 4),

  // Left card
  bone(0, 72, halfW, 180, 12, true),
  bone(halfW - 16, 88, -200, 16, 4),
  bone(halfW - 16, 114, -60, 40, 4),
  bone(halfW - 16, 164, -120, 12, 4),
  bone(halfW - 16, 186, -100, 12, 4),
  bone(halfW - 16, 208, -80, 12, 4),

  // Right card
  bone(halfW + 16, 72, halfW, 180, 12, true),
  bone(halfW + 16 + halfW - 16, 88, -200, 16, 4),
  bone(halfW + 16 + halfW - 16, 114, -60, 40, 4),
  bone(halfW + 16 + halfW - 16, 164, -120, 12, 4),
  bone(halfW + 16 + halfW - 16, 186, -100, 12, 4),
  bone(halfW + 16 + halfW - 16, 208, -80, 12, 4),

  // Comparison table
  bone(0, 276, dW, 220, 12, true),
  bone(16, 292, dW - 32, 28, 4, true),
  bone(16, 336, dW * 0.3, 14, 4),
  bone(dW * 0.4, 336, 80, 14, 4),
  bone(dW * 0.7, 336, 80, 14, 4),
  bone(16, 366, dW * 0.3, 14, 4),
  bone(dW * 0.4, 366, 80, 14, 4),
  bone(dW * 0.7, 366, 80, 14, 4),
  bone(16, 396, dW * 0.3, 14, 4),
  bone(dW * 0.4, 396, 80, 14, 4),
  bone(dW * 0.7, 396, 80, 14, 4),
  bone(16, 426, dW * 0.3, 14, 4),
  bone(dW * 0.4, 426, 80, 14, 4),
  bone(dW * 0.7, 426, 80, 14, 4),
  bone(16, 456, dW * 0.3, 14, 4),
  bone(dW * 0.4, 456, 80, 14, 4),
  bone(dW * 0.7, 456, 80, 14, 4),
];

/* ── Mobile ── */
const mW = 343;
const mobileBones: Bone[] = [
  bone(mW - 80, 0, 40, 12, 4),
  bone(mW - 136, 0, 44, 12, 4),
  bone(mW - 160, 24, 140, 20, 4),

  // Stacked cards
  bone(0, 56, mW, 150, 12, true),
  bone(mW - 12, 68, -160, 14, 4),
  bone(mW - 12, 92, -50, 32, 4),
  bone(mW - 12, 132, -100, 10, 4),
  bone(mW - 12, 150, -80, 10, 4),

  bone(0, 218, mW, 150, 12, true),
  bone(mW - 12, 230, -160, 14, 4),
  bone(mW - 12, 254, -50, 32, 4),
  bone(mW - 12, 294, -100, 10, 4),
  bone(mW - 12, 312, -80, 10, 4),

  bone(0, 382, mW, 180, 12, true),
  bone(12, 396, mW - 24, 24, 4, true),
  bone(12, 434, 100, 12, 4),
  bone(150, 434, 60, 12, 4),
  bone(12, 460, 100, 12, 4),
  bone(150, 460, 60, 12, 4),
  bone(12, 486, 100, 12, 4),
  bone(150, 486, 60, 12, 4),
];

/* ── Tablet ── */
const tW = 700;
const tHalf = (tW - 16) / 2;

const tabletBones: Bone[] = [
  bone(tW - 100, 0, 48, 14, 4),
  bone(tW - 168, 0, 56, 14, 4),
  bone(tW - 180, 28, 160, 22, 4),

  bone(0, 64, tHalf, 160, 12, true),
  bone(tHalf - 16, 80, -180, 14, 4),
  bone(tHalf - 16, 104, -50, 36, 4),
  bone(tHalf - 16, 148, -100, 10, 4),
  bone(tHalf - 16, 168, -80, 10, 4),

  bone(tHalf + 16, 64, tHalf, 160, 12, true),
  bone(tHalf + 16 + tHalf - 16, 80, -180, 14, 4),
  bone(tHalf + 16 + tHalf - 16, 104, -50, 36, 4),
  bone(tHalf + 16 + tHalf - 16, 148, -100, 10, 4),
  bone(tHalf + 16 + tHalf - 16, 168, -80, 10, 4),

  bone(0, 248, tW, 200, 12, true),
  bone(16, 264, tW - 32, 26, 4, true),
  bone(16, 304, tW * 0.3, 14, 4),
  bone(tW * 0.4, 304, 70, 14, 4),
  bone(tW * 0.7, 304, 70, 14, 4),
  bone(16, 332, tW * 0.3, 14, 4),
  bone(tW * 0.4, 332, 70, 14, 4),
  bone(tW * 0.7, 332, 70, 14, 4),
  bone(16, 360, tW * 0.3, 14, 4),
  bone(tW * 0.4, 360, 70, 14, 4),
  bone(tW * 0.7, 360, 70, 14, 4),
  bone(16, 388, tW * 0.3, 14, 4),
  bone(tW * 0.4, 388, 70, 14, 4),
  bone(tW * 0.7, 388, 70, 14, 4),
];

export const compareBones: ResponsiveBones = {
  breakpoints: {
    375: { name: "compare", viewportWidth: 375, width: mW, height: 580, bones: mobileBones },
    768: { name: "compare", viewportWidth: 768, width: tW, height: 470, bones: tabletBones },
    1280: { name: "compare", viewportWidth: 1280, width: dW, height: 510, bones: desktopBones },
  },
};
