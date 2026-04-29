import type { Bone, ResponsiveBones, SkeletonResult } from "boneyard-js";

const PERCENT_WIDTH = 100;

function pct(px: number, viewportWidth: number): number {
  return (px / viewportWidth) * 100;
}

/**
 * Create a boneyard skeleton bone.
 *
 * `x` and `w` are percentages of the rendered container width. `y`, `h`, and
 * `r` remain pixels, matching boneyard-js runtime rendering semantics.
 */
function bone(x: number, y: number, w: number, h: number, r: number, container = false): Bone {
  return { x, y, w, h, r, ...(container ? { c: true } : {}) };
}

function rightAnchoredBone(
  viewportWidth: number,
  rightOffsetPx: number,
  y: number,
  widthPx: number,
  h: number,
  r: number,
): Bone {
  return bone(
    pct(viewportWidth - rightOffsetPx - widthPx, viewportWidth),
    y,
    pct(widthPx, viewportWidth),
    h,
    r,
  );
}

function cardBones(
  viewportWidth: number,
  xPx: number,
  yPx: number,
  widthPx: number,
  heightPx: number,
  paddingPx: number,
  titleWidthPx: number,
  scoreWidthPx: number,
): Bone[] {
  const right = xPx + widthPx - paddingPx;
  return [
    bone(pct(xPx, viewportWidth), yPx, pct(widthPx, viewportWidth), heightPx, 12, true),
    bone(
      pct(right - titleWidthPx, viewportWidth),
      yPx + 16,
      pct(titleWidthPx, viewportWidth),
      16,
      4,
    ),
    bone(
      pct(right - scoreWidthPx, viewportWidth),
      yPx + 42,
      pct(scoreWidthPx, viewportWidth),
      40,
      4,
    ),
    bone(pct(right - 120, viewportWidth), yPx + 92, pct(120, viewportWidth), 12, 4),
    bone(pct(right - 100, viewportWidth), yPx + 114, pct(100, viewportWidth), 12, 4),
    bone(pct(right - 80, viewportWidth), yPx + 136, pct(80, viewportWidth), 12, 4),
  ];
}

function tableRows(
  viewportWidth: number,
  yStart: number,
  rowGap: number,
  firstWidthPx: number,
  valueWidthPx: number,
  rows: number,
): Bone[] {
  return Array.from({ length: rows }, (_, index) => {
    const y = yStart + index * rowGap;
    return [
      bone(pct(16, viewportWidth), y, pct(firstWidthPx, viewportWidth), 14, 4),
      bone(40, y, pct(valueWidthPx, viewportWidth), 14, 4),
      bone(70, y, pct(valueWidthPx, viewportWidth), 14, 4),
    ];
  }).flat();
}

function mobileTableRows(viewportWidth: number): Bone[] {
  return [434, 460, 486].flatMap((y) => [
    bone(pct(12, viewportWidth), y, pct(100, viewportWidth), 12, 4),
    bone(pct(150, viewportWidth), y, pct(60, viewportWidth), 12, 4),
  ]);
}

function validateResult(result: SkeletonResult): void {
  for (const b of result.bones) {
    if (b.x < 0 || b.w < 0 || b.x + b.w > 100) {
      throw new Error(`compareBones has out-of-bounds horizontal geometry: x=${b.x}, w=${b.w}`);
    }
  }
}

const dW = 1000;
const desktopCardWidth = Math.floor((dW - 16) / 2);

const desktopBones: Bone[] = [
  rightAnchoredBone(dW, 52, 0, 48, 14, 4),
  rightAnchoredBone(dW, 114, 0, 56, 14, 4),
  rightAnchoredBone(dW, 20, 32, 180, 24, 4),
  ...cardBones(dW, 0, 72, desktopCardWidth, 180, 16, 200, 60),
  ...cardBones(dW, desktopCardWidth + 16, 72, desktopCardWidth, 180, 16, 200, 60),
  bone(0, 276, PERCENT_WIDTH, 220, 12, true),
  bone(pct(16, dW), 292, pct(dW - 32, dW), 28, 4, true),
  ...tableRows(dW, 336, 30, 300, 80, 5),
];

const mW = 343;

const mobileBones: Bone[] = [
  rightAnchoredBone(mW, 40, 0, 40, 12, 4),
  rightAnchoredBone(mW, 92, 0, 44, 12, 4),
  rightAnchoredBone(mW, 20, 24, 140, 20, 4),
  ...cardBones(mW, 0, 56, mW, 150, 12, 160, 50),
  ...cardBones(mW, 0, 218, mW, 150, 12, 160, 50),
  bone(0, 382, PERCENT_WIDTH, 180, 12, true),
  bone(pct(12, mW), 396, pct(mW - 24, mW), 24, 4, true),
  ...mobileTableRows(mW),
];

const tW = 700;
const tabletCardWidth = Math.floor((tW - 16) / 2);

const tabletBones: Bone[] = [
  rightAnchoredBone(tW, 52, 0, 48, 14, 4),
  rightAnchoredBone(tW, 112, 0, 56, 14, 4),
  rightAnchoredBone(tW, 20, 28, 160, 22, 4),
  ...cardBones(tW, 0, 64, tabletCardWidth, 160, 16, 180, 50),
  ...cardBones(tW, tabletCardWidth + 16, 64, tabletCardWidth, 160, 16, 180, 50),
  bone(0, 248, PERCENT_WIDTH, 200, 12, true),
  bone(pct(16, tW), 264, pct(tW - 32, tW), 26, 4, true),
  ...tableRows(tW, 304, 28, 210, 70, 4),
];

export const compareBones: ResponsiveBones = {
  breakpoints: {
    375: {
      name: "compare",
      viewportWidth: 375,
      width: PERCENT_WIDTH,
      height: 580,
      bones: mobileBones,
    },
    768: {
      name: "compare",
      viewportWidth: 768,
      width: PERCENT_WIDTH,
      height: 470,
      bones: tabletBones,
    },
    1280: {
      name: "compare",
      viewportWidth: 1280,
      width: PERCENT_WIDTH,
      height: 510,
      bones: desktopBones,
    },
  },
};

Object.values(compareBones.breakpoints).forEach(validateResult);
