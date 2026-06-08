"""Tests for the unified storage-usage router (``GET /usage/storage``).

Mounts the usage router beside the dataset-library router on one in-memory
SQLite store (the sibling routers' pattern: a ``RemoteDBJobStore`` subclass that
skips the pgvector bootstrap so ``Base.metadata.create_all`` stands up every
table). Confirms the meter is zero for a fresh user, reports the configured
budget, and reflects saved data through the same total the save/run gate reads.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ...config import settings
from ...storage.models import Base
from ...storage.remote import RemoteDBJobStore
from ...storage.usage import STORAGE_CATEGORIES
from ..auth import AuthenticatedUser, get_authenticated_user
from ..routers.dataset_library import create_dataset_library_router
from ..routers.usage import create_usage_router

_ALICE = AuthenticatedUser(username="alice", role="user", groups=())

_ROWS = [{"q": "2+2", "a": "4"}, {"q": "3+3", "a": "6"}]


class _MemStore(RemoteDBJobStore):
    """In-memory SQLite job store for usage-router tests (no pgvector)."""

    def __init__(self) -> None:
        """Build an in-memory SQLite engine and create the ORM tables."""
        self._engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)


def _client(user: AuthenticatedUser) -> tuple[TestClient, _MemStore]:
    """Mount the usage + library routers on a fresh store, authed as ``user``.

    Args:
        user: Identity the auth dependency resolves to for every request.

    Returns:
        A ``(client, store)`` pair sharing one in-memory store.
    """
    store = _MemStore()
    app = FastAPI()
    app.include_router(create_usage_router(job_store=store))
    app.include_router(create_dataset_library_router(job_store=store))
    app.dependency_overrides[get_authenticated_user] = lambda: user
    return TestClient(app), store


def test_usage_is_zero_for_fresh_user() -> None:
    """A user with no data reports a zero total and every category at zero."""
    client, _ = _client(_ALICE)
    body = client.get("/usage/storage").json()
    assert body["used_bytes"] == 0
    assert body["quota_bytes"] == settings.user_storage_quota_bytes
    assert set(body["breakdown"]) == set(STORAGE_CATEGORIES)
    assert all(value == 0 for value in body["breakdown"].values())


def test_usage_reflects_saved_dataset() -> None:
    """Saving a dataset lifts the total and the datasets category off zero."""
    client, _ = _client(_ALICE)
    saved = client.post(
        "/datasets/library",
        json={"name": "Math", "source": "upload", "dataset": _ROWS, "column_schema": {}},
    )
    assert saved.status_code == 200, saved.text

    body = client.get("/usage/storage").json()
    assert body["breakdown"]["datasets"] > 0
    assert body["used_bytes"] == sum(body["breakdown"].values())


def test_usage_total_matches_library_meter() -> None:
    """The usage endpoint and the library's own meter report the same total."""
    client, _ = _client(_ALICE)
    client.post(
        "/datasets/library",
        json={"name": "Math", "source": "upload", "dataset": _ROWS, "column_schema": {}},
    )
    usage = client.get("/usage/storage").json()
    library = client.get("/datasets/library").json()["usage"]
    assert usage["used_bytes"] == library["used_bytes"]
    assert usage["quota_bytes"] == library["quota_bytes"]
