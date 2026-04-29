"""Request/response models for the /validate-code endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from .common import ColumnMapping


class ValidateCodeRequest(BaseModel):
    """Request payload for pre-submission code validation.

    Either `signature_code` or `metric_code` may be supplied on its own, so the
    wizard can validate each code block independently.
    """

    signature_code: str | None = None
    metric_code: str | None = None
    column_mapping: ColumnMapping
    sample_row: dict[str, Any] = Field(default_factory=dict)
    optimizer_name: str | None = None

    @model_validator(mode="after")
    def _ensure_at_least_one_code_block(self) -> ValidateCodeRequest:
        """Reject requests where both ``signature_code`` and ``metric_code`` are absent.

        Returns:
            The validated request instance.

        Raises:
            ValueError: When neither code block is provided.
        """
        if self.signature_code is None and self.metric_code is None:
            raise ValueError("At least one of signature_code or metric_code must be provided.")
        return self


class ValidateCodeResponse(BaseModel):
    """Response payload for code validation."""

    valid: bool
    signature_fields: dict[str, list[str]] | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
