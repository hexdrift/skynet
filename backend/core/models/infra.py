"""Models for the infra endpoints exposed from app.py — /health and /queue."""

from pydantic import BaseModel, Field

from .common import HEALTH_STATUS_OK


class HealthResponse(BaseModel):
    """Response payload for the health check endpoint."""

    status: str = Field(default=HEALTH_STATUS_OK)
    registered_assets: dict[str, list[str]]


class QueueStatusResponse(BaseModel):
    """Response payload for the queue status endpoint."""

    pending_jobs: int
    active_jobs: int
    worker_threads: int
    workers_alive: bool
