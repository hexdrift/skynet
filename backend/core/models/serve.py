"""Request/response models for the /serve/* inference endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import ModelConfig


class ServeRequest(BaseModel):
    """Request payload for running inference on an optimized program."""

    inputs: dict[str, Any] = Field(..., description="Input field values matching the program's signature.")
    model_config_override: ModelConfig | None = Field(
        default=None,
        description="Optional model config override. Uses the original optimization model if omitted.",
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def _ensure_inputs(self) -> ServeRequest:
        """Reject inference requests with no input fields.

        Returns:
            The validated request instance.

        Raises:
            ValueError: When ``inputs`` is empty.
        """
        if not self.inputs:
            raise ValueError("At least one input field is required.")
        return self


class ServeResponse(BaseModel):
    """Response payload from program inference.

    ``input_fields`` / ``output_fields`` are lists of signature field *names*.
    They are NOT the same shape as ``ColumnMapping.inputs`` / ``outputs``, which
    are ``{field_name: column_name}`` dicts used at the submission layer. The
    naming differs on purpose: here we are echoing the servable program's
    signature, not binding dataset columns.
    """

    optimization_id: str
    outputs: dict[str, Any]
    input_fields: list[str]
    output_fields: list[str]
    model_used: str


class ServeInfoResponse(BaseModel):
    """Metadata about a servable program (no inference call)."""

    optimization_id: str
    module_name: str
    optimizer_name: str
    model_name: str
    input_fields: list[str]
    output_fields: list[str]
    instructions: str | None = None
    demo_count: int = 0
