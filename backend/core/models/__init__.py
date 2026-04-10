"""Public re-exports for backwards compatibility.

Historically ``backend/core/models.py`` was a single 648-line file. It was
split into per-domain sub-modules per AGENTS.md, but every downstream import
site still writes ``from ..models import X``, so this ``__init__.py``
re-exports the old flat surface.
"""
from .analytics import (
    AnalyticsSummaryResponse,
    ModelStatsItem,
    ModelStatsResponse,
    OptimizerStatsItem,
    OptimizerStatsResponse,
)
from .artifacts import OptimizedDemo, OptimizedPredictor, ProgramArtifact
from .common import (
    HEALTH_STATUS_OK,
    ColumnMapping,
    ModelConfig,
    OptimizationStatus,
    SplitCounts,
    SplitFractions,
)
from .infra import HealthResponse, QueueStatusResponse
from .optimizations import (
    JobCancelResponse,
    JobDeleteResponse,
    OptimizationPayloadResponse,
    OptimizationStatusResponse,
    OptimizationSummaryResponse,
    PaginatedJobsResponse,
    ProgramArtifactResponse,
    _JobResponseBase,
)
from .results import GridSearchResponse, PairResult, RunResponse
from .serve import ServeInfoResponse, ServeRequest, ServeResponse
from .submissions import (
    GridSearchRequest,
    OptimizationSubmissionResponse,
    RunRequest,
    _OptimizationRequestBase,
)
from .telemetry import JobLogEntry, ProgressEvent
from .templates import TemplateCreateRequest, TemplateResponse
from .validation import ValidateCodeRequest, ValidateCodeResponse

__all__ = [
    # common
    "HEALTH_STATUS_OK",
    "ColumnMapping",
    "ModelConfig",
    "OptimizationStatus",
    "SplitCounts",
    "SplitFractions",
    # telemetry
    "JobLogEntry",
    "ProgressEvent",
    # artifacts
    "OptimizedDemo",
    "OptimizedPredictor",
    "ProgramArtifact",
    # results
    "GridSearchResponse",
    "PairResult",
    "RunResponse",
    # submissions
    "GridSearchRequest",
    "OptimizationSubmissionResponse",
    "RunRequest",
    "_OptimizationRequestBase",
    # optimizations
    "JobCancelResponse",
    "JobDeleteResponse",
    "OptimizationPayloadResponse",
    "OptimizationStatusResponse",
    "OptimizationSummaryResponse",
    "PaginatedJobsResponse",
    "ProgramArtifactResponse",
    "_JobResponseBase",
    # validation
    "ValidateCodeRequest",
    "ValidateCodeResponse",
    # serve
    "ServeInfoResponse",
    "ServeRequest",
    "ServeResponse",
    # templates
    "TemplateCreateRequest",
    "TemplateResponse",
    # analytics
    "AnalyticsSummaryResponse",
    "ModelStatsItem",
    "ModelStatsResponse",
    "OptimizerStatsItem",
    "OptimizerStatsResponse",
    # infra
    "HealthResponse",
    "QueueStatusResponse",
]
