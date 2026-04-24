"""Tests for the per-user job quota enforcement.

Rewrites the previously-skipped suite that targeted the removed
``core.job_quota_overrides`` module.  All assertions now go through
``core.config.settings.get_user_quota`` and
``core.api.routers._helpers.enforce_user_quota``.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

# noinspection PyProtectedMember
from ..routers import _helpers as _h  # noqa: SLF001
# noinspection PyProtectedMember
from ..routers._helpers import enforce_user_quota  # noqa: SLF001
from ...config import Settings


class _FakeJobStore:
    def __init__(self, counts: dict[str, int]) -> None:
        self._counts = counts

    def count_jobs(self, *, username: str | None = None, **_: object) -> int:
        return self._counts.get(username or "", 0)


def test_get_user_quota_returns_default_for_unknown_user() -> None:
    """get_user_quota returns the global default when the user has no override."""
    s = Settings(max_jobs_per_user=100)

    assert s.get_user_quota("random_user") == 100


def test_get_user_quota_admin_returns_none() -> None:
    """get_user_quota returns None (unlimited) for every username in admin_usernames."""
    s = Settings(admin_usernames="admin,superuser", max_jobs_per_user=100)

    assert s.get_user_quota("admin") is None
    assert s.get_user_quota("superuser") is None


def test_get_user_quota_admin_check_is_case_insensitive() -> None:
    """Admin username matching is case-insensitive."""
    s = Settings(admin_usernames="Admin", max_jobs_per_user=100)

    assert s.get_user_quota("admin") is None


def test_get_user_quota_override_int_takes_precedence() -> None:
    """A numeric override in QUOTA_OVERRIDES takes precedence over the global default."""
    # quota_overrides_json uses alias="QUOTA_OVERRIDES" in Settings
    s = Settings(**{"QUOTA_OVERRIDES": '{"power": 500}'}, max_jobs_per_user=100)

    assert s.get_user_quota("power") == 500


def test_get_user_quota_override_none_means_unlimited() -> None:
    """A null override in QUOTA_OVERRIDES grants unlimited quota (returns None)."""
    s = Settings(**{"QUOTA_OVERRIDES": '{"researcher": null}'}, max_jobs_per_user=100)

    assert s.get_user_quota("researcher") is None


def test_get_user_quota_admin_wins_over_override() -> None:
    """Admin membership overrides any per-user quota entry; the result is always None."""
    s = Settings(
        admin_usernames="alice",
        **{"QUOTA_OVERRIDES": '{"alice": 50}'},
        max_jobs_per_user=100,
    )

    assert s.get_user_quota("alice") is None


def test_get_user_quota_non_overridden_user_gets_default() -> None:
    """Users not listed in QUOTA_OVERRIDES still receive the global default quota."""
    s = Settings(**{"QUOTA_OVERRIDES": '{"other": 200}'}, max_jobs_per_user=100)

    assert s.get_user_quota("someone_else") == 100


def test_enforce_user_quota_allows_user_below_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """enforce_user_quota does not raise when the user is below their quota cap."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 100)
    store = _FakeJobStore({"bob": 42})
    enforce_user_quota(store, "bob")  # must not raise


def test_enforce_user_quota_rejects_user_at_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """enforce_user_quota raises HTTPException 409 when the user's count equals the cap."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 100)
    store = _FakeJobStore({"bob": 100})
    with pytest.raises(HTTPException, match=r"100"):
        enforce_user_quota(store, "bob")


def test_enforce_user_quota_rejects_user_over_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """enforce_user_quota raises HTTPException 409 when the user's count exceeds the cap."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 100)
    store = _FakeJobStore({"bob": 250})
    with pytest.raises(HTTPException) as exc:
        enforce_user_quota(store, "bob")
    assert exc.value.status_code == 409


def test_enforce_user_quota_409_detail_contains_quota_number(monkeypatch: pytest.MonkeyPatch) -> None:
    """The 409 detail message includes the quota number so the caller can display it."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 100)
    store = _FakeJobStore({"bob": 100})
    with pytest.raises(HTTPException) as exc:
        enforce_user_quota(store, "bob")
    assert "100" in exc.value.detail
    assert exc.value.status_code == 409


def test_enforce_user_quota_none_quota_bypasses_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """enforce_user_quota skips the check entirely when get_user_quota returns None."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: None)
    store = _FakeJobStore({"admin": 9999})
    enforce_user_quota(store, "admin")  # must not raise


def test_enforce_user_quota_override_raises_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A user below an elevated override quota is allowed through without raising."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 500)
    store = _FakeJobStore({"power": 400})
    enforce_user_quota(store, "power")  # 400 < 500 — must not raise


def test_enforce_user_quota_override_still_rejects_at_new_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A user at an elevated override quota is still rejected with 409."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 500)
    store = _FakeJobStore({"power": 500})
    with pytest.raises(HTTPException) as exc:
        enforce_user_quota(store, "power")
    assert exc.value.status_code == 409
    assert "500" in exc.value.detail
