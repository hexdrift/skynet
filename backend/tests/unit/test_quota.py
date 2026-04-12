"""Tests for the per-user job quota enforcement."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from core.api.routers._helpers import enforce_user_quota
from core.job_quota_overrides import get_user_quota


class _FakeJobStore:
    def __init__(self, counts: dict[str, int]) -> None:
        self._counts = counts

    def count_jobs(self, *, username: str | None = None, **_: object) -> int:
        return self._counts.get(username or "", 0)


def test_get_user_quota_returns_default_for_unknown_user() -> None:
    assert get_user_quota("random", default=100) == 100


def test_get_user_quota_admin_returns_none() -> None:
    with patch("core.job_quota_overrides.ADMIN_USERNAMES", frozenset({"admin"})):
        assert get_user_quota("admin", default=100) is None


def test_get_user_quota_override_int_takes_precedence() -> None:
    with patch("core.job_quota_overrides.QUOTA_OVERRIDES", {"power": 500}):
        assert get_user_quota("power", default=100) == 500


def test_get_user_quota_override_none_means_unlimited() -> None:
    with patch("core.job_quota_overrides.QUOTA_OVERRIDES", {"researcher": None}):
        assert get_user_quota("researcher", default=100) is None


def test_get_user_quota_admin_wins_over_override() -> None:
    with (
        patch("core.job_quota_overrides.ADMIN_USERNAMES", frozenset({"alice"})),
        patch("core.job_quota_overrides.QUOTA_OVERRIDES", {"alice": 50}),
    ):
        assert get_user_quota("alice", default=100) is None


def test_enforce_user_quota_allows_user_below_cap() -> None:
    store = _FakeJobStore({"bob": 42})
    enforce_user_quota(store, "bob")


def test_enforce_user_quota_rejects_user_at_cap() -> None:
    store = _FakeJobStore({"bob": 100})
    with pytest.raises(HTTPException) as exc:
        enforce_user_quota(store, "bob")
    assert exc.value.status_code == 409
    assert "100" in exc.value.detail
    assert "הגעת" in exc.value.detail


def test_enforce_user_quota_rejects_user_over_cap() -> None:
    store = _FakeJobStore({"bob": 250})
    with pytest.raises(HTTPException) as exc:
        enforce_user_quota(store, "bob")
    assert exc.value.status_code == 409


def test_enforce_user_quota_admin_bypass() -> None:
    store = _FakeJobStore({"admin": 9999})
    with patch("core.api.routers._helpers.get_user_quota", return_value=None):
        enforce_user_quota(store, "admin")


def test_enforce_user_quota_override_raises_cap() -> None:
    store = _FakeJobStore({"power": 400})
    with patch("core.api.routers._helpers.get_user_quota", return_value=500):
        enforce_user_quota(store, "power")


def test_enforce_user_quota_override_still_rejects_at_new_cap() -> None:
    store = _FakeJobStore({"power": 500})
    with patch("core.api.routers._helpers.get_user_quota", return_value=500), pytest.raises(HTTPException) as exc:
        enforce_user_quota(store, "power")
    assert exc.value.status_code == 409
    assert "500" in exc.value.detail
