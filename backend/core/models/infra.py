"""Models for the infra endpoints exposed from app.py — /health and /queue."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .constants import HEALTH_STATUS_OK


class HealthResponse(BaseModel):
    """Response payload for the health check endpoint."""

    status: str = Field(default=HEALTH_STATUS_OK)
    registered_assets: dict[str, list[str]]
    vector_search_enabled: bool | None = None


class QueueStatusResponse(BaseModel):
    """Response payload for the queue status endpoint."""

    pending_jobs: int
    active_jobs: int
    worker_threads: int
    workers_alive: bool
