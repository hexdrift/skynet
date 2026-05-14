"""Test configuration for Skynet backend.

Requirements:
    - OPENAI_API_KEY in backend/.env
    - PostgreSQL running with skynet_test database
    - Backend server running on localhost:8000 (for integration + load tests)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest
import requests  # type: ignore[import-untyped]
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

_BASE_URL = "http://localhost:8000"
_TEST_AUTH_GROUP = "skynet-tests"


def _base64url(value: bytes) -> str:
    """Encode bytes as unpadded base64url text."""
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def backend_auth_headers(username: str = "backend-test") -> dict[str, str]:
    """Build the bearer auth header expected by protected live-server tests.

    Args:
        username: Subject/name claim to place in the signed backend token.

    Returns:
        HTTP headers containing a signed bearer token.
    """
    secret = os.getenv("BACKEND_AUTH_SECRET")
    if not secret:
        pytest.skip(
            "BACKEND_AUTH_SECRET not set — live-server auth tests need a backend token secret",
        )
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
                "exp": now + 3600,
                "jti": str(uuid4()),
            },
        ).encode("utf-8"),
    )
    signature = _base64url(
        hmac.new(
            secret.encode("utf-8"),
            f"{header}.{payload}".encode("ascii"),
            hashlib.sha256,
        ).digest(),
    )
    return {"Authorization": f"Bearer {header}.{payload}.{signature}"}


def has_openai_key() -> bool:
    """Return ``True`` when ``OPENAI_API_KEY`` looks like a real key.

    Returns:
        ``True`` when the env var starts with ``sk-`` and is longer than 20
        characters; ``False`` otherwise.
    """
    key = os.getenv("OPENAI_API_KEY", "")
    return key.startswith("sk-") and len(key) > 20


def is_server_available() -> bool:
    """Return ``True`` when the backend at ``localhost:8000`` answers ``/health``.

    Returns:
        ``True`` on a 200 response within a 2 s timeout, ``False`` for any
        connection error or non-200 status.
    """
    try:
        return requests.get(f"{_BASE_URL}/health", timeout=2).status_code == 200
    except (requests.RequestException, OSError):
        return False


requires_llm = pytest.mark.skipif(
    not has_openai_key(),
    reason="OPENAI_API_KEY not set — set it in backend/.env",
)

requires_server = pytest.mark.skipif(
    not is_server_available(),
    reason="Backend server not running on localhost:8000 — start with: cd backend && ../.venv/bin/python main.py",
)


_TERMINAL = frozenset({"success", "failed", "cancelled"})


def wait_for_terminal(
    job_id: str,
    base_url: str = _BASE_URL,
    timeout: float = 180,
    username: str = "backend-test",
) -> dict:
    """Poll the backend until ``job_id`` reaches success/failed/cancelled.

    Args:
        job_id: Identifier returned by ``POST /run`` or ``POST /grid-search``.
        base_url: Base URL of the backend; defaults to ``localhost:8000``.
        timeout: Maximum seconds to wait before raising.
        username: Authenticated test user that owns the job.

    Returns:
        The final ``GET /optimizations/{job_id}`` JSON payload.

    Raises:
        TimeoutError: When the job does not reach a terminal status within
            ``timeout`` seconds.
    """
    deadline = time.monotonic() + timeout
    last: dict = {}
    headers = backend_auth_headers(username)
    while time.monotonic() < deadline:
        r = requests.get(
            f"{base_url}/optimizations/{job_id}",
            headers=headers,
            timeout=10,
        )
        last = r.json()
        if last.get("status") in _TERMINAL:
            return last
        time.sleep(3)
    raise TimeoutError(
        f"Job {job_id} did not finish within {timeout}s (last status: {last.get('status')!r})",
    )
