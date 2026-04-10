"""Aggregation response models for /analytics/* endpoints."""
from typing import List, Optional

from pydantic import BaseModel, Field


class AnalyticsSummaryResponse(BaseModel):
    """Pre-computed KPIs across all filtered jobs."""

    total_jobs: int = 0
    success_count: int = 0
    failed_count: int = 0
    cancelled_count: int = 0
    pending_count: int = 0
    running_count: int = 0
    success_rate: float = 0.0
    avg_improvement: Optional[float] = None
    max_improvement: Optional[float] = None
    min_improvement: Optional[float] = None
    avg_runtime: Optional[float] = None
    total_dataset_rows: int = 0
    total_pairs: int = 0
    completed_pairs: int = 0
    failed_pairs: int = 0


class OptimizerStatsItem(BaseModel):
    """Per-optimizer aggregated statistics."""

    name: str
    total_jobs: int = 0
    success_count: int = 0
    avg_improvement: Optional[float] = None
    success_rate: float = 0.0
    avg_runtime: Optional[float] = None


class OptimizerStatsResponse(BaseModel):
    """Response payload for /analytics/optimizers endpoint."""

    items: List[OptimizerStatsItem] = Field(default_factory=list)


class ModelStatsItem(BaseModel):
    """Per-model aggregated statistics."""

    name: str
    total_jobs: int = 0
    success_count: int = 0
    avg_improvement: Optional[float] = None
    success_rate: float = 0.0
    use_count: int = 0


class ModelStatsResponse(BaseModel):
    """Response payload for /analytics/models endpoint."""

    items: List[ModelStatsItem] = Field(default_factory=list)
