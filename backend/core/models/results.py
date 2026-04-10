"""Outbound result payloads for single optimization runs and grid searches."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .artifacts import ProgramArtifact
from .common import SplitCounts
from .telemetry import JobLogEntry


class RunResponse(BaseModel):
    """Result of a single optimization run."""

    module_name: str
    optimizer_name: str
    metric_name: Optional[str]
    split_counts: SplitCounts
    baseline_test_metric: Optional[float] = None
    optimized_test_metric: Optional[float] = None
    metric_improvement: Optional[float] = None
    optimization_metadata: Dict[str, Any] = Field(default_factory=dict)
    details: Dict[str, Any] = Field(default_factory=dict)
    program_artifact_path: Optional[str] = None
    program_artifact: Optional[ProgramArtifact] = None
    runtime_seconds: Optional[float] = None
    num_lm_calls: Optional[int] = None
    avg_response_time_ms: Optional[float] = None
    run_log: List[JobLogEntry] = Field(default_factory=list)
    baseline_test_results: List[Dict[str, Any]] = Field(default_factory=list)
    optimized_test_results: List[Dict[str, Any]] = Field(default_factory=list)


class PairResult(BaseModel):
    """Result of a single (generation, reflection) model pair run."""

    pair_index: int
    generation_model: str
    reflection_model: str
    baseline_test_metric: Optional[float] = None
    optimized_test_metric: Optional[float] = None
    metric_improvement: Optional[float] = None
    runtime_seconds: Optional[float] = None
    num_lm_calls: Optional[int] = None
    avg_response_time_ms: Optional[float] = None
    program_artifact: Optional[ProgramArtifact] = None
    error: Optional[str] = None
    baseline_test_results: List[Dict[str, Any]] = Field(default_factory=list)
    optimized_test_results: List[Dict[str, Any]] = Field(default_factory=list)


class GridSearchResponse(BaseModel):
    """Result of a grid search over model pairs.

    Contains a leaderboard of per-pair scores and highlights the best config.
    """

    module_name: str
    optimizer_name: str
    metric_name: Optional[str] = None
    split_counts: SplitCounts
    total_pairs: int
    completed_pairs: int = 0
    failed_pairs: int = 0
    pair_results: List[PairResult] = Field(default_factory=list)
    best_pair: Optional[PairResult] = None
    runtime_seconds: Optional[float] = None
