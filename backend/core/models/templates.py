"""Request/response models for the /templates CRUD endpoints."""
import json as _json
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, model_validator

_TEMPLATE_CONFIG_MAX_BYTES = 100_000


class TemplateCreateRequest(BaseModel):
    """Request payload for creating a job template."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    username: str
    config: Dict[str, Any] = Field(
        ..., description="Template configuration (signature, metric, model, optimizer, etc.)"
    )

    @model_validator(mode="after")
    def _validate_config_size(self) -> "TemplateCreateRequest":
        if len(_json.dumps(self.config)) > _TEMPLATE_CONFIG_MAX_BYTES:
            raise ValueError(
                f"Template config exceeds maximum size of {_TEMPLATE_CONFIG_MAX_BYTES // 1000}KB."
            )
        return self


class TemplateResponse(BaseModel):
    """Response payload for a job template."""

    template_id: str
    name: str
    description: Optional[str] = None
    username: str
    config: Dict[str, Any]
    created_at: datetime
