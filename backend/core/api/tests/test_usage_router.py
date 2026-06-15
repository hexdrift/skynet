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
from ...storage.models import AgentStagedDatasetModel, Base
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


def test_storage_items_empty_for_fresh_user() -> None:
    """A user with no data ranks to an empty items list."""
    client, _ = _client(_ALICE)
    body = client.get("/usage/storage/items").json()
    assert body == {"items": []}


def test_storage_items_lists_saved_dataset() -> None:
    """A saved dataset surfaces in the ranked items with its size and type."""
    client, _ = _client(_ALICE)
    client.post(
        "/datasets/library",
        json={"name": "Math", "source": "upload", "dataset": _ROWS, "column_schema": {}},
    )
    items = client.get("/usage/storage/items").json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["type"] == "dataset"
    assert item["name"] == "Math"
    assert item["bytes"] > 0


def test_storage_items_rejects_out_of_range_limit() -> None:
    """The ``limit`` query param is clamped to ``1..100`` by validation."""
    client, _ = _client(_ALICE)
    assert client.get("/usage/storage/items", params={"limit": 0}).status_code == 422
    assert client.get("/usage/storage/items", params={"limit": 101}).status_code == 422


def test_category_items_empty_for_fresh_user() -> None:
    """A deletable category lists empty for a user with no data."""
    client, _ = _client(_ALICE)
    body = client.get("/usage/storage/categories/optimizations").json()
    assert body == {"items": []}


def test_category_items_lists_saved_dataset() -> None:
    """The datasets category surfaces a saved dataset with its size and type."""
    client, _ = _client(_ALICE)
    client.post(
        "/datasets/library",
        json={"name": "Math", "source": "upload", "dataset": _ROWS, "column_schema": {}},
    )
    items = client.get("/usage/storage/categories/datasets").json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "dataset"
    assert items[0]["name"] == "Math"
    assert items[0]["bytes"] > 0


def test_category_items_rejects_non_deletable_category() -> None:
    """A byproduct category (no standalone artifact) is a 404."""
    client, _ = _client(_ALICE)
    assert client.get("/usage/storage/categories/embeddings").status_code == 404
    assert client.get("/usage/storage/categories/bogus").status_code == 404


def test_staged_upload_lists_and_deletes() -> None:
    """A pending upload lists under its category and the delete route clears it."""
    client, store = _client(_ALICE)
    with store._session_factory() as session:
        session.add(
            AgentStagedDatasetModel(
                id="st-1", username="alice", dataset_filename="data.csv", rows=[{"q": "1"}], row_count=1
            )
        )
        session.commit()

    listed = client.get("/usage/storage/categories/staged_uploads").json()["items"]
    assert [item["id"] for item in listed] == ["st-1"]
    assert listed[0]["type"] == "staged_upload"
    assert listed[0]["name"] == "data.csv"

    deleted = client.delete("/usage/storage/staged/st-1")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}

    again = client.delete("/usage/storage/staged/st-1")
    assert again.json() == {"deleted": False}
    assert client.get("/usage/storage/categories/staged_uploads").json()["items"] == []


def test_staged_bulk_delete_clears_dedupes_and_skips_unknown() -> None:
    """Bulk-delete removes owned staged rows, collapses dupes, and skips unknown ids."""
    client, store = _client(_ALICE)
    with store._session_factory() as session:
        session.add_all(
            AgentStagedDatasetModel(
                id=f"st-{n}",
                username="alice",
                dataset_filename=f"d{n}.csv",
                rows=[{"q": "1"}],
                row_count=1,
            )
            for n in (1, 2)
        )
        session.commit()

    resp = client.post(
        "/usage/storage/staged/bulk-delete",
        json={"ids": ["st-1", "st-1", "st-2", "ghost"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert sorted(body["deleted"]) == ["st-1", "st-2"]
    assert body["skipped"] == [{"id": "ghost", "reason": "not_found"}]
    assert client.get("/usage/storage/categories/staged_uploads").json()["items"] == []


def test_staged_bulk_delete_scopes_to_caller() -> None:
    """A caller cannot bulk-delete another user's staged upload — it is skipped."""
    client, store = _client(_ALICE)
    with store._session_factory() as session:
        session.add(
            AgentStagedDatasetModel(
                id="bob-1", username="bob", dataset_filename="b.csv", rows=[{"q": "1"}], row_count=1
            )
        )
        session.commit()

    resp = client.post("/usage/storage/staged/bulk-delete", json={"ids": ["bob-1"]})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": [], "skipped": [{"id": "bob-1", "reason": "not_found"}]}


def test_staged_bulk_delete_empty_is_noop() -> None:
    """An empty id list deletes nothing and returns empty result lists."""
    client, _ = _client(_ALICE)
    resp = client.post("/usage/storage/staged/bulk-delete", json={"ids": []})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": [], "skipped": []}
