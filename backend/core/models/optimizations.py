"""Outbound payloads for GET /optimizations/* endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .artifacts import ProgramArtifact
from .common import ColumnMapping, OptimizationStatus, OptimizationType, SplitFractions
from .results import GridSearchResponse, RunResponse
from .telemetry import JobLogEntry, ProgressEvent


class _JobResponseBase(BaseModel):
    """Shared fields across optimization response endpoints."""

    optimization_id: str
    optimization_type: OptimizationType
    status: OptimizationStatus
    message: str | None = None
    name: str | None = None
    description: str | None = None
    pinned: bool = False
    archived: bool = False

    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    elapsed: str | None = None
    elapsed_seconds: float | None = None
    estimated_remaining: str | None = None

    username: str | None = None
    module_name: str | None = None
    module_kwargs: dict[str, Any] = Field(default_factory=dict)
    optimizer_name: str | None = None
    column_mapping: ColumnMapping | None = None
    dataset_rows: int | None = None

    latest_metrics: dict[str, Any] = Field(default_factory=dict)

    # Run-specific (null for grid search)
    model_name: str | None = None
    model_settings: dict[str, Any] | None = None
    reflection_model_name: str | None = None
    task_model_name: str | None = None

    # Grid-search-specific (null for run)
    total_pairs: int | None = None
    completed_pairs: int | None = None
    failed_pairs: int | None = None
    generation_models: list[Any] | None = None
    reflection_models: list[Any] | None = None


class OptimizationStatusResponse(_JobResponseBase):
    """Full optimization detail returned by GET /optimizations/{optimization_id}."""

    progress_events: list[ProgressEvent] = Field(default_factory=list)
    logs: list[JobLogEntry] = Field(default_factory=list)
    result: RunResponse | None = None
    grid_result: GridSearchResponse | None = None


class OptimizationSummaryResponse(_JobResponseBase):
    """Lightweight dashboard view of an optimization."""

    split_fractions: SplitFractions | None = None
    shuffle: bool | None = None
    seed: int | None = None
    optimizer_kwargs: dict[str, Any] = Field(default_factory=dict)
    compile_kwargs: dict[str, Any] = Field(default_factory=dict)
    progress_count: int = 0
    log_count: int = 0

    # Metrics (run: direct values; grid search: best pair's values)
    baseline_test_metric: float | None = None
    optimized_test_metric: float | None = None
    metric_improvement: float | None = None

    best_pair_label: str | None = None

    # Stable hash of (signature_code, metric_code, dataset_content).
    # Two optimizations with the same fingerprint can be compared apples-to-apples.
    # ``None`` on optimizations submitted before this field was introduced.
    task_fingerprint: str | None = None


class PaginatedJobsResponse(BaseModel):
    """Paginated wrapper for optimization listings."""

    items: list[OptimizationSummaryResponse] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


class OptimizationCountsResponse(BaseModel):
    """Aggregate counts by status for dashboard stat cards."""

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

    optimization_ids: list[str] = Field(default_factory=list)


class BulkDeleteResponse(BaseModel):
    """Response payload for the bulk-delete endpoint."""

    deleted: list[str] = Field(default_factory=list)
    skipped: list[BulkDeleteSkipped] = Field(default_factory=list)


class BulkCancelSkipped(BaseModel):
    """One entry in the ``skipped`` list of a bulk-cancel response."""

    optimization_id: str
    reason: str


class BulkCancelRequest(BaseModel):
    """Request payload for the bulk-cancel endpoint."""

    optimization_ids: list[str] = Field(default_factory=list)


class BulkCancelResponse(BaseModel):
    """Response payload for the bulk-cancel endpoint."""

    cancelled: list[str] = Field(default_factory=list)
    skipped: list[BulkCancelSkipped] = Field(default_factory=list)


class OptimizationPayloadResponse(BaseModel):
    """Response payload for the payload retrieval endpoint."""

    optimization_id: str
    optimization_type: OptimizationType
    payload: dict[str, Any]


class ProgramArtifactResponse(BaseModel):
    """Response payload for the artifact retrieval endpoint."""

    program_artifact: ProgramArtifact | None
