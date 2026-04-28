"""Unit test fixtures.

In-memory fakes are used so the suite runs without a live server, database, or
LLM key.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ..routers.analytics import create_analytics_router
from ..routers.models import create_models_router
from ..routers.optimizations_meta import create_optimizations_meta_router
from .mocks import FakeJobStore

__all__ = ["FakeJobStore"]


@pytest.fixture
def job_store() -> FakeJobStore:
    """Provide a fresh in-memory ``FakeJobStore`` for each test.

    Returns:
        A new ``FakeJobStore`` instance with no seeded data.
    """
    return FakeJobStore()


@pytest.fixture
def router_app(job_store: FakeJobStore) -> FastAPI:
    """Build a minimal FastAPI app wired to the in-memory job store.

    The full ``create_app()`` factory would require Postgres and a worker;
    this fixture mounts only the routers that can be exercised with the fake.

    Args:
        job_store: In-memory store injected into the analytics and meta routers.

    Returns:
        A FastAPI application with the models, analytics, and optimizations
        meta routers mounted.
    """
    app = FastAPI()
    app.include_router(create_models_router())
    app.include_router(create_analytics_router(job_store=job_store))
    app.include_router(create_optimizations_meta_router(job_store=job_store))

    # Templates needs a job_store.engine for SQLAlchemy. Skip it here —
    # covered by a separate integration test.
    return app


@pytest.fixture
def client(router_app: FastAPI) -> TestClient:
    """Wrap ``router_app`` in a FastAPI ``TestClient`` for HTTP assertions.

    Args:
        router_app: The FastAPI application to drive.

    Returns:
        A ``TestClient`` bound to ``router_app``.
    """
    return TestClient(router_app)
