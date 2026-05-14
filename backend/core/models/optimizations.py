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

    model_name: str | None = Field(default=None, description="Single-run model name; null for grid searches.")
    model_settings: dict[str, Any] | None = Field(
        default=None, description="Single-run model settings; null for grid searches."
    )
    reflection_model_name: str | None = Field(
        default=None, description="Single-run reflection model name; null for grid searches."
    )
    task_model_name: str | None = Field(
        default=None, description="Single-run task model name; null for grid searches."
    )

    total_pairs: int | None = Field(default=None, description="Grid-search pair count; null for single runs.")
    completed_pairs: int | None = Field(
        default=None, description="Grid-search pairs that finished; null for single runs."
    )
    failed_pairs: int | None = Field(
        default=None, description="Grid-search pairs that errored; null for single runs."
    )
    generation_models: list[Any] | None = Field(
        default=None, description="Grid-search generation model list; null for single runs."
    )
    reflection_models: list[Any] | None = Field(
        default=None, description="Grid-search reflection model list; null for single runs."
    )

    # Stable hash of (signature_code, metric_code, dataset_content).
    # Two optimizations with the same fingerprint share the same task definition,
    # but they may still evaluate on different test splits if their seeds,
    # shuffle flags, or split fractions differ — use ``compare_fingerprint`` to
    # gate row-by-row comparison. ``None`` on optimizations submitted before
    # this field was introduced.
    task_fingerprint: str | None = None

    # Stable hash of (task_fingerprint, effective_seed, shuffle, split_fractions).
    # Two optimizations with the same compare_fingerprint evaluate on byte-identical
    # train/val/test splits and are safe to compare row-by-row. Derived at read
    # time so legacy jobs whose stored seed is ``None`` are gated by the same
    # ``stable_seed(optimization_id)`` fallback the split endpoints use.
    compare_fingerprint: str | None = None


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

    baseline_test_metric: float | None = Field(
        default=None,
        description="Baseline test metric; for grid searches this is the best pair's value.",
    )
    optimized_test_metric: float | None = Field(
        default=None,
        description="Optimized test metric; for grid searches this is the best pair's value.",
    )
    metric_improvement: float | None = Field(
        default=None,
        description="Metric improvement; for grid searches this is the best pair's value.",
    )

    best_pair_label: str | None = None


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
