"""Tests for grant-aware access on the logged-in (non-token) optimization routes.

Covers the access boundary added for Google-Drive-style sharing: a member with
a per-user grant can reach a run they don't own at their tier, mutations require
a high-enough tier (403 below it), and a stranger still 404s. Also verifies the
graceful fallback to owner-only when the job store exposes no grant engine
(the in-memory/local store used offline and in some unit tests).

The store mirrors the in-memory SQLite pattern of the sibling router tests: a
``RemoteDBJobStore`` subclass that skips the pgvector bootstrap and seeds rows
directly.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ...storage.models import Base, JobModel, OptimizationShareGrantModel
from ...storage.remote import RemoteDBJobStore
from ..auth import AuthenticatedUser, get_authenticated_user
from ..errors import DomainError
from ..routers._helpers import (
    filter_ids_at_least,
    load_job_with_role,
    require_role_at_least,
)
from ..routers.analytics import create_analytics_router
from ..routers.optimizations import create_optimizations_router
from ..sharing_access import ShareRole


class _MemStore(RemoteDBJobStore):
    """In-memory SQLite job store (skips the pgvector bootstrap)."""

    def __init__(self) -> None:
        """Build an in-memory SQLite engine and create the ORM tables."""
        self._engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)


def _user(name: str, *, admin: bool = False) -> AuthenticatedUser:
    """Build an authenticated user, optionally in the admin group."""
    return AuthenticatedUser(
        username=name,
        role="admin" if admin else "user",
        groups=("skynet-admins",) if admin else (),
    )


def _seed_job(store: _MemStore, optimization_id: str, owner: str, status: str = "success") -> None:
    """Insert a job owned by ``owner`` into the store."""
    with Session(store.engine) as session:
        session.add(
            JobModel(
                optimization_id=optimization_id,
                status=status,
                created_at=datetime.now(UTC),
                latest_metrics={},
                payload_overview={"optimization_type": "run", "username": owner},
                payload={"username": owner},
                username=owner,
            )
        )
        session.commit()


def _grant(store: _MemStore, optimization_id: str, username: str, role: str) -> None:
    """Insert a member grant for ``username`` at ``role``."""
    with Session(store.engine) as session:
        session.add(
            OptimizationShareGrantModel(
                optimization_id=optimization_id,
                grantee_username=username,
                role=role,
                created_by="alice",
                created_at=datetime.now(UTC),
            )
        )
        session.commit()


def _store_with_grant(role: str | None) -> _MemStore:
    """A store with a job owned by alice and (optionally) a bob grant at ``role``."""
    store = _MemStore()
    _seed_job(store, "opt-1", owner="alice")
    if role is not None:
        _grant(store, "opt-1", "bob", role)
    return store


def test_owner_resolves_to_owner_role() -> None:
    """The creator resolves to the owner tier."""
    store = _store_with_grant(None)
    _job, role = load_job_with_role(store, "opt-1", _user("alice"))
    assert role == ShareRole.owner


def test_admin_resolves_to_owner_role() -> None:
    """An admin resolves to the owner tier on any run."""
    store = _store_with_grant(None)
    _job, role = load_job_with_role(store, "opt-1", _user("carol", admin=True))
    assert role == ShareRole.owner


@pytest.mark.parametrize("role", ["viewer", "editor"])
def test_member_resolves_to_grant_role(role: str) -> None:
    """An invited member resolves to exactly their grant tier (viewer or editor)."""
    store = _store_with_grant(role)
    _job, resolved = load_job_with_role(store, "opt-1", _user("bob"))
    assert resolved == ShareRole(role)


def test_owner_role_grant_is_not_recognized() -> None:
    """A stale ``owner``-role grant grants nothing — owner isn't a member tier.

    Single-owner model: ownership is the creator's, reassigned only by transfer,
    so the resolver ignores any leftover ``owner``-role grant row rather than
    treating its holder as a co-owner.
    """
    store = _store_with_grant("owner")
    with pytest.raises(DomainError) as exc:
        load_job_with_role(store, "opt-1", _user("bob"))
    assert exc.value.status_code == 404


def test_stranger_404() -> None:
    """A caller with no ownership and no grant 404s (existence not leaked)."""
    store = _store_with_grant(None)
    with pytest.raises(DomainError) as exc:
        load_job_with_role(store, "opt-1", _user("bob"))
    assert exc.value.status_code == 404


def test_viewer_meets_viewer_minimum() -> None:
    """A viewer satisfies a viewer-floor route (read access)."""
    store = _store_with_grant("viewer")
    _job, role = require_role_at_least(store, "opt-1", _user("bob"), ShareRole.viewer)
    assert role == ShareRole.viewer


def test_viewer_below_editor_403() -> None:
    """A viewer hitting an editor route gets 403 (has access, wrong tier)."""
    store = _store_with_grant("viewer")
    with pytest.raises(DomainError) as exc:
        require_role_at_least(store, "opt-1", _user("bob"), ShareRole.editor)
    assert exc.value.status_code == 403
    assert exc.value.code == "optimization.insufficient_role"


def test_editor_below_owner_403() -> None:
    """An editor hitting an owner-only route (delete) gets 403."""
    store = _store_with_grant("editor")
    with pytest.raises(DomainError) as exc:
        require_role_at_least(store, "opt-1", _user("bob"), ShareRole.owner)
    assert exc.value.status_code == 403


def test_editor_meets_editor_minimum() -> None:
    """An editor satisfies an editor route (cancel / rename / retry)."""
    store = _store_with_grant("editor")
    _job, role = require_role_at_least(store, "opt-1", _user("bob"), ShareRole.editor)
    assert role == ShareRole.editor


def test_stranger_403_route_still_404() -> None:
    """No access at all stays 404 even on a tier-gated route (no leak)."""
    store = _store_with_grant(None)
    with pytest.raises(DomainError) as exc:
        require_role_at_least(store, "opt-1", _user("bob"), ShareRole.editor)
    assert exc.value.status_code == 404


def test_filter_ids_at_least_splits_by_tier() -> None:
    """Bulk filtering keeps ids meeting the tier and denies the rest."""
    store = _MemStore()
    _seed_job(store, "owned", owner="bob")
    _seed_job(store, "editor-grant", owner="alice")
    _seed_job(store, "viewer-grant", owner="alice")
    _seed_job(store, "no-grant", owner="alice")
    _grant(store, "editor-grant", "bob", "editor")
    _grant(store, "viewer-grant", "bob", "viewer")

    ids = ["owned", "editor-grant", "viewer-grant", "no-grant", "missing"]
    allowed, denied = filter_ids_at_least(store, ids, _user("bob"), ShareRole.editor)

    assert set(allowed) == {"owned", "editor-grant"}
    assert set(denied) == {"viewer-grant", "no-grant", "missing"}


def test_filter_ids_at_least_admin_keeps_all() -> None:
    """An admin bulk-passes every existing id regardless of grants."""
    store = _MemStore()
    _seed_job(store, "a", owner="alice")
    _seed_job(store, "b", owner="dave")
    allowed, denied = filter_ids_at_least(store, ["a", "b"], _user("carol", admin=True), ShareRole.owner)
    assert set(allowed) == {"a", "b"}
    assert denied == []


class _EnginelessStore:
    """A minimal store with rows but no grant-bearing ``engine`` (offline/local)."""

    def __init__(self) -> None:
        """Seed a single alice-owned row."""
        self._rows = {
            "opt-1": {
                "optimization_id": "opt-1",
                "status": "success",
                "payload": {"username": "alice"},
                "payload_overview": {"username": "alice"},
            }
        }

    def get_job(self, optimization_id: str) -> dict:
        """Return the row or raise ``KeyError`` like the real store."""
        return self._rows[optimization_id]


def test_engineless_store_falls_back_to_owner_only() -> None:
    """Without an engine, grants can't be read, so only owner/admin get access."""
    store = _EnginelessStore()
    _job, role = load_job_with_role(store, "opt-1", _user("alice"))
    assert role == ShareRole.owner
    with pytest.raises(DomainError) as exc:
        load_job_with_role(store, "opt-1", _user("bob"))
    assert exc.value.status_code == 404


def test_list_jobs_shared_with_returns_only_granted() -> None:
    """The store lists runs the user holds a grant on, not their own or others'."""
    store = _MemStore()
    _seed_job(store, "alice-run", owner="alice")
    _seed_job(store, "bob-own", owner="bob")
    _seed_job(store, "shared", owner="alice")
    _grant(store, "shared", "bob", "viewer")

    rows = store.list_jobs_shared_with("bob", limit=50, offset=0)
    assert [r["optimization_id"] for r in rows] == ["shared"]
    assert store.count_jobs_shared_with("bob") == 1
    assert store.count_jobs_shared_with("alice") == 0


def _client(store: _MemStore, username: str) -> TestClient:
    """Mount the optimizations router over ``store`` authed as ``username``."""
    app = FastAPI()
    app.include_router(create_optimizations_router(job_store=store, get_worker_ref=lambda: None))
    app.dependency_overrides[get_authenticated_user] = lambda: _user(username)
    return TestClient(app, raise_server_exceptions=False)


def test_shared_with_me_endpoint_lists_with_role() -> None:
    """GET /optimizations/shared-with-me returns granted runs with the caller's role."""
    store = _MemStore()
    _seed_job(store, "shared-edit", owner="alice")
    _seed_job(store, "not-mine", owner="alice")
    _grant(store, "shared-edit", "bob", "editor")

    resp = _client(store, "bob").get("/optimizations/shared-with-me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["optimization_id"] == "shared-edit"
    assert item["role"] == "editor"


def test_shared_with_me_empty_for_user_without_grants() -> None:
    """A user with no grants gets an empty shared list."""
    store = _MemStore()
    _seed_job(store, "alice-run", owner="alice")
    resp = _client(store, "carol").get("/optimizations/shared-with-me")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0}


def test_detail_effective_role_null_for_owner() -> None:
    """The owner's own detail view carries a null effective_role (implicitly owner)."""
    store = _MemStore()
    _seed_job(store, "opt-1", owner="alice")
    resp = _client(store, "alice").get("/optimizations/opt-1")
    assert resp.status_code == 200
    assert resp.json()["effective_role"] is None


def test_detail_effective_role_for_member() -> None:
    """A member's detail view carries their grant tier so the UI can gate actions."""
    store = _MemStore()
    _seed_job(store, "opt-1", owner="alice")
    _grant(store, "opt-1", "bob", "viewer")
    resp = _client(store, "bob").get("/optimizations/opt-1")
    assert resp.status_code == 200
    assert resp.json()["effective_role"] == "viewer"


def test_detail_404_for_stranger() -> None:
    """A non-member still 404s on the detail route (existence not leaked)."""
    store = _MemStore()
    _seed_job(store, "opt-1", owner="alice")
    resp = _client(store, "bob").get("/optimizations/opt-1")
    assert resp.status_code == 404


def test_list_jobs_visible_to_unions_owned_and_shared() -> None:
    """The store's visible-to union returns owned + granted, excluding others' private runs."""
    store = _MemStore()
    _seed_job(store, "bob-own", owner="bob")
    _seed_job(store, "alice-shared", owner="alice")
    _seed_job(store, "alice-private", owner="alice")
    _grant(store, "alice-shared", "bob", "viewer")

    ids = {r["optimization_id"] for r in store.list_jobs_visible_to("bob", limit=50, offset=0)}
    assert ids == {"bob-own", "alice-shared"}
    assert store.count_jobs_visible_to("bob") == 2
    assert store.count_jobs_visible_to("bob", status="success") == 2
    assert store.count_jobs_visible_to("alice") == 2


def test_list_endpoint_include_shared_attaches_role() -> None:
    """GET /optimizations?include_shared unions shared runs and tags their grant role."""
    store = _MemStore()
    _seed_job(store, "bob-own", owner="bob")
    _seed_job(store, "shared-edit", owner="alice")
    _grant(store, "shared-edit", "bob", "editor")

    resp = _client(store, "bob").get("/optimizations?include_shared=true")
    assert resp.status_code == 200
    items = {i["optimization_id"]: i for i in resp.json()["items"]}
    assert set(items) == {"bob-own", "shared-edit"}
    assert items["shared-edit"]["role"] == "editor"
    assert items["bob-own"].get("role") is None


def test_list_endpoint_default_owner_only() -> None:
    """Without include_shared the list stays owner-scoped (no behavior change)."""
    store = _MemStore()
    _seed_job(store, "bob-own", owner="bob")
    _seed_job(store, "shared", owner="alice")
    _grant(store, "shared", "bob", "viewer")

    resp = _client(store, "bob").get("/optimizations")
    ids = {i["optimization_id"] for i in resp.json()["items"]}
    assert ids == {"bob-own"}


def test_counts_endpoint_include_shared_reports_shared() -> None:
    """GET /optimizations/counts?include_shared folds shared in and reports the count."""
    store = _MemStore()
    _seed_job(store, "bob-own", owner="bob")
    _seed_job(store, "s1", owner="alice")
    _seed_job(store, "s2", owner="alice")
    _grant(store, "s1", "bob", "viewer")
    _grant(store, "s2", "bob", "editor")

    body = _client(store, "bob").get("/optimizations/counts?include_shared=true").json()
    assert body["total"] == 3
    assert body["success"] == 3
    assert body["shared"] == 2

    owner_only = _client(store, "bob").get("/optimizations/counts").json()
    assert owner_only["total"] == 1
    assert owner_only["shared"] == 0


def _analytics_client(store: _MemStore, username: str = "bob") -> TestClient:
    """Mount the analytics router over ``store`` authed as ``username``.

    The dashboard analytics now scope to the authenticated caller, so the tests
    authenticate as the user whose ``?username=`` view they assert on.
    """
    app = FastAPI()
    app.include_router(create_analytics_router(job_store=store))
    app.dependency_overrides[get_authenticated_user] = lambda: _user(username)
    return TestClient(app, raise_server_exceptions=False)


def test_analytics_dashboard_include_shared_owner_usage_and_filter() -> None:
    """Analytics unions shared runs, exposes an owner breakdown, and filters by owner."""
    store = _MemStore()
    _seed_job(store, "a1", owner="alice")
    _seed_job(store, "a2", owner="alice")
    _seed_job(store, "bob-own", owner="bob")
    _grant(store, "a1", "bob", "viewer")
    _grant(store, "a2", "bob", "editor")
    client = _analytics_client(store)

    body = client.get("/analytics/dashboard?username=bob&include_shared=true").json()
    assert body["filtered_total"] == 3
    assert {o["name"]: o["value"] for o in body["owner_usage"]} == {"alice": 2, "bob": 1}

    filtered = client.get("/analytics/dashboard?username=bob&include_shared=true&owner=alice").json()
    assert filtered["filtered_total"] == 2
    assert {o["name"] for o in filtered["owner_usage"]} == {"alice"}


def test_analytics_dashboard_access_usage_and_filter() -> None:
    """Analytics breaks runs down by caller access tier and filters by tier."""
    store = _MemStore()
    _seed_job(store, "mine", owner="bob")
    _seed_job(store, "as-viewer", owner="alice")
    _seed_job(store, "as-editor", owner="alice")
    _grant(store, "as-viewer", "bob", "viewer")
    _grant(store, "as-editor", "bob", "editor")
    client = _analytics_client(store)

    body = client.get("/analytics/dashboard?username=bob&include_shared=true").json()
    assert {a["name"]: a["value"] for a in body["access_usage"]} == {"mine": 1, "viewer": 1, "editor": 1}

    filtered = client.get("/analytics/dashboard?username=bob&include_shared=true&access=editor").json()
    assert filtered["filtered_total"] == 1
    assert {a["name"] for a in filtered["access_usage"]} == {"editor"}
