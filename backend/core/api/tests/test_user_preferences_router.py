"""Tests for the agent-facing browser-preference patch endpoint."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ..auth import AuthenticatedUser, get_authenticated_user
from ..routers.user_preferences import create_user_preferences_router


@pytest.fixture
def prefs_client() -> TestClient:
    """Build an authenticated client exposing only the preferences router.

    Returns:
        A ``TestClient`` over a minimal FastAPI app.
    """
    app = FastAPI()
    app.include_router(create_user_preferences_router())
    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(
        username="user@example.com",
        role="user",
        groups=(),
    )
    return TestClient(app)


def test_patch_echoes_only_the_requested_fields(prefs_client: TestClient) -> None:
    """Supported fields come back as the patch; unset ones are left out."""
    resp = prefs_client.post(
        "/settings/user-preferences",
        json={"lite_mode": True, "wizard_split_mode": "manual"},
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "updates": {"lite_mode": True, "wizard_split_mode": "manual"},
        "changed": ["lite_mode", "wizard_split_mode"],
    }


def test_retired_advanced_mode_is_not_part_of_the_patch(prefs_client: TestClient) -> None:
    """The removed advanced-mode toggle never reaches the browser patch."""
    resp = prefs_client.post(
        "/settings/user-preferences",
        json={"advanced_mode": True, "expand_advanced": True},
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "updates": {"expand_advanced": True},
        "changed": ["expand_advanced"],
    }
