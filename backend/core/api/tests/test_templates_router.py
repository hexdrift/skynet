from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from ..routers.templates import create_templates_router
from ...storage.models import Base as StorageBase

class _InMemoryStore:
    """Minimal fake with only the `engine` attribute templates router needs.

    StaticPool forces all connections to share the same underlying SQLite
    connection, which is required for in-memory databases when TestClient
    dispatches requests on a worker thread different from the setup thread.
    """

    def __init__(self) -> None:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        StorageBase.metadata.create_all(engine)
        self.engine = engine

@pytest.fixture
def tpl_store() -> _InMemoryStore:
    return _InMemoryStore()

@pytest.fixture
def tpl_client(tpl_store: _InMemoryStore) -> TestClient:
    app = FastAPI()
    app.include_router(create_templates_router(job_store=tpl_store))
    return TestClient(app, raise_server_exceptions=False)

def test_create_template_returns_201_with_id(tpl_client: TestClient) -> None:
    """POST /templates returns 201 with a template_id and the supplied name and username."""
    resp = tpl_client.post(
        "/templates",
        json={"name": "My Template", "username": "alice", "config": {"optimizer": "gepa"}},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "template_id" in body
    assert body["name"] == "My Template"
    assert body["username"] == "alice"

def test_create_template_trims_name(tpl_client: TestClient) -> None:
    """POST /templates strips leading and trailing whitespace from the template name."""
    resp = tpl_client.post(
        "/templates",
        json={"name": "  spaced  ", "username": "alice", "config": {}},
    )

    assert resp.status_code == 201
    assert resp.json()["name"] == "spaced"

def test_create_template_returns_422_on_missing_name(tpl_client: TestClient) -> None:
    """POST /templates returns 422 when the name field is absent."""
    resp = tpl_client.post(
        "/templates",
        json={"username": "alice", "config": {}},
    )

    assert resp.status_code == 422

def test_create_template_returns_422_on_missing_username(tpl_client: TestClient) -> None:
    """POST /templates returns 422 when the username field is absent."""
    resp = tpl_client.post(
        "/templates",
        json={"name": "T", "config": {}},
    )

    assert resp.status_code == 422

def test_list_templates_returns_empty_when_none_exist(tpl_client: TestClient) -> None:
    """GET /templates returns an empty list when no templates have been created."""
    resp = tpl_client.get("/templates")

    assert resp.status_code == 200
    assert resp.json() == []

def test_list_templates_returns_created_template(tpl_client: TestClient) -> None:
    """GET /templates returns the template that was just created."""
    tpl_client.post(
        "/templates",
        json={"name": "T1", "username": "alice", "config": {}},
    )

    resp = tpl_client.get("/templates")

    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "T1"

def test_list_templates_filters_by_username(tpl_client: TestClient) -> None:
    """GET /templates?username= returns only templates owned by the given user."""
    tpl_client.post("/templates", json={"name": "Alice's", "username": "alice", "config": {}})
    tpl_client.post("/templates", json={"name": "Bob's", "username": "bob", "config": {}})

    resp = tpl_client.get("/templates?username=alice")

    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["username"] == "alice"

def test_list_templates_respects_limit_and_offset(tpl_client: TestClient) -> None:
    """GET /templates with limit and offset returns non-overlapping pages."""
    for i in range(5):
        tpl_client.post("/templates", json={"name": f"T{i}", "username": "alice", "config": {}})

    page1 = tpl_client.get("/templates?limit=2&offset=0").json()
    page2 = tpl_client.get("/templates?limit=2&offset=2").json()

    assert len(page1) == 2
    assert len(page2) == 2
    ids1 = {t["template_id"] for t in page1}
    ids2 = {t["template_id"] for t in page2}
    assert ids1.isdisjoint(ids2)

def test_get_template_returns_404_for_unknown_id(tpl_client: TestClient) -> None:
    """GET /templates/{id} returns 404 for an id that does not exist."""
    resp = tpl_client.get("/templates/does-not-exist")

    assert resp.status_code == 404

def test_get_template_returns_correct_data(tpl_client: TestClient) -> None:
    """GET /templates/{id} returns the template data including template_id and config."""
    create_resp = tpl_client.post(
        "/templates",
        json={"name": "Lookup", "username": "carol", "config": {"key": "value"}},
    )
    tid = create_resp.json()["template_id"]

    resp = tpl_client.get(f"/templates/{tid}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["template_id"] == tid
    assert body["config"] == {"key": "value"}

def test_delete_template_returns_404_for_unknown_id(tpl_client: TestClient) -> None:
    """DELETE /templates/{id} returns 404 for an id that does not exist."""
    resp = tpl_client.delete("/templates/ghost?username=alice")

    assert resp.status_code == 404

def test_delete_template_returns_403_when_wrong_owner(tpl_client: TestClient) -> None:
    """DELETE /templates/{id} returns 403 when the requesting user does not own the template."""
    create_resp = tpl_client.post(
        "/templates",
        json={"name": "Mine", "username": "alice", "config": {}},
    )
    tid = create_resp.json()["template_id"]

    resp = tpl_client.delete(f"/templates/{tid}?username=eve")

    assert resp.status_code == 403

def test_delete_template_returns_422_when_username_missing(tpl_client: TestClient) -> None:
    """DELETE /templates/{id} returns 422 when the username query param is absent."""
    create_resp = tpl_client.post(
        "/templates",
        json={"name": "T", "username": "alice", "config": {}},
    )
    tid = create_resp.json()["template_id"]

    resp = tpl_client.delete(f"/templates/{tid}")

    assert resp.status_code == 422

def test_delete_template_removes_it_from_store(tpl_client: TestClient) -> None:
    """DELETE /templates/{id} returns deleted=True and subsequent GET returns 404."""
    create_resp = tpl_client.post(
        "/templates",
        json={"name": "ToDelete", "username": "alice", "config": {}},
    )
    tid = create_resp.json()["template_id"]

    del_resp = tpl_client.delete(f"/templates/{tid}?username=alice")

    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True

    get_resp = tpl_client.get(f"/templates/{tid}")
    assert get_resp.status_code == 404
