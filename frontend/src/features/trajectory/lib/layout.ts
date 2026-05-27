import type { CandidateMetrics, RejectedMetrics, RejectedNode, TrajectoryNode } from "./types";

const NODE_GAP_X = 96;
const NODE_GAP_Y = 132;
const NODE_RADIUS = 30;
const GHOST_RADIUS = 7;
const GHOST_ORBIT_BASE = NODE_RADIUS + 22;
const GHOST_ORBIT_STEP = 12;
const GHOST_ARC_RADIANS = Math.PI * 0.55;
const TOP_PAD = NODE_RADIUS + 20;

export interface LayoutResult {
  nodes: TrajectoryNode[];
  ghosts: RejectedNode[];
  edges: Array<{ from: string; to: string; isMerge: boolean }>;
  width: number;
  height: number;
  winnerId: string | null;
  spineIds: Set<string>;
}

function buildSpine(byId: Map<string, TrajectoryNode>, winnerId: string | null): Set<string> {
  const spine = new Set<string>();
  if (winnerId === null) return spine;
  let cursor: string | null = winnerId;
  while (cursor !== null) {
    if (spine.has(cursor)) break;
    spine.add(cursor);
    const node = byId.get(cursor);
    cursor = node?.parent_id ?? null;
  }
  return spine;
}

export function layoutTrajectory(
  candidates: CandidateMetrics[],
  rejected: RejectedMetrics[] = [],
): LayoutResult {
  if (candidates.length === 0) {
    return {
      nodes: [],
      ghosts: [],
      edges: [],
      width: 0,
      height: 0,
      winnerId: null,
      spineIds: new Set(),
    };
  }

  const byId = new Map<string, TrajectoryNode>();
  for (const c of candidates) {
    byId.set(c.candidate_id, {
      ...c,
      children: [],
      x: 0,
      y: 0,
      subtreeWidth: 1,
      isWinner: false,
      isSeed: c.parent_id === null,
      isOnSpine: false,
    });
  }

  let root: TrajectoryNode | null = null;
  for (const node of byId.values()) {
    if (node.parent_id === null) {
      if (root === null) root = node;
      continue;
    }
    const parent = byId.get(node.parent_id);
    if (parent !== undefined) parent.children.push(node);
  }
  if (root === null) {
    // No parent_id=null candidate. Fall back to the lowest-id node so the
    // tree still renders even on malformed payloads.
    root = candidates
      .map((c) => byId.get(c.candidate_id))
      .filter((n): n is TrajectoryNode => n !== undefined)
      .sort((a, b) => Number(a.candidate_id) - Number(b.candidate_id))[0] ?? null;
  }
  if (root === null) {
    return {
      nodes: [],
      ghosts: [],
      edges: [],
      width: 0,
      height: 0,
      winnerId: null,
      spineIds: new Set(),
    };
  }

  for (const node of byId.values()) {
    node.children.sort((a, b) => Number(a.candidate_id) - Number(b.candidate_id));
  }

  const computeWidth = (node: TrajectoryNode): number => {
    if (node.children.length === 0) {
      node.subtreeWidth = 1;
      return 1;
    }
    let total = 0;
    for (const c of node.children) total += computeWidth(c);
    node.subtreeWidth = Math.max(1, total);
    return node.subtreeWidth;
  };
  computeWidth(root);

  const place = (node: TrajectoryNode, leftSlot: number, depth: number): void => {
    node.y = depth * NODE_GAP_Y + TOP_PAD;
    if (node.children.length === 0) {
      node.x = leftSlot * NODE_GAP_X + NODE_GAP_X / 2;
      return;
    }
    let cursor = leftSlot;
    for (const child of node.children) {
      place(child, cursor, depth + 1);
      cursor += child.subtreeWidth;
    }
    const first = node.children[0];
    const last = node.children[node.children.length - 1];
    if (first !== undefined && last !== undefined) {
      node.x = (first.x + last.x) / 2;
    }
  };
  place(root, 0, 0);

  let winnerId: string | null = null;
  let bestScore = -Infinity;
  for (const node of byId.values()) {
    if (node.score > bestScore) {
      bestScore = node.score;
      winnerId = node.candidate_id;
    }
  }
  const spineIds = buildSpine(byId, winnerId);
  for (const node of byId.values()) {
    node.isWinner = node.candidate_id === winnerId;
    node.isOnSpine = spineIds.has(node.candidate_id);
  }

  const edges: Array<{ from: string; to: string; isMerge: boolean }> = [];
  for (const node of byId.values()) {
    if (node.parent_id !== null && byId.has(node.parent_id)) {
      edges.push({ from: node.parent_id, to: node.candidate_id, isMerge: false });
    }
    for (const extra of node.parents_extra) {
      if (byId.has(extra)) {
        edges.push({ from: extra, to: node.candidate_id, isMerge: true });
      }
    }
  }

  const ghostsByParent = new Map<string, RejectedMetrics[]>();
  for (const rej of rejected) {
    if (!byId.has(rej.parent_id)) continue;
    const list = ghostsByParent.get(rej.parent_id);
    if (list === undefined) ghostsByParent.set(rej.parent_id, [rej]);
    else list.push(rej);
  }
  const ghosts: RejectedNode[] = [];
  for (const [parentId, parentRejections] of ghostsByParent) {
    const parent = byId.get(parentId);
    if (parent === undefined) continue;
    parentRejections.sort((a, b) => a.iteration - b.iteration);
    // Fan rejected proposals out in a shallow arc on the trailing side of the
    // parent so they read as "tried but didn't stick" rather than children.
    parentRejections.forEach((rej, idx) => {
      const ring = Math.floor(idx / 5);
      const offsetInRing = idx % 5;
      const ringSize = Math.min(5, parentRejections.length - ring * 5);
      const spread = ringSize === 1 ? 0 : (offsetInRing - (ringSize - 1) / 2) / (ringSize - 1);
      const angle = -Math.PI / 2 + spread * GHOST_ARC_RADIANS;
      const r = GHOST_ORBIT_BASE + ring * GHOST_ORBIT_STEP;
      ghosts.push({
        ...rej,
        x: parent.x + r * Math.cos(angle),
        y: parent.y + r * Math.sin(angle),
      });
    });
  }

  const nodes = Array.from(byId.values());
  const xs = nodes.map((n) => n.x);
  const ys = nodes.map((n) => n.y);
  const ghostMaxX = ghosts.length > 0 ? Math.max(...ghosts.map((g) => g.x + GHOST_RADIUS)) : 0;
  const ghostMaxY = ghosts.length > 0 ? Math.max(...ghosts.map((g) => g.y + GHOST_RADIUS)) : 0;
  const width = Math.max(Math.max(...xs) + NODE_GAP_X / 2 + NODE_RADIUS, ghostMaxX + 12);
  const height = Math.max(Math.max(...ys) + NODE_GAP_Y / 2 + NODE_RADIUS, ghostMaxY + 12);

  return { nodes, ghosts, edges, width, height, winnerId, spineIds };
}

export const TRAJECTORY_LAYOUT = {
  nodeRadius: NODE_RADIUS,
  ghostRadius: GHOST_RADIUS,
  gapX: NODE_GAP_X,
  gapY: NODE_GAP_Y,
} as const;
