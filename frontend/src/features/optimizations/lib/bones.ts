/**
 * Boneyard skeleton bones for the optimization detail page.
 * Matches: breadcrumb + header card + tabs + content area.
 */

import type { Bone, ResponsiveBones } from "boneyard-js";

function bone(x: number, y: number, w: number, h: number, r: number, container = false): Bone {
  return container ? { x, y, w, h, r, c: true } : { x, y, w, h, r };
}

/* ── Desktop (1280+) ── */
const dW = 1000;
const desktopBones: Bone[] = [
  bone(dW - 120, 0, 60, 14, 4),
  bone(dW - 200, 0, 60, 14, 4),

  bone(0, 32, dW, 140, 12, true),
  bone(dW - 24, 48, -300, 22, 4), // name (RTL aligned right)
  bone(dW - 340, 48, -72, 22, 11), // status badge
  bone(dW - 24, 80, -220, 12, 4), // description
  bone(dW - 24, 100, -180, 10, 4), // optimization ID
  bone(dW - 24, 124, -60, 20, 8), // badge
  bone(dW - 100, 124, -80, 20, 4), // elapsed

  bone(0, 192, 220, 90, 12, true),
  bone(16, 208, 80, 12, 4),
  bone(16, 232, 120, 28, 4),

  bone(236, 192, 220, 90, 12, true),
  bone(252, 208, 80, 12, 4),
  bone(252, 232, 120, 28, 4),

  bone(472, 192, 220, 90, 12, true),
  bone(488, 208, 80, 12, 4),
  bone(488, 232, 120, 28, 4),

  bone(0, 304, dW, 44, 8, true),
  bone(16, 316, 80, 18, 4),
  bone(112, 316, 80, 18, 4),
  bone(208, 316, 80, 18, 4),
  bone(304, 316, 80, 18, 4),

  bone(0, 368, dW, 300, 12, true),
  bone(16, 384, dW - 32, 16, 4),
  bone(16, 416, dW - 100, 14, 4),
  bone(16, 446, dW - 200, 14, 4),
  bone(16, 476, dW * 0.6, 14, 4),
  bone(16, 506, dW * 0.7, 14, 4),
  bone(16, 536, dW * 0.5, 14, 4),
  bone(16, 566, dW * 0.8, 14, 4),
];

/* ── Mobile (375) ── */
const mW = 343;
const mobileBones: Bone[] = [
  bone(mW - 100, 0, 50, 12, 4),
  bone(mW - 160, 0, 50, 12, 4),

  bone(0, 28, mW, 120, 12, true),
  bone(mW - 16, 40, -200, 18, 4),
  bone(mW - 230, 40, -56, 18, 11),
  bone(mW - 16, 64, -160, 10, 4),
  bone(mW - 16, 82, -120, 10, 4),
  bone(mW - 16, 104, -50, 16, 8),
  bone(mW - 80, 104, -60, 16, 4),

  bone(0, 164, (mW - 8) / 2, 80, 12, true),
  bone(16, 178, 60, 10, 4),
  bone(16, 198, 80, 22, 4),

  bone((mW + 8) / 2, 164, (mW - 8) / 2, 80, 12, true),
  bone((mW + 8) / 2 + 16, 178, 60, 10, 4),
  bone((mW + 8) / 2 + 16, 198, 80, 22, 4),

  bone(0, 260, mW, 40, 8, true),
  bone(16, 272, 60, 14, 4),
  bone(88, 272, 60, 14, 4),
  bone(160, 272, 60, 14, 4),

  bone(0, 316, mW, 240, 12, true),
  bone(16, 330, mW - 32, 14, 4),
  bone(16, 358, mW - 60, 12, 4),
  bone(16, 384, mW - 100, 12, 4),
  bone(16, 410, mW * 0.6, 12, 4),
  bone(16, 436, mW * 0.7, 12, 4),
];

/* ── Tablet (768) ── */
const tW = 720;
const tabletBones: Bone[] = [
  bone(tW - 120, 0, 60, 14, 4),
  bone(tW - 200, 0, 60, 14, 4),

  bone(0, 32, tW, 130, 12, true),
  bone(tW - 24, 48, -250, 20, 4),
  bone(tW - 290, 48, -64, 20, 11),
  bone(tW - 24, 76, -180, 12, 4),
  bone(tW - 24, 96, -160, 10, 4),
  bone(tW - 24, 118, -56, 18, 8),
  bone(tW - 96, 118, -70, 18, 4),

  bone(0, 182, 200, 86, 12, true),
  bone(16, 196, 70, 12, 4),
  bone(16, 218, 100, 24, 4),

  bone(216, 182, 200, 86, 12, true),
  bone(232, 196, 70, 12, 4),
  bone(232, 218, 100, 24, 4),

  bone(432, 182, 200, 86, 12, true),
  bone(448, 196, 70, 12, 4),
  bone(448, 218, 100, 24, 4),

  bone(0, 288, tW, 44, 8, true),
  bone(16, 300, 70, 16, 4),
  bone(102, 300, 70, 16, 4),
  bone(188, 300, 70, 16, 4),
  bone(274, 300, 70, 16, 4),

  bone(0, 352, tW, 280, 12, true),
  bone(16, 368, tW - 32, 16, 4),
  bone(16, 400, tW - 80, 14, 4),
  bone(16, 428, tW - 160, 14, 4),
  bone(16, 456, tW * 0.6, 14, 4),
  bone(16, 484, tW * 0.7, 14, 4),
];

export const optimizationDetailBones: ResponsiveBones = {
  breakpoints: {
    375: {
      name: "optimization-detail",
      viewportWidth: 375,
      width: mW,
      height: 580,
      bones: mobileBones,
    },
    768: {
      name: "optimization-detail",
      viewportWidth: 768,
      width: tW,
      height: 650,
      bones: tabletBones,
    },
    1280: {
      name: "optimization-detail",
      viewportWidth: 1280,
      width: dW,
      height: 690,
      bones: desktopBones,
    },
  },
};
