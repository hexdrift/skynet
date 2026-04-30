"""Tests for admin quota routes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from .. import auth as auth_mod
from ..routers.admin import create_admin_router


class _FakeQuotaStore:
    """In-memory quota store for admin route tests."""

    def __init__(self) -> None:
        """Initialize empty override and audit state."""
        self.overrides: dict[str, int | None] = {}
        self.audit_events: list[dict[str, Any]] = []

    def list_user_quota_overrides(self) -> list[dict[str, Any]]:
        """Return all saved quota overrides."""
        return [
            {
                "username": username,
                "quota": quota,
                "updated_at": None,
                "updated_by": "admin@example.com",
            }
            for username, quota in sorted(self.overrides.items())
        ]

    def list_user_quota_audit_events(self) -> list[dict[str, Any]]:
        """Return saved audit events newest-first."""
        return list(reversed(self.audit_events))

    def get_effective_user_quota(self, username: str) -> int | None:
        """Return the override or the default test quota."""
        return self.overrides.get(username, 100)

    def count_jobs(self, *, username: str | None = None, **_: Any) -> int:
        """Return a stable fake job count."""
        return 7 if username else 0

    def get_user_quota_override(self, username: str) -> tuple[bool, int | None]:
        """Return whether an override exists and its value."""
        if username not in self.overrides:
            return False, None
        return True, self.overrides[username]

    def set_user_quota_override(self, username: str, quota: int | None, updated_by: str | None = None) -> None:
        """Store an override."""
        self.overrides[username] = quota

    def delete_user_quota_override(self, username: str) -> bool:
        """Delete an override if present."""
        return self.overrides.pop(username, None) is not None

    def record_user_quota_audit(
        self,
        *,
        actor: str,
        target_username: str,
        action: str,
        old_quota: int | None,
        new_quota: int | None,
    ) -> None:
        """Record an audit event."""
        self.audit_events.append(
            {
                "id": len(self.audit_events) + 1,
                "actor": actor,
                "target_username": target_username,
                "action": action,
                "old_quota": old_quota,
                "new_quota": new_quota,
                "created_at": None,
            }
        )


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
    signature = _base64url(hmac.new(secret.encode("utf-8"), f"{header}.{payload}".encode("ascii"), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a test client with signed-token admin authorization enabled."""
    monkeypatch.setattr(auth_mod.settings, "backend_auth_secret", SecretStr("test-secret"))
    monkeypatch.setattr(auth_mod.settings, "admin_usernames", "")
    monkeypatch.setattr(auth_mod.settings, "admin_groups", "skynet-admins")
    app = FastAPI()
    app.include_router(create_admin_router(job_store=_FakeQuotaStore()))
    return TestClient(app)


def test_admin_quota_routes_reject_missing_bearer(client: TestClient) -> None:
    """Admin quota routes reject unauthenticated requests."""
    response = client.get("/admin/quotas")

    assert response.status_code == 401


def test_admin_quota_routes_reject_non_admin_group(client: TestClient) -> None:
    """Signed users without an admin group cannot manage quotas."""
    response = client.get("/admin/quotas", headers={"Authorization": f"Bearer {_token(groups=['other'])}"})

    assert response.status_code == 403


def test_admin_can_set_list_and_delete_quota(client: TestClient) -> None:
    """Admin quota route writes live overrides and audit events."""
    headers = {"Authorization": f"Bearer {_token()}"}

    set_response = client.put("/admin/quotas", headers=headers, json={"username": "Power@Example.com", "quota": 500})
    list_response = client.get("/admin/quotas", headers=headers)
    delete_response = client.delete("/admin/quotas/power@example.com", headers=headers)

    assert set_response.status_code == 200
    assert set_response.json()["username"] == "power@example.com"
    assert set_response.json()["quota"] == 500
    assert list_response.status_code == 200
    assert list_response.json()["overrides"][0]["username"] == "power@example.com"
    assert list_response.json()["audit_events"][0]["action"] == "set"
    assert list_response.json()["audit_events"][0]["old_quota"] == 100
    assert delete_response.status_code == 200
    assert delete_response.json()["effective_quota"] == 100
