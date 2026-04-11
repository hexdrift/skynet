"""Inbound payloads for POST /run and POST /grid-search plus the initial ack."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import ColumnMapping, ModelConfig, OptimizationStatus, SplitFractions


class _OptimizationRequestBase(BaseModel):
    """Shared fields for all optimization job submissions."""

    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = Field(default=None, description="User-defined display name for this optimization.")
    description: Optional[str] = Field(default=None, max_length=280, description="Short description of the optimization goal (max 280 characters).")
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
    dataset_filename: Optional[str] = Field(default=None, description="Original dataset file name.")


    @model_validator(mode="after")
    def _ensure_dataset(self) -> "_OptimizationRequestBase":
        """Reject submissions whose ``dataset`` list is empty.

        Returns:
            The validated request instance.

        Raises:
            ValueError: If ``dataset`` is empty.
        """
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
        """Require non-empty generation and reflection model lists.

        Returns:
            The validated ``GridSearchRequest`` instance.

        Raises:
            ValueError: If either ``generation_models`` or
                ``reflection_models`` is empty.
        """
        if not self.generation_models:
            raise ValueError("At least one generation model is required.")
        if not self.reflection_models:
            raise ValueError("At least one reflection model is required.")
        return self


class OptimizationSubmissionResponse(BaseModel):
    """Immediate response to POST /run or POST /grid-search."""

    optimization_id: str
    optimization_type: str
    status: OptimizationStatus
    created_at: datetime
    name: Optional[str] = None
    description: Optional[str] = None
    username: str
    module_name: str
    optimizer_name: str
