import type { Bone, ResponsiveBones } from "boneyard-js";

function bone(x: number, y: number, w: number, h: number, r: number, container = false): Bone {
  return container ? { x, y, w, h, r, c: true } : { x, y, w, h, r };
}

function statCardBones(x: number, y: number, w: number): Bone[] {
  return [
    bone(x, y, w, 120, 12, true),
    bone(x + 16, y + 16, 50, 14, 4),
    bone(x + w - 56, y + 16, 40, 40, 12),
    bone(x + 16, y + 60, 60, 28, 4),
    bone(x + 16, y + 96, 70, 10, 4),
  ];
}

function tableRowBones(y: number, w: number): Bone[] {
  return [
    bone(16, y, 54, 22, 11),
    bone(86, y + 2, Math.min(w * 0.2, 140), 16, 4),
    bone(86 + Math.min(w * 0.2, 140) + 16, y + 2, 60, 16, 4),
    bone(w - 180, y + 2, 80, 16, 4),
    bone(w - 84, y + 2, 70, 16, 4),
  ];
}

const dW = 1100;
const dCard = (dW - 48) / 4;

const desktopBones: Bone[] = [
  bone(0, 0, 120, 28, 4),
  bone(0, 36, 100, 14, 4),
  ...statCardBones(0, 72, dCard),
  ...statCardBones(dCard + 16, 72, dCard),
  ...statCardBones((dCard + 16) * 2, 72, dCard),
  ...statCardBones((dCard + 16) * 3, 72, dCard),
  bone(0, 216, 100, 32, 8),
  bone(116, 216, 100, 32, 8),
  bone(0, 264, dW, 400, 12, true),
  bone(16, 280, dW - 32, 32, 4, true),
  ...tableRowBones(328, dW),
  ...tableRowBones(372, dW),
  ...tableRowBones(416, dW),
  ...tableRowBones(460, dW),
  ...tableRowBones(504, dW),
  ...tableRowBones(548, dW),
];

const mW = 343;
const mCard = (mW - 16) / 2;

const mobileBones: Bone[] = [
  bone(0, 0, 100, 24, 4),
  bone(0, 30, 80, 12, 4),
  ...statCardBones(0, 58, mCard),
  ...statCardBones(mCard + 16, 58, mCard),
  ...statCardBones(0, 194, mCard),
  ...statCardBones(mCard + 16, 194, mCard),
  bone(0, 338, 80, 28, 8),
  bone(96, 338, 80, 28, 8),
  bone(0, 382, mW, 300, 12, true),
  bone(16, 398, 54, 20, 10),
  bone(86, 400, 120, 14, 4),
  bone(16, 434, 54, 20, 10),
  bone(86, 436, 120, 14, 4),
  bone(16, 470, 54, 20, 10),
  bone(86, 472, 120, 14, 4),
  bone(16, 506, 54, 20, 10),
  bone(86, 508, 120, 14, 4),
];

const tW = 720;
const tCard = (tW - 48) / 4;

const tabletBones: Bone[] = [
  bone(0, 0, 120, 28, 4),
  bone(0, 36, 100, 14, 4),
  ...statCardBones(0, 72, tCard),
  ...statCardBones(tCard + 16, 72, tCard),
  ...statCardBones((tCard + 16) * 2, 72, tCard),
  ...statCardBones((tCard + 16) * 3, 72, tCard),
  bone(0, 216, 100, 32, 8),
  bone(116, 216, 100, 32, 8),
  bone(0, 264, tW, 350, 12, true),
  bone(16, 280, tW - 32, 32, 4, true),
  ...tableRowBones(328, tW),
  ...tableRowBones(372, tW),
  ...tableRowBones(416, tW),
  ...tableRowBones(460, tW),
];

export const dashboardBones: ResponsiveBones = {
  breakpoints: {
    375: { name: "dashboard", viewportWidth: 375, width: mW, height: 682, bones: mobileBones },
    768: { name: "dashboard", viewportWidth: 768, width: tW, height: 560, bones: tabletBones },
    1280: { name: "dashboard", viewportWidth: 1280, width: dW, height: 660, bones: desktopBones },
  },
};
