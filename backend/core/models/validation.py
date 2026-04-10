"""Request/response models for the /validate-code endpoint."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .common import ColumnMapping


class ValidateCodeRequest(BaseModel):
    """Request payload for pre-submission code validation.

    Either `signature_code` or `metric_code` may be supplied on its own, so the
    wizard can validate each code block independently.
    """

    signature_code: Optional[str] = None
    metric_code: Optional[str] = None
    column_mapping: ColumnMapping
    sample_row: Dict[str, Any] = Field(default_factory=dict)
    optimizer_name: Optional[str] = None


class ValidateCodeResponse(BaseModel):
    """Response payload for code validation."""

    valid: bool
    signature_fields: Optional[Dict[str, List[str]]] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
