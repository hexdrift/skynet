"""Unit test fixtures — in-memory fakes, no live server, DB, or LLM key."""

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
    return FakeJobStore()


@pytest.fixture
def router_app(job_store: FakeJobStore) -> FastAPI:
    """Build a minimal FastAPI app wired up with a subset of routers that
    only depend on job_store. Used for fast router-level tests without the
    full create_app() machinery (which would require Postgres + worker).
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
    return TestClient(router_app)
