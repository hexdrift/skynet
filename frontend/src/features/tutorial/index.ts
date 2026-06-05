export { TutorialOverlay } from "./components/tutorial-overlay";
export { TutorialMenu } from "./components/tutorial-menu";
export { TutorialProvider, useTutorialContext } from "./components/tutorial-provider";
export { ConceptsGuide } from "./components/concepts-guide.lazy";
export {
  consumePendingCompareDemo,
  consumePendingCompareExamples,
  registerTutorialHook,
  registerTutorialQuery,
} from "./lib/bridge";
export {
  DEMO_GRID_OPTIMIZATION_ID,
  DEMO_OPTIMIZATION_ID,
  DEMO_TRAJECTORY_PREVIEW_LAYOUT,
  buildGridDemoJob,
  resetDemoSimulation,
  startDemoSimulation,
} from "./lib/demo-data";
