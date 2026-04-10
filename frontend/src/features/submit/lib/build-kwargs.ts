/**
 * Pure builders for optimizer_kwargs and compile_kwargs.
 * Kept side-effect-free so they're trivially testable.
 */

export interface OptimizerKwargsInput {
  optimizerName: string;
  autoLevel: string;
  maxBootstrappedDemos: string;
  maxLabeledDemos: string;
  maxFullEvals: string;
  reflectionMinibatchSize: string;
  useMerge: boolean;
}

export function buildOptimizerKwargs(input: OptimizerKwargsInput): Record<string, unknown> {
  const { optimizerName, autoLevel, maxBootstrappedDemos, maxLabeledDemos, maxFullEvals, reflectionMinibatchSize, useMerge } = input;
  const kw: Record<string, unknown> = {};
  if (optimizerName === "miprov2") {
    if (autoLevel) kw.auto = autoLevel;
    if (maxBootstrappedDemos) kw.max_bootstrapped_demos = parseInt(maxBootstrappedDemos, 10);
    if (maxLabeledDemos) kw.max_labeled_demos = parseInt(maxLabeledDemos, 10);
  } else if (optimizerName === "gepa") {
    // GEPA requires exactly one of: auto, max_full_evals, max_metric_calls
    if (autoLevel) {
      kw.auto = autoLevel;
    } else if (maxFullEvals) {
      kw.max_full_evals = parseInt(maxFullEvals, 10);
    }
    if (reflectionMinibatchSize) kw.reflection_minibatch_size = parseInt(reflectionMinibatchSize, 10);
    kw.use_merge = useMerge;
  }
  return Object.keys(kw).length > 0 ? kw : {};
}

export interface CompileKwargsInput {
  optimizerName: string;
  autoLevel: string;
  numTrials: string;
  minibatch: boolean;
  minibatchSize: string;
}

export function buildCompileKwargs(input: CompileKwargsInput): Record<string, unknown> {
  const { optimizerName, autoLevel, numTrials, minibatch, minibatchSize } = input;
  const kw: Record<string, unknown> = {};
  if (optimizerName === "miprov2") {
    // When auto is set, num_trials/num_candidates are controlled by auto
    if (!autoLevel && numTrials) kw.num_trials = parseInt(numTrials, 10);
    kw.minibatch = minibatch;
    if (minibatch && minibatchSize) kw.minibatch_size = parseInt(minibatchSize, 10);
  }
  return Object.keys(kw).length > 0 ? kw : {};
}
