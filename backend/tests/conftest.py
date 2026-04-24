"""Test configuration for Skynet backend.

Requirements:
    - OPENAI_API_KEY in backend/.env
    - PostgreSQL running with skynet_test database
    - Backend server running on localhost:8000 (for integration + load tests)
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

_BASE_URL = "http://localhost:8000"


def has_openai_key() -> bool:
    """Return True if OPENAI_API_KEY is set and looks valid."""
    key = os.getenv("OPENAI_API_KEY", "")
    return key.startswith("sk-") and len(key) > 20


def is_server_available() -> bool:
    """Return True if the backend server is reachable on localhost:8000."""
    try:
        return requests.get(f"{_BASE_URL}/health", timeout=2).status_code == 200
    except Exception:
        return False


requires_llm = pytest.mark.skipif(
    not has_openai_key(),
    reason="OPENAI_API_KEY not set — set it in backend/.env",
)

requires_server = pytest.mark.skipif(
    not is_server_available(),
    reason="Backend server not running on localhost:8000 — start with: cd backend && ../.venv/bin/python main.py",
)


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """Skip the entire session if the server is down, then yield base URL."""
    if not is_server_available():
        pytest.skip(
            "Backend server not running on localhost:8000 — "
            "start with: cd backend && ../.venv/bin/python main.py"
        )
    return _BASE_URL


_TERMINAL = frozenset({"success", "failed", "cancelled"})


def wait_for_terminal(job_id: str, base_url: str = _BASE_URL, timeout: float = 180) -> dict:
    """Poll job until terminal status; raises TimeoutError if not reached within *timeout* s.

    Args:
        job_id: The optimization job ID to poll.
        base_url: Base URL of the backend server.
        timeout: Maximum seconds to wait before raising TimeoutError.

    Returns:
        The final job status response dict once a terminal status is reached.

    Raises:
        TimeoutError: If the job does not reach a terminal status within *timeout* seconds.
    """
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        r = requests.get(f"{base_url}/optimizations/{job_id}", timeout=10)
        last = r.json()
        if last.get("status") in _TERMINAL:
            return last
        time.sleep(3)
    raise TimeoutError(
        f"Job {job_id} did not finish within {timeout}s "
        f"(last status: {last.get('status')!r})"
    )


def wait_for_status(
    job_id: str,
    target: str | set[str],
    base_url: str = _BASE_URL,
    timeout: float = 30,
) -> dict:
    """Poll until job reaches *target* status; useful for cancellation/validation checks.

    Args:
        job_id: The optimization job ID to poll.
        target: A single status string or a set of acceptable status strings.
        base_url: Base URL of the backend server.
        timeout: Maximum seconds to wait before raising TimeoutError.

    Returns:
        The job status response dict once the target status is reached.

    Raises:
        TimeoutError: If the job does not reach *target* within *timeout* seconds.
    """
    targets = {target} if isinstance(target, str) else set(target)
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        r = requests.get(f"{base_url}/optimizations/{job_id}", timeout=10)
        last = r.json()
        if last.get("status") in targets:
            return last
        time.sleep(2)
    raise TimeoutError(
        f"Job {job_id} did not reach status {targets!r} within {timeout}s "
        f"(last status: {last.get('status')!r})"
    )
