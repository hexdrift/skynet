"""Assemble the optimizations ``APIRouter`` from the per-concern modules."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter

from .deletion import register_deletion_routes
from .detail import register_detail_routes
from .lifecycle import register_lifecycle_routes
from .listing import register_listing_routes
from .streaming import register_dashboard_stream, register_job_stream


def create_optimizations_router(*, job_store, get_worker_ref: Callable[[], Any]) -> APIRouter:
    """Build the optimizations router.

    Routes are registered in an order that keeps literal paths ahead of
    path-parameter patterns so FastAPI's first-match resolver picks the
    intended handler. Specifically, ``/optimizations/stream`` and all other
    literal ``/optimizations/{word}`` GETs are registered before
    ``/optimizations/{optimization_id}``.

    Args:
        job_store: Job-store instance the routes read from / write to.
        get_worker_ref: Zero-arg callable returning the active worker.

    Returns:
        A FastAPI ``APIRouter`` carrying every optimization route.
    """
    router = APIRouter()

    register_listing_routes(router, job_store=job_store)
    register_dashboard_stream(router, job_store=job_store)
    register_detail_routes(router, job_store=job_store)
    register_lifecycle_routes(router, job_store=job_store, get_worker_ref=get_worker_ref)
    register_deletion_routes(router, job_store=job_store)
    register_job_stream(router, job_store=job_store)

    return router
