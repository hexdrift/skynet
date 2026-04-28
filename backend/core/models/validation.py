"""Request/response models for the /validate-code endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

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


class ValidateCodeResponse(BaseModel):
    """Response payload for code validation."""

    valid: bool
    signature_fields: dict[str, list[str]] | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
