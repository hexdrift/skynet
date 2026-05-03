"""Inbound payloads for POST /run and POST /grid-search plus the initial ack."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import ColumnMapping, ModelConfig, OptimizationStatus, OptimizationType, SplitFractions


class _OptimizationRequestBase(BaseModel):
    """Shared fields for all optimization submissions."""

    # ``model_config`` here is the Pydantic class-config attr; ``RunRequest``
    # additionally exposes a wire-aliased field whose alias is also
    # ``model_config`` (the OpenAPI property name the frontend sends), so the
    # same identifier intentionally serves two purposes — class config here
    # vs. field alias on the subclass.
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, description="User-defined display name for this optimization.")
    description: str | None = Field(
        default=None, max_length=280, description="Short description of the optimization goal (max 280 characters)."
    )
    username: str
    module_name: str
    module_kwargs: dict[str, Any] = Field(default_factory=dict)
    signature_code: str
    metric_code: str
    optimizer_name: str
    optimizer_kwargs: dict[str, Any] = Field(default_factory=dict)
    compile_kwargs: dict[str, Any] = Field(default_factory=dict)
    dataset: list[dict[str, Any]]
    column_mapping: ColumnMapping
    split_fractions: SplitFractions = Field(default_factory=SplitFractions)
    shuffle: bool = True
    seed: int | None = None
    dataset_filename: str | None = Field(default=None, description="Original dataset file name.")
    is_private: bool = Field(
        default=False,
        description="When true, the optimization is excluded from the public explore map.",
    )

    @model_validator(mode="after")
    def _ensure_dataset(self) -> _OptimizationRequestBase:
        """Reject requests with an empty dataset.

        Returns:
            The validated request instance.

        Raises:
            ValueError: When ``dataset`` is empty.
        """
        if not self.dataset:
            raise ValueError("Dataset must contain at least one row.")
        return self


class RunRequest(_OptimizationRequestBase):
    """Payload for the /run endpoint."""

    model_settings: ModelConfig = Field(alias="model_config")
    reflection_model_settings: ModelConfig | None = Field(default=None, alias="reflection_model_config")
    task_model_settings: ModelConfig | None = Field(default=None, alias="task_model_config")


class GridSearchRequest(_OptimizationRequestBase):
    """Payload for the /grid-search endpoint — sweep over model pairs."""

    generation_models: list[ModelConfig] = Field(default_factory=list)
    reflection_models: list[ModelConfig] = Field(default_factory=list)
    use_all_available_generation_models: bool = Field(
        default=False,
        description=(
            "Populate generation_models from every available model in the catalog. "
            "When true, generation_models may be omitted and is replaced server-side."
        ),
    )
    use_all_available_reflection_models: bool = Field(
        default=False,
        description=(
            "Populate reflection_models from every available model in the catalog. "
            "When true, reflection_models may be omitted and is replaced server-side."
        ),
    )

    @model_validator(mode="after")
    def _validate_model_lists(self) -> GridSearchRequest:
        """Reject requests missing required model lists.

        Each side (``generation_models``, ``reflection_models``) must either be
        non-empty or be marked for server-side expansion via its matching
        ``use_all_available_*`` flag.

        Returns:
            The validated request instance.

        Raises:
            ValueError: When ``generation_models`` is empty and
                ``use_all_available_generation_models`` is false, or when
                ``reflection_models`` is empty and
                ``use_all_available_reflection_models`` is false.
        """
        if not self.use_all_available_generation_models and not self.generation_models:
            raise ValueError("At least one generation model is required.")
        if not self.use_all_available_reflection_models and not self.reflection_models:
            raise ValueError("At least one reflection model is required.")
        return self


class OptimizationSubmissionResponse(BaseModel):
    """Immediate response to POST /run or POST /grid-search."""

    optimization_id: str
    optimization_type: OptimizationType
    status: OptimizationStatus
    created_at: datetime
    name: str | None = None
    description: str | None = None
    username: str
    module_name: str
    optimizer_name: str
