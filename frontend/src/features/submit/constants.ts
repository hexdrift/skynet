import type { ModelConfig, SplitFractions } from "@/shared/types/api";
import { TERMS } from "@/shared/lib/terms";
import { msg } from "@/shared/lib/messages";

export const emptyModelConfig = (): ModelConfig => ({
  name: "",
  temperature: 0.7,
  max_tokens: 1024,
});

export const defaultSplit: SplitFractions = { train: 0.7, val: 0.15, test: 0.15 };

// Replay-only dataset roles for a react run. These columns are NOT signature
// I/O — they carry the recorded tool-call steps, the allowed-tool roster, and
// per-tool schema hashes the replay reward scores against. They map onto the
// backend ReplayMapping (state_before/state_after are optional).
export type ReactReplayRole =
  | "steps"
  | "allowed_tools"
  | "tool_schema_hashes"
  | "state_before"
  | "state_after";

// A dataset column's role. Non-react runs only ever use input/output/ignore;
// react runs additionally assign the replay roles above so a single per-column
// toggle in DatasetStep covers both the signature mapping and replay mapping.
export type ColumnRole = "input" | "output" | "ignore" | ReactReplayRole;

export const REACT_REPLAY_ROLES: readonly ReactReplayRole[] = [
  "steps",
  "allowed_tools",
  "tool_schema_hashes",
  "state_before",
  "state_after",
];

// The replay roles the backend requires every react run to provide.
// state_before/state_after are required too: the gate-progress signal a metric
// scores against is the delta between them, so an unmapped snapshot silently
// collapses that signal to zero.
export const REQUIRED_REPLAY_ROLES: readonly ReactReplayRole[] = [
  "steps",
  "allowed_tools",
  "tool_schema_hashes",
  "state_before",
  "state_after",
];

// UI-side model of the react (ReAct-agent) tool-source configuration. Scoring
// is owned by the authored metric_code, not a preset, so no reward knobs live
// here. `toolFilter` is a comma-separated string. The replay mapping is NOT
// here — it is derived from the dataset column roles. `use-submit-wizard`
// reshapes this into the backend's ToolSource wire model at submit time.
export interface ReactConfig {
  toolSourceKind: "live_mcp" | "dataset_snapshot";
  mcpUrl: string;
  mcpAuthHeader: string;
  toolFilter: string;
}

export const defaultReactConfig = (): ReactConfig => ({
  toolSourceKind: "live_mcp",
  mcpUrl: "",
  mcpAuthHeader: "",
  toolFilter: "",
});

export const STEPS = [
  { id: "basics", label: msg("auto.features.submit.constants.literal.1") },
  { id: "data", label: TERMS.dataset },
  { id: "params", label: msg("auto.features.submit.constants.literal.2") },
  { id: "code", label: msg("auto.features.submit.constants.literal.3") },
  { id: "model", label: TERMS.model },
  { id: "review", label: msg("auto.features.submit.constants.literal.4") },
] as const;

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
