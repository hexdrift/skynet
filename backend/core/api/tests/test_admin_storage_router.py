"""Tests for admin per-user storage-budget override routes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from .. import auth as auth_mod
from ..routers.admin import create_admin_router

_DEFAULT_BYTES = 2 * 1024 * 1024 * 1024


@dataclass
class _FakeUsage:
    """Stand-in for ``StorageUsage`` exposing only ``total``."""

    total: int


class _FakeStorageStore:
    """In-memory storage-budget override store for admin route tests."""

    def __init__(self) -> None:
        """Initialize empty override state and a stable per-user footprint."""
        self.overrides: dict[str, int] = {}
        self.used_by_user = 512 * 1024 * 1024

    def list_user_storage_quota_overrides(self) -> list[dict[str, Any]]:
        """Return all saved storage overrides ordered by username."""
        return [
            {
                "username": username,
                "quota_bytes": quota_bytes,
                "updated_at": None,
                "updated_by": "admin@example.com",
            }
            for username, quota_bytes in sorted(self.overrides.items())
        ]

    def get_effective_user_storage_quota(self, username: str) -> int:
        """Return the override or the default test budget."""
        return self.overrides.get(username, _DEFAULT_BYTES)

    def compute_user_storage(self, username: str) -> _FakeUsage:
        """Return a stable fake footprint for the user."""
        return _FakeUsage(total=self.used_by_user)

    def set_user_storage_quota_override(
        self, username: str, quota_bytes: int, updated_by: str | None = None
    ) -> None:
        """Store an override."""
        self.overrides[username] = quota_bytes

    def delete_user_storage_quota_override(self, username: str) -> bool:
        """Delete an override if present."""
        return self.overrides.pop(username, None) is not None


def _base64url(value: bytes) -> str:
    """Encode bytes as unpadded base64url."""
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _token(*, groups: list[str] | None = None, secret: str = "test-secret") -> str:
    """Return a signed backend token for route tests."""
    now = int(time.time())
    header = _base64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8"))
    payload = _base64url(
        json.dumps(
            {
                "aud": "skynet-backend",
                "iss": "skynet-frontend",
                "sub": "admin@example.com",
                "name": "admin@example.com",
                "role": "user",
                "groups": groups or ["skynet-admins"],
                "iat": now,
                "exp": now + 300,
            }
        ).encode("utf-8")
    )
    signature = _base64url(
        hmac.new(secret.encode("utf-8"), f"{header}.{payload}".encode("ascii"), hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{signature}"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a test client with signed-token admin authorization enabled."""
    monkeypatch.setattr(auth_mod.settings, "backend_auth_secret", SecretStr("test-secret"))
    monkeypatch.setattr(auth_mod.settings, "admin_usernames", "")
    monkeypatch.setattr(auth_mod.settings, "admin_groups", "skynet-admins")
    monkeypatch.setattr(auth_mod.settings, "user_storage_quota_bytes", _DEFAULT_BYTES)
    app = FastAPI()
    app.include_router(create_admin_router(job_store=_FakeStorageStore()))
    return TestClient(app)


def test_storage_quota_routes_reject_missing_bearer(client: TestClient) -> None:
    """Storage-budget routes reject unauthenticated requests."""
    response = client.get("/admin/storage-quotas")

    assert response.status_code == 401


def test_storage_quota_routes_reject_non_admin_group(client: TestClient) -> None:
    """Signed users without an admin group cannot manage storage budgets."""
    response = client.get(
        "/admin/storage-quotas", headers={"Authorization": f"Bearer {_token(groups=['other'])}"}
    )

    assert response.status_code == 403


def test_admin_can_set_list_and_delete_storage_quota(client: TestClient) -> None:
    """The PUT/GET/DELETE cycle writes, lists, and clears a storage override."""
    headers = {"Authorization": f"Bearer {_token()}"}
    five_gb = 5 * 1024 * 1024 * 1024

    set_response = client.put(
        "/admin/storage-quotas", headers=headers, json={"username": "Power@Example.com", "quota_bytes": five_gb}
    )
    list_response = client.get("/admin/storage-quotas", headers=headers)
    delete_response = client.delete("/admin/storage-quotas/power@example.com", headers=headers)

    assert set_response.status_code == 200
    body = set_response.json()
    assert body["username"] == "power@example.com"
    assert body["quota_bytes"] == five_gb
    assert body["effective_bytes"] == five_gb
    assert body["used_bytes"] == 512 * 1024 * 1024

    assert list_response.status_code == 200
    listing = list_response.json()
    assert listing["default_bytes"] == _DEFAULT_BYTES
    assert listing["overrides"][0]["username"] == "power@example.com"
    assert listing["overrides"][0]["effective_bytes"] == five_gb

    assert delete_response.status_code == 200
    cleared = delete_response.json()
    assert cleared["quota_bytes"] is None
    assert cleared["effective_bytes"] == _DEFAULT_BYTES


def test_storage_quota_rejects_zero_budget(client: TestClient) -> None:
    """A non-positive byte budget is rejected by request validation."""
    headers = {"Authorization": f"Bearer {_token()}"}

    response = client.put("/admin/storage-quotas", headers=headers, json={"username": "alice", "quota_bytes": 0})

    assert response.status_code == 422
