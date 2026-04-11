/**
 * Boneyard skeleton bones for the data tab.
 * Matches: eval summary bar + split tabs + data table.
 */

import type { Bone, ResponsiveBones } from "boneyard-js";

function bone(x: number, y: number, w: number, h: number, r: number, container = false): Bone {
  return container ? { x, y, w, h, r, c: true } : { x, y, w, h, r };
}

function tableRow(y: number, w: number): Bone[] {
  const col = (w - 32) / 5;
  return [
    bone(16, y, col * 0.4, 14, 4),
    bone(16 + col, y, col * 0.8, 14, 4),
    bone(16 + col * 2, y, col * 0.9, 14, 4),
    bone(16 + col * 3, y, col * 0.7, 14, 4),
    bone(16 + col * 4, y, col * 0.6, 14, 4),
  ];
}

/* ── Desktop ── */
const dW = 960;
const desktopBones: Bone[] = [
  bone(0, 0, dW, 72, 16, true),
  bone(dW - 16, 14, -140, 14, 4),
  bone(dW - 16, 36, -200, 10, 4),
  bone(16, 52, dW - 32, 8, 4), // gradient bar

  bone(0, 88, dW, 36, 8, true),
  bone(16, 96, 60, 18, 4),
  bone(92, 96, 60, 18, 4),
  bone(168, 96, 60, 18, 4),
  bone(244, 96, 60, 18, 4),

  bone(dW - 80, 140, 64, 12, 4),

  bone(0, 160, dW, 340, 12, true),
  bone(16, 176, dW - 32, 28, 4, true),

  ...tableRow(220, dW),
  ...tableRow(252, dW),
  ...tableRow(284, dW),
  ...tableRow(316, dW),
  ...tableRow(348, dW),
  ...tableRow(380, dW),
  ...tableRow(412, dW),
  ...tableRow(444, dW),
];

/* ── Mobile ── */
const mW = 343;
const mobileTableRow = (y: number): Bone[] => [
  bone(12, y, 40, 12, 4),
  bone(64, y, 100, 12, 4),
  bone(176, y, 80, 12, 4),
  bone(268, y, 60, 12, 4),
];

const mobileBones: Bone[] = [
  bone(0, 0, mW, 64, 14, true),
  bone(mW - 12, 12, -110, 12, 4),
  bone(mW - 12, 30, -160, 10, 4),
  bone(12, 48, mW - 24, 6, 3),

  bone(0, 78, mW, 32, 8, true),
  bone(12, 86, 50, 14, 4),
  bone(72, 86, 50, 14, 4),
  bone(132, 86, 50, 14, 4),
  bone(192, 86, 50, 14, 4),

  bone(mW - 60, 124, 50, 10, 4),

  bone(0, 142, mW, 260, 12, true),
  bone(12, 156, mW - 24, 24, 4, true),
  ...mobileTableRow(194),
  ...mobileTableRow(220),
  ...mobileTableRow(246),
  ...mobileTableRow(272),
  ...mobileTableRow(298),
  ...mobileTableRow(324),
  ...mobileTableRow(350),
];

/* ── Tablet ── */
const tW = 700;
const tabletBones: Bone[] = [
  bone(0, 0, tW, 70, 16, true),
  bone(tW - 16, 14, -130, 14, 4),
  bone(tW - 16, 34, -180, 10, 4),
  bone(16, 52, tW - 32, 8, 4),

  bone(0, 86, tW, 34, 8, true),
  bone(16, 94, 56, 16, 4),
  bone(86, 94, 56, 16, 4),
  bone(156, 94, 56, 16, 4),
  bone(226, 94, 56, 16, 4),

  bone(tW - 70, 134, 56, 10, 4),

  bone(0, 152, tW, 300, 12, true),
  bone(16, 168, tW - 32, 26, 4, true),
  ...tableRow(210, tW),
  ...tableRow(242, tW),
  ...tableRow(274, tW),
  ...tableRow(306, tW),
  ...tableRow(338, tW),
  ...tableRow(370, tW),
  ...tableRow(402, tW),
];

export const dataTabBones: ResponsiveBones = {
  breakpoints: {
    375: { name: "data-tab", viewportWidth: 375, width: mW, height: 420, bones: mobileBones },
    768: { name: "data-tab", viewportWidth: 768, width: tW, height: 470, bones: tabletBones },
    1280: { name: "data-tab", viewportWidth: 1280, width: dW, height: 510, bones: desktopBones },
  },
};
