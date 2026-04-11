/**
 * Shared type definitions
 * Re-exports core types from lib/types.ts for use in feature slices
 * Single source of truth for types matching backend Pydantic schemas
 */

export type {
  JobStatus,
  OptimizationType,
  ModelConfig,
  ColumnMapping,
  SplitFractions,
  RunRequest,
  GridSearchRequest,
  OptimizationSubmissionResponse,
  OptimizationSummaryResponse,
  PaginatedJobsResponse,
  OptimizationLogEntry,
  ProgressEvent,
  OptimizedDemo,
  OptimizedPredictor,
  ProgramArtifact,
  PairResult,
  RunResult,
  GridSearchResult,
  OptimizationStatusResponse,
  ValidateCodeResponse,
  HealthResponse,
  QueueStatusResponse,
  OptimizationPayloadResponse,
  TemplateResponse,
  DatasetRow,
  OptimizationDatasetResponse,
  EvalExampleResult,
  ServeInfoResponse,
  ServeResponse,
  CatalogModel,
  CatalogProvider,
  ModelCatalogResponse,
  DiscoverModelsResponse,
} from "@/lib/types";

// Alias for cleaner imports
export type { OptimizationSummaryResponse as Job } from "@/lib/types";
