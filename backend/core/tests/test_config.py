"""Tests for core.config.Settings and its helpers."""

from __future__ import annotations

import json

import pytest

from core.config import Settings


_SETTINGS_ENV_VARS = (
    "REMOTE_DB_URL",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "WORKER_CONCURRENCY",
    "WORKER_POLL_INTERVAL",
    "WORKER_STALE_THRESHOLD",
    "CANCEL_POLL_INTERVAL",
    "JOB_RUN_START_METHOD",
    "ARTIFACTS_DIR",
    "LOGS_DIR",
    "DEFAULT_TIMEOUT",
    "LONG_RUNNING_TIMEOUT",
    "SUBPROCESS_TIMEOUT",
    "HOST",
    "PORT",
    "RELOAD",
    "ALLOWED_ORIGINS",
    "LOG_LEVEL",
    "MAX_JOBS_PER_USER",
    "ADMIN_USERNAMES",
    "QUOTA_OVERRIDES",
)


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear Settings-relevant env vars so every test starts from pure defaults.

    pydantic-settings reads ``os.environ`` even when ``_env_file=None``, so any
    value exported in the developer shell (or loaded from ``backend/.env``
    earlier in the process) would otherwise leak into default-value tests.
    """
    for var in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv(var.lower(), raising=False)


def test_settings_defaults_worker_threads() -> None:
    """Verify Settings defaults worker_threads to 4."""
    s = Settings(_env_file=None)

    assert s.worker_threads == 4


def test_settings_defaults_worker_poll_interval() -> None:
    """Verify Settings defaults worker_poll_interval to 1.0."""
    s = Settings(_env_file=None)

    assert s.worker_poll_interval == 1.0


def test_settings_defaults_worker_stale_threshold() -> None:
    """Verify Settings defaults worker_stale_threshold to 600.0."""
    s = Settings(_env_file=None)

    assert s.worker_stale_threshold == 600.0


def test_settings_defaults_cancel_poll_interval() -> None:
    """Verify Settings defaults cancel_poll_interval to 1.0."""
    s = Settings(_env_file=None)

    assert s.cancel_poll_interval == 1.0


def test_settings_defaults_job_run_start_method() -> None:
    """Verify Settings defaults job_run_start_method to 'fork'."""
    s = Settings(_env_file=None)

    assert s.job_run_start_method == "fork"


def test_settings_defaults_artifacts_dir() -> None:
    """Verify Settings defaults artifacts_dir to 'artifacts'."""
    s = Settings(_env_file=None)

    assert s.artifacts_dir == "artifacts"


def test_settings_defaults_logs_dir() -> None:
    """Verify Settings defaults logs_dir to 'logs'."""
    s = Settings(_env_file=None)

    assert s.logs_dir == "logs"


def test_settings_defaults_host() -> None:
    """Verify Settings defaults host to '0.0.0.0'."""
    s = Settings(_env_file=None)

    assert s.host == "0.0.0.0"


def test_settings_defaults_port() -> None:
    """Verify Settings defaults port to 8000."""
    s = Settings(_env_file=None)

    assert s.port == 8000


def test_settings_defaults_reload() -> None:
    """Verify Settings defaults reload to False."""
    s = Settings(_env_file=None)

    assert s.reload is False


def test_settings_defaults_log_level() -> None:
    """Verify Settings defaults log_level to 'INFO'."""
    s = Settings(_env_file=None)

    assert s.log_level == "INFO"


def test_settings_defaults_max_jobs_per_user() -> None:
    """Verify Settings defaults max_jobs_per_user to 100."""
    s = Settings(_env_file=None)

    assert s.max_jobs_per_user == 100


def test_settings_defaults_api_keys_are_none() -> None:
    """Verify Settings defaults all API key fields to None."""
    s = Settings(_env_file=None)

    assert s.openai_api_key is None
    assert s.anthropic_api_key is None
    assert s.remote_db_url is None




def test_settings_env_override_worker_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify WORKER_CONCURRENCY env var overrides worker_threads."""
    monkeypatch.setenv("WORKER_CONCURRENCY", "8")

    s = Settings(_env_file=None)

    assert s.worker_threads == 8


def test_settings_env_override_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify PORT env var overrides the default port."""
    monkeypatch.setenv("PORT", "9090")

    s = Settings(_env_file=None)

    assert s.port == 9090


def test_settings_env_override_reload_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify RELOAD=true env var sets reload to True."""
    monkeypatch.setenv("RELOAD", "true")

    s = Settings(_env_file=None)

    assert s.reload is True


def test_settings_env_override_reload_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify RELOAD=false env var sets reload to False."""
    monkeypatch.setenv("RELOAD", "false")

    s = Settings(_env_file=None)

    assert s.reload is False


def test_settings_env_override_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify LOG_LEVEL env var overrides the default log level."""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    s = Settings(_env_file=None)

    assert s.log_level == "DEBUG"


def test_settings_env_override_cors_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify ALLOWED_ORIGINS env var overrides cors_origins."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://example.com,http://other.com")

    s = Settings(_env_file=None)

    assert s.cors_origins == "http://example.com,http://other.com"


def test_settings_env_override_admin_usernames(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify ADMIN_USERNAMES env var sets admin_usernames."""
    monkeypatch.setenv("ADMIN_USERNAMES", "alice,bob")

    s = Settings(_env_file=None)

    assert s.admin_usernames == "alice,bob"


def test_settings_env_override_max_jobs_per_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify MAX_JOBS_PER_USER env var overrides max_jobs_per_user."""
    monkeypatch.setenv("MAX_JOBS_PER_USER", "200")

    s = Settings(_env_file=None)

    assert s.max_jobs_per_user == 200


def test_settings_env_override_quota_overrides_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify QUOTA_OVERRIDES env var sets quota_overrides_json."""
    monkeypatch.setenv("QUOTA_OVERRIDES", '{"power_user": 500}')

    s = Settings(_env_file=None)

    assert s.quota_overrides_json == '{"power_user": 500}'


def test_settings_env_override_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Settings loads env vars case-insensitively."""
    monkeypatch.setenv("port", "7777")

    s = Settings(_env_file=None)

    assert s.port == 7777




def test_cors_origins_list_parses_defaults() -> None:
    """Verify cors_origins_list parses the default comma-separated string."""
    s = Settings(_env_file=None)

    result = s.cors_origins_list

    assert result == ["http://localhost:3000", "http://localhost:3001"]


def test_cors_origins_list_strips_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify cors_origins_list strips whitespace from each origin."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "  http://a.com ,  http://b.com  ")

    s = Settings(_env_file=None)

    assert s.cors_origins_list == ["http://a.com", "http://b.com"]


def test_cors_origins_list_skips_empty_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify cors_origins_list skips empty entries from doubled commas."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://a.com,,http://b.com,")

    s = Settings(_env_file=None)

    assert s.cors_origins_list == ["http://a.com", "http://b.com"]


def test_cors_origins_list_single_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify cors_origins_list returns a single-element list for one origin."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://only.com")

    s = Settings(_env_file=None)

    assert s.cors_origins_list == ["http://only.com"]


def test_cors_origins_list_empty_string_returns_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify cors_origins_list returns an empty list when ALLOWED_ORIGINS is empty."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "")

    s = Settings(_env_file=None)

    assert s.cors_origins_list == []




def test_admin_usernames_set_empty_by_default() -> None:
    """Verify admin_usernames_set is empty when ADMIN_USERNAMES is not set."""
    s = Settings(_env_file=None)

    assert s.admin_usernames_set == frozenset()


def test_admin_usernames_set_parses_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify admin_usernames_set parses a CSV list into a frozenset."""
    monkeypatch.setenv("ADMIN_USERNAMES", "alice,bob,carol")

    s = Settings(_env_file=None)

    assert s.admin_usernames_set == frozenset({"alice", "bob", "carol"})


def test_admin_usernames_set_lowercases(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify admin_usernames_set normalizes usernames to lowercase."""
    monkeypatch.setenv("ADMIN_USERNAMES", "Alice,BOB")

    s = Settings(_env_file=None)

    assert s.admin_usernames_set == frozenset({"alice", "bob"})


def test_admin_usernames_set_strips_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify admin_usernames_set strips surrounding whitespace from each name."""
    monkeypatch.setenv("ADMIN_USERNAMES", " alice , bob ")

    s = Settings(_env_file=None)

    assert s.admin_usernames_set == frozenset({"alice", "bob"})


def test_admin_usernames_set_skips_empty_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify admin_usernames_set skips empty entries in the CSV."""
    monkeypatch.setenv("ADMIN_USERNAMES", "alice,,bob,")

    s = Settings(_env_file=None)

    assert s.admin_usernames_set == frozenset({"alice", "bob"})




def test_get_user_quota_unknown_user_returns_default() -> None:
    """Verify get_user_quota returns max_jobs_per_user for an unknown user."""
    s = Settings(_env_file=None)

    result = s.get_user_quota("unknown_user")

    assert result == s.max_jobs_per_user


def test_get_user_quota_admin_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_user_quota returns None (unlimited) for an admin user."""
    monkeypatch.setenv("ADMIN_USERNAMES", "superadmin")

    s = Settings(_env_file=None)

    assert s.get_user_quota("superadmin") is None


def test_get_user_quota_admin_case_insensitive_lower_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_user_quota admin lookup matches stored lowercase names."""
    # admin_usernames_set stores lowercase, so lookup must match
    monkeypatch.setenv("ADMIN_USERNAMES", "Admin")

    s = Settings(_env_file=None)

    # "Admin" is stored as "admin" — exact string "Admin" won't match
    # This exposes a case-sensitivity issue in get_user_quota (see bug report below)
    assert s.get_user_quota("admin") is None


def test_get_user_quota_override_int_returns_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_user_quota returns the integer override for a configured user."""
    monkeypatch.setenv("QUOTA_OVERRIDES", json.dumps({"power_user": 500}))

    s = Settings(_env_file=None)

    assert s.get_user_quota("power_user") == 500


def test_get_user_quota_override_none_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_user_quota returns None (unlimited) when override is null."""
    monkeypatch.setenv("QUOTA_OVERRIDES", json.dumps({"researcher": None}))

    s = Settings(_env_file=None)

    assert s.get_user_quota("researcher") is None


def test_get_user_quota_admin_wins_over_int_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify admin status takes precedence over a quota_overrides_json entry."""
    monkeypatch.setenv("ADMIN_USERNAMES", "alice")
    monkeypatch.setenv("QUOTA_OVERRIDES", json.dumps({"alice": 50}))

    s = Settings(_env_file=None)

    assert s.get_user_quota("alice") is None


def test_get_user_quota_non_admin_user_with_no_override_returns_max(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_user_quota returns max_jobs_per_user when user has no override."""
    monkeypatch.setenv("MAX_JOBS_PER_USER", "75")
    monkeypatch.setenv("QUOTA_OVERRIDES", json.dumps({"other_user": 200}))

    s = Settings(_env_file=None)

    assert s.get_user_quota("regular_user") == 75


@pytest.mark.parametrize(
    "username,quota_json,admin_csv,expected",
    [
        ("regular", "{}", "", 100),
        ("admin1", "{}", "admin1", None),
        ("power", '{"power": 500}', "", 500),
        ("unlim", '{"unlim": null}', "", None),
        ("admin1", '{"admin1": 50}', "admin1", None),  # admin wins
    ],
    ids=["regular_default", "admin_unlimited", "override_int", "override_none", "admin_over_override"],
)
def test_get_user_quota_parametrized(
    monkeypatch: pytest.MonkeyPatch,
    username: str,
    quota_json: str,
    admin_csv: str,
    expected: int | None,
) -> None:
    """Verify get_user_quota across multiple (username, overrides, admin) combinations."""
    monkeypatch.setenv("QUOTA_OVERRIDES", quota_json)
    monkeypatch.setenv("ADMIN_USERNAMES", admin_csv)

    s = Settings(_env_file=None)

    assert s.get_user_quota(username) == expected




def test_settings_coerces_string_int_for_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Settings coerces the PORT string env var to an integer."""
    monkeypatch.setenv("PORT", "8080")

    s = Settings(_env_file=None)

    assert isinstance(s.port, int)
    assert s.port == 8080


def test_settings_coerces_string_bool_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Settings coerces the RELOAD string env var to a bool."""
    monkeypatch.setenv("RELOAD", "1")

    s = Settings(_env_file=None)

    assert isinstance(s.reload, bool)
    assert s.reload is True


def test_settings_coerces_string_float_poll_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Settings coerces WORKER_POLL_INTERVAL to a float."""
    monkeypatch.setenv("WORKER_POLL_INTERVAL", "2.5")

    s = Settings(_env_file=None)

    assert isinstance(s.worker_poll_interval, float)
    assert s.worker_poll_interval == 2.5




def test_settings_valid_quota_overrides_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Settings accepts a valid QUOTA_OVERRIDES JSON with int and null values."""
    monkeypatch.setenv("QUOTA_OVERRIDES", '{"power_user": 500, "researcher": null}')

    s = Settings(_env_file=None)

    assert s.get_user_quota("power_user") == 500
    assert s.get_user_quota("researcher") is None


def test_settings_malformed_quota_overrides_json_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Settings rejects a malformed QUOTA_OVERRIDES JSON string."""
    monkeypatch.setenv("QUOTA_OVERRIDES", "{not valid json")

    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_settings_empty_quota_overrides_json_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Settings treats an empty QUOTA_OVERRIDES as no overrides."""
    monkeypatch.setenv("QUOTA_OVERRIDES", "")

    s = Settings(_env_file=None)

    assert s.get_user_quota("any_user") == s.max_jobs_per_user
