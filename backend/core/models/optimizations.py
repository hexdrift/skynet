"""Outbound payloads for GET /optimizations/* endpoints."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .artifacts import ProgramArtifact
from .common import ColumnMapping, OptimizationStatus, SplitFractions
from .results import GridSearchResponse, RunResponse
from .telemetry import JobLogEntry, ProgressEvent


class _JobResponseBase(BaseModel):
    """Shared fields across job response endpoints."""

    optimization_id: str
    optimization_type: str
    status: OptimizationStatus
    message: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    pinned: bool = False
    archived: bool = False

    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    elapsed: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    estimated_remaining: Optional[str] = None

    username: Optional[str] = None
    module_name: Optional[str] = None
    module_kwargs: Dict[str, Any] = Field(default_factory=dict)
    optimizer_name: Optional[str] = None
    column_mapping: Optional[ColumnMapping] = None
    dataset_rows: Optional[int] = None

    latest_metrics: Dict[str, Any] = Field(default_factory=dict)

    # Run-specific (null for grid search)
    model_name: Optional[str] = None
    model_settings: Optional[Dict[str, Any]] = None
    reflection_model_name: Optional[str] = None
    prompt_model_name: Optional[str] = None
    task_model_name: Optional[str] = None

    # Grid-search-specific (null for run)
    total_pairs: Optional[int] = None
    completed_pairs: Optional[int] = None
    failed_pairs: Optional[int] = None
    generation_models: Optional[List[Any]] = None
    reflection_models: Optional[List[Any]] = None


class OptimizationStatusResponse(_JobResponseBase):
    """Full job detail returned by GET /jobs/{id}."""

    progress_events: List[ProgressEvent] = Field(default_factory=list)
    logs: List[JobLogEntry] = Field(default_factory=list)
    result: Optional[RunResponse] = None
    grid_result: Optional[GridSearchResponse] = None


class OptimizationSummaryResponse(_JobResponseBase):
    """Lightweight dashboard view of a job."""

    split_fractions: Optional[SplitFractions] = None
    shuffle: Optional[bool] = None
    seed: Optional[int] = None
    optimizer_kwargs: Dict[str, Any] = Field(default_factory=dict)
    compile_kwargs: Dict[str, Any] = Field(default_factory=dict)
    progress_count: int = 0
    log_count: int = 0

    # Metrics (run: direct values; grid search: best pair's values)
    baseline_test_metric: Optional[float] = None
    optimized_test_metric: Optional[float] = None
    metric_improvement: Optional[float] = None

    best_pair_label: Optional[str] = None


class PaginatedJobsResponse(BaseModel):
    """Paginated wrapper for job listings."""

    items: List[OptimizationSummaryResponse] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


class OptimizationCountsResponse(BaseModel):
    """Aggregate counts by status for dashboard stat cards.

    The dashboard fetches pages incrementally via infinite scroll, so
    counting locally-loaded items would under-report totals. This
    endpoint runs cheap ``COUNT`` queries and returns the full picture
    in one call.
    """

    total: int = 0
    pending: int = 0
    validating: int = 0
    running: int = 0
    success: int = 0
    failed: int = 0
    cancelled: int = 0


class JobCancelResponse(BaseModel):
    """Response payload for the cancel endpoint."""

    optimization_id: str
    status: str


class JobDeleteResponse(BaseModel):
    """Response payload for the delete endpoint."""

    optimization_id: str
    deleted: bool


class BulkDeleteSkipped(BaseModel):
    """One entry in the ``skipped`` list of a bulk-delete response."""

    optimization_id: str
    reason: str


class BulkDeleteRequest(BaseModel):
    """Request payload for the bulk-delete endpoint."""

    optimization_ids: List[str] = Field(default_factory=list)


class BulkDeleteResponse(BaseModel):
    """Response payload for the bulk-delete endpoint."""

    deleted: List[str] = Field(default_factory=list)
    skipped: List[BulkDeleteSkipped] = Field(default_factory=list)


class OptimizationPayloadResponse(BaseModel):
    """Response payload for the payload retrieval endpoint."""

    optimization_id: str
    optimization_type: str
    payload: Dict[str, Any]


class ProgramArtifactResponse(BaseModel):
    """Response payload for the artifact retrieval endpoint.

    Attributes:
        program_artifact: Serialized artifact containing base64-encoded program pickle.
    """

    program_artifact: Optional[ProgramArtifact]
