"""Tests for signed backend API authentication."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from .. import auth as auth_mod
from ..auth import AuthenticatedUser, get_authenticated_user, require_admin_user


def _base64url(value: bytes) -> str:
    """Encode bytes as unpadded base64url."""
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _sign(payload: dict[str, Any], secret: str = "test-secret") -> str:
    """Sign a test HS256 JWT.

    Args:
        payload: JWT payload to encode.
        secret: HMAC secret.

    Returns:
        A compact JWT string.
    """
    header = _base64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8"))
    body = _base64url(json.dumps(payload).encode("utf-8"))
    signature = _base64url(hmac.new(secret.encode("utf-8"), f"{header}.{body}".encode("ascii"), hashlib.sha256).digest())
    return f"{header}.{body}.{signature}"


def _payload(**overrides: Any) -> dict[str, Any]:
    """Build a valid backend auth payload with optional overrides."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "aud": "skynet-backend",
        "iss": "skynet-frontend",
        "sub": "alice@example.com",
        "name": "alice@example.com",
        "role": "user",
        "groups": ["skynet-admins"],
        "iat": now,
        "exp": now + 300,
    }
    payload.update(overrides)
    return payload


def test_get_authenticated_user_accepts_valid_signed_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid backend token resolves to an authenticated user."""
    monkeypatch.setattr(auth_mod.settings, "backend_auth_secret", SecretStr("test-secret"))
    token = _sign(_payload())

    user = get_authenticated_user(f"Bearer {token}")

    assert user.username == "alice@example.com"
    assert user.groups == ("skynet-admins",)


def test_get_authenticated_user_rejects_missing_token() -> None:
    """A missing Authorization header is rejected."""
    with pytest.raises(HTTPException) as exc:
        get_authenticated_user(None)

    assert exc.value.status_code == 401


def test_get_authenticated_user_rejects_bad_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    """A token signed with another secret is rejected."""
    monkeypatch.setattr(auth_mod.settings, "backend_auth_secret", SecretStr("test-secret"))
    token = _sign(_payload(), secret="wrong-secret")

    with pytest.raises(HTTPException) as exc:
        get_authenticated_user(f"Bearer {token}")

    assert exc.value.status_code == 401


def test_require_admin_user_accepts_matching_idp_group(monkeypatch: pytest.MonkeyPatch) -> None:
    """An IdP group configured as admin grants backend admin access."""
    monkeypatch.setattr(auth_mod.settings, "admin_usernames", "")
    monkeypatch.setattr(auth_mod.settings, "admin_groups", "skynet-admins")
    user = AuthenticatedUser(username="alice@example.com", role="user", groups=("skynet-admins",))

    assert require_admin_user(user) is user


def test_require_admin_user_rejects_non_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """A user with no matching break-glass username or group is rejected."""
    monkeypatch.setattr(auth_mod.settings, "admin_usernames", "")
    monkeypatch.setattr(auth_mod.settings, "admin_groups", "skynet-admins")
    user = AuthenticatedUser(username="alice@example.com", role="user", groups=("other",))

    with pytest.raises(HTTPException) as exc:
        require_admin_user(user)

    assert exc.value.status_code == 403
