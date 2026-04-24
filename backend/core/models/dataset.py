"""Models for dataset profiling and automatic split-plan recommendations.

Descriptive shapes returned by ``POST /datasets/profile``. The profiler
produces a ``DatasetProfile`` summarizing an uploaded dataset, and the
planner turns that profile into a ``SplitPlan`` the submit wizard renders
as the "we'll split it like this" card. Users can accept the plan or
override it on final submission.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .common import ColumnMapping, SplitCounts, SplitFractions


class ProfileWarningCode(str, Enum):
    """Machine-readable codes for profiler warnings surfaced to the UI."""

    too_small = "too_small"
    class_imbalance = "class_imbalance"
    rare_class = "rare_class"
    duplicates = "duplicates"
    missing_target = "missing_target"


class ProfileWarning(BaseModel):
    """Single profiler finding that the user should see before submitting."""

    code: ProfileWarningCode
    message: str = Field(description="Human-readable Hebrew message for the submit wizard.")
    details: dict[str, Any] = Field(default_factory=dict)


class TargetColumnProfile(BaseModel):
    """Summary of the output column chosen as the primary target."""

    name: str
    kind: str = Field(description="One of 'categorical', 'numeric', 'freeform'.")
    unique_values: int = Field(ge=0)
    class_histogram: dict[str, int] = Field(
        default_factory=dict,
        description="Class → count map; empty for non-categorical targets.",
    )


class DatasetProfile(BaseModel):
    """Structural summary of an uploaded dataset."""

    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    target: TargetColumnProfile | None = Field(
        default=None,
        description=(
            "Primary target the planner reasons about. The first categorical "
            "column among the outputs (or the first output if none are "
            "categorical), kept for convenience and backward compatibility."
        ),
    )
    targets: list[TargetColumnProfile] = Field(
        default_factory=list,
        description="Profile for every output column, in mapping order.",
    )
    duplicate_count: int = Field(default=0, ge=0)
    warnings: list[ProfileWarning] = Field(default_factory=list)


class SplitPlan(BaseModel):
    """Recommended split configuration for a profiled dataset."""

    fractions: SplitFractions
    shuffle: bool
    seed: int = Field(ge=0)
    counts: SplitCounts
    stratify: bool = Field(
        default=False,
        description=(
            "When true, the planner recommends stratified sampling so rare "
            "classes survive in val and test."
        ),
    )
    stratify_column: str | None = Field(
        default=None,
        description=(
            "Dataset column whose values define the strata when stratify is "
            "true. Null otherwise."
        ),
    )
    rationale: list[str] = Field(
        default_factory=list,
        description="Ordered list of short Hebrew bullets explaining each decision.",
    )


class ProfileDatasetRequest(BaseModel):
    """Inbound body for ``POST /datasets/profile``."""

    dataset: list[dict[str, Any]]
    column_mapping: ColumnMapping
    seed: int | None = Field(
        default=None,
        description="Optional RNG seed for reproducibility; a random one is chosen if omitted.",
    )


class ProfileDatasetResponse(BaseModel):
    """Outbound body for ``POST /datasets/profile``."""

    profile: DatasetProfile
    plan: SplitPlan
