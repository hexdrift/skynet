"""Request/response models for the /serve/* inference endpoints."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import ModelConfig


class ServeRequest(BaseModel):
    """Request payload for running inference on an optimized program."""

    inputs: Dict[str, Any] = Field(
        ..., description="Input field values matching the program's signature."
    )
    model_config_override: Optional[ModelConfig] = Field(
        default=None,
        description="Optional model config override. Uses the original optimization model if omitted.",
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def _ensure_inputs(self) -> "ServeRequest":
        if not self.inputs:
            raise ValueError("At least one input field is required.")
        return self


class ServeResponse(BaseModel):
    """Response payload from program inference."""

    optimization_id: str
    outputs: Dict[str, Any]
    input_fields: List[str]
    output_fields: List[str]
    model_used: str


class ServeInfoResponse(BaseModel):
    """Metadata about a servable program (no inference call)."""

    optimization_id: str
    module_name: str
    optimizer_name: str
    model_name: str
    input_fields: List[str]
    output_fields: List[str]
    instructions: Optional[str] = None
    demo_count: int = 0
