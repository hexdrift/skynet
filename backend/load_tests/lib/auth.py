"""Bearer-token minting for load-test clients.

Mirrors :func:`tests.conftest.backend_auth_headers` but is import-safe from
the load_tests package (no pytest dependency). Reads
``BACKEND_AUTH_SECRET`` from the environment; raises explicitly when
unset so the harness fails fast instead of producing 401s.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from uuid import uuid4

_TEST_AUTH_GROUP = "skynet-load-tests"


def _base64url(value: bytes) -> str:
    """Encode bytes as unpadded base64url text."""
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _secret() -> str:
    """Return the shared backend auth secret from the environment.

    Returns:
        The HS256 signing secret used by ``get_authenticated_user``.

    Raises:
        RuntimeError: When ``BACKEND_AUTH_SECRET`` is unset; the harness
            cannot mint tokens without it and 401s would otherwise hide
            real load-test failures.
    """
    secret = os.getenv("BACKEND_AUTH_SECRET")
    if not secret:
        raise RuntimeError(
            "BACKEND_AUTH_SECRET is required for the load-test harness."
        )
    return secret


def build_token(username: str, *, ttl_seconds: int = 3600) -> str:
    """Build a signed HS256 bearer JWT accepted by the backend.

    Args:
        username: Subject/name claim used by quota lookups and ownership.
        ttl_seconds: Token lifetime; the orchestrator runs scenarios serially
            so the default 1 h is comfortably longer than the longest run.

    Returns:
        The compact JWT string (no ``Bearer `` prefix).
    """
    now = int(time.time())
    header = _base64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8"))
    payload = _base64url(
        json.dumps(
            {
                "aud": "skynet-backend",
                "iss": "skynet-frontend",
                "sub": username,
                "name": username,
                "role": "user",
                "groups": [_TEST_AUTH_GROUP],
                "iat": now,
                "exp": now + ttl_seconds,
                "jti": str(uuid4()),
            },
        ).encode("utf-8"),
    )
    signature = _base64url(
        hmac.new(
            _secret().encode("utf-8"),
            f"{header}.{payload}".encode("ascii"),
            hashlib.sha256,
        ).digest(),
    )
    return f"{header}.{payload}.{signature}"


def auth_headers(username: str) -> dict[str, str]:
    """Return ``Authorization`` headers for the given test user.

    Args:
        username: Subject claim of the minted token.

    Returns:
        A single-entry dict ready to pass as ``headers=`` to httpx.
    """
    return {"Authorization": f"Bearer {build_token(username)}"}
