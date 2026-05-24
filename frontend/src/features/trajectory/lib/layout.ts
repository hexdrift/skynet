import type { CandidateMetrics, TrajectoryNode } from "./types";

const NODE_GAP_X = 64;
const NODE_GAP_Y = 96;
const NODE_RADIUS = 22;

export interface LayoutResult {
  nodes: TrajectoryNode[];
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

export function layoutTrajectory(candidates: CandidateMetrics[]): LayoutResult {
  if (candidates.length === 0) {
    return { nodes: [], edges: [], width: 0, height: 0, winnerId: null, spineIds: new Set() };
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
    return { nodes: [], edges: [], width: 0, height: 0, winnerId: null, spineIds: new Set() };
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
    node.y = depth * NODE_GAP_Y + NODE_RADIUS + 12;
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

  const nodes = Array.from(byId.values());
  const xs = nodes.map((n) => n.x);
  const ys = nodes.map((n) => n.y);
  const width = Math.max(...xs) + NODE_GAP_X / 2 + NODE_RADIUS;
  const height = Math.max(...ys) + NODE_GAP_Y / 2 + NODE_RADIUS;

  return { nodes, edges, width, height, winnerId, spineIds };
}

export const TRAJECTORY_LAYOUT = {
  nodeRadius: NODE_RADIUS,
  gapX: NODE_GAP_X,
  gapY: NODE_GAP_Y,
} as const;
