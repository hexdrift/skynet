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
import type { ParsedDataset } from "./parse-dataset";

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
}

const registry: Partial<TutorialHooks> = {};

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
