"""Pydantic request and response models local to the optimizations routes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from ....i18n import CLONE_NAME_PREFIX
from ....models import OptimizationSubmissionResponse


class SidebarJobItem(BaseModel):
    """Compact per-optimization entry for the sidebar navigation list."""

    optimization_id: str
    status: str
    name: str | None = None
    module_name: str | None = None
    optimizer_name: str | None = None
    model_name: str | None = None
    username: str | None = None
    created_at: datetime | None = None
    pinned: bool = False
    optimization_type: str | None = None
    total_pairs: int | None = None


class SidebarJobsResponse(BaseModel):
    """Paginated response for the sidebar optimization list."""

    items: list[SidebarJobItem]
    total: int


class CloneJobRequest(BaseModel):
    """Request body for cloning an optimization."""

    count: int = Field(default=1, ge=1, le=5, description="Number of copies to create (1–5).")
    name_prefix: str | None = Field(
        default=None,
        max_length=100,
        description=f"Prefix prepended to each clone's name. Defaults to '{CLONE_NAME_PREFIX}'.",
    )


class CloneJobResponse(BaseModel):
    """List of newly-created clones plus the source id for reference."""

    source_optimization_id: str
    created: list[OptimizationSubmissionResponse]


class CompareJobsRequest(BaseModel):
    """Request body for side-by-side comparison of 2–5 optimizations."""

    optimization_ids: list[str] = Field(min_length=2, max_length=5)


class CompareJobSnapshot(BaseModel):
    """Compact per-optimization snapshot used in comparison responses."""

    optimization_id: str
    status: str
    name: str | None = None
    optimization_type: str | None = None
    module_name: str | None = None
    optimizer_name: str | None = None
    model_name: str | None = None
    dataset_rows: int | None = None
    baseline_test_metric: float | None = None
    optimized_test_metric: float | None = None
    metric_improvement: float | None = None


class CompareJobsResponse(BaseModel):
    """Response for POST /optimizations/compare."""

    jobs: list[CompareJobSnapshot]
    differing_fields: list[str]
    missing_optimization_ids: list[str]


class BulkMetadataRequest(BaseModel):
    """Request body for bulk pin or bulk archive."""

    optimization_ids: list[str] = Field(min_length=1, max_length=100)
    value: bool = Field(description="Target state — true to pin/archive, false to clear.")


class BulkMetadataSkipped(BaseModel):
    """An optimization that was omitted from a bulk update, with a human-readable reason."""

    optimization_id: str
    reason: str


class BulkMetadataResponse(BaseModel):
    """Response for POST /optimizations/bulk-pin and /bulk-archive."""

    updated: list[str]
    skipped: list[BulkMetadataSkipped]
