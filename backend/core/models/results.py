"""Outbound result payloads for single optimization runs and grid searches."""

from typing import Any

from pydantic import BaseModel, Field

from .artifacts import ProgramArtifact
from .common import SplitCounts
from .telemetry import JobLogEntry


class RunResponse(BaseModel):
    """Result of a single optimization run."""

    module_name: str
    optimizer_name: str
    metric_name: str | None
    split_counts: SplitCounts
    baseline_test_metric: float | None = None
    optimized_test_metric: float | None = None
    metric_improvement: float | None = None
    optimization_metadata: dict[str, Any] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)
    program_artifact_path: str | None = None
    program_artifact: ProgramArtifact | None = None
    runtime_seconds: float | None = None
    num_lm_calls: int | None = None
    avg_response_time_ms: float | None = None
    run_log: list[JobLogEntry] = Field(default_factory=list)
    baseline_test_results: list[dict[str, Any]] = Field(default_factory=list)
    optimized_test_results: list[dict[str, Any]] = Field(default_factory=list)


class PairResult(BaseModel):
    """Result of a single (generation, reflection) model pair run."""

    pair_index: int
    generation_model: str
    reflection_model: str
    baseline_test_metric: float | None = None
    optimized_test_metric: float | None = None
    metric_improvement: float | None = None
    runtime_seconds: float | None = None
    num_lm_calls: int | None = None
    avg_response_time_ms: float | None = None
    program_artifact: ProgramArtifact | None = None
    error: str | None = None
    baseline_test_results: list[dict[str, Any]] = Field(default_factory=list)
    optimized_test_results: list[dict[str, Any]] = Field(default_factory=list)


class GridSearchResponse(BaseModel):
    """Result of a grid search over model pairs.

    Contains a leaderboard of per-pair scores and highlights the best config.
    """

    module_name: str
    optimizer_name: str
    metric_name: str | None = None
    split_counts: SplitCounts
    total_pairs: int
    completed_pairs: int = 0
    failed_pairs: int = 0
    pair_results: list[PairResult] = Field(default_factory=list)
    best_pair: PairResult | None = None
    runtime_seconds: float | None = None
