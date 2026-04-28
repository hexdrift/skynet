"""Public re-exports for backwards compatibility.

Historically ``backend/core/models.py`` was a single 648-line file. It was
split into per-domain sub-modules per AGENTS.md, but every downstream import
site still writes ``from ..models import X``, so this ``__init__.py``
re-exports the old flat surface.
"""

from __future__ import annotations

from .analytics import (
    AnalyticsSummaryResponse,
    DashboardAnalyticsJob,
    DashboardAnalyticsNameValue,
    DashboardAnalyticsOptimizerAverage,
    DashboardAnalyticsResponse,
    DashboardAnalyticsTimelineBucket,
    ModelStatsItem,
    ModelStatsResponse,
    OptimizerStatsItem,
    OptimizerStatsResponse,
)
from .artifacts import OptimizedDemo, OptimizedPredictor, ProgramArtifact
from .common import (
    ColumnMapping,
    ModelConfig,
    OptimizationStatus,
    SplitCounts,
    SplitFractions,
)
from .constants import HEALTH_STATUS_OK
from .dataset import (
    DatasetProfile,
    InputColumnProfile,
    ProfileDatasetRequest,
    ProfileDatasetResponse,
    ProfileWarning,
    ProfileWarningCode,
    SplitPlan,
    TargetColumnProfile,
)
from .infra import HealthResponse, QueueStatusResponse
from .optimizations import (
    BulkCancelRequest,
    BulkCancelResponse,
    BulkCancelSkipped,
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkDeleteSkipped,
    JobCancelResponse,
    JobDeleteResponse,
    OptimizationCountsResponse,
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
    "HEALTH_STATUS_OK",
    "AnalyticsSummaryResponse",
    "BulkCancelRequest",
    "BulkCancelResponse",
    "BulkCancelSkipped",
    "BulkDeleteRequest",
    "BulkDeleteResponse",
    "BulkDeleteSkipped",
    "ColumnMapping",
    "DashboardAnalyticsJob",
    "DashboardAnalyticsNameValue",
    "DashboardAnalyticsOptimizerAverage",
    "DashboardAnalyticsResponse",
    "DashboardAnalyticsTimelineBucket",
    "DatasetProfile",
    "GridSearchRequest",
    "GridSearchResponse",
    "HealthResponse",
    "InputColumnProfile",
    "JobCancelResponse",
    "JobDeleteResponse",
    "JobLogEntry",
    "ModelConfig",
    "ModelStatsItem",
    "ModelStatsResponse",
    "OptimizationCountsResponse",
    "OptimizationPayloadResponse",
    "OptimizationStatus",
    "OptimizationStatusResponse",
    "OptimizationSubmissionResponse",
    "OptimizationSummaryResponse",
    "OptimizedDemo",
    "OptimizedPredictor",
    "OptimizerStatsItem",
    "OptimizerStatsResponse",
    "PaginatedJobsResponse",
    "PairResult",
    "ProfileDatasetRequest",
    "ProfileDatasetResponse",
    "ProfileWarning",
    "ProfileWarningCode",
    "ProgramArtifact",
    "ProgramArtifactResponse",
    "ProgressEvent",
    "QueueStatusResponse",
    "RunRequest",
    "RunResponse",
    "ServeInfoResponse",
    "ServeRequest",
    "ServeResponse",
    "SplitCounts",
    "SplitFractions",
    "SplitPlan",
    "TargetColumnProfile",
    "TemplateCreateRequest",
    "TemplateResponse",
    "ValidateCodeRequest",
    "ValidateCodeResponse",
    "_JobResponseBase",
    "_OptimizationRequestBase",
]
