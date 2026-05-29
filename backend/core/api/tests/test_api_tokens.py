"""Tests for personal access token (PAT) generation, auth, and lifecycle.

The lifecycle tests run against a shared in-memory SQLite engine (StaticPool so
the table and rows persist across sessions and the TestClient's worker thread),
exercising the real ``get_authenticated_user`` PAT path rather than the auth
bypass — so a generated token genuinely round-trips through hashing + DB lookup.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from ...storage.models import ApiTokenModel
from ..auth import (
    API_TOKEN_PREFIX,
    AuthenticatedUser,
    generate_api_token,
    get_authenticated_user,
    hash_api_token,
    is_api_token,
    token_last4,
)
from ..routers.api_tokens import create_api_tokens_router


def test_generate_api_token_is_prefixed_and_unique() -> None:
    """Generated tokens carry the prefix, are high-entropy, and don't repeat."""
    first = generate_api_token()
    second = generate_api_token()
    assert first.startswith(API_TOKEN_PREFIX)
    assert is_api_token(first)
    assert first != second
    assert len(first) > 40


def test_hash_is_deterministic_and_never_plaintext() -> None:
    """The stored hash is stable per token and never equals the plaintext."""
    token = generate_api_token()
    assert hash_api_token(token) == hash_api_token(token)
    assert hash_api_token(token) != token
    assert len(hash_api_token(token)) == 64


def test_is_api_token_rejects_jwt_shape() -> None:
    """A JWT-shaped credential is not mistaken for a PAT."""
    assert is_api_token("eyJhbGciOiJIUzI1Ni.payload.sig") is False


def test_token_last4_matches_tail() -> None:
    """``token_last4`` returns the trailing four characters."""
    token = generate_api_token()
    assert token_last4(token) == token[-4:]


class _Store:
    """Minimal store exposing only the SQLAlchemy engine the routes need."""

    def __init__(self, engine: Any) -> None:
        """Hold the engine the api-tokens router and auth path open sessions on.

        Args:
            engine: A SQLAlchemy engine with the ``api_tokens`` table created.
        """
        self.engine = engine


@pytest.fixture
def token_app() -> FastAPI:
    """Build an app with the api-tokens router over an in-memory SQLite store.

    Returns:
        A FastAPI app whose ``app.state.job_store`` and router both point at a
        shared in-memory SQLite store holding the ``api_tokens`` table.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    ApiTokenModel.__table__.create(engine)
    store = _Store(engine)
    app = FastAPI()
    app.state.job_store = store
    app.include_router(create_api_tokens_router(job_store=store))
    return app


def _bypass_as(app: FastAPI, username: str = "alice") -> None:
    """Override auth so endpoint calls act as ``username`` without a token.

    Args:
        app: App whose auth dependency is overridden.
        username: Identity the override returns.
    """
    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(
        username=username, role="user", groups=()
    )


def test_generate_then_authenticate_with_pat(token_app: FastAPI) -> None:
    """A generated PAT authenticates a later request via the real auth path."""
    _bypass_as(token_app)
    client = TestClient(token_app)
    created = client.post("/settings/api-token")
    assert created.status_code == 201
    token = created.json()["token"]
    assert token.startswith(API_TOKEN_PREFIX)

    # Drop the bypass so the PAT flows through get_authenticated_user → DB lookup.
    token_app.dependency_overrides.clear()
    info = client.get("/settings/api-token", headers={"Authorization": f"Bearer {token}"})
    assert info.status_code == 200
    assert info.json()["last4"] == token[-4:]


def test_regenerate_invalidates_previous_token(token_app: FastAPI) -> None:
    """Rotating issues a new token and invalidates the old (one per user)."""
    _bypass_as(token_app)
    client = TestClient(token_app)
    first = client.post("/settings/api-token").json()["token"]
    second = client.post("/settings/api-token").json()["token"]
    assert first != second

    token_app.dependency_overrides.clear()
    assert (
        client.get("/settings/api-token", headers={"Authorization": f"Bearer {second}"}).status_code
        == 200
    )
    assert (
        client.get("/settings/api-token", headers={"Authorization": f"Bearer {first}"}).status_code
        == 401
    )


def test_revoke_then_token_rejected(token_app: FastAPI) -> None:
    """After revoke, the token no longer authenticates."""
    _bypass_as(token_app)
    client = TestClient(token_app)
    token = client.post("/settings/api-token").json()["token"]
    assert client.delete("/settings/api-token").status_code == 204

    token_app.dependency_overrides.clear()
    assert (
        client.get("/settings/api-token", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


def test_get_returns_null_when_no_token(token_app: FastAPI) -> None:
    """A user with no active token gets a null metadata response."""
    _bypass_as(token_app)
    client = TestClient(token_app)
    response = client.get("/settings/api-token")
    assert response.status_code == 200
    assert response.json() is None
