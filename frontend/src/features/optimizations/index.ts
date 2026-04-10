/**
 * Optimizations feature — public API.
 *
 * Currently exposes only the pure helpers and constants extracted from
 * app/optimizations/[id]/page.tsx. Full decomposition of the 2735-line
 * page body into tab components + hooks is a dedicated follow-up
 * (audit #13).
 */
export { STATUS_COLORS, PIPELINE_STAGES, STAGE_INFO, type PipelineStage } from "./constants";
export { formatPercent, formatImprovement, jsonPreview, formatDuration, formatLogTimestamp, logTimeBucket, formatOutput } from "./lib/formatters";
export { detectStage } from "./lib/detect-stage";
export { extractScoresFromLogs, type ScorePoint } from "./lib/extract-scores";
export { DataTab } from "./components/DataTab";
export { LogsTab } from "./components/LogsTab";
export { ExportMenu, exportPromptAsJson, exportLogsAsCsv } from "./components/ExportMenu";
export { DeleteJobDialog } from "./components/DeleteJobDialog";
export { StatusBadge, InfoCard, LangPicker, CopyButton } from "./components/ui-primitives";
export { ServeCodeSnippets } from "./components/ServeCodeSnippets";
export { ServeChat, type ServeChatProps } from "./components/ServeChat";
export { ConfigTab } from "./components/ConfigTab";
