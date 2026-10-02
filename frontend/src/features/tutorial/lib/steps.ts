/**
 * Tutorial System — Step Definitions
 * Skynet prompt optimization platform
 *
 * Focused, replayable walkthroughs for the product's main user workflows.
 * Works even for users with zero optimizations.
 */

import {
  resetDemoSimulation,
  DEMO_DATASET_ID,
  DEMO_EMAIL_ROWS,
  DEMO_METRIC_CODE,
  DEMO_OPTIMIZATION_ID,
  getCachedDemoDashboardAnalytics,
  getCachedDemoDashboardJobs,
  getCachedDemoExplorePoints,
  getDemoDatasets,
  getDemoSignatureCode,
} from "./demo-data";
import { TERMS } from "@/shared/lib/terms";
import { formatMsg, msg } from "@/shared/lib/messages";
import { perLocale } from "@/shared/lib/per-locale";
import { PHONE_MEDIA_QUERY } from "@/shared/lib/device-class";
import { TUTORIAL_SUBMIT_SPLASH_MS } from "./tutorial-timing";
import { WIZARD_STAGE } from "@/features/submit";

/**
 * The short end-to-end path plus three focused workflow guides.
 *
 * The quick start covers only what a first run cannot skip, in the order the
 * work happens: tag data, set up and submit the optimization, read the score.
 * Testers gave up midway when it opened on result screens, so everything
 * after the score lives in the focused guides. Keeping each guide narrow makes the tutorial useful after onboarding too:
 * users can replay only the part they need instead of stepping through the
 * entire application again.
 */
export type TutorialTrack = "quick" | "data" | "results" | "workspace" | "advanced";

// The advanced guide is the quick start at full length, so every quick step
// also runs there; it adds the splits, search depth and a deeper results tour.
const QUICK_AND_ADVANCED: readonly TutorialTrack[] = ["quick", "advanced"];
const QUICK_DATA_AND_ADVANCED: readonly TutorialTrack[] = ["quick", "data", "advanced"];
const DATA_AND_ADVANCED: readonly TutorialTrack[] = ["data", "advanced"];
const DATA_ONLY: readonly TutorialTrack[] = ["data"];
const ADVANCED_ONLY: readonly TutorialTrack[] = ["advanced"];
const RESULTS_AND_ADVANCED: readonly TutorialTrack[] = ["results", "advanced"];
const RESULTS_ONLY: readonly TutorialTrack[] = ["results"];
const WORKSPACE_ONLY: readonly TutorialTrack[] = ["workspace"];

/** Where a step sits in the product's one workflow: prepare data, optimize, use the result. */
export type TutorialStage = "data" | "optimize" | "results";

export interface TutorialStep {
  id: string;
  /** Workflow stage shown as a progress strip, so steps read as one journey. */
  stage?: TutorialStage;
  title: string;
  description: string;
  target: string;
  placement?: "top" | "bottom" | "left" | "right" | "auto";
  /** Vertical nudge in pixels — positive moves the card down, negative up. Used to de-overlap dense sections. */
  offsetY?: number;
  /** Override the default popover height (260px) for steps that need more breathing room. */
  popoverHeight?: number;
  /** Override spotlight padding (default 8) for this step. */
  highlightPadding?: number;
  /** Override spotlight border radius (default 12) for this step. */
  highlightRadius?: number;
  beforeShow?: () => void | Promise<void>;
  /**
   * Best-effort UI cleanup fired when the step is left (PREV / NEXT / exit).
   * Use to undo sticky state the step set (e.g. selected rows, query strings,
   * optimizer choice) so traversal doesn't accumulate. Fire-and-forget —
   * the return value is not awaited.
   */
  afterHide?: () => void | Promise<void>;
  /** Focused guides that include this step. */
  tracks: readonly TutorialTrack[];
  readingTimeSec: number;
}

export interface TutorialTrackDefinition {
  id: TutorialTrack;
  name: string;
  description: string;
  icon: string;
  steps: TutorialStep[];
}

import {
  callTutorialHook,
  hasTutorialHook,
  setTutorialNavigating,
  queryTutorialHook,
  waitForHook,
} from "./bridge";
import { isGeneralistAgentEnabled } from "@/features/agent-panel";

function navigateTo(path: string) {
  // Prefer in-app client navigation via the tutorial-overlay hook.
  // Fall back to a full reload if no overlay is mounted (e.g. tests).
  if (hasTutorialHook("routerPush")) {
    callTutorialHook("routerPush", path);
  } else {
    setTutorialNavigating(true);
    window.location.href = path;
  }
}

/**
 * Wait for a selector to appear and have layout (non-zero rect) — handles
 * route + wizard + AnimatePresence transitions where the element exists
 * in the DOM but is still at 0×0 during the enter animation.
 */
function isElementVisible(selector: string): boolean {
  const el = document.querySelector(selector) as HTMLElement | null;
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
}

function waitForElement(selector: string, timeoutMs = 5000): Promise<boolean> {
  return new Promise((resolve) => {
    if (isElementVisible(selector)) {
      resolve(true);
      return;
    }
    const start = Date.now();
    const check = () => {
      if (isElementVisible(selector)) {
        resolve(true);
        return;
      }
      if (Date.now() - start > timeoutMs) {
        resolve(false);
        return;
      }
      requestAnimationFrame(check);
    };
    requestAnimationFrame(check);
  });
}

/**
 * Wait until an element's rect is unchanged across two consecutive frames, so
 * a spring-in (e.g. the selection bar) is measured at its resting position.
 */
function waitForStableRect(selector: string, timeoutMs = 2000): Promise<void> {
  return new Promise((resolve) => {
    const start = Date.now();
    let prev: DOMRect | null = null;
    const check = () => {
      const rect = document.querySelector(selector)?.getBoundingClientRect() ?? null;
      const stable =
        !!rect &&
        !!prev &&
        rect.x === prev.x &&
        rect.y === prev.y &&
        rect.width === prev.width &&
        rect.height === prev.height;
      if (stable || Date.now() - start > timeoutMs) {
        resolve();
        return;
      }
      prev = rect;
      requestAnimationFrame(check);
    };
    requestAnimationFrame(check);
  });
}

/** Show a splash screen identical to the real submit animation */
function showSubmitSplash(): Promise<void> {
  callTutorialHook("showTutorialSplash");
  return new Promise((resolve) => setTimeout(resolve, TUTORIAL_SUBMIT_SPLASH_MS));
}

// The pages each guide visits, in order. Warmed when the guide starts so its
// route changes land on an already-loaded page instead of waiting on one.
const TRACK_ROUTES: Record<TutorialTrack, readonly string[]> = {
  quick: ["/tagger", "/submit", `/optimizations/${DEMO_OPTIMIZATION_ID}`],
  data: ["/datasets", "/tagger"],
  results: [`/optimizations/${DEMO_OPTIMIZATION_ID}`],
  workspace: ["/", "/explore"],
  advanced: ["/tagger", "/submit", `/optimizations/${DEMO_OPTIMIZATION_ID}`],
};

export function warmTrackRoutes(track: TutorialTrack): void {
  for (const path of TRACK_ROUTES[track]) {
    if (path === window.location.pathname) continue;
    callTutorialHook("routerPrefetch", path);
    // The dev server compiles a route on its first request (seconds each) and
    // router.prefetch is a no-op in development, so request the page itself.
    if (process.env.NODE_ENV === "development") void fetch(path).catch(() => {});
  }
}

export function resetTutorialOneShotState(): void {
  // Reserved for future per-tour ephemeral flags. Currently a no-op:
  // the submit splash now keys off path transition (not a one-shot flag),
  // so nothing needs resetting between tour runs.
}

async function ensureDashboard() {
  if (window.location.pathname !== "/") {
    navigateTo("/");
    await waitForElement("[data-tutorial='dashboard-kpis']");
  }
  await waitForHook("setTab");
  // One commit tick so backward arrivals measure after React tab commit
  await new Promise<void>((r) => requestAnimationFrame(() => r()));
}

/** Inject demo jobs + analytics into dashboard for the tutorial — cached “real” data path */
function injectDemoDashboardData() {
  callTutorialHook("setDemoJobs", getCachedDemoDashboardJobs());
  callTutorialHook("setDemoAnalytics", getCachedDemoDashboardAnalytics());
}

async function ensureSubmit() {
  if (!window.location.pathname.startsWith("/submit")) {
    navigateTo("/submit");
    await waitForElement("[data-tutorial='wizard-stepper']");
  }
  await waitForHook("setWizardStep");
  await new Promise<void>((r) => requestAnimationFrame(() => r()));
}

async function ensureDemoDetail() {
  const path = `/optimizations/${DEMO_OPTIMIZATION_ID}`;
  if (window.location.pathname === path) {
    await waitForHook("setDetailTab");
    await new Promise<void>((r) => requestAnimationFrame(() => r()));
    return;
  }
  navigateTo(path);
  await waitForElement("[data-tutorial='detail-header']");
  await waitForHook("setDetailTab");
  await new Promise<void>((r) => requestAnimationFrame(() => r()));
}

function setTab(tab: string) {
  callTutorialHook("setTab", tab);
}

function setWizardStep(step: number) {
  callTutorialHook("setWizardStep", step);
}

/** A wizard stage is a run of substeps; open the one that holds `field`. */
function showWizardSubstep(stage: keyof typeof WIZARD_STAGE, field?: string) {
  callTutorialHook("showWizardSubstep", stage, field);
  setWizardStep(WIZARD_STAGE[stage]);
}

function setDetailTab(tab: string) {
  callTutorialHook("setDetailTab", tab);
}

function setOptimizerName(name: string) {
  callTutorialHook("setOptimizerName", name);
}

async function ensureTagger() {
  // A saved session (/tagger/[id]) never shows setup, so leave it for the plain page.
  if (window.location.pathname !== "/tagger") {
    navigateTo("/tagger");
    await waitForHook("setTaggerStartingNew");
    // Force the sessions chooser into setup; no-op if already in setup
    callTutorialHook("setTaggerStartingNew", true);
    await waitForElement("[data-tutorial='tagger-setup']");
  } else if (!hasTutorialHook("setTaggerStep")) {
    // Already on /tagger but still on the sessions panel (startingNew false)
    await waitForHook("setTaggerStartingNew");
    callTutorialHook("setTaggerStartingNew", true);
    await waitForElement("[data-tutorial='tagger-setup']");
  }
  await waitForHook("setTaggerStep");
}

async function ensureExplore() {
  if (window.location.pathname !== "/explore") {
    navigateTo("/explore");
    await waitForElement("[data-tutorial='explore-search']");
  }
  await waitForHook("setDemoExplorePoints");
  callTutorialHook("setDemoExplorePoints", getCachedDemoExplorePoints());
}

/** Open /datasets with a demo card, so a new account's empty library still shows the controls. */
async function ensureDatasets() {
  if (window.location.pathname !== "/datasets") {
    navigateTo("/datasets");
    await waitForElement("[data-tutorial='datasets-library']");
  }
  await waitForHook("setDemoDatasets");
  callTutorialHook("setDemoDatasets", getDemoDatasets());
  await waitForElement("[data-tutorial='datasets-add']");
}

/** Whether the agent panel was already open before the tour showed it. */
let agentPanelWasOpen = false;

function setGeneralistPanelOpen(open: boolean) {
  callTutorialHook("setGeneralistPanelOpen", open);
}

/** Inject demo data into tagger setup when empty and advance to the requested step */
function injectDemoTaggerData(targetStep: number) {
  if (!queryTutorialHook("hasTaggerData")) {
    callTutorialHook("setTaggerDemoData", {
      rows: DEMO_EMAIL_ROWS.map((row, index) => ({ id: index + 1, email_text: row.email_text })),
      cols: ["email_text"],
      textCol: "email_text",
    });
  }
  callTutorialHook("setTaggerStep", targetStep);
}

// Half the demo emails already carry a label, so the annotator shows real
// progress and the next email still waiting for one.
const DEMO_TAGGED_ROWS = 3;

/** Open the tagger's labeling screen on the demo emails, part-way through. */
async function showDemoTaggingSession() {
  await ensureTagger();
  const categories = [...new Set(DEMO_EMAIL_ROWS.map((row) => row.category))];
  callTutorialHook("showTaggerDemoSession", {
    rows: DEMO_EMAIL_ROWS.map((row, index) => ({ id: index + 1, email_text: row.email_text })),
    textCol: "email_text",
    categories: categories.map((category) => ({ id: category, label: category })),
    labels: Object.fromEntries(
      DEMO_EMAIL_ROWS.slice(0, DEMO_TAGGED_ROWS).map((row, index) => [
        String(index + 1),
        [row.category],
      ]),
    ),
    index: DEMO_TAGGED_ROWS,
  });
  await waitForElement("[data-tutorial='tagger-annotation']");
}

// Mirrors the backend planner's medium tier for the 200-email run the demo
// result shows; the six demo rows alone would only earn the "too small" plan.
const DEMO_SPLIT_PLAN = {
  fractions: { train: 0.6, val: 0.2, test: 0.2 },
  shuffle: true,
  seed: 42,
  counts: { train: 120, val: 40, test: 40 },
  rationale: [],
};

// One shared object per tour, so re-injecting on every wizard step is a no-op
// state update rather than a "new upload" that re-stages and re-profiles it.
const DEMO_PARSED_DATASET = {
  columns: ["email_text", "category"],
  rows: DEMO_EMAIL_ROWS.map((row) => ({ ...row })),
  rowCount: DEMO_EMAIL_ROWS.length,
};
const DEMO_COLUMN_ROLES = { email_text: "input", category: "output" } as const;

/** Inject sample dataset + code into the wizard for the tutorial */
function injectSampleDataset() {
  callTutorialHook("setParsedDataset", DEMO_PARSED_DATASET);
  callTutorialHook("setColumnRoles", DEMO_COLUMN_ROLES);
  callTutorialHook("setDatasetFileName", "emails_sample.csv");
  callTutorialHook("setSignatureCode", getDemoSignatureCode());
  callTutorialHook("setMetricCode", DEMO_METRIC_CODE);
}

const tutorialSteps: TutorialStep[] = perLocale(() => [
  {
    id: "dd-dataset-add",
    stage: "data",
    title: msg("tutorial.step.dataset_add.title"),
    description: msg("tutorial.step.dataset_add.body"),
    target: "[data-tutorial='datasets-add']",
    placement: "bottom",
    beforeShow: ensureDatasets,
    tracks: DATA_ONLY,
    readingTimeSec: 9,
  },
  {
    id: "dd-dataset-actions",
    stage: "data",
    title: msg("tutorial.step.dataset_actions.title"),
    description: msg("tutorial.step.dataset_actions.body"),
    target: "[data-tutorial='datasets-selection']",
    placement: "top",
    beforeShow: async () => {
      await ensureDatasets();
      await waitForHook("setSelectedDatasetIds");
      callTutorialHook("setSelectedDatasetIds", [DEMO_DATASET_ID]);
      await waitForElement("[data-tutorial='datasets-selection']");
      await waitForStableRect("[data-tutorial='datasets-selection']");
    },
    afterHide: () => {
      callTutorialHook("setSelectedDatasetIds", []);
    },
    tracks: DATA_ONLY,
    readingTimeSec: 9,
  },
  {
    id: "dd-tagger-setup",
    stage: "data",
    title: msg("tutorial.step.tagger_setup.title"),
    // The synthetic-dataset option only renders with AI assist on.
    get description() {
      return queryTutorialHook("taggerAssistAvailable") === false
        ? msg("tutorial.step.tagger_setup.body_manual")
        : msg("tutorial.step.tagger_setup.body");
    },
    target: "[data-tutorial='tagger-data']",
    placement: "auto",
    beforeShow: async () => {
      await ensureTagger();
      injectDemoTaggerData(0);
    },
    tracks: QUICK_DATA_AND_ADVANCED,
    readingTimeSec: 13,
  },
  {
    id: "dd-tagger-modes",
    stage: "data",
    // With AI assist off, the same anchor sits on the task card instead of the
    // mode picker, so the copy is chosen once setup has mounted.
    get title() {
      return queryTutorialHook("taggerAssistAvailable") === false
        ? msg("tutorial.step.tagger_task.title")
        : msg("auto.features.tutorial.lib.steps.literal.31");
    },
    get description() {
      return queryTutorialHook("taggerAssistAvailable") === false
        ? msg("tutorial.step.tagger_task.body")
        : msg("tutorial.step.tagger_modes.body");
    },
    target: "[data-tutorial='tagger-modes']",
    placement: "auto",
    beforeShow: async () => {
      await ensureTagger();
      injectDemoTaggerData(1);
      await waitForElement("[data-tutorial='tagger-modes']");
    },
    tracks: QUICK_DATA_AND_ADVANCED,
    readingTimeSec: 13,
  },
  {
    id: "dd-tagging-live",
    stage: "data",
    title: msg("tutorial.step.tagging_live.title"),
    description: msg("tutorial.step.tagging_live.body"),
    target: "[data-tutorial='tagger-annotation']",
    placement: "auto",
    beforeShow: showDemoTaggingSession,
    // Setup is unmounted while labeling, and the setup steps wait for it.
    afterHide: () => {
      callTutorialHook("clearTaggerDemoSession");
    },
    tracks: DATA_AND_ADVANCED,
    readingTimeSec: 15,
  },
  {
    id: "dd-data-upload",
    stage: "optimize",
    title: msg("tutorial.step.data_upload.title"),
    description: msg("tutorial.step.data_upload.body"),
    target: "[data-tutorial='wizard-step-2']",
    placement: "left",
    beforeShow: async () => {
      await ensureSubmit();
      injectSampleDataset();
      showWizardSubstep("evaluation", "dataset-upload");
      await waitForElement("[data-tutorial='dataset-upload']");
    },
    tracks: QUICK_AND_ADVANCED,
    readingTimeSec: 16,
  },
  {
    id: "dd-data-splits",
    stage: "optimize",
    title: msg("tutorial.step.data_splits.title"),
    description: msg("tutorial.step.data_splits.body"),
    target: "[data-tutorial='data-splits']",
    placement: "auto",
    beforeShow: async () => {
      await ensureSubmit();
      injectSampleDataset();
      showWizardSubstep("evaluation", "data-splits");
      await waitForElement("[data-tutorial='data-splits']");
      callTutorialHook("setDemoSplitPlan", DEMO_SPLIT_PLAN);
    },
    tracks: ADVANCED_ONLY,
    readingTimeSec: 15,
  },
  {
    id: "dd-code-setup",
    stage: "optimize",
    title: `${msg("auto.features.tutorial.lib.steps.literal.20")} + ${TERMS.metric}`,
    description: msg("tutorial.step.code_setup.body"),
    target: "[data-tutorial='code-editors']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      injectSampleDataset();
      showWizardSubstep("evaluation", "code-editors");
      callTutorialHook("setCodeAssistMode", "auto");
      callTutorialHook("chooseModule", "predict");
      callTutorialHook("setSignatureCode", getDemoSignatureCode());
      callTutorialHook("setMetricCode", DEMO_METRIC_CODE);
      await waitForElement("[data-tutorial='code-editors']");
    },
    tracks: QUICK_AND_ADVANCED,
    readingTimeSec: 18,
  },
  {
    id: "dd-search-depth",
    stage: "optimize",
    title: msg("tutorial.step.search_depth.title"),
    description: msg("tutorial.step.search_depth.body"),
    target: "[data-tutorial='auto-level']",
    placement: "auto",
    beforeShow: async () => {
      await ensureSubmit();
      setOptimizerName("gepa");
      showWizardSubstep("optimization", "auto-level");
      await waitForElement("[data-tutorial='auto-level']");
    },
    tracks: ADVANCED_ONLY,
    readingTimeSec: 14,
  },
  {
    id: "dd-models",
    stage: "optimize",
    title: msg("auto.features.tutorial.lib.steps.template.24"),
    description: formatMsg("tutorial.step.models.body", {
      p1: TERMS.generationModel,
      p2: TERMS.reflectionModel,
    }),
    target: "[data-tutorial='model-catalog']",
    placement: "bottom",
    beforeShow: async () => {
      await ensureSubmit();
      callTutorialHook("setDemoModels");
      showWizardSubstep("optimization", "model-catalog");
      await waitForElement("[data-tutorial='model-catalog']");
    },
    tracks: QUICK_AND_ADVANCED,
    readingTimeSec: 10,
  },
  {
    id: "dd-review",
    stage: "optimize",
    title: msg("auto.features.tutorial.lib.steps.template.27"),
    description: msg("tutorial.step.review.body"),
    target: "[data-tutorial='wizard-stage-review']",
    placement: "bottom",
    beforeShow: async () => {
      await ensureSubmit();
      setOptimizerName("gepa");
      callTutorialHook("setDemoModels");
      showWizardSubstep("review", "wizard-stage-review");
    },
    tracks: QUICK_AND_ADVANCED,
    readingTimeSec: 13,
  },
  {
    id: "dd-live-run",
    stage: "results",
    title: msg("tutorial.step.live_run.title"),
    description: msg("tutorial.step.live_run.body"),
    target: "[data-tutorial='pipeline-stages']",
    placement: "bottom",
    beforeShow: async () => {
      const path = `/optimizations/${DEMO_OPTIMIZATION_ID}`;
      if (window.location.pathname === path) {
        // Stepping back from the scores: stream the run again so the bar moves.
        await ensureDemoDetail();
        callTutorialHook("replayDemoSimulation");
      } else {
        resetDemoSimulation();
        await showSubmitSplash();
        await ensureDemoDetail();
      }
      setDetailTab("overview");
      await waitForElement("[data-tutorial='pipeline-stages']");
    },
    tracks: QUICK_AND_ADVANCED,
    readingTimeSec: 10,
  },
  {
    id: "dd-scores",
    stage: "results",
    title: msg("tutorial.step.scores.title"),
    description: msg("tutorial.step.scores.body"),
    target: "[data-tutorial='score-cards']",
    placement: "bottom",
    beforeShow: async () => {
      await ensureDemoDetail();
      // Moving on before the live run ends jumps straight to its final scores.
      callTutorialHook("finishDemoSimulation");
      setDetailTab("overview");
      await waitForElement("[data-tutorial='score-cards']");
    },
    tracks: QUICK_AND_ADVANCED,
    readingTimeSec: 11,
  },
  {
    id: "dd-score-chart",
    stage: "results",
    title: msg("tutorial.step.score_chart.title"),
    description: msg("tutorial.step.score_chart.body"),
    target: "[data-tutorial='score-chart']",
    placement: "top",
    beforeShow: async () => {
      await ensureDemoDetail();
      // This guide describes a finished run; without this the page replays
      // the run live and the chart has no trials yet.
      callTutorialHook("finishDemoSimulation");
      setDetailTab("overview");
      await waitForElement("[data-tutorial='score-chart']");
    },
    tracks: RESULTS_AND_ADVANCED,
    readingTimeSec: 13,
  },
  {
    id: "dd-trajectory",
    stage: "results",
    title: msg("auto.features.tutorial.lib.steps.literal.46"),
    description: msg("auto.features.tutorial.lib.steps.literal.48"),
    target: "[data-tutorial='trajectory-panel']",
    placement: "top",
    beforeShow: async () => {
      await ensureDemoDetail();
      setDetailTab("overview");
      // Re-stream the candidates so the user sees the tree grow instead of
      // landing on a completed graph with no explanation of its branches.
      callTutorialHook("replayDemoSimulation");
      await waitForElement("[data-tutorial='trajectory-panel']");
    },
    // The replay hides the Artifact tab until it ends, so skip to the result.
    afterHide: () => {
      callTutorialHook("finishDemoSimulation");
    },
    tracks: RESULTS_AND_ADVANCED,
    readingTimeSec: 12,
  },
  {
    id: "dd-playground",
    stage: "results",
    title: msg("auto.features.tutorial.lib.steps.literal.25"),
    description: `${formatMsg("auto.features.tutorial.lib.steps.template.36", { p1: TERMS.model })} ${msg("auto.features.tutorial.lib.steps.literal.41")}`,
    target: "[data-tutorial='serve-playground']",
    placement: "bottom",
    offsetY: 0,
    beforeShow: async () => {
      await ensureDemoDetail();
      setDetailTab("playground");
      await waitForElement("[data-tutorial='serve-playground']");
    },
    tracks: RESULTS_ONLY,
    readingTimeSec: 9,
  },
  {
    id: "dd-code",
    stage: "results",
    title: msg("tutorial.step.code.title"),
    description: msg("tutorial.step.code.body"),
    target: "[data-tutorial='code-sources']",
    placement: "top",
    beforeShow: async () => {
      await ensureDemoDetail();
      setDetailTab("code");
      await waitForElement("[data-tutorial='code-sources']");
    },
    tracks: RESULTS_ONLY,
    readingTimeSec: 11,
  },
  {
    id: "dd-artifact",
    stage: "results",
    title: msg("tutorial.step.artifact.title"),
    description: msg("tutorial.step.artifact.body"),
    target: "[data-tutorial='artifact-output']",
    placement: "top",
    beforeShow: async () => {
      await ensureDemoDetail();
      setDetailTab("artifact");
      await waitForElement("[data-tutorial='artifact-output']");
    },
    tracks: RESULTS_ONLY,
    readingTimeSec: 12,
  },
  {
    id: "dd-data-tab",
    stage: "results",
    title: msg("auto.features.tutorial.lib.steps.literal.24"),
    description: formatMsg("auto.features.tutorial.lib.steps.template.35", {
      p1: TERMS.dataset,
      p2: TERMS.score,
      p3: TERMS.model,
      p4: TERMS.splitTrain,
      p5: TERMS.splitVal,
      p6: TERMS.splitTest,
      p7: TERMS.score,
    }),
    target: "[data-tutorial='data-table']",
    placement: "bottom",
    offsetY: 0,
    beforeShow: async () => {
      await ensureDemoDetail();
      setDetailTab("data");
      await waitForElement("[data-tutorial='data-table']");
    },
    tracks: RESULTS_ONLY,
    readingTimeSec: 13,
  },
  {
    id: "dd-logs",
    stage: "results",
    title: msg("auto.features.tutorial.lib.steps.literal.26"),
    description: formatMsg("auto.features.tutorial.lib.steps.template.37", { p1: TERMS.optimizer }),
    target: "[data-tutorial='live-logs']",
    placement: "top",
    beforeShow: async () => {
      await ensureDemoDetail();
      setDetailTab("logs");
      await waitForElement("[data-tutorial='live-logs']");
    },
    tracks: RESULTS_ONLY,
    readingTimeSec: 9,
  },
  {
    id: "dd-result-actions",
    stage: "results",
    title: msg("tutorial.step.result_actions.title"),
    description: msg("tutorial.step.result_actions.body"),
    target: "[data-tutorial='result-actions']",
    placement: "left",
    beforeShow: async () => {
      await ensureDemoDetail();
      setDetailTab("overview");
      await waitForElement("[data-tutorial='result-actions']");
    },
    tracks: RESULTS_ONLY,
    readingTimeSec: 9,
  },
  {
    id: "dd-sidebar-nav",
    title: msg("tutorial.step.sidebar_nav.title"),
    description: msg("tutorial.step.sidebar_nav.body"),
    target: "[data-tutorial='sidebar-nav']",
    placement: "right",
    beforeShow: async () => {
      await ensureDashboard();
      await waitForElement("[data-tutorial='sidebar-nav']");
    },
    tracks: WORKSPACE_ONLY,
    readingTimeSec: 6,
  },
  {
    id: "dd-table",
    title: formatMsg("auto.features.tutorial.lib.steps.template.1", {
      p1: TERMS.optimizationPlural,
    }),
    description: formatMsg("auto.features.tutorial.lib.steps.template.2", {
      p1: TERMS.optimization,
    }),
    target: "[data-tutorial='dashboard-table']",
    placement: "top",
    offsetY: 0,
    beforeShow: async () => {
      await ensureDashboard();
      injectDemoDashboardData();
      setTab("jobs");
      await waitForElement("[data-tutorial='dashboard-table']");
    },
    tracks: WORKSPACE_ONLY,
    readingTimeSec: 11,
  },
  {
    id: "dd-analytics",
    title: msg("auto.features.tutorial.lib.steps.literal.9"),
    description: formatMsg("auto.features.tutorial.lib.steps.template.47", {
      p1: TERMS.module,
      p2: TERMS.optimizationPlural,
    }),
    target: "[data-tutorial='analytics-content']",
    placement: "bottom",
    beforeShow: async () => {
      await ensureDashboard();
      injectDemoDashboardData();
      setTab("analytics");
      await waitForElement("[data-tutorial='analytics-content']");
      await new Promise((r) => setTimeout(r, 250));
    },
    tracks: WORKSPACE_ONLY,
    readingTimeSec: 9,
  },
  {
    id: "dd-explore",
    title: msg("auto.features.tutorial.lib.steps.literal.38"),
    description: msg("auto.features.tutorial.lib.steps.literal.49"),
    target: "[data-tutorial='explore-search']",
    placement: "bottom",
    beforeShow: async () => {
      await ensureExplore();
    },
    tracks: WORKSPACE_ONLY,
    readingTimeSec: 11,
  },
  {
    id: "dd-agent-panel",
    title: msg("auto.features.tutorial.lib.steps.literal.44"),
    description: msg("auto.features.tutorial.lib.steps.literal.50"),
    target: "[data-tutorial='agent-panel']",
    placement: "left",
    beforeShow: async () => {
      agentPanelWasOpen = isElementVisible("[data-tutorial='agent-panel']");
      setGeneralistPanelOpen(true);
      await waitForElement("[data-tutorial='agent-panel']");
    },
    afterHide: () => {
      if (!agentPanelWasOpen) setGeneralistPanelOpen(false);
    },
    tracks: WORKSPACE_ONLY,
    readingTimeSec: 10,
  },
]);

const AGENT_PANEL_STEP_IDS = new Set(["dd-agent-panel"]);
// Phones render neither these detail tabs, the dashboard table nor the
// sidebar (they get bottom tabs), so the steps would only stall on a
// missing target before being skipped.
const DESKTOP_ONLY_STEP_IDS = new Set(["dd-code", "dd-data-tab", "dd-table", "dd-sidebar-nav"]);

function isPhoneViewport(): boolean {
  return typeof window !== "undefined" && window.matchMedia(PHONE_MEDIA_QUERY).matches;
}

function getVisibleSteps(): TutorialStep[] {
  const generalist = isGeneralistAgentEnabled();
  const phone = isPhoneViewport();
  return tutorialSteps.filter((s) => {
    if (!generalist && AGENT_PANEL_STEP_IDS.has(s.id)) return false;
    if (phone && DESKTOP_ONLY_STEP_IDS.has(s.id)) return false;
    return true;
  });
}

export function getTrack(trackId: TutorialTrack): TutorialTrackDefinition | undefined {
  const steps = getVisibleSteps().filter((s) => s.tracks.includes(trackId));
  if (steps.length === 0) return undefined;
  const metadata: Record<TutorialTrack, { name: string; description: string }> = {
    quick: {
      name: msg("tutorial.track.quick.name"),
      description: msg("tutorial.track.quick.desc"),
    },
    data: {
      name: msg("tutorial.track.data.name"),
      description: msg("tutorial.track.data.desc"),
    },
    results: {
      name: msg("tutorial.track.results.name"),
      description: msg("tutorial.track.results.desc"),
    },
    workspace: {
      name: msg("tutorial.track.workspace.name"),
      description: msg("tutorial.track.workspace.desc"),
    },
    advanced: {
      name: msg("tutorial.track.advanced.name"),
      description: msg("tutorial.track.advanced.desc"),
    },
  };
  return {
    id: trackId,
    name: metadata[trackId].name,
    description: metadata[trackId].description,
    icon: trackId,
    steps,
  };
}
