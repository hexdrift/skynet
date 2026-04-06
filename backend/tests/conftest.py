"""Test configuration for Skynet backend.

All tests use real OpenAI API calls and a real PostgreSQL database.
No mocks.

Requirements:
    - OPENAI_API_KEY in backend/.env
    - PostgreSQL running with skynet_test database
    - Backend server running on localhost:8000 (for integration + load tests)
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load .env so tests can access OPENAI_API_KEY, REMOTE_DB_URL, etc.
load_dotenv(REPO_ROOT / ".env")


def has_openai_key() -> bool:
    """Check if OPENAI_API_KEY is set and looks valid."""
    key = os.getenv("OPENAI_API_KEY", "")
    return key.startswith("sk-") and len(key) > 20


requires_llm = pytest.mark.skipif(
    not has_openai_key(),
    reason="OPENAI_API_KEY not set — set it in backend/.env",
)
