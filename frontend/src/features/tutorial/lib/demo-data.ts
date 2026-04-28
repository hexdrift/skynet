/**
 * Tutorial Demo Simulation
 *
 * Provides a fake optimization that progresses through all pipeline stages
 * over ~11 seconds, producing realistic GEPA logs and scores.
 * Used when the tutorial navigates to /optimizations/tutorial-demo.
 */

import type {
  OptimizationStatusResponse,
  ProgressEvent,
  OptimizationLogEntry,
  PairResult,
  GridSearchResult,
  EvalExampleResult,
  OptimizationDatasetResponse,
  DatasetRow,
} from "@/shared/types/api";
import { TERMS } from "@/shared/lib/terms";
import { formatMsg, msg } from "@/shared/lib/messages";

export const DEMO_OPTIMIZATION_ID = "a7e3b291-4d2f-4f8c-b142-9d5e6f8a1c3b";
export const DEMO_GRID_OPTIMIZATION_ID = "c3f9d215-8a47-4e6b-a1d3-7b2f9c58e4a1";

function ts(start: Date, offsetMs: number): string {
  return new Date(start.getTime() + offsetMs).toISOString();
}

function fmtElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return m > 0 ? `${m}:${String(s).padStart(2, "0")}` : `0:${String(s).padStart(2, "0")}`;
}

const TRIAL_SCORES = [65.0, 70.0, 68.0, 72.5, 75.0, 71.0, 80.0, 84.0];
const NUM_TRIALS = TRIAL_SCORES.length;

function baseJob(start: Date): OptimizationStatusResponse {
  return {
    optimization_id: DEMO_OPTIMIZATION_ID,
    optimization_type: "run",
    status: "validating",
    name: msg("auto.features.tutorial.lib.demo.data.literal.1"),
    description: formatMsg("auto.features.tutorial.lib.demo.data.template.1", {
      p1: TERMS.optimization,
    }),
    username: "demo",
    created_at: start.toISOString(),
    started_at: start.toISOString(),
    elapsed_seconds: 0,
    elapsed: "0:00",
    module_name: "Predict",
    module_kwargs: {},
    optimizer_name: "GEPA",
    optimizer_kwargs: { auto: "light", reflection_minibatch_size: 3 },
    compile_kwargs: {},
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
        message: msg("auto.features.tutorial.lib.demo.data.literal.2"),
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
        message: msg("auto.features.tutorial.lib.demo.data.literal.3"),
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
        message: msg("auto.features.tutorial.lib.demo.data.literal.4"),
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
      message: msg("auto.features.tutorial.lib.demo.data.literal.5"),
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
      logger: "dspy.gepa",
      message: `Starting GEPA reflection over ${NUM_TRIALS} iterations...`,
      pair_index: null,
    },
  ];

  for (let i = 0; i < trialsDone; i++) {
    const offset = 5000 + i * 550;
    logs.push(
      {
        timestamp: ts(start, offset),
        level: "INFO",
        logger: "dspy.gepa",
        message: `Iteration ${i + 1}: Reflecting on minibatch (size=3)...`,
        pair_index: null,
      },
      {
        timestamp: ts(start, offset + 300),
        level: "INFO",
        logger: "dspy.gepa",
        message: `Iteration ${i + 1}: Full valset score for new program: ${((TRIAL_SCORES[i] ?? 0) / 100).toFixed(2)}`,
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
      tqdm_desc: "GEPA",
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
      message: msg("auto.features.tutorial.lib.demo.data.literal.6"),
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
      logger: "dspy.gepa",
      message: `Starting GEPA reflection over ${NUM_TRIALS} iterations...`,
      pair_index: null,
    },
  ];

  for (let i = 0; i < NUM_TRIALS; i++) {
    const offset = 5000 + i * 550;
    logs.push(
      {
        timestamp: ts(start, offset),
        level: "INFO",
        logger: "dspy.gepa",
        message: `Iteration ${i + 1}: Reflecting on minibatch (size=3)...`,
        pair_index: null,
      },
      {
        timestamp: ts(start, offset + 300),
        level: "INFO",
        logger: "dspy.gepa",
        message: `Iteration ${i + 1}: Full valset score for new program: ${((TRIAL_SCORES[i] ?? 0) / 100).toFixed(2)}`,
        pair_index: null,
      },
    );
  }

  logs.push(
    {
      timestamp: ts(start, 9200),
      level: "INFO",
      logger: "dspy.gepa",
      message: "Best program found with score: 0.84",
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
      optimizer_name: "GEPA",
      baseline_test_metric: 0.62,
      optimized_test_metric: 0.84,
      metric_improvement: 0.22,
      runtime_seconds: elapsed,
      num_lm_calls: 156,
      split_counts: { train: 120, val: 40, test: 40 },
    },
  };
}

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
 *   0.2s  — validating
 *   1.0s  — splitting
 *   1.75s — baseline evaluation
 *   2.5s+ — optimizing (trials appear every ~275ms)
 *   5.25s — done (success)
 */
/** Cached completed state — once the simulation finishes, revisits skip straight to done. */
let _cachedDoneState: OptimizationStatusResponse | null = null;

/** Reset the cached state so the next visit re-runs the simulation. */
export function resetDemoSimulation() {
  _cachedDoneState = null;
}

export function startDemoSimulation(callbacks: DemoCallbacks): () => void {
  const { setJob, setLoading } = callbacks;

  if (_cachedDoneState) {
    setLoading(false);
    setJob(() => _cachedDoneState!);
    return () => {};
  }

  const start = new Date();
  const timers: Array<ReturnType<typeof setTimeout>> = [];

  const set = (job: OptimizationStatusResponse) => setJob(() => job);

  timers.push(
    setTimeout(() => {
      setLoading(false);
      set(buildValidating(start));
    }, 200),
  );

  timers.push(setTimeout(() => set(buildSplitting(start)), 1000));

  timers.push(setTimeout(() => set(buildBaseline(start)), 1750));

  for (let i = 0; i < NUM_TRIALS; i++) {
    timers.push(setTimeout(() => set(buildOptimizing(start, i + 1)), 2500 + i * 275));
  }

  timers.push(
    setTimeout(() => {
      const done = buildDone(start);
      _cachedDoneState = done;
      set(done);
    }, 5250),
  );

  return () => timers.forEach(clearTimeout);
}

import type { PaginatedJobsResponse, OptimizationSummaryResponse } from "@/shared/types/api";
import type { DashboardAnalytics, DashboardAnalyticsJob } from "@/shared/lib/api";

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString();
}

const DEMO_JOBS: OptimizationSummaryResponse[] = [
  {
    optimization_id: "demo-001",
    optimization_type: "run",
    status: "success",
    name: msg("auto.features.tutorial.lib.demo.data.literal.7"),
    description: msg("auto.features.tutorial.lib.demo.data.literal.8"),
    created_at: daysAgo(5),
    completed_at: daysAgo(5),
    elapsed: "2:45",
    elapsed_seconds: 165,
    module_name: "ChainOfThought",
    optimizer_name: "GEPA",
    model_name: "gpt-4o-mini",
    dataset_rows: 200,
    baseline_test_metric: 0.62,
    optimized_test_metric: 0.84,
    metric_improvement: 0.22,
    username: "demo",
  },
  {
    optimization_id: "demo-002",
    optimization_type: "run",
    status: "success",
    name: msg("auto.features.tutorial.lib.demo.data.literal.9"),
    description: msg("auto.features.tutorial.lib.demo.data.literal.10"),
    created_at: daysAgo(3),
    completed_at: daysAgo(3),
    elapsed: "4:12",
    elapsed_seconds: 252,
    module_name: "Predict",
    optimizer_name: "GEPA",
    model_name: "gpt-4o",
    dataset_rows: 350,
    baseline_test_metric: 0.71,
    optimized_test_metric: 0.89,
    metric_improvement: 0.18,
    username: "demo",
  },
  {
    optimization_id: DEMO_GRID_OPTIMIZATION_ID,
    optimization_type: "grid_search",
    status: "success",
    name: msg("auto.features.tutorial.lib.demo.data.literal.11"),
    description: formatMsg("auto.features.tutorial.lib.demo.data.template.2", {
      p1: TERMS.modelPlural,
      p2: TERMS.pairPlural,
      p3: TERMS.generationModel,
      p4: TERMS.reflectionModel,
      p5: TERMS.task,
    }),
    created_at: daysAgo(2),
    completed_at: daysAgo(2),
    elapsed: "8:30",
    elapsed_seconds: 510,
    module_name: "ChainOfThought",
    optimizer_name: "GEPA",
    model_name: "gpt-4o-mini",
    dataset_rows: 150,
    baseline_test_metric: 0.55,
    optimized_test_metric: 0.82,
    metric_improvement: 0.27,
    username: "demo",
    total_pairs: 4,
    completed_pairs: 4,
  },
  {
    optimization_id: "demo-004",
    optimization_type: "run",
    status: "failed",
    name: msg("auto.features.tutorial.lib.demo.data.literal.12"),
    description: msg("auto.features.tutorial.lib.demo.data.literal.13"),
    created_at: daysAgo(1),
    elapsed: "0:32",
    elapsed_seconds: 32,
    module_name: "Predict",
    optimizer_name: "GEPA",
    model_name: "gpt-4o",
    dataset_rows: 80,
    username: "demo",
    message: "Metric function raised an exception",
  },
  {
    optimization_id: "demo-005",
    optimization_type: "run",
    status: "running",
    name: msg("auto.features.tutorial.lib.demo.data.literal.14"),
    description: msg("auto.features.tutorial.lib.demo.data.literal.15"),
    created_at: daysAgo(0),
    elapsed: "1:15",
    elapsed_seconds: 75,
    module_name: "ChainOfThought",
    optimizer_name: "GEPA",
    model_name: "gpt-4o-mini",
    dataset_rows: 120,
    baseline_test_metric: 0.48,
    username: "demo",
    latest_metrics: { tqdm_percent: 45, tqdm_n: 4, tqdm_total: 9 },
  },
];

function toAnalyticsJob(j: OptimizationSummaryResponse): DashboardAnalyticsJob {
  return {
    optimization_id: j.optimization_id,
    name: j.name,
    optimizer_name: j.optimizer_name,
    model_name: j.model_name,
    status: j.status,
    baseline_test_metric: j.baseline_test_metric ?? null,
    optimized_test_metric: j.optimized_test_metric ?? null,
    metric_improvement: j.metric_improvement ?? null,
    elapsed_seconds: j.elapsed_seconds ?? null,
    dataset_rows: j.dataset_rows ?? null,
    optimization_type: j.optimization_type,
    created_at: j.created_at,
  };
}

export const DEMO_DASHBOARD_JOBS: PaginatedJobsResponse = {
  items: DEMO_JOBS,
  total: DEMO_JOBS.length,
  limit: 20,
  offset: 0,
};

export const DEMO_DASHBOARD_ANALYTICS: DashboardAnalytics = {
  filtered_total: DEMO_JOBS.length,
  status_counts: { success: 3, failed: 1, running: 1 },
  optimizer_counts: { GEPA: 5 },
  job_type_counts: { run: 4, grid_search: 1 },
  model_usage: [
    { name: "gpt-4o-mini", value: 3 },
    { name: "gpt-4o", value: 2 },
  ],
  success_count: 3,
  failed_count: 1,
  running_count: 1,
  terminal_count: 4,
  success_rate: 75,
  avg_improvement: 0.21,
  avg_runtime_seconds: 309,
  total_dataset_rows: 900,
  total_pairs_run: 4,
  grid_search_count: 1,
  single_run_count: 4,
  best_improvement: 0.23,
  improvement_by_optimizer: [{ name: "GEPA", average: 0.21, count: 3 }],
  runtime_minutes_by_optimizer: [{ name: "GEPA", average: 3.71, count: 5 }],
  top_improvement: DEMO_JOBS.filter((j) => j.metric_improvement).map(toAnalyticsJob),
  runtime_distribution: DEMO_JOBS.filter((j) => j.elapsed_seconds).map(toAnalyticsJob),
  dataset_vs_improvement: DEMO_JOBS.filter((j) => j.metric_improvement).map(toAnalyticsJob),
  efficiency: DEMO_JOBS.filter((j) => j.metric_improvement).map(toAnalyticsJob),
  top_jobs_by_improvement: DEMO_JOBS.filter((j) => j.metric_improvement)
    .sort((a, b) => (b.metric_improvement ?? 0) - (a.metric_improvement ?? 0))
    .map(toAnalyticsJob),
  timeline: [
    { date: daysAgo(5).slice(0, 10), count: 1 },
    { date: daysAgo(3).slice(0, 10), count: 1 },
    { date: daysAgo(2).slice(0, 10), count: 1 },
    { date: daysAgo(1).slice(0, 10), count: 1 },
    { date: daysAgo(0).slice(0, 10), count: 1 },
  ],
  available_optimizers: ["GEPA"],
  available_models: ["gpt-4o-mini", "gpt-4o"],
};

/**
 * Demo compare data — three completed runs on the same task. IDs are
 * well-known so the /compare page can recognize and render them
 * without a backend fetch.
 */
export const DEMO_COMPARE_IDS = ["tutorial-compare-a", "tutorial-compare-b", "tutorial-compare-c"];

const COMPARE_TASK_NAME = msg("auto.features.tutorial.lib.demo.data.literal.16");
const COMPARE_FINGERPRINT = "tutorial-fingerprint-email-classifier";

function compareInstructions(variant: "a" | "b" | "c"): string {
  if (variant === "a") {
    return `Classify the email into exactly one category: spam, important, or promotional.

Use these signals:
- Promotional language ("free", "% off", "limited time") → promotional
- Personal or work content (meetings, reports, requests) → important
- Unsolicited offers with suspicious sender behavior → spam

Respond with only the category label, lowercase, no punctuation.`;
  }
  if (variant === "b") {
    return `Read the email_text and decide whether it is spam, important, or promotional.
Return the single best-fit category.`;
  }
  return `Given email_text, output category as one of {spam, important, promotional}.
Think step-by-step about the intent of the message before answering.`;
}

function compareDemos(variant: "a" | "b" | "c") {
  const shared = [
    {
      inputs: { email_text: "Your quarterly report is ready for review" },
      outputs: { category: "important" },
    },
    {
      inputs: { email_text: "50% off all items this weekend only" },
      outputs: { category: "promotional" },
    },
  ];
  if (variant === "a") {
    return [
      ...shared,
      {
        inputs: { email_text: "Click here to win $1000 now!" },
        outputs: { category: "spam" },
      },
    ];
  }
  if (variant === "b") {
    return shared;
  }
  return [
    shared[0]!,
    {
      inputs: { email_text: "Meeting moved to 3pm tomorrow" },
      outputs: { category: "important" },
    },
  ];
}

function buildCompareJob(opts: {
  id: string;
  name: string;
  description: string;
  modelName: string;
  moduleName: string;
  baseline: number;
  optimized: number;
  runtimeSeconds: number;
  numLmCalls: number;
  variant: "a" | "b" | "c";
}): OptimizationStatusResponse {
  const elapsed = opts.runtimeSeconds;
  const improvement = opts.optimized - opts.baseline;
  const prompt = {
    predictor_name: "EmailClassifier",
    signature_name: "EmailClassifier",
    instructions: compareInstructions(opts.variant),
    input_fields: ["email_text"],
    output_fields: ["category"],
    demos: compareDemos(opts.variant),
    formatted_prompt: "",
  };
  return {
    optimization_id: opts.id,
    optimization_type: "run",
    status: "success",
    name: opts.name,
    description: opts.description,
    username: "demo",
    created_at: daysAgo(4),
    started_at: daysAgo(4),
    completed_at: daysAgo(4),
    elapsed_seconds: elapsed,
    elapsed: fmtElapsed(elapsed),
    module_name: opts.moduleName,
    module_kwargs: {},
    optimizer_name: "GEPA",
    optimizer_kwargs: { auto: "light" },
    compile_kwargs: {},
    model_name: opts.modelName,
    dataset_rows: 200,
    column_mapping: { inputs: { email_text: "str" }, outputs: { category: "str" } },
    split_fractions: { train: 0.6, val: 0.2, test: 0.2 },
    shuffle: true,
    seed: 42,
    baseline_test_metric: opts.baseline,
    optimized_test_metric: opts.optimized,
    metric_improvement: improvement,
    task_fingerprint: COMPARE_FINGERPRINT,
    progress_events: [],
    logs: [],
    latest_metrics: {},
    progress_count: 0,
    log_count: 0,
    result: {
      module_name: opts.moduleName,
      optimizer_name: "GEPA",
      baseline_test_metric: opts.baseline,
      optimized_test_metric: opts.optimized,
      metric_improvement: improvement,
      runtime_seconds: elapsed,
      num_lm_calls: opts.numLmCalls,
      split_counts: { train: 120, val: 40, test: 40 },
      program_artifact: { optimized_prompt: prompt },
    },
  };
}

const GRID_TASK_NAME = msg("auto.features.tutorial.lib.demo.data.literal.17");

function gridInstructions(variant: 0 | 1 | 2 | 3): string {
  if (variant === 0) {
    return "Summarize the article in one concise sentence that captures the main point.";
  }
  if (variant === 1) {
    return "Read the article and produce a one-sentence summary that highlights the most important fact or event.";
  }
  if (variant === 2) {
    return "Given an article, write a single-sentence summary. Focus on the core message, omit stylistic filler.";
  }
  return "Summarize the article into one sentence. Prioritize specific entities, numbers, and outcomes over generic framing.";
}

function gridPair(
  idx: 0 | 1 | 2 | 3,
  opts: {
    genModel: string;
    refModel: string;
    baseline: number;
    optimized: number;
    runtime: number;
    numLmCalls: number;
    avgMs: number;
  },
): PairResult {
  return {
    pair_index: idx,
    generation_model: opts.genModel,
    reflection_model: opts.refModel,
    baseline_test_metric: opts.baseline,
    optimized_test_metric: opts.optimized,
    metric_improvement: opts.optimized - opts.baseline,
    runtime_seconds: opts.runtime,
    num_lm_calls: opts.numLmCalls,
    avg_response_time_ms: opts.avgMs,
    program_artifact: {
      optimized_prompt: {
        predictor_name: "ArticleSummarizer",
        signature_name: "ArticleSummarizer",
        instructions: gridInstructions(idx),
        input_fields: ["article"],
        output_fields: ["summary"],
        demos: [
          {
            inputs: {
              article:
                "A local library announced extended weekend hours starting in May to accommodate student demand.",
            },
            outputs: {
              summary: "A local library will extend weekend hours in May to meet student demand.",
            },
          },
        ],
        formatted_prompt: "",
      },
    },
  };
}

const GRID_PAIR_TRIAL_SCORES: Record<0 | 1 | 2 | 3, number[]> = {
  0: [0.52, 0.58, 0.61, 0.66, 0.68, 0.72, 0.74],
  1: [0.55, 0.61, 0.68, 0.73, 0.76, 0.8, 0.82],
  2: [0.53, 0.59, 0.64, 0.68, 0.72, 0.75, 0.77],
  3: [0.57, 0.64, 0.71, 0.77, 0.81, 0.84, 0.86],
};

function buildGridPairLogs(
  pairIdx: 0 | 1 | 2 | 3,
  start: Date,
  baseOffsetMs: number,
): OptimizationLogEntry[] {
  const scores = GRID_PAIR_TRIAL_SCORES[pairIdx];
  const logs: OptimizationLogEntry[] = [
    {
      timestamp: ts(start, baseOffsetMs),
      level: "INFO",
      logger: "dspy.gepa",
      message: `Starting GEPA reflection over ${scores.length} iterations...`,
      pair_index: pairIdx,
    },
  ];
  scores.forEach((score, i) => {
    const offset = baseOffsetMs + 400 + i * 550;
    logs.push(
      {
        timestamp: ts(start, offset),
        level: "INFO",
        logger: "dspy.gepa",
        message: `Iteration ${i + 1}: Reflecting on minibatch (size=3)...`,
        pair_index: pairIdx,
      },
      {
        timestamp: ts(start, offset + 300),
        level: "INFO",
        logger: "dspy.gepa",
        message: `Iteration ${i + 1}: Full valset score for new program: ${score.toFixed(2)}`,
        pair_index: pairIdx,
      },
    );
  });
  const finalScore = scores[scores.length - 1]!;
  logs.push({
    timestamp: ts(start, baseOffsetMs + 400 + scores.length * 550 + 600),
    level: "INFO",
    logger: "dspy.gepa",
    message: `Best program found with score: ${finalScore.toFixed(2)}`,
    pair_index: pairIdx,
  });
  return logs;
}

export function buildGridDemoJob(): OptimizationStatusResponse {
  const pairs: PairResult[] = [
    gridPair(0, {
      genModel: "openai/gpt-4o-mini",
      refModel: "openai/gpt-4o-mini",
      baseline: 0.48,
      optimized: 0.74,
      runtime: 180,
      numLmCalls: 82,
      avgMs: 260,
    }),
    gridPair(1, {
      genModel: "openai/gpt-4o-mini",
      refModel: "openai/gpt-4o",
      baseline: 0.48,
      optimized: 0.82,
      runtime: 245,
      numLmCalls: 96,
      avgMs: 320,
    }),
    gridPair(2, {
      genModel: "openai/gpt-4o",
      refModel: "openai/gpt-4o-mini",
      baseline: 0.48,
      optimized: 0.77,
      runtime: 230,
      numLmCalls: 94,
      avgMs: 420,
    }),
    gridPair(3, {
      genModel: "openai/gpt-4o",
      refModel: "openai/gpt-4o",
      baseline: 0.48,
      optimized: 0.86,
      runtime: 380,
      numLmCalls: 118,
      avgMs: 650,
    }),
  ];

  const best = pairs[0]!;
  const grid: GridSearchResult = {
    module_name: "ChainOfThought",
    optimizer_name: "GEPA",
    split_counts: { train: 90, val: 30, test: 30 },
    total_pairs: pairs.length,
    completed_pairs: pairs.length,
    failed_pairs: 0,
    pair_results: pairs,
    best_pair: best,
    runtime_seconds: pairs.reduce((sum, p) => sum + (p.runtime_seconds ?? 0), 0),
  };

  const logStart = new Date();
  const pairLogs = ([0, 1, 2, 3] as const).flatMap((idx) =>
    buildGridPairLogs(idx, logStart, idx * 8000),
  );

  return {
    optimization_id: DEMO_GRID_OPTIMIZATION_ID,
    optimization_type: "grid_search",
    status: "success",
    name: GRID_TASK_NAME,
    description: formatMsg("auto.features.tutorial.lib.demo.data.template.3", {
      p1: TERMS.modelPlural,
      p2: TERMS.pairPlural,
      p3: TERMS.generationModel,
      p4: TERMS.reflectionModel,
      p5: TERMS.task,
    }),
    username: "demo",
    created_at: daysAgo(2),
    started_at: daysAgo(2),
    completed_at: daysAgo(2),
    elapsed_seconds: grid.runtime_seconds,
    elapsed: fmtElapsed(grid.runtime_seconds ?? 0),
    module_name: "ChainOfThought",
    module_kwargs: {},
    optimizer_name: "GEPA",
    optimizer_kwargs: { auto: "light" },
    compile_kwargs: {},
    model_name: "openai/gpt-4o-mini",
    dataset_rows: 150,
    column_mapping: { inputs: { article: "str" }, outputs: { summary: "str" } },
    split_fractions: { train: 0.6, val: 0.2, test: 0.2 },
    shuffle: true,
    seed: 42,
    baseline_test_metric: best.baseline_test_metric,
    optimized_test_metric: best.optimized_test_metric,
    metric_improvement: best.metric_improvement,
    total_pairs: pairs.length,
    completed_pairs: pairs.length,
    progress_events: [],
    logs: pairLogs,
    latest_metrics: {},
    progress_count: 0,
    log_count: pairLogs.length,
    grid_result: grid,
  };
}

export const DEMO_COMPARE_JOBS: OptimizationStatusResponse[] = [
  buildCompareJob({
    id: DEMO_COMPARE_IDS[0]!,
    name: `${COMPARE_TASK_NAME} · gpt-4o-mini`,
    description: formatMsg("auto.features.tutorial.lib.demo.data.template.4", { p1: TERMS.model }),
    modelName: "gpt-4o-mini",
    moduleName: "ChainOfThought",
    baseline: 0.62,
    optimized: 0.84,
    runtimeSeconds: 165,
    numLmCalls: 148,
    variant: "a",
  }),
  buildCompareJob({
    id: DEMO_COMPARE_IDS[1]!,
    name: `${COMPARE_TASK_NAME} · gpt-4o`,
    description: formatMsg("auto.features.tutorial.lib.demo.data.template.5", { p1: TERMS.model }),
    modelName: "gpt-4o",
    moduleName: "ChainOfThought",
    baseline: 0.62,
    optimized: 0.79,
    runtimeSeconds: 272,
    numLmCalls: 156,
    variant: "b",
  }),
  buildCompareJob({
    id: DEMO_COMPARE_IDS[2]!,
    name: `${COMPARE_TASK_NAME} · Predict`,
    description: msg("auto.features.tutorial.lib.demo.data.literal.18"),
    modelName: "gpt-4o-mini",
    moduleName: "Predict",
    baseline: 0.62,
    optimized: 0.71,
    runtimeSeconds: 110,
    numLmCalls: 92,
    variant: "c",
  }),
];

/**
 * Per-example test-set outputs for the three compare runs.
 * Designed so A=6/8 (0.75), B=6/8 (0.75), C=5/8 (0.625) — close to
 * the overall optimized scores in DEMO_COMPARE_JOBS — with a mix of
 * agreements and principled disagreements so the "hide agreements"
 * filter has something meaningful to hide.
 */
const COMPARE_EXAMPLE_ROWS: Array<{
  email_text: string;
  category: "spam" | "important" | "promotional";
}> = [
  { email_text: "Your quarterly report is ready for review", category: "important" },
  { email_text: "50% off all items this weekend only", category: "promotional" },
  { email_text: "Meeting moved to 3pm tomorrow", category: "important" },
  { email_text: "Click here to win $1000 now!", category: "spam" },
  { email_text: "Payroll update: new pay period starts Monday", category: "important" },
  { email_text: "Limited time: free shipping on orders over $50", category: "promotional" },
  { email_text: "Reminder: your subscription renews tomorrow", category: "promotional" },
  {
    email_text: "Urgent: verify your account to avoid suspension",
    category: "spam",
  },
];

const COMPARE_PASS_MATRIX: Record<"a" | "b" | "c", boolean[]> = {
  a: [true, true, true, false, true, true, false, true],
  b: [true, true, false, true, true, true, true, false],
  c: [true, true, false, true, false, true, true, false],
};

const COMPARE_PRED_MATRIX: Record<"a" | "b" | "c", string[]> = {
  a: [
    "important",
    "promotional",
    "important",
    "promotional",
    "important",
    "promotional",
    "important",
    "spam",
  ],
  b: [
    "important",
    "promotional",
    "promotional",
    "spam",
    "important",
    "promotional",
    "promotional",
    "promotional",
  ],
  c: [
    "important",
    "promotional",
    "spam",
    "spam",
    "promotional",
    "promotional",
    "promotional",
    "important",
  ],
};

function buildCompareExamples(variant: "a" | "b" | "c"): EvalExampleResult[] {
  const passes = COMPARE_PASS_MATRIX[variant];
  const preds = COMPARE_PRED_MATRIX[variant];
  return COMPARE_EXAMPLE_ROWS.map((_, i) => ({
    index: i,
    outputs: { category: preds[i]! },
    score: passes[i]! ? 1 : 0,
    pass: passes[i]!,
  }));
}

export const DEMO_COMPARE_EXAMPLES: Record<string, EvalExampleResult[]> = {
  [DEMO_COMPARE_IDS[0]!]: buildCompareExamples("a"),
  [DEMO_COMPARE_IDS[1]!]: buildCompareExamples("b"),
  [DEMO_COMPARE_IDS[2]!]: buildCompareExamples("c"),
};

const COMPARE_DATASET_ROWS: DatasetRow[] = COMPARE_EXAMPLE_ROWS.map((r, i) => ({
  index: i,
  row: { email_text: r.email_text, category: r.category },
}));

export const DEMO_COMPARE_DATASET: OptimizationDatasetResponse = {
  total_rows: COMPARE_DATASET_ROWS.length,
  splits: {
    train: [],
    val: [],
    test: COMPARE_DATASET_ROWS,
  },
  column_mapping: {
    inputs: { email_text: "email_text" },
    outputs: { category: "category" },
  },
  split_counts: { train: 0, val: 0, test: COMPARE_DATASET_ROWS.length },
};
