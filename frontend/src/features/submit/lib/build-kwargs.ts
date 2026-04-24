/**
 * Pure builders for optimizer_kwargs.
 * Kept side-effect-free so they're trivially testable.
 */

export interface OptimizerKwargsInput {
  autoLevel: string;
  maxFullEvals: string;
  reflectionMinibatchSize: string;
  useMerge: boolean;
}

export function buildOptimizerKwargs(input: OptimizerKwargsInput): Record<string, unknown> {
  const { autoLevel, maxFullEvals, reflectionMinibatchSize, useMerge } = input;
  const kw: Record<string, unknown> = {};
  // GEPA requires exactly one of: auto, max_full_evals, max_metric_calls
  if (autoLevel) {
    kw.auto = autoLevel;
  } else if (maxFullEvals) {
    kw.max_full_evals = parseInt(maxFullEvals, 10);
  }
  if (reflectionMinibatchSize)
    kw.reflection_minibatch_size = parseInt(reflectionMinibatchSize, 10);
  kw.use_merge = useMerge;
  return Object.keys(kw).length > 0 ? kw : {};
}
