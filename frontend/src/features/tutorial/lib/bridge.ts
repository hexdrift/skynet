/**
 * Typed bridge between the tutorial system and the components it drives.
 *
 * The tutorial runs outside the React component tree (it's plain JS in
 * `lib/tutorial-steps.ts`) but needs to push state into React components
 * like the submit wizard and the dashboard tabs. Previously this was done
 * by attaching setters to `window.__skynet*` with `(window as any)` casts
 * scattered across 20+ sites.
 *
 * This module replaces that pattern with a typed singleton registry:
 *
 *     // Producer (inside a React effect):
 *     useEffect(() => registerTutorialHook("setWizardStep", setStep), []);
 *
 *     // Consumer (from tutorial-steps.ts):
 *     callTutorialHook("setWizardStep", 1);
 *
 * The registry lives in module-level state, which is a per-tab singleton
 * in the browser — identical behavior to the old window globals, but with
 * full type checking at both ends.
 */
import type { ParsedDataset } from "@/features/submit/lib/parse-dataset";
import type {
  PaginatedJobsResponse,
  OptimizationStatusResponse,
  EvalExampleResult,
  OptimizationDatasetResponse,
} from "@/shared/types/api";
import type { DashboardAnalytics } from "@/shared/lib/api";

/**
 * The set of hooks the tutorial system can invoke. Every hook is a
 * callback the producing component registers in a React effect. Keep
 * this map in sync with the keys consumed by ``tutorial-steps.ts``.
 */
export interface TutorialHooks {
  /** Switch the dashboard between the "jobs" and "analytics" tabs. */
  setTab: (tab: string) => void;
  /** Jump the submit wizard to a specific step index. */
  setWizardStep: (step: number) => void;
  /** Switch the optimization-detail page between its tabs. */
  setDetailTab: (tab: string) => void;
  /** Switch the /compare page between its tabs (overview / config / prompts / examples). */
  setCompareTab: (tab: string) => void;
  /** Seed the wizard's optimizer selector. */
  setOptimizerName: (name: string) => void;
  /** Seed the wizard's parsed dataset. */
  setParsedDataset: (dataset: ParsedDataset) => void;
  /** Seed the wizard's column roles. */
  setColumnRoles: (roles: Record<string, "input" | "output" | "ignore">) => void;
  /** Seed the wizard's dataset filename display. */
  setDatasetFileName: (name: string) => void;
  /** Seed the wizard's signature code editor. */
  setSignatureCode: (code: string) => void;
  /** Seed the wizard's metric code editor. */
  setMetricCode: (code: string) => void;
  /** Show the tutorial splash overlay. */
  showTutorialSplash: () => void;
  /** Navigate via next/router without a full page reload. */
  routerPush: (path: string) => void;
  /** Inject demo jobs into the dashboard table when empty. */
  setDemoJobs: (data: PaginatedJobsResponse) => void;
  /** Programmatically select job IDs in the dashboard table (for the compare-flow demo). */
  setSelectedJobIds: (ids: string[]) => void;
  /** Inject demo analytics into the dashboard charts when empty. */
  setDemoAnalytics: (data: DashboardAnalytics) => void;
  /** Jump the tagger setup wizard to a specific step. */
  setTaggerStep: (step: number) => void;
  /** Inject demo rows into the tagger setup. */
  setTaggerDemoData: (data: { rows: unknown[]; cols: string[]; textCol: string }) => void;
}

/**
 * Hooks that return a value (queries). Kept separate from fire-and-forget
 * hooks so callTutorialHook stays simple.
 */
export interface TutorialQueries {
  /** Check if the dashboard currently has real job data. */
  hasDashboardData: () => boolean;
  /** Check if the tagger setup has data loaded. */
  hasTaggerData: () => boolean;
}

const registry: Partial<TutorialHooks> = {};
const queryRegistry: Partial<TutorialQueries> = {};

/**
 * Register a callback the tutorial system can invoke. Returns an
 * unregistration function suitable for a React effect cleanup.
 */
export function registerTutorialHook<K extends keyof TutorialHooks>(
  key: K,
  fn: TutorialHooks[K],
): () => void {
  registry[key] = fn;
  return () => {
    if (registry[key] === fn) {
      delete registry[key];
    }
  };
}

/**
 * Invoke a registered tutorial hook, if any producer has registered one.
 * Silently no-ops when no producer is mounted.
 */
export function callTutorialHook<K extends keyof TutorialHooks>(
  key: K,
  ...args: Parameters<TutorialHooks[K]>
): void {
  const fn = registry[key];
  if (fn) {
    (fn as (...a: Parameters<TutorialHooks[K]>) => void)(...args);
  }
}

/**
 * True when a producer has registered the given hook. Useful for code
 * that needs to pick between a client-side API (if mounted) and a
 * fallback path (if not).
 */
export function hasTutorialHook<K extends keyof TutorialHooks>(key: K): boolean {
  return key in registry;
}

/** Register a query hook that returns a value. */
export function registerTutorialQuery<K extends keyof TutorialQueries>(
  key: K,
  fn: TutorialQueries[K],
): () => void {
  queryRegistry[key] = fn;
  return () => {
    if (queryRegistry[key] === fn) delete queryRegistry[key];
  };
}

/** Call a query hook and return its result, or undefined if not registered. */
export function queryTutorialHook<K extends keyof TutorialQueries>(
  key: K,
  ...args: Parameters<TutorialQueries[K]>
): ReturnType<TutorialQueries[K]> | undefined {
  const fn = queryRegistry[key];
  if (fn) return (fn as (...a: Parameters<TutorialQueries[K]>) => ReturnType<TutorialQueries[K]>)(...args);
  return undefined;
}

/**
 * True while the tutorial has triggered a client-side navigation that
 * expects a splash transition. Used by tutorial-overlay to suppress
 * re-rendering mid-transition.
 */
let navigating = false;

export function setTutorialNavigating(value: boolean): void {
  navigating = value;
}

export function isTutorialNavigating(): boolean {
  return navigating;
}

/**
 * One-shot payload for the /compare page. The tutorial seeds this
 * BEFORE navigating, and the compare page consumes it on mount in
 * place of the normal backend fetch. Cleared after consumption so a
 * subsequent non-tutorial visit falls back to the live API.
 */
let pendingCompareDemo: OptimizationStatusResponse[] | null = null;

export function setPendingCompareDemo(jobs: OptimizationStatusResponse[]): void {
  pendingCompareDemo = jobs;
}

export function consumePendingCompareDemo(): OptimizationStatusResponse[] | null {
  const jobs = pendingCompareDemo;
  pendingCompareDemo = null;
  return jobs;
}

/**
 * One-shot payload for the optimization-detail page when the tutorial is
 * showcasing grid search. Unlike the single-run demo (which progresses
 * through phases via startDemoSimulation), the grid demo is pre-completed:
 * the detail page just renders the job directly.
 */
let pendingGridDemo: OptimizationStatusResponse | null = null;

export function setPendingGridDemo(job: OptimizationStatusResponse): void {
  pendingGridDemo = job;
}

export function consumePendingGridDemo(): OptimizationStatusResponse | null {
  const job = pendingGridDemo;
  pendingGridDemo = null;
  return job;
}

/**
 * One-shot payload for the /compare page's "examples" tab. Provides
 * per-example results keyed by optimization_id and the shared dataset
 * so the PerExampleSection can render without hitting the backend
 * during the tutorial.
 */
export interface PendingCompareExamples {
  byJobId: Record<string, EvalExampleResult[]>;
  dataset: OptimizationDatasetResponse;
}

let pendingCompareExamples: PendingCompareExamples | null = null;

export function setPendingCompareExamples(value: PendingCompareExamples): void {
  pendingCompareExamples = value;
}

export function consumePendingCompareExamples(): PendingCompareExamples | null {
  const v = pendingCompareExamples;
  pendingCompareExamples = null;
  return v;
}
