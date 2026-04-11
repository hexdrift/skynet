/**
 * DSPy-specific constants
 * Module types and optimizer configurations - source of truth for allowed modules/optimizers
 */

export const DSPY_MODULES = {
  PREDICT: 'Predict',
  COT: 'ChainOfThought',
} as const;

export const DSPY_OPTIMIZERS = {
  MIPROV2: 'MIPROv2',
  GEPA: 'GEPA',
} as const;

export const OPTIMIZER_PARAMS = {
  MIPROV2: {
    num_trials: {
      default: 30,
      min: 1,
      max: 100,
      description: 'מספר ניסיונות לאופטימיזציה',
    },
    auto_level: {
      default: 1,
      min: 0,
      max: 3,
      description: 'רמת אוטומציה',
    },
  },
  GEPA: {
    generations: {
      default: 10,
      min: 1,
      max: 50,
      description: 'מספר דורות',
    },
    population_size: {
      default: 20,
      min: 5,
      max: 100,
      description: 'גודל אוכלוסייה',
    },
  },
} as const;

export type DspyModule = typeof DSPY_MODULES[keyof typeof DSPY_MODULES];
export type DspyOptimizer = typeof DSPY_OPTIMIZERS[keyof typeof DSPY_OPTIMIZERS];
