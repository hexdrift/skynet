import type { ModelConfig, SplitFractions } from "@/shared/types/api";
import { msg } from "@/shared/lib/messages";
import { WIZARD_STAGE_ORDER, type WizardStageId } from "./lib/wizard-steps";

export const emptyModelConfig = (): ModelConfig => ({
  name: "",
  token_source: "byok",
  temperature: 0.7,
  max_tokens: 1024,
});

export const defaultSplit: SplitFractions = { train: 0.7, val: 0.15, test: 0.15 };

// A dataset column's role. React is now a generic GEPA module, so every run —
// react included — maps columns to signature I/O exactly the same way.
export type ColumnRole = "input" | "output" | "ignore";

// UI-side model of the react (ReAct-agent) tool-source configuration. React is
// generic: scoring is owned by the standard authored metric_code, so no reward
// knobs live here — only the live tool roster. Tools always come from a live
// MCP server, unfiltered (the wizard no longer offers dataset snapshots or
// tool filters; the backend keeps supporting both for old runs).
// `use-submit-wizard` reshapes this into the backend's ToolSource wire model
// at submit time.
export interface ReactConfig {
  mcpUrl: string;
  mcpAuthHeader: string;
}

export const defaultReactConfig = (): ReactConfig => ({
  mcpUrl: "",
  mcpAuthHeader: "",
});

// Labels are thunks, not pre-resolved strings: `msg()` reads the active locale's
// catalog, which is delivered out of band and is empty at module-eval time on the
// server (frozen process-wide to the raw key) but populated in the browser —
// resolving eagerly here would hydrate-mismatch. Resolving per render keeps both
// sides inside the request, where the catalog is pinned.
const STAGE_LABELS: Record<WizardStageId, () => string> = {
  goal: () => msg("submit.stage.goal"),
  evaluation: () => msg("submit.stage.evaluation"),
  optimization: () => msg("submit.stage.optimization"),
  review: () => msg("submit.stage.review"),
};

export const WIZARD_STAGES: ReadonlyArray<{ id: WizardStageId; label: () => string }> =
  WIZARD_STAGE_ORDER.map((id) => ({ id, label: STAGE_LABELS[id] }));

export const RECENT_KEY = "skynet:recent-model-configs";
export const MAX_RECENT = 5;

/** RTL: forward = slide from left, backward = slide from right. */
export const slideVariants = {
  enter: (direction: number) => ({
    x: direction > 0 ? -80 : 80,
    opacity: 0,
    scale: 0.97,
  }),
  center: {
    x: 0,
    opacity: 1,
    scale: 1,
  },
  exit: (direction: number) => ({
    x: direction > 0 ? 80 : -80,
    opacity: 0,
    scale: 0.97,
  }),
};
