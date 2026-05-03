"""Directory service client for looking up network users.

Step 1: only ``NullDirectoryClient`` ships, returning no directory matches.
Admin username autocomplete falls back on previously-seen users from the
local job store.

Step 2 (deferred): when ``AD_LDAP_URL`` and bind credentials are configured,
``build_directory_client`` will return an LDAP-backed implementation that
queries Active Directory for live network users.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DirectoryUser:
    """Network user resolved from a directory lookup."""

    username: str
    display_name: str | None = None
    email: str | None = None


class DirectoryClient(Protocol):
    """Abstract provider for network-wide username search."""

    def search_users(self, query: str, *, limit: int = 10) -> list[DirectoryUser]:
        """Return network users matching ``query``.

        Args:
            query: Free-text fragment matched against username, display name, or email.
            limit: Maximum number of matches to return.

        Returns:
            Matching directory users, possibly empty.
        """
        ...


class NullDirectoryClient:
    """No-op directory client returning zero matches.

    Active whenever AD/LDAP credentials are absent. Keeps the admin
    autocomplete working against DB-known users only.
    """

    def search_users(self, query: str, *, limit: int = 10) -> list[DirectoryUser]:
        """Return an empty list — no directory configured.

        Args:
            query: Ignored.
            limit: Ignored.

        Returns:
            Always an empty list.
        """
        return []


def build_directory_client() -> DirectoryClient:
    """Construct the configured directory client.

    Step 1 always returns :class:`NullDirectoryClient`. When LDAP support
    lands, inspect environment variables here to pick the live implementation.

    Returns:
        A directory client suitable for the current environment.
    """
    # TODO: On-premise - swap NullDirectoryClient for an LDAP-backed client when
    # AD_LDAP_URL / AD_LDAP_BIND_DN / AD_LDAP_BIND_PASSWORD / AD_LDAP_SEARCH_BASE
    # are set. See AIRGAP.md "Internal LDAP / Active Directory User Search".
    return NullDirectoryClient()
