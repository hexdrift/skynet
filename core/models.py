from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

HEALTH_STATUS_OK = "ok"


class ColumnMapping(BaseModel):
    """Describe how dataframe columns map onto DSPy signature fields."""

    inputs: Dict[str, str] = Field(default_factory=dict)
    outputs: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ensure_non_empty(self) -> "ColumnMapping":
        """Validate that mappings include inputs and no shared columns.

        Args:
            self: The ``ColumnMapping`` instance being validated.

        Returns:
            ColumnMapping: Validated mapping.

        Raises:
            ValueError: If inputs are missing or columns overlap.
        """
        if not self.inputs:
            raise ValueError("At least one input column must be specified.")
        shared = set(self.inputs.values()) & set(self.outputs.values())
        if shared:
            raise ValueError(
                "Input and output column mappings must not reuse the same columns:"
                f" {sorted(shared)}"
            )
        return self


class ModelConfig(BaseModel):
    """Configuration block for language-model/backbone selection."""

    name: str
    base_url: Optional[str] = None
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    extra: Dict[str, Any] = Field(default_factory=dict)

    def normalized_identifier(self) -> str:
        """Return the Litellm identifier (deprecated: identical to ``name``).

        Args:
            None.

        Returns:
            str: Normalized model identifier preferred by LiteLLM.
        """

        return self.name.strip("/")


class SplitFractions(BaseModel):
    """Train/val/test fraction spec."""

    train: float = 0.7
    val: float = 0.15
    test: float = 0.15

    @model_validator(mode="after")
    def _validate(self) -> "SplitFractions":
        """Verify that split fractions are non-negative and sum to one.

        Args:
            self: The ``SplitFractions`` instance being validated.

        Returns:
            SplitFractions: Validated fraction set.

        Raises:
            ValueError: If constraints are violated.
        """
        parts = [self.train, self.val, self.test]
        if any(part < 0 for part in parts):
            raise ValueError("Split fractions must be non-negative.")
        total = sum(parts)
        if abs(total - 1.0) > 1e-6:
            raise ValueError("Split fractions must sum to 1.0.")
        return self


# ---------------------------------------------------------------------------
# Request payloads (inbound — what clients send)
# ---------------------------------------------------------------------------


class _OptimizationRequestBase(BaseModel):
    """Shared fields for all optimization job submissions."""

    model_config = ConfigDict(populate_by_name=True)

    username: str
    module_name: str
    module_kwargs: Dict[str, Any] = Field(default_factory=dict)
    signature_code: str
    metric_code: str
    optimizer_name: str
    optimizer_kwargs: Dict[str, Any] = Field(default_factory=dict)
    compile_kwargs: Dict[str, Any] = Field(default_factory=dict)
    dataset: List[Dict[str, Any]]
    column_mapping: ColumnMapping
    split_fractions: SplitFractions = Field(default_factory=SplitFractions)
    shuffle: bool = True
    seed: Optional[int] = None

    @model_validator(mode="after")
    def _ensure_dataset(self) -> "_OptimizationRequestBase":
        if not self.dataset:
            raise ValueError("Dataset must contain at least one row.")
        return self


class RunRequest(_OptimizationRequestBase):
    """Payload for the /run endpoint."""

    model_settings: ModelConfig = Field(alias="model_config")
    reflection_model_settings: Optional[ModelConfig] = Field(
        default=None, alias="reflection_model_config"
    )
    prompt_model_settings: Optional[ModelConfig] = Field(
        default=None, alias="prompt_model_config"
    )
    task_model_settings: Optional[ModelConfig] = Field(
        default=None, alias="task_model_config"
    )


class GridSearchRequest(_OptimizationRequestBase):
    """Payload for the /grid-search endpoint — sweep over model pairs."""

    generation_models: List[ModelConfig]
    reflection_models: List[ModelConfig]

    @model_validator(mode="after")
    def _validate_model_lists(self) -> "GridSearchRequest":
        if not self.generation_models:
            raise ValueError("At least one generation model is required.")
        if not self.reflection_models:
            raise ValueError("At least one reflection model is required.")
        return self


# ---------------------------------------------------------------------------
# Intermediate / telemetry models
# ---------------------------------------------------------------------------


class SplitCounts(BaseModel):
    """Container for the number of examples in each dataset split.

    Attributes:
        train: Number of training examples.
        val: Number of validation examples.
        test: Number of test examples.
    """

    train: int
    val: int
    test: int


class ProgressEvent(BaseModel):
    """Structured telemetry emitted while an optimization job runs."""

    timestamp: datetime
    event: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)


class JobLogEntry(BaseModel):
    """Log line captured from DSPy/optimizer loggers."""

    timestamp: datetime
    level: str
    logger: str
    message: str


class OptimizedDemo(BaseModel):
    """A single few-shot demonstration example from an optimized predictor.

    Attributes:
        inputs: Dictionary of input field names to their values.
        outputs: Dictionary of output field names to their values.
    """

    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)


class OptimizedPredictor(BaseModel):
    """Extracted prompt and demos from a single predictor in the compiled program.

    Attributes:
        predictor_name: Name or identifier of the predictor within the module.
        signature_name: Class name of the DSPy signature used by this predictor.
        instructions: The optimized instruction/prompt string for this predictor.
        input_fields: List of input field names in the signature.
        output_fields: List of output field names in the signature.
        demos: List of few-shot demonstration examples.
        formatted_prompt: Complete prompt as a single formatted string with instructions and demos.
    """

    predictor_name: str
    signature_name: Optional[str] = None
    instructions: str
    input_fields: List[str] = Field(default_factory=list)
    output_fields: List[str] = Field(default_factory=list)
    demos: List[OptimizedDemo] = Field(default_factory=list)
    formatted_prompt: str = Field(
        default="",
        description="Complete prompt as a single formatted string including instructions and demos.",
    )


class ProgramArtifact(BaseModel):
    """Serializable payload that carries the optimized DSPy program files."""

    path: Optional[str] = Field(
        default=None,
        description="Absolute path on the server where the artifact lives.",
    )
    program_pickle_base64: Optional[str] = Field(
        default=None,
        description="Base64-encoded contents of the saved program.pkl file.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="metadata.json contents already parsed into a dict.",
    )
    optimized_prompt: Optional[OptimizedPredictor] = Field(
        default=None,
        description="Extracted prompt and demos from the compiled program predictor.",
    )


# ---------------------------------------------------------------------------
# Result payloads (outbound — job results)
# ---------------------------------------------------------------------------


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
    run_log: List[JobLogEntry] = Field(default_factory=list)


class PairResult(BaseModel):
    """Result of a single (generation, reflection) model pair run."""

    pair_index: int
    generation_model: str
    reflection_model: str
    baseline_test_metric: Optional[float] = None
    optimized_test_metric: Optional[float] = None
    metric_improvement: Optional[float] = None
    runtime_seconds: Optional[float] = None
    program_artifact: Optional[ProgramArtifact] = None
    error: Optional[str] = None


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


# ---------------------------------------------------------------------------
# Job status / response payloads (outbound — what clients receive)
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Response payload for the health check endpoint.

    Attributes:
        status: Health status string, typically "ok".
        registered_assets: Dictionary of registered modules, metrics, and optimizers.
    """

    status: str = Field(default=HEALTH_STATUS_OK)
    registered_assets: Dict[str, List[str]]


class JobStatus(str, Enum):
    """Enumerate background job states."""

    pending = "pending"
    validating = "validating"
    running = "running"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"


class JobSubmissionResponse(BaseModel):
    """Immediate response to POST /run or POST /grid-search."""

    job_id: str
    job_type: str
    status: JobStatus
    created_at: datetime
    username: str
    module_name: str
    optimizer_name: str


class _JobResponseBase(BaseModel):
    """Shared fields across job response endpoints."""

    # Identity & status
    job_id: str
    job_type: str
    status: JobStatus
    message: Optional[str] = None

    # Timestamps
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    elapsed: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    estimated_remaining: Optional[str] = None

    # Payload summary (universal)
    username: Optional[str] = None
    module_name: Optional[str] = None
    module_kwargs: Dict[str, Any] = Field(default_factory=dict)
    optimizer_name: Optional[str] = None
    column_mapping: Optional[ColumnMapping] = None
    dataset_rows: Optional[int] = None

    # Live telemetry
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


class JobStatusResponse(_JobResponseBase):
    """Full job detail returned by GET /jobs/{id}."""

    progress_events: List[ProgressEvent] = Field(default_factory=list)
    logs: List[JobLogEntry] = Field(default_factory=list)
    result: Optional[RunResponse] = None
    grid_result: Optional[GridSearchResponse] = None


class JobSummaryResponse(_JobResponseBase):
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

    # Grid search (null for run)
    best_pair_label: Optional[str] = None


class PaginatedJobsResponse(BaseModel):
    """Paginated wrapper for job listings."""

    items: List[JobSummaryResponse] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


class QueueStatusResponse(BaseModel):
    """Response payload for the queue status endpoint."""

    pending_jobs: int
    active_jobs: int
    worker_threads: int
    workers_alive: bool


class JobCancelResponse(BaseModel):
    """Response payload for the cancel endpoint."""

    job_id: str
    status: str


class JobDeleteResponse(BaseModel):
    """Response payload for the delete endpoint."""

    job_id: str
    deleted: bool


class JobPayloadResponse(BaseModel):
    """Response payload for the payload retrieval endpoint."""

    job_id: str
    job_type: str
    payload: Dict[str, Any]


class ProgramArtifactResponse(BaseModel):
    """Response payload for the artifact retrieval endpoint.

    Attributes:
        program_artifact: Serialized artifact containing base64-encoded program pickle.
    """

    program_artifact: Optional[ProgramArtifact]
