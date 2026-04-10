"""Telemetry models emitted while a job runs (progress events + log lines)."""
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


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
