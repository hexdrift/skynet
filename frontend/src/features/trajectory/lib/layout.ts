import type { CandidateMetrics, RejectedMetrics, RejectedNode, TrajectoryNode } from "./types";

const NODE_GAP_X = 96;
const NODE_GAP_Y = 132;
const NODE_RADIUS = 30;
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

type Slot = { kind: "node"; node: TrajectoryNode } | { kind: "ghost"; ghost: RejectedNode };

function slotIteration(slot: Slot): number {
  return slot.kind === "node" ? (slot.node.iteration ?? -Infinity) : slot.ghost.iteration;
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

  // Rejected proposals are leaf children of the version they tried to
  // improve: each takes its own slot one row down, so the tree reads the
  // same with or without them and the caller relayouts to close the gaps.
  const ghosts: RejectedNode[] = [];
  const slotsByParent = new Map<string, Slot[]>();
  for (const node of byId.values()) {
    slotsByParent.set(
      node.candidate_id,
      node.children.map((child) => ({ kind: "node", node: child })),
    );
  }
  for (const rej of rejected) {
    const slots = slotsByParent.get(rej.parent_id);
    if (slots === undefined) continue;
    const ghost: RejectedNode = { ...rej, x: 0, y: 0 };
    ghosts.push(ghost);
    slots.push({ kind: "ghost", ghost });
  }
  // Interleave kept and rejected children in the order the optimizer tried
  // them; the stable sort keeps id order for candidates without an iteration.
  for (const slots of slotsByParent.values()) {
    slots.sort((a, b) => {
      const ia = slotIteration(a);
      const ib = slotIteration(b);
      return ia === ib ? 0 : ia < ib ? -1 : 1;
    });
  }

  const computeWidth = (node: TrajectoryNode): number => {
    let total = 0;
    for (const slot of slotsByParent.get(node.candidate_id) ?? []) {
      total += slot.kind === "node" ? computeWidth(slot.node) : 1;
    }
    node.subtreeWidth = Math.max(1, total);
    return node.subtreeWidth;
  };
  computeWidth(root);

  const place = (node: TrajectoryNode, leftSlot: number, depth: number): void => {
    node.y = depth * NODE_GAP_Y + TOP_PAD;
    const slots = slotsByParent.get(node.candidate_id) ?? [];
    if (slots.length === 0) {
      node.x = leftSlot * NODE_GAP_X + NODE_GAP_X / 2;
      return;
    }
    let cursor = leftSlot;
    const xs: number[] = [];
    for (const slot of slots) {
      if (slot.kind === "node") {
        place(slot.node, cursor, depth + 1);
        cursor += slot.node.subtreeWidth;
        xs.push(slot.node.x);
      } else {
        slot.ghost.x = cursor * NODE_GAP_X + NODE_GAP_X / 2;
        slot.ghost.y = (depth + 1) * NODE_GAP_Y + TOP_PAD;
        cursor += 1;
        xs.push(slot.ghost.x);
      }
    }
    const first = xs[0];
    const last = xs[xs.length - 1];
    if (first !== undefined && last !== undefined) node.x = (first + last) / 2;
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
  const xs = [...nodes.map((n) => n.x), ...ghosts.map((g) => g.x)];
  const ys = [...nodes.map((n) => n.y), ...ghosts.map((g) => g.y)];
  const width = Math.max(...xs) + NODE_GAP_X / 2 + NODE_RADIUS;
  const height = Math.max(...ys) + NODE_GAP_Y / 2 + NODE_RADIUS;

  return { nodes, ghosts, edges, width, height, winnerId, spineIds };
}

// The rejected-proposals toggle morphs between the full layout and this one:
// the kept tree closes its gaps while every ghost retracts into its parent.
export function collapseGhosts(full: LayoutResult, withoutRejected: LayoutResult): LayoutResult {
  const byId = new Map(withoutRejected.nodes.map((n) => [n.candidate_id, n]));
  const ghosts = full.ghosts.map((ghost) => {
    const parent = byId.get(ghost.parent_id);
    return parent === undefined ? ghost : { ...ghost, x: parent.x, y: parent.y };
  });
  return { ...withoutRejected, ghosts };
}

// Positions and bounds at `t` of the way from `from` to `to`; structure comes
// from `to`. Anything `from` lacks starts at its final place.
export function interpolateLayout(from: LayoutResult, to: LayoutResult, t: number): LayoutResult {
  const lerp = (a: number, b: number) => a + (b - a) * t;
  const fromNodes = new Map(from.nodes.map((n) => [n.candidate_id, n]));
  const fromGhosts = new Map(from.ghosts.map((g) => [g.rejection_id, g]));
  const nodes = to.nodes.map((node) => {
    const start = fromNodes.get(node.candidate_id) ?? node;
    return { ...node, x: lerp(start.x, node.x), y: lerp(start.y, node.y) };
  });
  const ghosts = to.ghosts.map((ghost) => {
    const start = fromGhosts.get(ghost.rejection_id) ?? ghost;
    return { ...ghost, x: lerp(start.x, ghost.x), y: lerp(start.y, ghost.y) };
  });
  return {
    ...to,
    nodes,
    ghosts,
    width: lerp(from.width, to.width),
    height: lerp(from.height, to.height),
  };
}

export const TRAJECTORY_LAYOUT = {
  nodeRadius: NODE_RADIUS,
  gapX: NODE_GAP_X,
  gapY: NODE_GAP_Y,
} as const;
