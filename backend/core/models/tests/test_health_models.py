"""Tests for HealthResponse and QueueStatusResponse infra models."""

from __future__ import annotations

from core.models.constants import HEALTH_STATUS_OK
from core.models.infra import HealthResponse, QueueStatusResponse


def test_health_response_default_status_is_ok() -> None:
    """Verify HealthResponse defaults its status to HEALTH_STATUS_OK."""
    resp = HealthResponse(registered_assets={"modules": [], "metrics": [], "optimizers": []})

    assert resp.status == HEALTH_STATUS_OK


def test_health_response_stores_registered_assets() -> None:
    """Verify HealthResponse persists the registered_assets mapping."""
    assets = {"modules": ["predict"], "metrics": ["accuracy"], "optimizers": ["gepa"]}
    resp = HealthResponse(registered_assets=assets)

    assert resp.registered_assets == assets


def test_health_response_custom_status_accepted() -> None:
    """Verify HealthResponse accepts a non-default status string."""
    resp = HealthResponse(status="degraded", registered_assets={})

    assert resp.status == "degraded"


def test_queue_status_response_stores_counts() -> None:
    """Verify QueueStatusResponse stores all queue counts and the workers_alive flag."""
    resp = QueueStatusResponse(
        pending_jobs=3,
        active_jobs=1,
        worker_threads=4,
        workers_alive=True,
    )

    assert resp.pending_jobs == 3
    assert resp.active_jobs == 1
    assert resp.worker_threads == 4
    assert resp.workers_alive is True


def test_queue_status_response_workers_dead() -> None:
    """Verify QueueStatusResponse accepts workers_alive=False with zero counts."""
    resp = QueueStatusResponse(
        pending_jobs=0,
        active_jobs=0,
        worker_threads=0,
        workers_alive=False,
    )

    assert resp.workers_alive is False
