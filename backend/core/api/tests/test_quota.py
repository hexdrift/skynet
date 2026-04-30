"""Tests for the per-user job quota enforcement.

Rewrites the previously-skipped suite that targeted the removed
``core.job_quota_overrides`` module.  All assertions now go through
``core.config.settings.get_user_quota`` and
``core.api.routers._helpers.enforce_user_quota``.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from ...config import Settings

# noinspection PyProtectedMember
from ..routers import _helpers as _h

# noinspection PyProtectedMember
from ..routers._helpers import enforce_user_quota


class _FakeJobStore:
    """Minimal fake store that returns canned per-user job counts."""

    def __init__(self, counts: dict[str, int]) -> None:
        """Capture per-username counts to return from ``count_jobs``.

        Args:
            counts: Mapping of username to the number of jobs for that user.
        """
        self._counts = counts

    def count_jobs(self, *, username: str | None = None, **_: object) -> int:
        """Return the canned count for ``username`` (zero if absent).

        Args:
            username: Username to look up. ``None`` is treated as the empty key.
            **_: Ignored extra filters; preserved to match the real signature.

        Returns:
            The number of jobs recorded for that username.
        """
        return self._counts.get(username or "", 0)


class _FakeLiveQuotaJobStore(_FakeJobStore):
    """Fake store that exposes the live quota resolver used by Postgres."""

    def __init__(self, counts: dict[str, int], quota: int | None) -> None:
        """Capture canned counts and an effective quota.

        Args:
            counts: Mapping of username to the number of jobs for that user.
            quota: Effective quota to return, or ``None`` for unlimited.
        """
        super().__init__(counts)
        self._quota = quota

    def get_effective_user_quota(self, username: str) -> int | None:
        """Return the canned live quota.

        Args:
            username: Username being resolved.

        Returns:
            The quota configured for this fake store.
        """
        return self._quota


def test_get_user_quota_returns_default_for_unknown_user() -> None:
    """Unknown users fall back to the default per-user job cap."""
    s = Settings(max_jobs_per_user=100)

    assert s.get_user_quota("random_user") == 100


def test_get_user_quota_admin_uses_default_quota() -> None:
    """Admin usernames do not bypass normal quota enforcement."""
    s = Settings(admin_usernames="admin,superuser", max_jobs_per_user=100)

    assert s.get_user_quota("admin") == 100
    assert s.get_user_quota("superuser") == 100


def test_get_user_quota_admin_check_does_not_override_case_insensitively() -> None:
    """Admin casing has no effect on quota resolution."""
    s = Settings(admin_usernames="Admin", max_jobs_per_user=100)

    assert s.get_user_quota("admin") == 100


def test_get_user_quota_override_int_takes_precedence() -> None:
    """An integer override raises the cap above the default."""
    # quota_overrides_json uses alias="QUOTA_OVERRIDES" in Settings
    s = Settings(QUOTA_OVERRIDES='{"power": 500}', max_jobs_per_user=100)

    assert s.get_user_quota("power") == 500


def test_get_user_quota_override_none_means_unlimited() -> None:
    """An override of ``null`` makes that user's quota unlimited."""
    s = Settings(QUOTA_OVERRIDES='{"researcher": null}', max_jobs_per_user=100)

    assert s.get_user_quota("researcher") is None


def test_get_user_quota_override_wins_over_admin_status() -> None:
    """Quota overrides are independent from admin authorization."""
    s = Settings(
        admin_usernames="alice",
        QUOTA_OVERRIDES='{"alice": 50}',
        max_jobs_per_user=100,
    )

    assert s.get_user_quota("alice") == 50


def test_get_user_quota_non_overridden_user_gets_default() -> None:
    """A user not in the override map still receives the default cap."""
    s = Settings(QUOTA_OVERRIDES='{"other": 200}', max_jobs_per_user=100)

    assert s.get_user_quota("someone_else") == 100


def test_enforce_user_quota_allows_user_below_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A user under the cap passes ``enforce_user_quota`` without raising."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 100)
    store = _FakeJobStore({"bob": 42})
    enforce_user_quota(store, "bob")


def test_enforce_user_quota_rejects_user_at_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A user exactly at the cap is rejected with a 409 referencing the cap."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 100)
    store = _FakeJobStore({"bob": 100})
    with pytest.raises(HTTPException, match=r"100"):
        enforce_user_quota(store, "bob")


def test_enforce_user_quota_rejects_user_over_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A user over the cap is rejected with a 409."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 100)
    store = _FakeJobStore({"bob": 250})
    with pytest.raises(HTTPException) as exc:
        enforce_user_quota(store, "bob")
    assert exc.value.status_code == 409


def test_enforce_user_quota_409_detail_contains_quota_number(monkeypatch: pytest.MonkeyPatch) -> None:
    """The 409 detail includes the configured quota number."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 100)
    store = _FakeJobStore({"bob": 100})
    with pytest.raises(HTTPException) as exc:
        enforce_user_quota(store, "bob")
    assert "100" in exc.value.detail
    assert exc.value.status_code == 409


def test_enforce_user_quota_none_quota_bypasses_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Users with an unlimited quota (``None``) bypass the check entirely."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: None)
    store = _FakeJobStore({"admin": 9999})
    enforce_user_quota(store, "admin")


def test_enforce_user_quota_override_raises_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A higher per-user override is honoured by the enforcement helper."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 500)
    store = _FakeJobStore({"power": 400})
    enforce_user_quota(store, "power")


def test_enforce_user_quota_override_still_rejects_at_new_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """An overridden quota is still enforced once the user reaches it."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 500)
    store = _FakeJobStore({"power": 500})
    with pytest.raises(HTTPException) as exc:
        enforce_user_quota(store, "power")
    assert exc.value.status_code == 409
    assert "500" in exc.value.detail


def test_enforce_user_quota_uses_live_store_quota_before_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """A DB-backed live quota can raise the cap without changing config."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 100)
    store = _FakeLiveQuotaJobStore({"power": 250}, quota=500)
    enforce_user_quota(store, "power")


def test_enforce_user_quota_live_none_bypasses_config_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A DB-backed ``None`` quota gives a user unlimited quota immediately."""
    monkeypatch.setattr(_h.settings.__class__, "get_user_quota", lambda self, u: 100)
    store = _FakeLiveQuotaJobStore({"researcher": 9999}, quota=None)
    enforce_user_quota(store, "researcher")
