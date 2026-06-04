// Wire shape for trajectory events. Matches CandidateEvent.to_metrics() and
// RejectedEvent.to_metrics() in backend/core/service_gateway/optimization/trajectory.py.

// The backend keys candidates by their GEPA list index (0-based). The UI
// shifts this by 1 so the seed reads as candidate 1 rather than candidate 0.
export function displayCandidateId(id: string): string {
  const n = Number(id);
  return Number.isFinite(n) ? String(n + 1) : id;
}

export interface PerExampleScore {
  id: string;
  score: number;
}

export interface CandidateMetrics {
  candidate_id: string;
  parent_id: string | null;
  parents_extra: string[];
  generation: number;
  score: number;
  per_example: PerExampleScore[];
  prompt: Record<string, string>;
  discovered_at_evals: number;
  iteration: number | null;
  timestamp: string;
}

export interface RejectedMetrics {
  rejection_id: string;
  iteration: number;
  parent_id: string;
  parent_score: number;
  proposal_score: number;
  subsample_size: number;
  proposal_prompt: Record<string, string>;
  parent_prompt: Record<string, string>;
  subsample_ids: string[];
  per_example_parent: PerExampleScore[];
  per_example_proposal: PerExampleScore[];
}

export interface ValsetRow {
  id: string;
  inputs: Record<string, string>;
  outputs: Record<string, string>;
}

// A candidate prediction is either a flat field→value map (current runs, where
// nested fields like the agent's history arrive as JSON strings — the same
// shape as ValsetRow.outputs, so each value renders structurally) or a plain
// string (legacy runs / non-Prediction metric returns).
export type PredictionValue = string | Record<string, string>;

export interface MinibatchEntry {
  example_id: string;
  score: number;
  feedback: string;
  prediction: PredictionValue;
  sequence: number;
  // GEPA iteration the reflective propose() was on when this feedback fired.
  // null when the event predates iteration plumbing or fires outside a
  // propose() call (baseline / full-valset evaluation).
  iteration: number | null;
}

export interface ValsetPrediction {
  example_id: string;
  prediction: PredictionValue;
  score: number;
}

export interface ValsetOutputsEvent {
  candidate_index: number;
  predictions: ValsetPrediction[];
}

export interface TrajectoryNode extends CandidateMetrics {
  children: TrajectoryNode[];
  x: number;
  y: number;
  subtreeWidth: number;
  isWinner: boolean;
  isSeed: boolean;
  isOnSpine: boolean;
}

export interface RejectedNode extends RejectedMetrics {
  x: number;
  y: number;
}
