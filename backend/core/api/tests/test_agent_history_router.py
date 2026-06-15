"""Tests for the agent-history conversation router's bulk-delete route.

Mounts the conversation router on an in-memory SQLite store (the sibling
routers' pattern: a ``RemoteDBJobStore`` subclass that skips the pgvector
bootstrap so ``Base.metadata.create_all`` stands up the conversation tables).
Covers the per-id outcomes of ``POST /agent/conversations/bulk-delete``: owned
rows delete, duplicates collapse, unknown and other-users' ids are skipped, and
an empty request is a no-op.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ...storage.models import AgentConversationModel, Base
from ...storage.remote import RemoteDBJobStore
from ..auth import AuthenticatedUser, get_authenticated_user
from ..errors import DomainError
from ..routers.agent_history import create_agent_history_router

_ALICE = AuthenticatedUser(username="alice", role="user", groups=())


class _MemStore(RemoteDBJobStore):
    """In-memory SQLite job store for agent-history tests (no pgvector)."""

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
    """Mount the agent-history router on a fresh store, authed as ``user``.

    Args:
        user: Identity the auth dependency resolves to for every request.

    Returns:
        A ``(client, store)`` pair sharing one in-memory store.
    """
    store = _MemStore()
    app = FastAPI()
    app.include_router(create_agent_history_router(job_store=store))
    app.dependency_overrides[get_authenticated_user] = lambda: user

    @app.exception_handler(DomainError)
    async def _domain_error_handler(_request, exc: DomainError) -> JSONResponse:
        """Mirror the app-level envelope so tests can assert on ``code``."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code, "params": exc.params},
        )

    return TestClient(app), store


def _seed(store: _MemStore, *conversations: tuple[str, str]) -> None:
    """Insert ``(id, username)`` conversation rows directly into the store.

    Args:
        store: The in-memory store to seed.
        conversations: ``(id, username)`` pairs to insert.
    """
    with store._session_factory() as session:
        session.add_all(
            AgentConversationModel(id=cid, username=username, title=cid)
            for cid, username in conversations
        )
        session.commit()


def _ids(store: _MemStore) -> set[str]:
    """Return the set of conversation ids currently in the store.

    Args:
        store: The store to read.

    Returns:
        Every ``AgentConversationModel.id`` present.
    """
    with store._session_factory() as session:
        return {row.id for row in session.query(AgentConversationModel)}


def test_bulk_delete_removes_owned_conversations() -> None:
    """Bulk-delete clears every owned id and leaves none of them behind."""
    client, store = _client(_ALICE)
    _seed(store, ("c-1", "alice"), ("c-2", "alice"))

    resp = client.post("/agent/conversations/bulk-delete", json={"ids": ["c-1", "c-2"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert sorted(body["deleted"]) == ["c-1", "c-2"]
    assert body["skipped"] == []
    assert _ids(store) == set()


def test_bulk_delete_dedupes_and_skips_unknown() -> None:
    """Duplicate ids collapse to one delete; an unknown id is skipped, not fatal."""
    client, store = _client(_ALICE)
    _seed(store, ("c-1", "alice"))

    resp = client.post(
        "/agent/conversations/bulk-delete",
        json={"ids": ["c-1", "c-1", "ghost"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted"] == ["c-1"]
    assert body["skipped"] == [{"id": "ghost", "reason": "not_found"}]


def test_bulk_delete_skips_other_users_conversations() -> None:
    """A caller cannot bulk-delete another user's conversation — it is skipped."""
    client, store = _client(_ALICE)
    _seed(store, ("bob-1", "bob"))

    resp = client.post("/agent/conversations/bulk-delete", json={"ids": ["bob-1"]})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": [], "skipped": [{"id": "bob-1", "reason": "not_found"}]}
    assert _ids(store) == {"bob-1"}


def test_bulk_delete_empty_is_noop() -> None:
    """An empty id list deletes nothing and returns empty result lists."""
    client, _ = _client(_ALICE)
    resp = client.post("/agent/conversations/bulk-delete", json={"ids": []})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": [], "skipped": []}
