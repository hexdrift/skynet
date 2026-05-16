export type JobStatus = "pending" | "validating" | "running" | "success" | "failed" | "cancelled";
export type OptimizationType = "run" | "grid_search";

// Levels emitted by the backend (`backend/core/api/routers/optimizations_meta.py`).
// `(string & {})` keeps the union behaviour for autocomplete while still
// accepting any backend-future level without a TS error.
export type LogLevel = "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";

// Same brand pattern: documented values plus an escape hatch for any
// backend-future kind (`backend/core/models/dataset.py:42`).
export type ProfileKind = "categorical" | "numeric" | "freeform";

export interface ModelConfig {
  name: string;
  base_url?: string | null;
  temperature?: number | null;
  max_tokens?: number | null;
  top_p?: number | null;
  // `api_key` is the only well-known extra; the wizard reads/writes it
  // (`features/submit/hooks/use-submit-wizard.ts`). Other keys flow through
  // unchanged.
  extra?: { api_key?: string; [k: string]: unknown };
}

export interface ColumnMapping {
  inputs: Record<string, string>;
  outputs: Record<string, string>;
}

export interface SplitFractions {
  train: number;
  val: number;
  test: number;
}

export interface SplitCounts {
  train: number;
  val: number;
  test: number;
}

interface OptimizationRequestBase {
  name?: string | null;
  description?: string | null;
  username: string;
  module_name: string;
  module_kwargs?: Record<string, unknown>;
  signature_code: string;
  metric_code: string;
  optimizer_name: string;
  optimizer_kwargs?: Record<string, unknown>;
  compile_kwargs?: Record<string, unknown>;
  dataset: Array<Record<string, unknown>>;
  dataset_filename?: string | null;
  column_mapping: ColumnMapping;
  split_fractions?: SplitFractions;
  shuffle?: boolean;
  seed?: number | null;
  is_private?: boolean;
}

export interface RunRequest extends OptimizationRequestBase {
  model_config: ModelConfig;
  reflection_model_config?: ModelConfig;
  task_model_config?: ModelConfig;
}

export interface GridSearchRequest extends OptimizationRequestBase {
  generation_models: ModelConfig[];
  reflection_models: ModelConfig[];
  use_all_available_generation_models?: boolean;
  use_all_available_reflection_models?: boolean;
}

export interface OptimizationSubmissionResponse {
  optimization_id: string;
  optimization_type: OptimizationType;
  status: JobStatus;
  created_at: string;
  name?: string | null;
  description?: string | null;
  username: string;
  module_name: string;
  optimizer_name: string;
}

export interface OptimizationSummaryResponse {
  optimization_id: string;
  optimization_type: OptimizationType;
  status: JobStatus;
  message?: string | null;
  name?: string | null;
  description?: string | null;
  pinned?: boolean;
  archived?: boolean;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  elapsed?: string | null;
  elapsed_seconds?: number | null;
  estimated_remaining?: string | null;
  username?: string | null;
  module_name?: string | null;
  module_kwargs?: Record<string, unknown>;
  optimizer_name?: string | null;
  column_mapping?: ColumnMapping;
  dataset_rows?: number | null;
  latest_metrics?: Record<string, unknown>;
  model_name?: string | null;
  model_settings?: Record<string, unknown>;
  reflection_model_name?: string | null;
  task_model_name?: string | null;
  total_pairs?: number | null;
  completed_pairs?: number | null;
  failed_pairs?: number | null;
  generation_models?: ModelConfig[];
  reflection_models?: ModelConfig[];
  split_fractions?: SplitFractions;
  shuffle?: boolean;
  seed?: number | null;
  optimizer_kwargs?: Record<string, unknown>;
  compile_kwargs?: Record<string, unknown>;
  progress_count?: number | null;
  log_count?: number | null;
  baseline_test_metric?: number | null;
  optimized_test_metric?: number | null;
  metric_improvement?: number | null;
  best_pair_label?: string | null;
  task_fingerprint?: string | null;
  compare_fingerprint?: string | null;
}

export interface PaginatedJobsResponse {
  items: OptimizationSummaryResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface OptimizationLogEntry {
  timestamp: string;
  level: LogLevel | (string & {});
  logger: string;
  message: string;
  pair_index?: number | null;
}

export interface ProgressEvent {
  timestamp: string;
  event?: string | null;
  metrics: Record<string, unknown>;
}

export interface OptimizedDemo {
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
}

export interface OptimizedPredictor {
  predictor_name: string;
  signature_name?: string | null;
  instructions: string;
  input_fields: string[];
  output_fields: string[];
  demos: OptimizedDemo[];
  formatted_prompt: string;
}

export interface ProgramArtifact {
  path?: string | null;
  program_pickle_base64?: string | null;
  metadata?: Record<string, unknown>;
  optimized_prompt?: OptimizedPredictor;
}

export interface EvalExampleResult {
  index: number;
  outputs: Record<string, unknown>;
  score: number;
  pass: boolean;
  error?: string | null;
}

export interface LMStageStats {
  calls: number;
  avg_response_time_ms?: number | null;
}

export interface LMActivity {
  generation: Record<string, LMStageStats>;
  reflection: Record<string, LMStageStats>;
}

export interface PairResult {
  pair_index: number;
  generation_model: string;
  reflection_model: string;
  generation_reasoning_effort?: string | null;
  reflection_reasoning_effort?: string | null;
  baseline_test_metric?: number | null;
  optimized_test_metric?: number | null;
  metric_improvement?: number | null;
  runtime_seconds?: number | null;
  num_lm_calls?: number | null;
  avg_response_time_ms?: number | null;
  lm_activity?: LMActivity | null;
  program_artifact?: ProgramArtifact | null;
  error?: string | null;
  baseline_test_results?: EvalExampleResult[];
  optimized_test_results?: EvalExampleResult[];
}

export interface RunResult {
  module_name: string;
  optimizer_name: string;
  metric_name?: string | null;
  split_counts?: SplitCounts;
  baseline_test_metric?: number | null;
  optimized_test_metric?: number | null;
  metric_improvement?: number | null;
  optimization_metadata?: Record<string, unknown>;
  details?: Record<string, unknown>;
  program_artifact_path?: string | null;
  program_artifact?: ProgramArtifact | null;
  runtime_seconds?: number | null;
  num_lm_calls?: number | null;
  avg_response_time_ms?: number | null;
  lm_activity?: LMActivity | null;
  run_log?: OptimizationLogEntry[];
  baseline_test_results?: EvalExampleResult[];
  optimized_test_results?: EvalExampleResult[];
}

export interface GridSearchResult {
  module_name: string;
  optimizer_name: string;
  metric_name?: string | null;
  split_counts?: SplitCounts;
  total_pairs: number;
  completed_pairs: number;
  failed_pairs: number;
  pair_results: PairResult[];
  best_pair?: PairResult | null;
  runtime_seconds?: number | null;
}

export interface OptimizationStatusResponse extends OptimizationSummaryResponse {
  progress_events: ProgressEvent[];
  logs: OptimizationLogEntry[];
  result?: RunResult | null;
  grid_result?: GridSearchResult | null;
}

export interface ValidateCodeResponse {
  valid: boolean;
  signature_fields?: { inputs: string[]; outputs: string[] };
  errors: string[];
  warnings: string[];
}

export interface QueueStatusResponse {
  pending_jobs: number;
  active_jobs: number;
  worker_threads: number;
  workers_alive: boolean;
}

export interface OptimizationPayloadResponse {
  optimization_id: string;
  optimization_type: OptimizationType;
  payload: Record<string, unknown>;
}

export interface TemplateResponse {
  template_id: string;
  name: string;
  description?: string | null;
  username: string;
  config: Record<string, unknown>;
  created_at: string;
}

export interface DatasetRow {
  index: number;
  row: Record<string, unknown>;
}

export interface OptimizationDatasetResponse {
  total_rows: number;
  splits: {
    train: DatasetRow[];
    val: DatasetRow[];
    test: DatasetRow[];
  };
  column_mapping: ColumnMapping;
  split_counts: SplitCounts;
}

export interface ServeInfoResponse {
  optimization_id: string;
  module_name: string;
  optimizer_name: string;
  model_name: string;
  input_fields: string[];
  output_fields: string[];
  instructions?: string | null;
  demo_count: number;
}

export interface ServeResponse {
  optimization_id: string;
  outputs: Record<string, unknown>;
  input_fields: string[];
  output_fields: string[];
  model_used: string;
}

export interface CatalogModel {
  value: string;
  label: string;
  provider: string;
  data_center?: string | null;
  supports_thinking: boolean;
  supports_vision: boolean;
  available: boolean;
  max_input_tokens?: number | null;
}

export interface CatalogProvider {
  slug: string;
  label: string;
  data_center?: string | null;
  env_var?: string | null;
  default_base_url?: string | null;
  has_env_key: boolean;
}

export interface ModelCatalogResponse {
  providers: CatalogProvider[];
  models: CatalogModel[];
}

export interface DiscoverModelsResponse {
  models: string[];
  base_url: string;
  error?: string | null;
}

export type ProfileWarningCode =
  | "too_small"
  | "class_imbalance"
  | "rare_class"
  | "duplicates"
  | "missing_target";

export interface ProfileWarning {
  code: ProfileWarningCode;
  message: string;
  details: Record<string, unknown>;
}

export interface TargetColumnProfile {
  name: string;
  kind: ProfileKind | (string & {});
  unique_values: number;
  class_histogram: Record<string, number>;
}

export type ColumnKind = "text" | "image";

export interface InputColumnProfile {
  name: string;
  kind: ColumnKind;
}

export interface DatasetProfile {
  row_count: number;
  column_count: number;
  target: TargetColumnProfile | null;
  targets: TargetColumnProfile[];
  inputs: InputColumnProfile[];
  duplicate_count: number;
  warnings: ProfileWarning[];
}

export interface SplitPlan {
  fractions: SplitFractions;
  shuffle: boolean;
  seed: number;
  counts: SplitCounts;
  rationale: string[];
}

export interface ProfileDatasetRequest {
  dataset: Array<Record<string, unknown>>;
  column_mapping: ColumnMapping;
  seed?: number | null;
}

export interface ProfileDatasetResponse {
  profile: DatasetProfile;
  plan: SplitPlan;
}
