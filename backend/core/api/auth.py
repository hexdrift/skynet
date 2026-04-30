"""Backend API authentication and authorization helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import Header

from ..config import settings
from .errors import DomainError

_EXPECTED_ALGORITHM = "HS256"
_EXPECTED_AUDIENCE = "skynet-backend"
_EXPECTED_ISSUER = "skynet-frontend"


@dataclass(frozen=True)
class AuthenticatedUser:
    """Authenticated backend API user."""

    username: str
    role: str
    groups: tuple[str, ...]


def _decode_base64url(value: str) -> bytes:
    """Decode an unpadded base64url string.

    Args:
        value: Base64url string to decode.

    Returns:
        Decoded bytes.
    """
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _json_part(value: str) -> dict[str, Any]:
    """Decode one JWT JSON segment.

    Args:
        value: Encoded JWT segment.

    Returns:
        Decoded JSON object.

    Raises:
        DomainError: When the segment is malformed.
    """
    try:
        decoded = json.loads(_decode_base64url(value))
    except (ValueError, json.JSONDecodeError) as exc:
        raise DomainError("auth.invalid_token", status=401) from exc
    if not isinstance(decoded, dict):
        raise DomainError("auth.invalid_token", status=401)
    return decoded


def _verify_hs256(token: str, secret: str) -> dict[str, Any]:
    """Verify an HS256 JWT and return its payload.

    Args:
        token: JWT from the Authorization header.
        secret: Shared HMAC secret.

    Returns:
        Verified payload.

    Raises:
        DomainError: When the token is malformed, unsigned, expired, or for
            another audience/issuer.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise DomainError("auth.invalid_token", status=401)
    header = _json_part(parts[0])
    payload = _json_part(parts[1])
    if header.get("alg") != _EXPECTED_ALGORITHM or header.get("typ") != "JWT":
        raise DomainError("auth.invalid_token", status=401)
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual = _decode_base64url(parts[2])
    if not hmac.compare_digest(expected, actual):
        raise DomainError("auth.invalid_token", status=401)
    now = int(time.time())
    if payload.get("aud") != _EXPECTED_AUDIENCE or payload.get("iss") != _EXPECTED_ISSUER:
        raise DomainError("auth.invalid_token", status=401)
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < now:
        raise DomainError("auth.invalid_token", status=401)
    return payload


def _normalise_groups(groups: Any) -> tuple[str, ...]:
    """Normalize token group claims into lowercase strings.

    Args:
        groups: Raw ``groups`` claim.

    Returns:
        Tuple of normalized groups.
    """
    if isinstance(groups, str):
        values: Sequence[Any] = [groups]
    elif isinstance(groups, Sequence):
        values = groups
    else:
        values = []
    return tuple(str(group).strip().lower() for group in values if str(group).strip())


def get_authenticated_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    """Verify the bearer token and return the authenticated user.

    Args:
        authorization: HTTP Authorization header.

    Returns:
        The authenticated backend user.

    Raises:
        DomainError: When authentication is missing or invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise DomainError("auth.missing_token", status=401)
    if settings.backend_auth_secret is None:
        raise DomainError("auth.not_configured", status=500)
    payload = _verify_hs256(
        authorization.removeprefix("Bearer ").strip(),
        settings.backend_auth_secret.get_secret_value(),
    )
    username = str(payload.get("name") or payload.get("email") or payload.get("sub") or "").strip().lower()
    if not username:
        raise DomainError("auth.invalid_token", status=401)
    role = str(payload.get("role") or "user").strip().lower()
    return AuthenticatedUser(username=username, role=role, groups=_normalise_groups(payload.get("groups")))


def require_admin_user(user: AuthenticatedUser) -> AuthenticatedUser:
    """Return ``user`` only when backend admin authorization passes.

    Args:
        user: Authenticated user resolved from a signed backend token.

    Returns:
        The same user when authorized.

    Raises:
        DomainError: When the user is not a backend admin.
    """
    if user.username in settings.admin_usernames_set:
        return user
    if settings.admin_groups_set and settings.admin_groups_set.intersection(user.groups):
        return user
    raise DomainError("admin.forbidden", status=403)
