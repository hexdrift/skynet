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
  OptimizedPredictor,
  PairResult,
  OptimizationStatusResponse,
  ValidateCodeResponse,
  QueueStatusResponse,
  OptimizationPayloadResponse,
  TemplateResponse,
  DatasetRow,
  OptimizationDatasetResponse,
  EvalExampleResult,
  ServeInfoResponse,
  CatalogModel,
  CatalogProvider,
  ModelCatalogResponse,
  DiscoverModelsResponse,
} from "./api";

// Alias for cleaner imports
export type { OptimizationSummaryResponse as Job } from "./api";
