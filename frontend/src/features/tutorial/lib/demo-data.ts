/**
 * Tutorial Demo Simulation
 *
 * Provides a fake optimization that progresses through all pipeline stages
 * over ~11 seconds, producing realistic MIPROv2 logs and scores.
 * Used when the tutorial navigates to /optimizations/tutorial-demo.
 */

import type { OptimizationStatusResponse, ProgressEvent, OptimizationLogEntry } from "@/shared/types/api";

export const DEMO_OPTIMIZATION_ID = "a7e3b291-4d2f-4f8c-b142-9d5e6f8a1c3b";

/* ── Helpers ── */

function ts(start: Date, offsetMs: number): string {
  return new Date(start.getTime() + offsetMs).toISOString();
}

function fmtElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return m > 0 ? `${m}:${String(s).padStart(2, "0")}` : `0:${String(s).padStart(2, "0")}`;
}

/* ── Trial data ── */

const TRIAL_SCORES = [65.0, 70.0, 68.0, 72.5, 75.0, 71.0, 80.0, 84.0];
const NUM_TRIALS = TRIAL_SCORES.length;

/* ── Phase builders ── */

function baseJob(start: Date): OptimizationStatusResponse {
  return {
    optimization_id: DEMO_OPTIMIZATION_ID,
    optimization_type: "run",
    status: "validating",
    name: "סיווג אימיילים",
    description: "אופטימיזציה לסיווג אימיילים לקטגוריות: spam, important, promotional",
    username: "demo",
    created_at: start.toISOString(),
    started_at: start.toISOString(),
    elapsed_seconds: 0,
    elapsed: "0:00",
    module_name: "Predict",
    module_kwargs: {},
    optimizer_name: "MIPROv2",
    optimizer_kwargs: { num_candidates: 8, max_bootstrapped_demos: 3 },
    compile_kwargs: { num_trials: NUM_TRIALS },
    model_name: "gpt-4o-mini",
    dataset_rows: 200,
    column_mapping: { inputs: { email_text: "str" }, outputs: { category: "str" } },
    split_fractions: { train: 0.6, val: 0.2, test: 0.2 },
    shuffle: true,
    seed: 42,
    progress_events: [],
    logs: [],
    latest_metrics: {},
    progress_count: 0,
    log_count: 0,
  };
}

function buildValidating(start: Date): OptimizationStatusResponse {
  const elapsed = (Date.now() - start.getTime()) / 1000;
  return {
    ...baseJob(start),
    status: "validating",
    elapsed_seconds: elapsed,
    elapsed: fmtElapsed(elapsed),
    logs: [
      {
        timestamp: ts(start, 200),
        level: "INFO",
        logger: "skynet.worker",
        message: "Starting optimization: סיווג אימיילים",
        pair_index: null,
      },
      {
        timestamp: ts(start, 400),
        level: "INFO",
        logger: "dspy.validators",
        message: "Validating signature and metric code...",
        pair_index: null,
      },
    ],
    log_count: 2,
  };
}

function buildSplitting(start: Date): OptimizationStatusResponse {
  const elapsed = (Date.now() - start.getTime()) / 1000;
  return {
    ...baseJob(start),
    status: "running",
    elapsed_seconds: elapsed,
    elapsed: fmtElapsed(elapsed),
    progress_events: [
      {
        timestamp: ts(start, 1500),
        event: "validation_passed",
        metrics: { message: "All checks passed" },
      },
    ],
    logs: [
      {
        timestamp: ts(start, 200),
        level: "INFO",
        logger: "skynet.worker",
        message: "Starting optimization: סיווג אימיילים",
        pair_index: null,
      },
      {
        timestamp: ts(start, 400),
        level: "INFO",
        logger: "dspy.validators",
        message: "Validating signature and metric code...",
        pair_index: null,
      },
      {
        timestamp: ts(start, 1500),
        level: "INFO",
        logger: "dspy.validators",
        message: "Validation passed ✓",
        pair_index: null,
      },
      {
        timestamp: ts(start, 1800),
        level: "INFO",
        logger: "dspy.datasets",
        message: "Splitting 200 examples into train/val/test...",
        pair_index: null,
      },
    ],
    progress_count: 1,
    log_count: 4,
  };
}

function buildBaseline(start: Date): OptimizationStatusResponse {
  const elapsed = (Date.now() - start.getTime()) / 1000;
  return {
    ...baseJob(start),
    status: "running",
    elapsed_seconds: elapsed,
    elapsed: fmtElapsed(elapsed),
    progress_events: [
      { timestamp: ts(start, 1500), event: "validation_passed", metrics: {} },
      {
        timestamp: ts(start, 2800),
        event: "dataset_splits_ready",
        metrics: { train_examples: 120, val_examples: 40, test_examples: 40 },
      },
    ],
    logs: [
      {
        timestamp: ts(start, 200),
        level: "INFO",
        logger: "skynet.worker",
        message: "Starting optimization: סיווג אימיילים",
        pair_index: null,
      },
      {
        timestamp: ts(start, 400),
        level: "INFO",
        logger: "dspy.validators",
        message: "Validating signature and metric code...",
        pair_index: null,
      },
      {
        timestamp: ts(start, 1500),
        level: "INFO",
        logger: "dspy.validators",
        message: "Validation passed ✓",
        pair_index: null,
      },
      {
        timestamp: ts(start, 1800),
        level: "INFO",
        logger: "dspy.datasets",
        message: "Splitting 200 examples into train/val/test...",
        pair_index: null,
      },
      {
        timestamp: ts(start, 2800),
        level: "INFO",
        logger: "dspy.datasets",
        message: "Dataset split: train=120, val=40, test=40",
        pair_index: null,
      },
      {
        timestamp: ts(start, 3000),
        level: "INFO",
        logger: "dspy.runners",
        message: "Evaluating default program on test set...",
        pair_index: null,
      },
    ],
    progress_count: 2,
    log_count: 6,
  };
}

function buildOptimizing(start: Date, trialsDone: number): OptimizationStatusResponse {
  const elapsed = (Date.now() - start.getTime()) / 1000;

  const events: ProgressEvent[] = [
    { timestamp: ts(start, 1500), event: "validation_passed", metrics: {} },
    {
      timestamp: ts(start, 2800),
      event: "dataset_splits_ready",
      metrics: { train_examples: 120, val_examples: 40, test_examples: 40 },
    },
    {
      timestamp: ts(start, 4200),
      event: "baseline_evaluated",
      metrics: { baseline_test_metric: 0.62 },
    },
  ];
  if (trialsDone > 0) {
    events.push({ timestamp: ts(start, 5000), event: "optimizer_progress", metrics: {} });
  }

  const logs: OptimizationLogEntry[] = [
    {
      timestamp: ts(start, 200),
      level: "INFO",
      logger: "skynet.worker",
      message: "Starting optimization: סיווג אימיילים",
      pair_index: null,
    },
    {
      timestamp: ts(start, 400),
      level: "INFO",
      logger: "dspy.validators",
      message: "Validating signature and metric code...",
      pair_index: null,
    },
    {
      timestamp: ts(start, 1500),
      level: "INFO",
      logger: "dspy.validators",
      message: "Validation passed ✓",
      pair_index: null,
    },
    {
      timestamp: ts(start, 1800),
      level: "INFO",
      logger: "dspy.datasets",
      message: "Splitting 200 examples into train/val/test...",
      pair_index: null,
    },
    {
      timestamp: ts(start, 2800),
      level: "INFO",
      logger: "dspy.datasets",
      message: "Dataset split: train=120, val=40, test=40",
      pair_index: null,
    },
    {
      timestamp: ts(start, 3000),
      level: "INFO",
      logger: "dspy.runners",
      message: "Evaluating default program on test set...",
      pair_index: null,
    },
    {
      timestamp: ts(start, 4200),
      level: "INFO",
      logger: "dspy.runners",
      message: "Default program score: 62.0",
      pair_index: null,
    },
    {
      timestamp: ts(start, 4500),
      level: "INFO",
      logger: "dspy.optimizers.miprov2",
      message: `Starting MIPROv2 optimization with ${NUM_TRIALS} trials...`,
      pair_index: null,
    },
  ];

  for (let i = 0; i < trialsDone; i++) {
    const offset = 5000 + i * 550;
    logs.push(
      {
        timestamp: ts(start, offset),
        level: "INFO",
        logger: "dspy.optimizers.miprov2",
        message: `===== Trial ${i + 1} / ${NUM_TRIALS} =====`,
        pair_index: null,
      },
      {
        timestamp: ts(start, offset + 300),
        level: "INFO",
        logger: "dspy.optimizers.miprov2",
        message: `Score: ${(TRIAL_SCORES[i] ?? 0).toFixed(1)} with parameters {num_demos=${Math.min(i + 1, 3)}}`,
        pair_index: null,
      },
    );
  }

  return {
    ...baseJob(start),
    status: "running",
    elapsed_seconds: elapsed,
    elapsed: fmtElapsed(elapsed),
    baseline_test_metric: 0.62,
    progress_events: events,
    logs,
    latest_metrics: {
      tqdm_desc: "MIPROv2",
      tqdm_percent: (trialsDone / NUM_TRIALS) * 100,
      tqdm_n: trialsDone,
      tqdm_total: NUM_TRIALS,
    },
    progress_count: events.length,
    log_count: logs.length,
  };
}

function buildDone(start: Date): OptimizationStatusResponse {
  const elapsed = (Date.now() - start.getTime()) / 1000;

  const events: ProgressEvent[] = [
    { timestamp: ts(start, 1500), event: "validation_passed", metrics: {} },
    {
      timestamp: ts(start, 2800),
      event: "dataset_splits_ready",
      metrics: { train_examples: 120, val_examples: 40, test_examples: 40 },
    },
    {
      timestamp: ts(start, 4200),
      event: "baseline_evaluated",
      metrics: { baseline_test_metric: 0.62 },
    },
    { timestamp: ts(start, 5000), event: "optimizer_progress", metrics: {} },
    {
      timestamp: ts(start, 9500),
      event: "optimized_evaluated",
      metrics: { optimized_test_metric: 0.84 },
    },
  ];

  const logs: OptimizationLogEntry[] = [
    {
      timestamp: ts(start, 200),
      level: "INFO",
      logger: "skynet.worker",
      message: "Starting optimization: סיווג אימיילים",
      pair_index: null,
    },
    {
      timestamp: ts(start, 400),
      level: "INFO",
      logger: "dspy.validators",
      message: "Validating signature and metric code...",
      pair_index: null,
    },
    {
      timestamp: ts(start, 1500),
      level: "INFO",
      logger: "dspy.validators",
      message: "Validation passed ✓",
      pair_index: null,
    },
    {
      timestamp: ts(start, 1800),
      level: "INFO",
      logger: "dspy.datasets",
      message: "Splitting 200 examples into train/val/test...",
      pair_index: null,
    },
    {
      timestamp: ts(start, 2800),
      level: "INFO",
      logger: "dspy.datasets",
      message: "Dataset split: train=120, val=40, test=40",
      pair_index: null,
    },
    {
      timestamp: ts(start, 3000),
      level: "INFO",
      logger: "dspy.runners",
      message: "Evaluating default program on test set...",
      pair_index: null,
    },
    {
      timestamp: ts(start, 4200),
      level: "INFO",
      logger: "dspy.runners",
      message: "Default program score: 62.0",
      pair_index: null,
    },
    {
      timestamp: ts(start, 4500),
      level: "INFO",
      logger: "dspy.optimizers.miprov2",
      message: `Starting MIPROv2 optimization with ${NUM_TRIALS} trials...`,
      pair_index: null,
    },
  ];

  for (let i = 0; i < NUM_TRIALS; i++) {
    const offset = 5000 + i * 550;
    logs.push(
      {
        timestamp: ts(start, offset),
        level: "INFO",
        logger: "dspy.optimizers.miprov2",
        message: `===== Trial ${i + 1} / ${NUM_TRIALS} =====`,
        pair_index: null,
      },
      {
        timestamp: ts(start, offset + 300),
        level: "INFO",
        logger: "dspy.optimizers.miprov2",
        message: `Score: ${(TRIAL_SCORES[i] ?? 0).toFixed(1)} with parameters {num_demos=${Math.min(i + 1, 3)}}`,
        pair_index: null,
      },
    );
  }

  logs.push(
    {
      timestamp: ts(start, 9200),
      level: "INFO",
      logger: "dspy.optimizers.miprov2",
      message: "Best program found with score: 84.0",
      pair_index: null,
    },
    {
      timestamp: ts(start, 9500),
      level: "INFO",
      logger: "dspy.runners",
      message: "Evaluating optimized program on test set...",
      pair_index: null,
    },
    {
      timestamp: ts(start, 10200),
      level: "INFO",
      logger: "dspy.runners",
      message: "Optimized program score: 84.0",
      pair_index: null,
    },
    {
      timestamp: ts(start, 10500),
      level: "INFO",
      logger: "skynet.worker",
      message: "Optimization complete ✓",
      pair_index: null,
    },
  );

  return {
    ...baseJob(start),
    status: "success",
    elapsed_seconds: elapsed,
    elapsed: fmtElapsed(elapsed),
    completed_at: new Date().toISOString(),
    baseline_test_metric: 0.62,
    optimized_test_metric: 0.84,
    metric_improvement: 0.22,
    progress_events: events,
    logs,
    latest_metrics: {
      tqdm_desc: "Completed",
      tqdm_percent: 100,
      tqdm_n: NUM_TRIALS,
      tqdm_total: NUM_TRIALS,
    },
    progress_count: events.length,
    log_count: logs.length,
    result: {
      module_name: "Predict",
      optimizer_name: "MIPROv2",
      baseline_test_metric: 0.62,
      optimized_test_metric: 0.84,
      metric_improvement: 0.22,
      runtime_seconds: elapsed,
      num_lm_calls: 156,
      split_counts: { train: 120, val: 40, test: 40 },
    },
  };
}

/* ═══════════════════════════════════════════════════════════
   Public API — schedule demo simulation
   ═══════════════════════════════════════════════════════════ */

export interface DemoCallbacks {
  setJob: (
    updater: (prev: OptimizationStatusResponse | null) => OptimizationStatusResponse,
  ) => void;
  setLoading: (v: boolean) => void;
}

/**
 * Starts a simulated optimization that progresses through all pipeline stages.
 * Returns a cleanup function that cancels all pending timers.
 *
 * Timeline:
 *   0.4s  — validating
 *   2.0s  — splitting
 *   3.5s  — baseline evaluation
 *   5.0s+ — optimizing (trials appear every ~550ms)
 *  10.5s  — done (success)
 */
/** Cached completed state — once the simulation finishes, revisits skip straight to done. */
let _cachedDoneState: OptimizationStatusResponse | null = null;

/** Reset the cached state so the next visit re-runs the simulation. */
export function resetDemoSimulation() {
  _cachedDoneState = null;
}

export function startDemoSimulation(callbacks: DemoCallbacks): () => void {
  const { setJob, setLoading } = callbacks;

  // If simulation already completed, show final state immediately
  if (_cachedDoneState) {
    setLoading(false);
    setJob(() => _cachedDoneState!);
    return () => {};
  }

  const start = new Date();
  const timers: ReturnType<typeof setTimeout>[] = [];

  const set = (job: OptimizationStatusResponse) => setJob(() => job);

  timers.push(
    setTimeout(() => {
      setLoading(false);
      set(buildValidating(start));
    }, 400),
  );

  timers.push(setTimeout(() => set(buildSplitting(start)), 2000));

  timers.push(setTimeout(() => set(buildBaseline(start)), 3500));

  // Phase 4: Optimizing — trials appear one by one
  for (let i = 0; i < NUM_TRIALS; i++) {
    timers.push(setTimeout(() => set(buildOptimizing(start, i + 1)), 5000 + i * 550));
  }

  // Phase 5: Done — cache the final state
  timers.push(
    setTimeout(() => {
      const done = buildDone(start);
      _cachedDoneState = done;
      set(done);
    }, 10500),
  );

  return () => timers.forEach(clearTimeout);
}
