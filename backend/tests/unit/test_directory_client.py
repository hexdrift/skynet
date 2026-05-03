"""Tests for directory client selection and LDAP entry conversion."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.api.directory_client import DirectoryUser, LdapDirectoryClient, NullDirectoryClient, build_directory_client

_LDAP_ENV_VARS = (
    "AD_LDAP_URL",
    "AD_LDAP_BIND_DN",
    "AD_LDAP_BIND_PASSWORD",
    "AD_LDAP_SEARCH_BASE",
    "AD_LDAP_USER_FILTER",
    "AD_LDAP_USERNAME_ATTR",
)


@pytest.fixture(autouse=True)
def _isolate_ldap_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear LDAP env vars before each directory-client test."""
    for name in _LDAP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_build_directory_client_returns_null_without_required_env() -> None:
    """Missing LDAP env vars select the null fallback."""
    client = build_directory_client()

    assert isinstance(client, NullDirectoryClient)


def test_build_directory_client_returns_ldap_when_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Complete LDAP env vars select the LDAP-backed client."""
    monkeypatch.setenv("AD_LDAP_URL", "ldaps://dc1.example.internal:636")
    monkeypatch.setenv("AD_LDAP_BIND_DN", "CN=svc,DC=example,DC=internal")
    monkeypatch.setenv("AD_LDAP_BIND_PASSWORD", "secret")
    monkeypatch.setenv("AD_LDAP_SEARCH_BASE", "DC=example,DC=internal")
    monkeypatch.setenv("AD_LDAP_USERNAME_ATTR", "userPrincipalName")

    client = build_directory_client()

    assert isinstance(client, LdapDirectoryClient)
    assert client.username_attr == "userPrincipalName"


def test_ldap_entry_to_user_uses_first_non_empty_attribute() -> None:
    """LDAP entries are normalized into directory user matches."""
    client = LdapDirectoryClient(
        url="ldaps://dc1.example.internal:636",
        bind_dn="CN=svc,DC=example,DC=internal",
        bind_password="secret",
        search_base="DC=example,DC=internal",
    )
    entry = SimpleNamespace(
        entry_attributes_as_dict={
            "sAMAccountName": ["", "alice"],
            "displayName": ["Alice Example"],
            "mail": ["alice@example.internal"],
        }
    )

    assert client._entry_to_user(entry) == DirectoryUser(
        username="alice",
        display_name="Alice Example",
        email="alice@example.internal",
    )
