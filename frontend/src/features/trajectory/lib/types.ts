// Wire shape for trajectory events. Matches CandidateEvent.to_metrics() and
// RejectedEvent.to_metrics() in backend/core/service_gateway/optimization/trajectory.py.

// The backend keys candidates by their GEPA list index (0-based). The UI
// shifts this by 1 so the seed reads as "מועמד 1" rather than "מועמד 0".
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

export interface MinibatchEntry {
  example_id: string;
  score: number;
  feedback: string;
  prediction: string;
  sequence: number;
}

export interface ValsetPrediction {
  example_id: string;
  prediction: string;
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
