export type JobStatus = "pending" | "validating" | "running" | "success" | "failed" | "cancelled";
export type OptimizationType = "run" | "grid_search";

export interface ModelConfig {
  name: string;
  base_url?: string;
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
  extra?: Record<string, unknown>;
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

interface OptimizationRequestBase {
  name?: string;
  description?: string;
  username: string;
  module_name: string;
  module_kwargs?: Record<string, unknown>;
  signature_code: string;
  metric_code: string;
  optimizer_name: string;
  optimizer_kwargs?: Record<string, unknown>;
  compile_kwargs?: Record<string, unknown>;
  dataset: Array<Record<string, unknown>>;
  column_mapping: ColumnMapping;
  split_fractions?: SplitFractions;
  shuffle?: boolean;
  seed?: number;
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
  name?: string;
  description?: string;
  username: string;
  module_name: string;
  optimizer_name: string;
}

export interface OptimizationSummaryResponse {
  optimization_id: string;
  optimization_type: OptimizationType;
  status: JobStatus;
  message?: string;
  name?: string;
  description?: string;
  pinned?: boolean;
  archived?: boolean;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  elapsed?: string;
  elapsed_seconds?: number;
  estimated_remaining?: string;
  username?: string;
  module_name?: string;
  module_kwargs?: Record<string, unknown>;
  optimizer_name?: string;
  column_mapping?: ColumnMapping;
  dataset_rows?: number;
  latest_metrics?: Record<string, unknown>;
  model_name?: string;
  model_settings?: Record<string, unknown>;
  reflection_model_name?: string;
  task_model_name?: string;
  total_pairs?: number;
  completed_pairs?: number;
  failed_pairs?: number;
  generation_models?: ModelConfig[];
  reflection_models?: ModelConfig[];
  split_fractions?: SplitFractions;
  shuffle?: boolean;
  seed?: number;
  optimizer_kwargs?: Record<string, unknown>;
  compile_kwargs?: Record<string, unknown>;
  progress_count?: number;
  log_count?: number;
  baseline_test_metric?: number;
  optimized_test_metric?: number;
  metric_improvement?: number;
  best_pair_label?: string;
  task_fingerprint?: string;
}

export interface PaginatedJobsResponse {
  items: OptimizationSummaryResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface OptimizationLogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
  pair_index?: number | null;
}

export interface ProgressEvent {
  timestamp: string;
  event?: string;
  metrics: Record<string, unknown>;
}

export interface OptimizedDemo {
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
}

export interface OptimizedPredictor {
  predictor_name: string;
  signature_name?: string;
  instructions: string;
  input_fields: string[];
  output_fields: string[];
  demos: OptimizedDemo[];
  formatted_prompt: string;
}

export interface ProgramArtifact {
  path?: string;
  program_pickle_base64?: string;
  metadata?: Record<string, unknown>;
  optimized_prompt?: OptimizedPredictor;
}

export interface PairResult {
  pair_index: number;
  generation_model: string;
  reflection_model: string;
  generation_reasoning_effort?: string | null;
  reflection_reasoning_effort?: string | null;
  baseline_test_metric?: number;
  optimized_test_metric?: number;
  metric_improvement?: number;
  runtime_seconds?: number;
  num_lm_calls?: number;
  avg_response_time_ms?: number;
  program_artifact?: ProgramArtifact;
  error?: string;
  baseline_test_results?: EvalExampleResult[];
  optimized_test_results?: EvalExampleResult[];
}

export interface RunResult {
  module_name: string;
  optimizer_name: string;
  metric_name?: string;
  split_counts?: { train: number; val: number; test: number };
  baseline_test_metric?: number;
  optimized_test_metric?: number;
  metric_improvement?: number;
  program_artifact?: ProgramArtifact;
  runtime_seconds?: number;
  num_lm_calls?: number;
  avg_response_time_ms?: number;
}

export interface GridSearchResult {
  module_name: string;
  optimizer_name: string;
  metric_name?: string;
  split_counts?: { train: number; val: number; test: number };
  total_pairs: number;
  completed_pairs: number;
  failed_pairs: number;
  pair_results: PairResult[];
  best_pair?: PairResult;
  runtime_seconds?: number;
}

export interface OptimizationStatusResponse extends OptimizationSummaryResponse {
  progress_events: ProgressEvent[];
  logs: OptimizationLogEntry[];
  result?: RunResult;
  grid_result?: GridSearchResult;
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
  description?: string;
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
  split_counts: { train: number; val: number; test: number };
}

export interface EvalExampleResult {
  index: number;
  outputs: Record<string, unknown>;
  score: number;
  pass: boolean;
  error?: string;
}

export interface ServeInfoResponse {
  optimization_id: string;
  module_name: string;
  optimizer_name: string;
  model_name: string;
  input_fields: string[];
  output_fields: string[];
  instructions?: string;
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
  supports_thinking: boolean;
  supports_vision: boolean;
  available: boolean;
  max_input_tokens?: number;
}

export interface CatalogProvider {
  slug: string;
  label: string;
  env_var?: string;
  default_base_url?: string;
  has_env_key: boolean;
}

export interface ModelCatalogResponse {
  providers: CatalogProvider[];
  models: CatalogModel[];
}

export interface DiscoverModelsResponse {
  models: string[];
  base_url: string;
  error?: string;
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
  kind: "categorical" | "numeric" | "freeform" | string;
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
  counts: { train: number; val: number; test: number };
  stratify: boolean;
  stratify_column: string | null;
  rationale: string[];
}

export interface ProfileDatasetRequest {
  dataset: Array<Record<string, unknown>>;
  column_mapping: ColumnMapping;
  seed?: number;
}

export interface ProfileDatasetResponse {
  profile: DatasetProfile;
  plan: SplitPlan;
}
