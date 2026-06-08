"""Tests for the personal dataset-library CRUD router.

Exercises the owner-scoped save/list/read/rename/delete surface against an
in-memory SQLite store (the sibling routers' pattern: a ``RemoteDBJobStore``
subclass that skips the pgvector bootstrap so ``Base.metadata.create_all``
stands up the ``datasets`` and ``dataset_blobs`` tables). Covers the three save
gates — per-file cap (413), content-hash dedupe, and per-user quota (409) — plus
cross-user isolation.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ...storage.models import Base
from ...storage.remote import RemoteDBJobStore
from ..auth import AuthenticatedUser, get_authenticated_user
from ..errors import DomainError
from ..routers import dataset_library as dataset_library_module
from ..routers.dataset_library import create_dataset_library_router

_ALICE = AuthenticatedUser(username="alice", role="user", groups=())
_BOB = AuthenticatedUser(username="bob", role="user", groups=())

_ROWS = [{"q": "2+2", "a": "4"}, {"q": "3+3", "a": "6"}]
_SCHEMA = {
    "column_order": ["q", "a"],
    "column_roles": {"q": "input", "a": "output"},
    "column_kinds": {"q": "text", "a": "text"},
}


class _MemStore(RemoteDBJobStore):
    """In-memory SQLite job store for dataset-library tests (no pgvector)."""

    def __init__(self) -> None:
        """Build an in-memory SQLite engine and create the ORM tables."""
        self._engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)


def _app_for(store: _MemStore, user: AuthenticatedUser) -> FastAPI:
    """Mount the library router on a store, authed as ``user``, with the error map.

    Args:
        store: Backing store the router reads and writes.
        user: Identity the auth dependency resolves to for every request.

    Returns:
        A FastAPI app whose ``DomainError``s render the production ``code`` envelope.
    """
    app = FastAPI()
    app.include_router(create_dataset_library_router(job_store=store))
    app.dependency_overrides[get_authenticated_user] = lambda: user

    @app.exception_handler(DomainError)
    async def _domain_error_handler(_request, exc: DomainError) -> JSONResponse:
        """Mirror the app-level envelope so tests can assert on ``code``."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code, "params": exc.params},
        )

    return app


def _make_client(user: AuthenticatedUser) -> tuple[TestClient, _MemStore]:
    """Build a test client whose library router is authed as ``user``.

    Args:
        user: Identity the auth dependency resolves to for every request.

    Returns:
        A ``(client, store)`` pair sharing one in-memory store.
    """
    store = _MemStore()
    return TestClient(_app_for(store, user)), store


def _save(client: TestClient, *, name: str = "Math", rows=_ROWS) -> dict:
    """Save a dataset and return the decoded JSON envelope.

    Args:
        client: Authenticated test client.
        name: Display name for the entry.
        rows: Dataset rows to save.

    Returns:
        The parsed ``SaveDatasetResponse`` body.
    """
    resp = client.post(
        "/datasets/library",
        json={"name": name, "source": "upload", "dataset": rows, "column_schema": _SCHEMA},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_save_then_read_round_trip() -> None:
    """A saved dataset lists, fetches, and returns its rows with saved columns."""
    client, _ = _make_client(_ALICE)
    saved = _save(client)
    assert saved["deduplicated"] is False
    dataset_id = saved["dataset"]["id"]
    assert saved["dataset"]["row_count"] == 2
    assert saved["dataset"]["column_count"] == 2

    listing = client.get("/datasets/library").json()
    assert [d["id"] for d in listing["datasets"]] == [dataset_id]
    assert listing["usage"]["used_bytes"] > 0
    assert listing["usage"]["quota_bytes"] > 0

    meta = client.get(f"/datasets/library/{dataset_id}").json()
    assert meta["name"] == "Math"

    rows = client.get(f"/datasets/library/{dataset_id}/rows").json()
    assert rows["columns"] == ["q", "a"]
    assert rows["rows"] == _ROWS
    assert rows["row_count"] == 2


def test_rename_updates_name() -> None:
    """PATCH renames the entry and the new name is reflected on read."""
    client, _ = _make_client(_ALICE)
    dataset_id = _save(client)["dataset"]["id"]
    renamed = client.patch(f"/datasets/library/{dataset_id}", json={"name": "Arithmetic"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Arithmetic"
    assert client.get(f"/datasets/library/{dataset_id}").json()["name"] == "Arithmetic"


def test_identical_resave_dedupes() -> None:
    """Re-saving byte-identical rows returns the existing entry, not a copy."""
    client, _ = _make_client(_ALICE)
    first = _save(client)["dataset"]["id"]
    again = _save(client, name="Math copy")
    assert again["deduplicated"] is True
    assert again["dataset"]["id"] == first
    assert len(client.get("/datasets/library").json()["datasets"]) == 1


def test_per_file_cap_rejects_with_413(monkeypatch: pytest.MonkeyPatch) -> None:
    """A file above the per-file compressed cap is rejected with 413."""
    monkeypatch.setattr(dataset_library_module.settings, "dataset_max_file_bytes", 1)
    client, _ = _make_client(_ALICE)
    resp = client.post(
        "/datasets/library",
        json={"name": "Big", "source": "upload", "dataset": _ROWS, "column_schema": {}},
    )
    assert resp.status_code == 413
    assert resp.json()["code"] == "dataset.library.too_large"


def test_quota_rejects_with_409(monkeypatch: pytest.MonkeyPatch) -> None:
    """A save that would exceed the per-user quota is rejected with 409."""
    client, _ = _make_client(_ALICE)
    _save(client)
    monkeypatch.setattr(dataset_library_module.settings, "dataset_user_quota_bytes", 1)
    resp = client.post(
        "/datasets/library",
        json={"name": "Second", "source": "upload", "dataset": [{"q": "9", "a": "9"}], "column_schema": {}},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "dataset.library.quota_exceeded"


def test_delete_removes_entry_and_rows() -> None:
    """Deleting an entry makes both its metadata and rows 404 afterwards."""
    client, _ = _make_client(_ALICE)
    dataset_id = _save(client)["dataset"]["id"]
    deleted = client.delete(f"/datasets/library/{dataset_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/datasets/library/{dataset_id}").status_code == 404
    assert client.get(f"/datasets/library/{dataset_id}/rows").status_code == 404
    assert client.get("/datasets/library").json()["datasets"] == []


def test_owner_scoping_hides_other_users_dataset() -> None:
    """A non-owner gets 404 — never another user's entry — on a shared store."""
    client_a, store = _make_client(_ALICE)
    dataset_id = _save(client_a)["dataset"]["id"]

    client_b = TestClient(_app_for(store, _BOB))

    assert client_b.get(f"/datasets/library/{dataset_id}").status_code == 404
    assert client_b.get("/datasets/library").json()["datasets"] == []
