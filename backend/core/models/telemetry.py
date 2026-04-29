"""Telemetry models emitted while an optimization runs (progress events + log lines)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProgressEvent(BaseModel):
    """Structured telemetry emitted while an optimization runs."""

    timestamp: datetime
    event: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class JobLogEntry(BaseModel):
    """Log line captured from DSPy/optimizer loggers."""

    timestamp: datetime
    level: str
    logger: str
    message: str
    # Storage layer at backend/core/storage/remote.py writes pair_index for
    # grid-search rows so the frontend can filter logs to the active pair;
    # without this field Pydantic strips it on serialization and the
    # per-pair log filter never matches.
    pair_index: int | None = None
