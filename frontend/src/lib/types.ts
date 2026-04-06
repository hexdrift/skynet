/* ── Job lifecycle ── */
export type JobStatus = "pending" | "validating" | "running" | "success" | "failed" | "cancelled";
export type JobType = "run" | "grid_search";

/* ── Request models ── */
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
  username: string;
  module_name: string;
  module_kwargs?: Record<string, unknown>;
  signature_code: string;
  metric_code: string;
  optimizer_name: string;
  optimizer_kwargs?: Record<string, unknown>;
  compile_kwargs?: Record<string, unknown>;
  dataset: Record<string, unknown>[];
  column_mapping: ColumnMapping;
  split_fractions?: SplitFractions;
  shuffle?: boolean;
  seed?: number;
}

export interface RunRequest extends OptimizationRequestBase {
  model_config: ModelConfig;
  reflection_model_config?: ModelConfig;
  prompt_model_config?: ModelConfig;
  task_model_config?: ModelConfig;
}

export interface GridSearchRequest extends OptimizationRequestBase {
  generation_models: ModelConfig[];
  reflection_models: ModelConfig[];
}

/* ── Response models ── */
export interface JobSubmissionResponse {
  job_id: string;
  job_type: JobType;
  status: JobStatus;
  created_at: string;
  name?: string;
  username: string;
  module_name: string;
  optimizer_name: string;
}

export interface JobSummaryResponse {
  job_id: string;
  job_type: JobType;
  status: JobStatus;
  message?: string;
  name?: string;
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
  prompt_model_name?: string;
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
}

export interface PaginatedJobsResponse {
  items: JobSummaryResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface JobLogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
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
  baseline_test_metric?: number;
  optimized_test_metric?: number;
  metric_improvement?: number;
  runtime_seconds?: number;
  program_artifact?: ProgramArtifact;
  error?: string;
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

export interface JobStatusResponse extends JobSummaryResponse {
  progress_events: ProgressEvent[];
  logs: JobLogEntry[];
  result?: RunResult;
  grid_result?: GridSearchResult;
}

export interface ValidateCodeResponse {
  valid: boolean;
  signature_fields?: { inputs: string[]; outputs: string[] };
  errors: string[];
  warnings: string[];
}

export interface HealthResponse {
  status: string;
  registered_assets: Record<string, string[]>;
}

export interface QueueStatusResponse {
  pending_jobs: number;
  active_jobs: number;
  worker_threads: number;
  workers_alive: boolean;
}

export interface JobPayloadResponse {
  job_id: string;
  job_type: JobType;
  payload: Record<string, unknown>;
}

/* ── Templates ── */

export interface TemplateResponse {
  template_id: string;
  name: string;
  description?: string;
  username: string;
  config: Record<string, unknown>;
  created_at: string;
}

/* ── Serving ── */

export interface ServeInfoResponse {
  job_id: string;
  module_name: string;
  optimizer_name: string;
  model_name: string;
  input_fields: string[];
  output_fields: string[];
  instructions?: string;
  demo_count: number;
}

export interface ServeResponse {
  job_id: string;
  outputs: Record<string, unknown>;
  input_fields: string[];
  output_fields: string[];
  model_used: string;
}

/* ── Model catalog ── */

export interface CatalogModel {
  value: string;
  label: string;
  provider: string;
  supports_thinking: boolean;
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
