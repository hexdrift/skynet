"""Unit test fixtures.

In-memory fakes are used so the suite runs without a live server, database, or
LLM key.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from .. import auth as auth_mod
from ..auth import AuthenticatedUser, get_authenticated_user
from ..routers.analytics import create_analytics_router
from ..routers.models import create_models_router
from ..routers.optimizations_meta import create_optimizations_meta_router
from .mocks import FakeJobStore

__all__ = ["FakeJobStore", "TEST_USER", "bypass_auth"]


TEST_USER = AuthenticatedUser(username="alice", role="admin", groups=("skynet-admins",))


@pytest.fixture(autouse=True)
def _enable_test_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mark the default test user as admin.

    Most router-level tests don't exercise ownership scoping — they exercise
    the routes themselves. Enrolling the default test user as admin lets
    seeded jobs be accessed regardless of payload-level username, so existing
    fixtures don't need to be reseeded with the auth user's identity. Tests
    that target ownership/scoping behavior should explicitly construct a
    non-admin :class:`AuthenticatedUser` and pass it to :func:`bypass_auth`.
    """
    monkeypatch.setattr(auth_mod.settings, "admin_groups", "skynet-admins")


def bypass_auth(app: FastAPI, *, user: AuthenticatedUser | None = None) -> None:
    """Override the auth dependency on ``app`` to skip token verification.

    Router tests would otherwise need to mint signed JWTs for every request.
    The override resolves :func:`get_authenticated_user` to a fixed user so
    the routes see an authenticated identity without HMAC overhead.

    Args:
        app: The FastAPI app whose ``dependency_overrides`` should be patched.
        user: Optional explicit user to inject; defaults to ``TEST_USER``.
    """
    app.dependency_overrides[get_authenticated_user] = lambda: user or TEST_USER


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
    Auth is bypassed via ``dependency_overrides`` so router tests don't need
    to mint signed tokens — the override returns a fixed non-admin user.

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
    bypass_auth(app)

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
